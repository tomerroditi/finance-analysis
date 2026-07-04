import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { createElement } from "react";
import { useScraping, RESEND_COOLDOWN_SECONDS } from "./useScraping";
import { scrapingApi } from "../services/api";
import type { ScraperState } from "./useScraping";

vi.mock("../services/api", () => ({
  scrapingApi: {
    start: vi.fn().mockResolvedValue({ data: 1 }),
    getStatus: vi.fn().mockResolvedValue({ data: { status: "in_progress" } }),
    abort: vi.fn().mockResolvedValue({ data: { status: "aborted" } }),
    submit2fa: vi.fn().mockResolvedValue({ data: { status: "success" } }),
    resend2fa: vi
      .fn()
      .mockResolvedValue({ data: { status: "resent", process_id: 1 } }),
  },
}));

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient();
  return createElement(QueryClientProvider, { client: qc }, children);
}

const acc = { service: "banks", provider: "onezero", account_name: "Acc" };

const waitingScraper: ScraperState = {
  process_id: 1,
  account: acc,
  status: "waiting_for_2fa",
  last_updated: Date.now(),
};

describe("useScraping.startScraper force2fa", () => {
  beforeEach(() => vi.clearAllMocks());

  it("sends force_2fa: true when opts.force2fa is set", async () => {
    const { result } = renderHook(() => useScraping(), { wrapper });
    await act(async () => {
      await result.current.startScraper(acc, 30, { force2fa: true });
    });
    await waitFor(() =>
      expect(scrapingApi.start).toHaveBeenCalledWith(
        expect.objectContaining({
          service: "banks",
          provider: "onezero",
          account: "Acc",
          scraping_period_days: 30,
          force_2fa: true,
        }),
      ),
    );
  });

  it("omits force_2fa when no opts are passed", async () => {
    const { result } = renderHook(() => useScraping(), { wrapper });
    await act(async () => {
      await result.current.startScraper(acc, null);
    });
    await waitFor(() => expect(scrapingApi.start).toHaveBeenCalledTimes(1));
    const payload = (scrapingApi.start as unknown as ReturnType<typeof vi.fn>)
      .mock.calls[0][0];
    expect(payload.force_2fa).toBeUndefined();
  });
});

describe("useScraping.scrapeAll", () => {
  beforeEach(() => vi.clearAllMocks());

  const idleAcc = { service: "banks", provider: "hapoalim", account_name: "Idle" };
  const runningAcc = {
    service: "banks",
    provider: "onezero",
    account_name: "Running",
  };
  const waiting2faAcc = {
    service: "credit_cards",
    provider: "max",
    account_name: "Waiting2fa",
  };

  it("does not call startScraper for an account already in_progress or waiting_for_2fa, but does for idle accounts", async () => {
    // Two distinct process_ids so seeding runningAcc and waiting2faAcc into
    // runningScrapers doesn't have the second startScraper's default `{
    // data: 1 }` response clobber the first one's entry under the same
    // dict key. Use *Once so the mock's steady-state resolution (used by
    // later describe blocks in this file) is untouched.
    (scrapingApi.start as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ data: 201 })
      .mockResolvedValueOnce({ data: 202 });

    const { result } = renderHook(() => useScraping(), { wrapper });

    // Seed runningAcc into runningScrapers as "in_progress" — startScraper's
    // normal, only outcome.
    await act(async () => {
      await result.current.startScraper(runningAcc, null);
    });

    // Drive waiting2faAcc into a genuine "waiting_for_2fa" state through the
    // same public path the "restarted" resend flow uses elsewhere in this
    // file (see useScraping.resendTfa 'swaps in the new process id under
    // "restarted"' below): start it, then resolve resend2fa with a
    // different process_id so resendTfa tracks the new process as
    // waiting_for_2fa. This proves the dedupe against real hook state
    // instead of a hand-constructed fixture.
    await act(async () => {
      await result.current.startScraper(waiting2faAcc, null);
    });
    (scrapingApi.resend2fa as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { status: "restarted", process_id: 999 },
    });
    const seededWaiting = result.current.getScraperForAccount(waiting2faAcc);
    expect(seededWaiting).toBeDefined();
    await act(async () => {
      await result.current.resendTfa(seededWaiting!, null);
    });
    expect(result.current.getScraperForAccount(waiting2faAcc)?.status).toBe(
      "waiting_for_2fa",
    );

    (scrapingApi.start as ReturnType<typeof vi.fn>).mockClear();

    await act(async () => {
      result.current.scrapeAll([idleAcc, runningAcc, waiting2faAcc], null);
    });

    await waitFor(() => expect(scrapingApi.start).toHaveBeenCalledTimes(1));
    expect(scrapingApi.start).toHaveBeenCalledWith(
      expect.objectContaining({
        service: idleAcc.service,
        provider: idleAcc.provider,
        account: idleAcc.account_name,
      }),
    );
  });

  it("starts every account when none are currently active", async () => {
    const { result } = renderHook(() => useScraping(), { wrapper });

    await act(async () => {
      result.current.scrapeAll([idleAcc, runningAcc], null);
    });

    await waitFor(() => expect(scrapingApi.start).toHaveBeenCalledTimes(2));
  });
});

