import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { createElement } from "react";
import { useScraping } from "./useScraping";
import { useScrapingPoller, POLL_INTERVAL_MS } from "./useScrapingPoller";
import { useScrapingStore } from "../stores/scrapingStore";
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

/** Seed a running scrape the way `startScraper` would. */
function seedRunning(processId: number, account = acc) {
  act(() => {
    useScrapingStore.getState().trackStarted(processId, account);
  });
}

describe("useScrapingPoller — polling survives the page that started the scrape", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });
  afterEach(() => vi.useRealTimers());

  it("keeps advancing a scrape while no page-level consumer is mounted", async () => {
    // The poller used to live in `useScraping`, so it died with the Data
    // Sources page: a scrape that finished while the user was on another page
    // never fired its completion invalidations, and the freshly scraped
    // transactions stayed invisible for the full 5-minute staleTime.
    // `ScrapingTracker` mounts this above the router precisely so the page
    // going away changes nothing.
    const tracker = renderHook(() => useScrapingPoller(false), { wrapper });
    const page = renderHook(() => useScraping(), { wrapper });
    seedRunning(11);

    // The user navigates away — only the tracker is left mounted.
    page.unmount();
    (scrapingApi.getStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { status: "success" },
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });

    expect(scrapingApi.getStatus).toHaveBeenCalledWith(11);
    expect(useScrapingStore.getState().runningScrapers[11].status).toBe(
      "success",
    );
    tracker.unmount();
  });

  it("stops polling once the tracker itself unmounts", async () => {
    const tracker = renderHook(() => useScrapingPoller(false), { wrapper });
    seedRunning(12);
    tracker.unmount();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3);
    });

    expect(scrapingApi.getStatus).not.toHaveBeenCalled();
  });

  it("polls every live scraper on a single tick", async () => {
    // Two accounts can scrape at once, so a tick has to cover both. A
    // per-account poller would multiply the request rate instead.
    const tracker = renderHook(() => useScrapingPoller(false), { wrapper });
    seedRunning(21, acc);
    seedRunning(22, other);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });

    expect(scrapingApi.getStatus).toHaveBeenCalledWith(21);
    expect(scrapingApi.getStatus).toHaveBeenCalledWith(22);
    tracker.unmount();
  });

  it("does not stack ticks while a slow round trip is in flight", async () => {
    // Without the in-flight guard, a status call slower than the interval
    // would let ticks pile up — re-firing the same completion invalidations
    // and multiplying load on a backend that is evidently already struggling.
    let release: (value: unknown) => void = () => {};
    (scrapingApi.getStatus as ReturnType<typeof vi.fn>).mockReturnValueOnce(
      new Promise((resolve) => {
        release = resolve;
      }),
    );
    const tracker = renderHook(() => useScrapingPoller(false), { wrapper });
    seedRunning(31);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 4);
    });

    expect(scrapingApi.getStatus).toHaveBeenCalledTimes(1);

    await act(async () => {
      release({ data: { status: "in_progress" } });
    });
    tracker.unmount();
  });

  it("makes no status requests when nothing is live", async () => {
    const tracker = renderHook(() => useScrapingPoller(false), { wrapper });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 5);
    });

    expect(scrapingApi.getStatus).not.toHaveBeenCalled();
    tracker.unmount();
  });

  it("leaves a finished scrape alone instead of re-polling it forever", async () => {
    // A terminal status stays on screen for the user to read, but it is not
    // live — polling it would be a request per 2s per finished card, for as
    // long as the tab stays open.
    const tracker = renderHook(() => useScrapingPoller(false), { wrapper });
    seedRunning(41);
    act(() => {
      useScrapingStore.getState().updateStatus(41, { status: "failed" });
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3);
    });

    expect(scrapingApi.getStatus).not.toHaveBeenCalled();
    tracker.unmount();
  });
});

describe("useScrapingPoller — Demo Mode", () => {
  beforeEach(() => vi.clearAllMocks());

  it("drops scrapers from the other mode when Demo Mode is switched", async () => {
    // `process_id` is a per-database autoincrement, so real #5 and demo #5
    // are different scrapes. Carrying the map across a toggle would poll —
    // and offer an Abort button for — a run in the database we just left.
    const { rerender, unmount } = renderHook(
      ({ demo }: { demo: boolean }) => useScrapingPoller(demo),
      { wrapper, initialProps: { demo: false } },
    );
    seedRunning(51);
    expect(useScrapingStore.getState().runningScrapers[51]).toBeDefined();

    rerender({ demo: true });

    await waitFor(() =>
      expect(useScrapingStore.getState().runningScrapers).toEqual({}),
    );
    unmount();
  });

  it("keeps a scrape started before the tracker's first effect ran", async () => {
    // The very first `setDemo` only records the mode. Treating it as a change
    // would wipe a scrape the user launched between the store's creation and
    // the tracker mounting.
    seedRunning(52);

    const { unmount } = renderHook(() => useScrapingPoller(false), { wrapper });

    await waitFor(() => expect(useScrapingStore.getState().demo).toBe(false));
    expect(useScrapingStore.getState().runningScrapers[52]).toBeDefined();
    unmount();
  });
});
