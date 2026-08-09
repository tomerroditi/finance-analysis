import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { createElement } from "react";
import {
  useScraping,
  useScrapingPoller,
  RESEND_COOLDOWN_SECONDS,
  INITIAL_2FA_COOLDOWN_SECONDS,
} from "./useScraping";
import { scrapingApi } from "../services/api";
import { useScrapingStore } from "../stores/scrapingStore";
import type { ScraperState } from "./useScraping";

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

type Wrapper = ({ children }: { children: ReactNode }) => ReactNode;

/**
 * Render the state hook together with the app-wide poller.
 *
 * In the app those are two separate mounts — `useScrapingPoller` is mounted
 * once by `Layout` (via `ScrapingTracker`) while any number of components call
 * `useScraping` — because the state lives in a global store rather than in the
 * hook. Tests that assert on polling need both.
 */
function renderScraping(w: Wrapper = wrapper) {
  return renderHook(
    () => {
      useScrapingPoller();
      return useScraping();
    },
    { wrapper: w },
  );
}

// The store is global and outlives a single render, which is the whole point
// (scraping state survives navigation) — so each test must start from clean
// state instead of inheriting the previous test's scrapers.
beforeEach(() => {
  useScrapingStore.getState().reset();
});

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
    const { result } = renderScraping();
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
    const { result } = renderScraping();
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

    const { result } = renderScraping();

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
      await result.current.resendTfa(seededWaiting!);
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
    const { result } = renderScraping();

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
    const { result } = renderScraping();

    await act(async () => {
      await result.current.resendTfa(waitingScraper);
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
    const { result } = renderScraping();

    // Seed runningScrapers with the waiting scraper the way startScraper
    // would, so resendTfa has an existing entry to preserve.
    await act(async () => {
      await result.current.startScraper(acc, 30);
    });
    (scrapingApi.start as ReturnType<typeof vi.fn>).mockClear();

    await act(async () => {
      await result.current.resendTfa(waitingScraper);
    });

    const scraper = result.current.getScraperForAccount(acc);
    expect(scraper?.process_id).toBe(1);
  });

  it('swaps in the new process id under "restarted"', async () => {
    (scrapingApi.resend2fa as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { status: "restarted", process_id: 2 },
    });
    const { result } = renderScraping();

    await act(async () => {
      await result.current.startScraper(acc, 30);
    });

    await act(async () => {
      await result.current.resendTfa(waitingScraper);
    });

    const scraper = result.current.getScraperForAccount(acc);
    expect(scraper?.process_id).toBe(2);
    expect(scraper?.status).toBe("waiting_for_2fa");
  });

  it("starts a 60s cooldown on success", async () => {
    (scrapingApi.resend2fa as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { status: "resent", process_id: 1 },
    });
    const { result } = renderScraping();

    expect(result.current.resendCooldownRemaining(1)).toBe(0);

    await act(async () => {
      await result.current.resendTfa(waitingScraper);
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
    const { result } = renderScraping();

    await act(async () => {
      await result.current.resendTfa(waitingScraper);
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
    const { result } = renderScraping();

    await act(async () => {
      await result.current.resendTfa(waitingScraper);
    });

    expect(result.current.resendErrors[1]).toEqual({ kind: "expired" });
  });
});

describe("useScraping.resendTfa restarted — stale process cleanup (regression)", () => {
  // Regression coverage for a leak that `getScraperForAccount` masks: it
  // sorts by highest process_id and returns only the top entry, so a stale
  // old-id record sitting unseen in `runningScrapers` doesn't show up
  // through that lookup even if it's still there. But the *polling effect*
  // iterates every entry whose status is in_progress/waiting_for_2fa —
  // Object.values(runningScrapers).filter(...) — with no dedup by account.
  // If `resendTfa`'s "restarted" branch ever stopped deleting the old
  // process_id before adding the new one, the leaked old entry would (a)
  // permanently disable scrape buttons via `isAnyScraping`'s `.some()` over
  // ALL entries, and (b) keep polling a dead process every 2s forever. This
  // test drives the real polling effect (not getScraperForAccount) so it
  // can't be fooled by that masking.
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("stops polling the old process_id and only polls the new one after a restart", async () => {
    const oldProcessId = 1;
    const newProcessId = 2;

    (scrapingApi.start as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: oldProcessId,
    });
    // First poll tick (still under oldProcessId) reports waiting_for_2fa,
    // so the seeded scraper reaches the state resend is actually offered
    // from in the app. Every later call also resolves to waiting_for_2fa
    // so the loop keeps polling instead of retiring the entry.
    (scrapingApi.getStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { status: "waiting_for_2fa" },
    });
    (scrapingApi.resend2fa as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { status: "restarted", process_id: newProcessId },
    });

    const { result } = renderScraping();

    // Seed a real waiting_for_2fa entry under oldProcessId the way the app
    // actually gets there (start -> poll), instead of hand-constructing
    // runningScrapers.
    await act(async () => {
      await result.current.startScraper(acc, 30);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    const scraperBeforeResend = result.current.getScraperForAccount(acc)!;
    expect(scraperBeforeResend.process_id).toBe(oldProcessId);
    expect(scraperBeforeResend.status).toBe("waiting_for_2fa");

    (scrapingApi.getStatus as ReturnType<typeof vi.fn>).mockClear();

    await act(async () => {
      await result.current.resendTfa(scraperBeforeResend);
    });

    // Sanity: the swap actually happened.
    expect(result.current.getScraperForAccount(acc)?.process_id).toBe(
      newProcessId,
    );

    // Advance past several poll ticks. The old process_id must NEVER be
    // polled again — only the new one. This is the assertion that fails
    // if the "restarted" branch stops deleting `next[oldProcessId]` before
    // adding the new entry: the stale old entry would keep being polled
    // forever alongside the new one.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000 * 5);
    });

    const calledIds = (
      scrapingApi.getStatus as ReturnType<typeof vi.fn>
    ).mock.calls.map(([id]) => id);

    expect(calledIds).toContain(newProcessId);
    expect(calledIds).not.toContain(oldProcessId);
  });
});

