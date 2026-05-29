import { useCallback, useSyncExternalStore } from "react";

const ENABLED_KEY = "fa.budgetAlerts.enabled";
const THRESHOLD_KEY = "fa.budgetAlerts.threshold";
const DEFAULT_THRESHOLD = 0.8;

// Module-level pub-sub so the Settings popup, sidebar bell, popup, and the
// in-page banner all reflect changes immediately (same pattern as
// useBudgetAlertDismissals).
const listeners = new Set<() => void>();
function emit() {
  listeners.forEach((l) => l());
}
function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

function readEnabled(): boolean {
  try {
    const v = window.localStorage.getItem(ENABLED_KEY);
    return v === null ? true : v === "true";
  } catch {
    return true;
  }
}

function readThreshold(): number {
  try {
    const v = window.localStorage.getItem(THRESHOLD_KEY);
    const n = v === null ? DEFAULT_THRESHOLD : parseFloat(v);
    return Number.isFinite(n) ? Math.min(1, Math.max(0, n)) : DEFAULT_THRESHOLD;
  } catch {
    return DEFAULT_THRESHOLD;
  }
}

/**
 * Budget-alert display preferences, persisted to localStorage:
 * - `enabled`: whether budget alerts are surfaced at all (sidebar bell +
 *   in-page banner). Default true.
 * - `threshold`: fraction of budget (0–1) at which an alert fires. Default 0.8.
 *
 * Returns primitive snapshots (stable for useSyncExternalStore) plus setters
 * that broadcast to every subscriber.
 */
export function useBudgetAlertSettings() {
  const enabled = useSyncExternalStore(subscribe, readEnabled, () => true);
  const threshold = useSyncExternalStore(
    subscribe,
    readThreshold,
    () => DEFAULT_THRESHOLD,
  );

  const setEnabled = useCallback((value: boolean) => {
    try {
      window.localStorage.setItem(ENABLED_KEY, String(value));
    } catch {
      // ignore (private mode / quota)
    }
    emit();
  }, []);

  const setThreshold = useCallback((value: number) => {
    const clamped = Math.min(1, Math.max(0, value));
    try {
      window.localStorage.setItem(THRESHOLD_KEY, String(clamped));
    } catch {
      // ignore
    }
    emit();
  }, []);

  return { enabled, threshold, setEnabled, setThreshold };
}
