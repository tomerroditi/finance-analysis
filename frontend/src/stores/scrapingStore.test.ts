import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { createElement } from "react";
import { useScraping } from "../hooks/useScraping";
import { useScrapingStore, useIsAnyScraping } from "./scrapingStore";
import { scrapingApi } from "../services/api";

vi.mock("../services/api", () => ({
  scrapingApi: {
    start: vi.fn().mockResolvedValue({ data: 1 }),
    getStatus: vi.fn().mockResolvedValue({ data: { status: "in_progress" } }),
    getActive: vi.fn().mockResolvedValue({ data: [] }),
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
const other = { service: "banks", provider: "hapoalim", account_name: "Other" };

describe("scrapingStore — state survives the component that created it", () => {
  beforeEach(() => vi.clearAllMocks());

  it("still knows the scraper after its page unmounts and remounts", async () => {
    // The whole point of the store. `useState` inside the hook meant an
    // in-app navigation wiped the scraper — including the `process_id` a
    // waiting 2FA prompt needs to submit its code, so the user was left
    // looking at a prompt they could not answer while the backend sat parked.
    (scrapingApi.start as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: 5,
    });
    const first = renderHook(() => useScraping(), { wrapper });
    await act(async () => {
      await first.result.current.startScraper(acc, 30);
    });
    first.unmount();

    const second = renderHook(() => useScraping(), { wrapper });

    expect(second.result.current.getScraperForAccount(acc)).toMatchObject({
      process_id: 5,
      status: "in_progress",
    });
    expect(second.result.current.isAnyScraping).toBe(true);
  });

  it("carries the resend cooldown across a remount", async () => {
    // Unlike a running scrape, a cooldown exists nowhere but the client —
    // `/active` cannot restore it, so losing it on navigation meant Resend
    // unlocked early and the user could fire a second OTP within seconds.
    (scrapingApi.resend2fa as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { status: "resent", process_id: 9 },
    });
    const first = renderHook(() => useScraping(), { wrapper });
    act(() => {
      useScrapingStore.getState().trackStarted(9, acc);
      useScrapingStore.getState().updateStatus(9, { status: "waiting_for_2fa" });
    });
    await act(async () => {
      await first.result.current.resendTfa(
        first.result.current.getScraperForAccount(acc)!,
      );
    });
    first.unmount();

    const second = renderHook(() => useScraping(), { wrapper });

    expect(second.result.current.resendCooldownRemaining(9)).toBeGreaterThan(0);
  });

  it("carries a resend error across a remount", async () => {
    (scrapingApi.resend2fa as ReturnType<typeof vi.fn>).mockRejectedValueOnce({
      response: { status: 400, data: { detail: "Too soon" } },
    });
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => {});
    const first = renderHook(() => useScraping(), { wrapper });
    act(() => {
      useScrapingStore.getState().trackStarted(10, acc);
      useScrapingStore
        .getState()
        .updateStatus(10, { status: "waiting_for_2fa" });
    });
    await act(async () => {
      await first.result.current.resendTfa(
        first.result.current.getScraperForAccount(acc)!,
      );
    });
    first.unmount();

    const second = renderHook(() => useScraping(), { wrapper });

    expect(second.result.current.resendErrors[10]).toEqual({
      kind: "rate_limited",
      detail: "Too soon",
    });
    consoleError.mockRestore();
  });
});

describe("scrapingStore — one store, many consumers", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows a scrape started elsewhere to useIsAnyScraping", async () => {
    // `MonthlyBudgetView` and `OverviewBudgetView` each called `useScraping()`,
    // which gave them their own isolated `useState`. Their freshness banners
    // therefore never saw a scrape the Data Sources page had started — and
    // each instance also ran its own 2-second poller.
    (scrapingApi.start as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: 6,
    });
    const page = renderHook(() => useScraping(), { wrapper });
    const banner = renderHook(() => useIsAnyScraping(), { wrapper });

    expect(banner.result.current).toBe(false);

    await act(async () => {
      await page.result.current.startScraper(acc, 30);
    });

    expect(banner.result.current).toBe(true);
  });

  it("reports idle again once the scrape reaches a terminal state", async () => {
    const banner = renderHook(() => useIsAnyScraping(), { wrapper });
    act(() => {
      useScrapingStore.getState().trackStarted(7, acc);
    });
    expect(banner.result.current).toBe(true);

    act(() => {
      useScrapingStore.getState().updateStatus(7, { status: "success" });
    });

    expect(banner.result.current).toBe(false);
  });

  it("counts a 2FA-waiting scrape as live", () => {
    // It is not finished — the backend is parked on it — so a freshness
    // banner must not claim the data is settled.
    const banner = renderHook(() => useIsAnyScraping(), { wrapper });
    act(() => {
      useScrapingStore.getState().trackStarted(8, acc);
      useScrapingStore.getState().updateStatus(8, { status: "waiting_for_2fa" });
    });

    expect(banner.result.current).toBe(true);
  });
});