describe("useScraping — cache invalidation on scrape completion", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("invalidates everything a new batch of transactions changes", async () => {
    // Completion is detected by POLLING, so the global MutationCache sweep
    // in queryClient.ts never runs for it. Before this list existed only
    // last-scrapes + bank-balances were invalidated, so freshly scraped
    // transactions stayed invisible on Transactions / Dashboard / Budget for
    // the full 5-minute staleTime.
    const qc = new QueryClient();
    const invalidate = vi.spyOn(qc, "invalidateQueries");
    const localWrapper = ({ children }: { children: ReactNode }) =>
      createElement(QueryClientProvider, { client: qc }, children);

    (scrapingApi.start as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: 77,
    });
    (scrapingApi.getStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { status: "success" },
    });

    const { result } = renderScraping(localWrapper);
    await act(async () => {
      await result.current.startScraper(acc, 30);
    });
    invalidate.mockClear();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    const invalidatedHeads = invalidate.mock.calls.map(
      ([arg]) => (arg?.queryKey as readonly unknown[])[0],
    );
    expect(invalidatedHeads).toEqual(
      expect.arrayContaining([
        "transactions",
        "analytics",
        "budget",
        "pending-refunds",
        "insurance-accounts",
        "bank-balances",
        "last-scrapes",
      ]),
    );
    // Narrow keys only — never a blanket invalidateQueries() sweep.
    expect(
      invalidate.mock.calls.every(([arg]) => arg?.queryKey !== undefined),
    ).toBe(true);
  });

  it("does not invalidate while a scrape is still in progress", async () => {
    const qc = new QueryClient();
    const invalidate = vi.spyOn(qc, "invalidateQueries");
    const localWrapper = ({ children }: { children: ReactNode }) =>
      createElement(QueryClientProvider, { client: qc }, children);

    (scrapingApi.start as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: 78,
    });
    (scrapingApi.getStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { status: "in_progress" },
    });

    const { result } = renderScraping(localWrapper);
    await act(async () => {
      await result.current.startScraper(acc, 30);
    });
    invalidate.mockClear();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000 * 3);
    });

    expect(invalidate).not.toHaveBeenCalled();
  });
});

