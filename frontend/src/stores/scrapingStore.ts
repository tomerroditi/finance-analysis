import { create } from "zustand";

export interface Account {
  service: string;
  provider: string;
  account_name: string;
}

export interface ScraperState {
  process_id: number;
  account: Account;
  status: string; // 'in_progress', 'waiting_for_2fa', 'success', 'failed', 'canceled'
  last_updated: number;
  /**
   * Technical failure detail — the provider's own message, HTTP body or
   * exception text. Shown as secondary "technical details" copy, never as the
   * primary explanation.
   */
  error_message?: string;
  /**
   * Failure category (`INVALID_PASSWORD`, `TIMEOUT`, `GENERAL_ERROR`, …) that
   * selects the translated user-facing message. Undefined for scrapes recorded
   * before the backend tracked it, where `error_message` is all there is.
   */
  error_type?: string;
}

/**
 * Resend-2FA failure surfaced to the UI. `kind` lets the component decide
 * between showing the server's own actionable message verbatim (rate
 * limit) versus a translated, friendlier message (expired process) —
 * backend error strings are English-only and not meant to be shown
 * unfiltered for every failure mode.
 */
export interface ResendError {
  kind: "rate_limited" | "expired" | "unknown";
  detail?: string;
}

/** One entry of `GET /api/scraping/active`. */
export interface ActiveScrape {
  process_id: number;
  service: string;
  provider: string;
  account_name: string;
  status: string;
}

/** A scrape the backend is still working on — as opposed to a finished one
 * whose outcome is being left on screen for the user to read. */
export function isLive(scraper: ScraperState): boolean {
  return scraper.status === "in_progress" || scraper.status === "waiting_for_2fa";
}

interface ScrapingStoreState {
  runningScrapers: Record<number, ScraperState>;
  /**
   * Resend-2FA cooldown deadlines as absolute timestamps, keyed by the
   * process_id the user was looking at when they clicked Resend. If a resend
   * swaps in a new process_id (the "restarted" case), the cooldown key
   * follows it so the UI — which keys off the *current* scraper's
   * process_id — still finds it.
   */
  resendCooldownEnd: Record<number, number>;
  resendErrors: Record<number, ResendError>;
  /**
   * Which demo mode the state above belongs to, or `null` before anything
   * has been recorded. `process_id` is a per-database autoincrement, so demo
   * 5 and real 5 are different scrapes: state from the other mode is not
   * stale, it is *wrong*, and polling it would read another database's run.
   */
  demo: boolean | null;

  trackStarted: (processId: number, account: Account) => void;
  updateStatus: (
    processId: number,
    patch: Pick<ScraperState, "status"> &
      Partial<Pick<ScraperState, "error_message" | "error_type">>,
  ) => void;
  replaceProcess: (oldProcessId: number, newProcessId: number, account: Account) => void;
  touch: (processId: number) => void;
  hydrate: (entries: ActiveScrape[]) => void;
  setResendCooldown: (processId: number, endsAt: number) => void;
  seedInitialCooldown: (processId: number, endsAt: number) => void;
  setResendError: (processId: number, error: ResendError) => void;
  clearResendError: (processId: number) => void;
  setDemo: (demo: boolean) => void;
  reset: () => void;
}

const EMPTY = {
  runningScrapers: {} as Record<number, ScraperState>,
  resendCooldownEnd: {} as Record<number, number>,
  resendErrors: {} as Record<number, ResendError>,
  demo: null as boolean | null,
};

/**
 * App-wide scraping state.
 *
 * This used to be `useState` inside `useScraping`, which meant it died with
 * whichever component called the hook. Navigating away from Data Sources
 * dropped every running scraper — including the `process_id` a waiting 2FA
 * prompt needs to submit its code, leaving the user with an unanswerable
 * prompt while the backend sat parked on it. `GET /api/scraping/active` made
 * the *running/waiting* part recoverable on remount, but only that part:
 * a half-typed OTP, a resend cooldown and a resend error exist nowhere but
 * the client, and there is no endpoint that can bring them back.
 *
 * Three components called the hook independently (`DataSources`,
 * `MonthlyBudgetView`, `OverviewBudgetView`), so they each kept their own
 * copy of this state and each ran their own 2-second poller. The budget
 * views' freshness banners therefore only ever saw scrapes that happened to
 * be running when they mounted. One store, one poller, one answer.
 *
 * Deliberately not persisted: a `process_id` is meaningless once the backend
 * restarts, and `ScrapingTracker` re-hydrates what is genuinely still live
 * from the backend registry on every cold load.
 */
