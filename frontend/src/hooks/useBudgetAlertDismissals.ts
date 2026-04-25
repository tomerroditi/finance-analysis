import { useCallback, useSyncExternalStore } from "react";
import { useDemoMode } from "../context/DemoModeContext";

const STORAGE_KEY_BASE = "fa.budgetAlertsDismissed";

function storageKey(isDemoMode: boolean, year?: number, month?: number): string {
  const mode = isDemoMode ? "demo" : "real";
  return `${STORAGE_KEY_BASE}.${mode}.${year ?? "x"}-${month ?? "x"}`;
}

function readSet(key: string): Set<number> {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.filter((v): v is number => typeof v === "number"));
  } catch {
    return new Set();
  }
}

function writeSet(key: string, value: Set<number>): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(Array.from(value)));
  } catch {
    // localStorage unavailable (private mode, quota) — fail silently
  }
}

// Module-level cache + pub-sub. The bell badge and the popup both subscribe
// here, so dismissing in one updates the other immediately. Without this they
// each held their own useState copy of the dismissed set and the bell's badge
// stayed stale until a remount.
const cache = new Map<string, Set<number>>();
const subscribers = new Set<() => void>();

function getCachedSet(key: string): Set<number> {
  let value = cache.get(key);
  if (!value) {
    value = readSet(key);
    cache.set(key, value);
  }
  return value;
}

function setCachedSet(key: string, value: Set<number>): void {
  cache.set(key, value);
  writeSet(key, value);
  subscribers.forEach((fn) => fn());
}

function subscribe(onChange: () => void): () => void {
  subscribers.add(onChange);
  return () => {
    subscribers.delete(onChange);
  };
}

/**
 * Tracks which budget-alert rule_ids the user has dismissed for a given month.
 * Persisted in localStorage, scoped by demo-vs-real mode and year/month so:
 * - dismissing in demo mode doesn't carry over to real data,
 * - dismissals expire naturally once the calendar moves to a new month.
 *
 * Backed by a module-level cache + pub-sub so all callers (bell badge,
 * popup) reflect the same dismissed set in real time.
 */
export function useBudgetAlertDismissals(year?: number, month?: number) {
  const { isDemoMode } = useDemoMode();
  const key = storageKey(isDemoMode, year, month);

  const getSnapshot = useCallback(() => getCachedSet(key), [key]);
  const dismissed = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  const isDismissed = useCallback(
    (ruleId: number) => dismissed.has(ruleId),
    [dismissed],
  );

  const dismiss = useCallback(
    (ruleId: number) => {
      const current = getCachedSet(key);
      if (current.has(ruleId)) return;
      const next = new Set(current);
      next.add(ruleId);
      setCachedSet(key, next);
    },
    [key],
  );

  const dismissAll = useCallback(
    (ruleIds: number[]) => {
      const current = getCachedSet(key);
      let changed = false;
      const next = new Set(current);
      for (const id of ruleIds) {
        if (!next.has(id)) {
          next.add(id);
          changed = true;
        }
      }
      if (changed) setCachedSet(key, next);
    },
    [key],
  );

  return { isDismissed, dismiss, dismissAll };
}