describe("useScraping — resend cooldown timer lifecycle", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("stops ticking once the cooldown expires", async () => {
    // The 1 s tick interval's only dep is `resendCooldownEnd`, which does NOT
    // change when a deadline merely passes — so nothing used to clear it and
    // the hook re-rendered once a second for the rest of the page's life
    // after a single Resend.
    (scrapingApi.resend2fa as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { status: "resent", process_id: 1 },
    });

    let renders = 0;
    const { result } = renderHook(
      () => {
        renders += 1;
        useScrapingPoller();
        return useScraping();
      },
      { wrapper },
    );

    await act(async () => {
      await result.current.resendTfa(waitingScraper);
    });
    expect(result.current.resendCooldownRemaining(1)).toBeGreaterThan(0);

    // Mid-cooldown the countdown must still tick (that's what the interval
    // is for).
    const beforeTicks = renders;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(renders).toBeGreaterThan(beforeTicks);

    // Run out the cooldown, then let a lot more time pass: no further
    // renders may happen.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(RESEND_COOLDOWN_SECONDS * 1000);
    });
    expect(result.current.resendCooldownRemaining(1)).toBe(0);

    const afterExpiry = renders;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(renders).toBe(afterExpiry);
  });
});

describe("useScraping — initial 2FA cooldown", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  /** Start a scrape and let one poll return `waiting_for_2fa`. */
  async function scrapeIntoWaitingFor2fa(processId: number) {
    (scrapingApi.start as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: processId,
    });
    (scrapingApi.getStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { status: "waiting_for_2fa" },
    });

    const { result } = renderScraping();
    await act(async () => {
      await result.current.startScraper(acc, 30);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    return result;
  }

  it("blocks Resend as soon as the code input appears", async () => {
    // Reaching waiting_for_2fa means an OTP was just sent. Resend used to be
    // live immediately, so "Scrape" then "Resend" fired a second OTP seconds
    // after the first — before the SMS had arrived.
    const result = await scrapeIntoWaitingFor2fa(42);

    expect(result.current.getScraperForAccount(acc)?.status).toBe(
      "waiting_for_2fa",
    );
    const remaining = result.current.resendCooldownRemaining(42);
    expect(remaining).toBeGreaterThan(0);
    expect(remaining).toBeLessThanOrEqual(INITIAL_2FA_COOLDOWN_SECONDS);
  });

  it("releases Resend once the initial window elapses", async () => {
    const result = await scrapeIntoWaitingFor2fa(43);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(INITIAL_2FA_COOLDOWN_SECONDS * 1000);
    });

    expect(result.current.resendCooldownRemaining(43)).toBe(0);
  });

  it("does not re-seed the window on every poll while waiting", async () => {
    // The polling branch fires on each tick, not just on the status
    // transition. Re-seeding there would pin the countdown at 30s forever and
    // Resend would never unlock.
    const result = await scrapeIntoWaitingFor2fa(44);
    const first = result.current.resendCooldownRemaining(44);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    expect(result.current.resendCooldownRemaining(44)).toBeLessThan(first);
  });

  it("does not shorten the longer cooldown a real resend just set", async () => {
    (scrapingApi.start as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: 45,
    });
    (scrapingApi.getStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { status: "waiting_for_2fa" },
    });
    (scrapingApi.resend2fa as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { status: "resent", process_id: 45 },
    });

    const { result } = renderScraping();
    await act(async () => {
      await result.current.startScraper(acc, 30);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    // Wait out the initial window, then resend for the full 60s.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(INITIAL_2FA_COOLDOWN_SECONDS * 1000);
    });
    const scraper = result.current.getScraperForAccount(acc)!;
    await act(async () => {
      await result.current.resendTfa(scraper);
    });

    // Further polls must leave the 60s deadline alone, not clamp it to 30s.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(result.current.resendCooldownRemaining(45)).toBeGreaterThan(
      INITIAL_2FA_COOLDOWN_SECONDS,
    );
  });
});