export const useScrapingStore = create<ScrapingStoreState>((set) => ({
  ...EMPTY,

  trackStarted: (processId, account) =>
    set((state) => ({
      runningScrapers: {
        ...state.runningScrapers,
        [processId]: {
          process_id: processId,
          account,
          status: "in_progress",
          last_updated: Date.now(),
        },
      },
    })),

  updateStatus: (processId, patch) =>
    set((state) => {
      const existing = state.runningScrapers[processId];
      if (!existing) return state;
      return {
        runningScrapers: {
          ...state.runningScrapers,
          [processId]: { ...existing, ...patch, last_updated: Date.now() },
        },
      };
    }),

  // Browser providers can't re-issue an OTP mid-flow, so the backend aborts
  // and relaunches: the old process is genuinely gone and its id must not
  // linger, or `getScraperForAccount` (highest process_id wins) would still
  // be right but the abandoned entry would keep the account looking busy.
  replaceProcess: (oldProcessId, newProcessId, account) =>
    set((state) => {
      const next = { ...state.runningScrapers };
      delete next[oldProcessId];
      next[newProcessId] = {
        process_id: newProcessId,
        account,
        status: "waiting_for_2fa",
        last_updated: Date.now(),
      };
      return { runningScrapers: next };
    }),

  touch: (processId) =>
    set((state) => {
      const existing = state.runningScrapers[processId];
      if (!existing) return state;
      return {
        runningScrapers: {
          ...state.runningScrapers,
          [processId]: { ...existing, last_updated: Date.now() },
        },
      };
    }),

  // Merged rather than assigned, existing entries winning. The response is a
  // snapshot that may predate a scrape started microseconds ago, and a
  // locally-known terminal state (a just-failed scrape the user is still
  // reading) has to survive — the endpoint only reports what is *live*, so
  // it cannot distinguish "finished" from "never existed".
  hydrate: (entries) =>
    set((state) => {
      const next = { ...state.runningScrapers };
      let changed = false;
      for (const entry of entries) {
        if (next[entry.process_id]) continue;
        next[entry.process_id] = {
          process_id: entry.process_id,
          account: {
            service: entry.service,
            provider: entry.provider,
            account_name: entry.account_name,
          },
          status: entry.status,
          last_updated: Date.now(),
        };
        changed = true;
      }
      return changed ? { runningScrapers: next } : state;
    }),

  setResendCooldown: (processId, endsAt) =>
    set((state) => ({
      resendCooldownEnd: { ...state.resendCooldownEnd, [processId]: endsAt },
    })),

  // `!== undefined` rather than a falsy check: an already-elapsed deadline
  // must not be re-seeded, and a real resend's longer cooldown must not be
  // clobbered back down to the initial window.
  seedInitialCooldown: (processId, endsAt) =>
    set((state) =>
      state.resendCooldownEnd[processId] !== undefined
        ? state
        : {
            resendCooldownEnd: {
              ...state.resendCooldownEnd,
              [processId]: endsAt,
            },
          },
    ),

  setResendError: (processId, error) =>
    set((state) => ({
      resendErrors: { ...state.resendErrors, [processId]: error },
    })),

  clearResendError: (processId) =>
    set((state) => {
      if (state.resendErrors[processId] === undefined) return state;
      const next = { ...state.resendErrors };
      delete next[processId];
      return { resendErrors: next };
    }),

  // Switching Demo Mode swaps the database under us without a page reload,
  // so everything keyed by process_id belongs to the mode it was recorded
  // in. Only a genuine *change* clears: the first call merely records which
  // mode we are in, and must not wipe a scrape the user started before the
  // tracker's first effect ran.
  setDemo: (demo) =>
    set((state) => {
      if (state.demo === demo) return state;
      return state.demo === null ? { demo } : { ...EMPTY, demo };
    }),

  reset: () => set({ ...EMPTY }),
}));

/**
 * True while any scrape is running or waiting on a 2FA code.
 *
 * A selector rather than a derived value inside `useScraping` so a component
 * that only needs this fact — the budget views' data-freshness banners —
 * re-renders when it flips and not on every status poll of every scraper.
 */
export function useIsAnyScraping(): boolean {
  return useScrapingStore((state) =>
    Object.values(state.runningScrapers).some(isLive),
  );
}