describe("useScraping.resendTfa", () => {
  beforeEach(() => vi.clearAllMocks());

  it("calls resend2fa with the account, not abort + start", async () => {
    (scrapingApi.resend2fa as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { status: "resent", process_id: 1 },
    });
    const { result } = renderHook(() => useScraping(), { wrapper });

    await act(async () => {
      await result.current.resendTfa(waitingScraper, 30);
    });

    expect(scrapingApi.resend2fa).toHaveBeenCalledWith(
      "banks",
      "onezero",
      "Acc",
    );
    expect(scrapingApi.abort).not.toHaveBeenCalled();
    expect(scrapingApi.start).not.toHaveBeenCalled();
  });

  it('keeps the same process tracked under "resent"', async () => {
    (scrapingApi.resend2fa as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { status: "resent", process_id: 1 },
    });
    const { result } = renderHook(() => useScraping(), { wrapper });

    // Seed runningScrapers with the waiting scraper the way startScraper
    // would, so resendTfa has an existing entry to preserve.
    await act(async () => {
      await result.current.startScraper(acc, 30);
    });
    (scrapingApi.start as ReturnType<typeof vi.fn>).mockClear();

    await act(async () => {
      await result.current.resendTfa(waitingScraper, 30);
    });

    const scraper = result.current.getScraperForAccount(acc);
    expect(scraper?.process_id).toBe(1);
  });

  it('swaps in the new process id under "restarted"', async () => {
    (scrapingApi.resend2fa as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { status: "restarted", process_id: 2 },
    });
    const { result } = renderHook(() => useScraping(), { wrapper });

    await act(async () => {
      await result.current.startScraper(acc, 30);
    });

    await act(async () => {
      await result.current.resendTfa(waitingScraper, 30);
    });

    const scraper = result.current.getScraperForAccount(acc);
    expect(scraper?.process_id).toBe(2);
    expect(scraper?.status).toBe("waiting_for_2fa");
  });

  it("starts a 60s cooldown on success", async () => {
    (scrapingApi.resend2fa as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { status: "resent", process_id: 1 },
    });
    const { result } = renderHook(() => useScraping(), { wrapper });

    expect(result.current.resendCooldownRemaining(1)).toBe(0);

    await act(async () => {
      await result.current.resendTfa(waitingScraper, 30);
    });

    expect(RESEND_COOLDOWN_SECONDS).toBe(60);
    expect(result.current.resendCooldownRemaining(1)).toBeGreaterThan(0);
    expect(result.current.resendCooldownRemaining(1)).toBeLessThanOrEqual(
      RESEND_COOLDOWN_SECONDS,
    );
  });

  it("surfaces the server's rate-limit message and still starts the cooldown", async () => {
    (scrapingApi.resend2fa as ReturnType<typeof vi.fn>).mockRejectedValueOnce({
      response: {
        status: 400,
        data: { detail: "Wait about a minute before requesting another code." },
      },
    });
    const { result } = renderHook(() => useScraping(), { wrapper });

    await act(async () => {
      await result.current.resendTfa(waitingScraper, 30);
    });

    expect(result.current.resendErrors[1]).toEqual({
      kind: "rate_limited",
      detail: "Wait about a minute before requesting another code.",
    });
    expect(result.current.resendCooldownRemaining(1)).toBeGreaterThan(0);
  });

  it("classifies a 404 as an expired process", async () => {
    (scrapingApi.resend2fa as ReturnType<typeof vi.fn>).mockRejectedValueOnce({
      response: { status: 404, data: { detail: "Scraping process not found" } },
    });
    const { result } = renderHook(() => useScraping(), { wrapper });

    await act(async () => {
      await result.current.resendTfa(waitingScraper, 30);
    });

    expect(result.current.resendErrors[1]).toEqual({ kind: "expired" });
  });
});