describe("useScraping — state survives leaving the page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("keeps a waiting_for_2fa scraper (and the half-typed code) across unmount/remount", async () => {
    // Navigating away from Data Sources unmounts it. While this state lived in
    // the hook's own useState, that wiped it: the user came back to an idle
    // card with no way to answer a 2FA prompt the backend was still parked on.
    (scrapingApi.start as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: 300,
    });
    (scrapingApi.getStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { status: "waiting_for_2fa" },
    });

    const first = renderScraping();
    await act(async () => {
      await first.result.current.startScraper(acc, 30);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    act(() => {
      first.result.current.setTfaCode("banks_onezero_Acc", "123");
    });
    expect(first.result.current.getScraperForAccount(acc)?.status).toBe(
      "waiting_for_2fa",
    );

    // Leave the page…
    first.unmount();
    // …and come back.
    const second = renderScraping();

    const scraper = second.result.current.getScraperForAccount(acc);
    expect(scraper?.process_id).toBe(300);
    expect(scraper?.status).toBe("waiting_for_2fa");
    expect(second.result.current.tfaCodes["banks_onezero_Acc"]).toBe("123");
    expect(second.result.current.isAnyScraping).toBe(true);
  });

  it("keeps polling a scrape started before the page was left", async () => {
    (scrapingApi.start as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: 301,
    });
    (scrapingApi.getStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { status: "in_progress" },
    });

    const first = renderScraping();
    await act(async () => {
      await first.result.current.startScraper(acc, 30);
    });
    first.unmount();

    // The poller lives in Layout, above the router — remounting the page must
    // not be what keeps a running scrape alive, but a remount must also not
    // lose track of it.
    const second = renderScraping();
    (scrapingApi.getStatus as ReturnType<typeof vi.fn>).mockClear();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    expect(scrapingApi.getStatus).toHaveBeenCalledWith(301);
    expect(second.result.current.isAnyScraping).toBe(true);
  });

  it("adopts scrapes already running on the backend on a cold load", async () => {
    // A real page reload loses every process id, so a 2FA prompt would be
    // unanswerable and a running scrape invisible. GET /scraping/active is the
    // authoritative recovery path.
    (scrapingApi.getActive as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: [
        {
          process_id: 400,
          service: "banks",
          provider: "onezero",
          account_name: "Acc",
          status: "waiting_for_2fa",
        },
      ],
    });

    const { result } = renderScraping();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    const scraper = result.current.getScraperForAccount(acc);
    expect(scraper?.process_id).toBe(400);
    expect(scraper?.status).toBe("waiting_for_2fa");
  });

  it("does not let the adopted status clobber fresher local state", async () => {
    // The optimistic in_progress flip on 2FA submit must win over a DB row
    // that still reads waiting_for_2fa when /active answers late.
    (scrapingApi.start as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: 401,
    });
    let resolveActive: (value: unknown) => void = () => {};
    (scrapingApi.getActive as ReturnType<typeof vi.fn>).mockReturnValueOnce(
      new Promise((resolve) => {
        resolveActive = resolve;
      }),
    );

    const { result } = renderScraping();
    await act(async () => {
      await result.current.startScraper(acc, 30);
    });

    await act(async () => {
      resolveActive({
        data: [
          {
            process_id: 401,
            service: "banks",
            provider: "onezero",
            account_name: "Acc",
            status: "waiting_for_2fa",
          },
        ],
      });
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.getScraperForAccount(acc)?.status).toBe("in_progress");
  });
});