describe("scrapingStore — parallel accounts", () => {
  beforeEach(() => vi.clearAllMocks());

  it("tracks two accounts scraping at once, independently", async () => {
    (scrapingApi.start as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ data: 101 })
      .mockResolvedValueOnce({ data: 102 });
    const { result } = renderHook(() => useScraping(), { wrapper });

    await act(async () => {
      await result.current.startScraper(acc, 30);
      await result.current.startScraper(other, 30);
    });

    expect(result.current.getScraperForAccount(acc)?.process_id).toBe(101);
    expect(result.current.getScraperForAccount(other)?.process_id).toBe(102);
  });

  it("leaves the other account untouched when one reaches 2FA", async () => {
    // The 2FA "verifying" state used to be a single shared flag, so a prompt
    // on one account greyed out the other card's buttons. Two accounts can
    // genuinely sit on a prompt at the same time.
    const { result } = renderHook(() => useScraping(), { wrapper });
    act(() => {
      useScrapingStore.getState().trackStarted(103, acc);
      useScrapingStore.getState().trackStarted(104, other);
      useScrapingStore
        .getState()
        .updateStatus(103, { status: "waiting_for_2fa" });
    });

    expect(result.current.getScraperForAccount(acc)?.status).toBe(
      "waiting_for_2fa",
    );
    expect(result.current.getScraperForAccount(other)?.status).toBe(
      "in_progress",
    );
  });

  it("skips only the accounts already running when Scrape All fires", async () => {
    (scrapingApi.start as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: 105,
    });
    const { result } = renderHook(() => useScraping(), { wrapper });
    act(() => {
      useScrapingStore.getState().trackStarted(106, acc);
    });

    await act(async () => {
      result.current.scrapeAll([acc, other], 30);
    });

    expect(scrapingApi.start).toHaveBeenCalledTimes(1);
    expect(scrapingApi.start).toHaveBeenCalledWith(
      expect.objectContaining({ account: "Other" }),
    );
  });

  it("re-reads the store so Scrape All sees a just-started account", async () => {
    // `scrapeAll` used to close over a render-time snapshot, so firing it
    // immediately after a card's own Play button could launch that same
    // account a second time.
    (scrapingApi.start as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: 107,
    });
    const { result } = renderHook(() => useScraping(), { wrapper });

    await act(async () => {
      await result.current.startScraper(acc, 30);
      result.current.scrapeAll([acc], 30);
    });

    expect(scrapingApi.start).toHaveBeenCalledTimes(1);
  });
});

describe("scrapingStore — hydration merge", () => {
  it("does not overwrite a locally-known terminal state", () => {
    // `/active` only reports what is live, so it cannot distinguish "already
    // finished" from "never existed". A just-failed scrape the user is still
    // reading has to survive the merge.
    act(() => {
      useScrapingStore.getState().trackStarted(201, acc);
      useScrapingStore.getState().updateStatus(201, {
        status: "failed",
        error_type: "INVALID_PASSWORD",
      });
      useScrapingStore.getState().hydrate([
        {
          process_id: 201,
          service: acc.service,
          provider: acc.provider,
          account_name: acc.account_name,
          status: "in_progress",
        },
      ]);
    });

    expect(useScrapingStore.getState().runningScrapers[201]).toMatchObject({
      status: "failed",
      error_type: "INVALID_PASSWORD",
    });
  });

  it("adds scrapers it has never seen", () => {
    act(() => {
      useScrapingStore.getState().hydrate([
        {
          process_id: 202,
          service: acc.service,
          provider: acc.provider,
          account_name: acc.account_name,
          status: "waiting_for_2fa",
        },
      ]);
    });

    expect(useScrapingStore.getState().runningScrapers[202]).toMatchObject({
      status: "waiting_for_2fa",
      account: acc,
    });
  });

  it("leaves state untouched when it has nothing new to add", () => {
    // Identity matters: returning a fresh object every poll would re-render
    // every subscriber twice a second for the life of the tab.
    act(() => {
      useScrapingStore.getState().trackStarted(203, acc);
    });
    const before = useScrapingStore.getState().runningScrapers;

    act(() => {
      useScrapingStore.getState().hydrate([
        {
          process_id: 203,
          service: acc.service,
          provider: acc.provider,
          account_name: acc.account_name,
          status: "in_progress",
        },
      ]);
    });

    expect(useScrapingStore.getState().runningScrapers).toBe(before);
  });
});
