import { create } from "zustand";

export interface Account {
  service: string;
  provider: string;
  account_name: string;
}

export interface ScraperState {
  process_id: number;
  account: Account;
  status: string; // 'in_progress', 'waiting_for_2fa', 'success', 'failed'
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

/** Stable identity of an account across renders and store keys. */
export function accountKey(acc: Account): string {
  return `${acc.service}_${acc.provider}_${acc.account_name}`;
}

/** True while a scraper still needs the user or the provider. */
export function isScraperActive(scraper: ScraperState): boolean {
  return scraper.status === "in_progress" || scraper.status === "waiting_for_2fa";
}

interface ScrapingStoreState {
  /** Every scraper this client knows about, keyed by process id. */
  runningScrapers: Record<number, ScraperState>;
  /** Absolute epoch-ms deadlines for the resend-2FA cooldown, by process id. */
  resendCooldownEnd: Record<number, number>;
  resendErrors: Record<number, ResendError>;
  /** Half-typed 2FA codes, keyed by `accountKey`. */
  tfaCodes: Record<string, string>;
  /** Accounts with a `/scraping/start` request in flight, keyed by `accountKey`. */
  pendingStarts: Record<string, boolean>;

  upsertScraper: (scraper: ScraperState) => void;
  /** Merge a patch into a tracked scraper. No-op when it is not tracked. */
  patchScraper: (processId: number, patch: Partial<ScraperState>) => void;
  /** Swap a tracked scraper for one under a new process id (resend restart). */
  replaceScraper: (oldProcessId: number, next: ScraperState) => void;
  setResendCooldown: (processId: number, endsAt: number) => void;
  /** Start a cooldown only if the process has none yet. */
  seedResendCooldown: (processId: number, endsAt: number) => void;
  setResendError: (processId: number, error: ResendError | undefined) => void;
  setTfaCode: (key: string, code: string) => void;
  setPendingStart: (key: string, pending: boolean) => void;
  reset: () => void;
}

/**
 * Scraping state, held globally rather than inside the Data Sources page.
 *
 * Scrapes outlive the page: a browser-based provider takes tens of seconds,
 * and a 2FA-waiting scraper sits parked until the user types the code from
 * their phone. While this lived in `useScraping`'s component state, every
 * in-app navigation unmounted Data Sources and wiped it — the user came back
 * to idle cards, with no way to answer a 2FA prompt that was still very much
 * waiting on the backend, and no indication a scrape was running at all.
 *
 * Holding it here means navigation is free, and the (single) poller in
 * `useScrapingPoller` keeps every mounted consumer in sync. Deliberately NOT
 * persisted to disk: process ids are meaningless once the backend process is
 * gone. Across a real page reload the client re-adopts live scrapes from
 * `GET /api/scraping/active`, which is authoritative.
 */
export const useScrapingStore = create<ScrapingStoreState>((set) => ({
  runningScrapers: {},
  resendCooldownEnd: {},
  resendErrors: {},
  tfaCodes: {},
  pendingStarts: {},

  upsertScraper: (scraper) =>
    set((state) => ({
      runningScrapers: {
        ...state.runningScrapers,
        [scraper.process_id]: scraper,
      },
    })),

  patchScraper: (processId, patch) =>
    set((state) => {
      const existing = state.runningScrapers[processId];
      if (!existing) return state;
      return {
        runningScrapers: {
          ...state.runningScrapers,
          [processId]: { ...existing, ...patch },
        },
      };
    }),

  replaceScraper: (oldProcessId, next) =>
    set((state) => {
      const runningScrapers = { ...state.runningScrapers };
      delete runningScrapers[oldProcessId];
      runningScrapers[next.process_id] = next;
      return { runningScrapers };
    }),

  setResendCooldown: (processId, endsAt) =>
    set((state) => ({
      resendCooldownEnd: { ...state.resendCooldownEnd, [processId]: endsAt },
    })),

  seedResendCooldown: (processId, endsAt) =>
    set((state) =>
      // `!== undefined` rather than a falsy check: an already-elapsed deadline
      // must not be re-seeded, and a real resend's longer cooldown must not be
      // clobbered back down to the shorter initial one.
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
    set((state) => {
      const resendErrors = { ...state.resendErrors };
      if (error) resendErrors[processId] = error;
      else delete resendErrors[processId];
      return { resendErrors };
    }),

  setTfaCode: (key, code) =>
    set((state) => ({ tfaCodes: { ...state.tfaCodes, [key]: code } })),

  setPendingStart: (key, pending) =>
    set((state) => {
      const pendingStarts = { ...state.pendingStarts };
      if (pending) pendingStarts[key] = true;
      else delete pendingStarts[key];
      return { pendingStarts };
    }),

  reset: () =>
    set({
      runningScrapers: {},
      resendCooldownEnd: {},
      resendErrors: {},
      tfaCodes: {},
      pendingStarts: {},
    }),
}));