describe("useScraping — parallel per-account scraping", () => {
  const accA = { service: "banks", provider: "hapoalim", account_name: "A" };
  const accB = { service: "credit_cards", provider: "max", account_name: "B" };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("tracks and polls a second account started while the first is running", async () => {
    (scrapingApi.start as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ data: 501 })
      .mockResolvedValueOnce({ data: 502 });
    (scrapingApi.getStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { status: "in_progress" },
    });

    const { result } = renderScraping();
    await act(async () => {
      await result.current.startScraper(accA, null);
    });
    // Clicking a second source while the first runs must start it, not be
    // swallowed — the whole point of dropping the global isAnyScraping gate.
    await act(async () => {
      await result.current.startScraper(accB, null);
    });

    expect(result.current.activeScraperCount).toBe(2);
    expect(result.current.getScraperForAccount(accA)?.process_id).toBe(501);
    expect(result.current.getScraperForAccount(accB)?.process_id).toBe(502);

    (scrapingApi.getStatus as ReturnType<typeof vi.fn>).mockClear();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    const polled = (
      scrapingApi.getStatus as ReturnType<typeof vi.fn>
    ).mock.calls.map(([id]) => id);
    expect(polled).toContain(501);
    expect(polled).toContain(502);
  });

  it("ignores a second start for the SAME account while the first request is in flight", async () => {
    // Per-account guard, not a global one: two clicks on one card must not
    // fire two scrapes (two OTP SMS), but a click on another card must.
    let resolveStart: (value: unknown) => void = () => {};
    (scrapingApi.start as ReturnType<typeof vi.fn>).mockReturnValueOnce(
      new Promise((resolve) => {
        resolveStart = resolve;
      }),
    );

    const { result } = renderScraping();
    let firstStart: Promise<void> = Promise.resolve();
    act(() => {
      firstStart = result.current.startScraper(accA, null);
    });
    expect(result.current.isStartPending(accA)).toBe(true);
    expect(result.current.isStartPending(accB)).toBe(false);

    await act(async () => {
      await result.current.startScraper(accA, null);
    });
    expect(scrapingApi.start).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveStart({ data: 503 });
      await firstStart;
    });
    expect(result.current.isStartPending(accA)).toBe(false);
    expect(result.current.getScraperForAccount(accA)?.process_id).toBe(503);
  });
});

describe("useScraping — 2FA pending state is per account", () => {
  const accA = { service: "banks", provider: "onezero", account_name: "A" };
  const accB = { service: "banks", provider: "onezero", account_name: "B" };

  beforeEach(() => vi.clearAllMocks());

  it("only marks the account whose code is in flight as pending", async () => {
    // Two accounts can sit on a 2FA prompt at the same time now. A shared
    // `tfaMutation.isPending` greyed out the other card's Verify/Resend
    // buttons while an unrelated account's code was being verified.
    let resolveSubmit: (value: unknown) => void = () => {};
    (scrapingApi.submit2fa as ReturnType<typeof vi.fn>).mockReturnValueOnce(
      new Promise((resolve) => {
        resolveSubmit = resolve;
      }),
    );

    const { result } = renderScraping();
    const scraperA: ScraperState = {
      process_id: 601,
      account: accA,
      status: "waiting_for_2fa",
      last_updated: Date.now(),
    };

    act(() => {
      result.current.submitTfa(scraperA, "123456");
    });

    await waitFor(() => expect(result.current.isTfaPending(accA)).toBe(true));
    expect(result.current.isTfaPending(accB)).toBe(false);

    await act(async () => {
      resolveSubmit({ data: { status: "success" } });
    });
    await waitFor(() => expect(result.current.isTfaPending(accA)).toBe(false));
  });
});
