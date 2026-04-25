import { useCallback, useEffect, useState } from "react";
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

/**
 * Tracks which budget-alert rule_ids the user has dismissed for a given month.
 * Persisted in localStorage, scoped by demo-vs-real mode and year/month so:
 * - dismissing in demo mode doesn't carry over to real data,
 * - dismissals expire naturally once the calendar moves to a new month.
 */
export function useBudgetAlertDismissals(year?: number, month?: number) {
  const { isDemoMode } = useDemoMode();
  const key = storageKey(isDemoMode, year, month);
  const [dismissed, setDismissed] = useState<Set<number>>(() => readSet(key));

  useEffect(() => {
    setDismissed(readSet(key));
  }, [key]);

  const isDismissed = useCallback(
    (ruleId: number) => dismissed.has(ruleId),
    [dismissed],
  );

  const dismiss = useCallback(
    (ruleId: number) => {
      setDismissed((prev) => {
        if (prev.has(ruleId)) return prev;
        const next = new Set(prev);
        next.add(ruleId);
        writeSet(key, next);
        return next;
      });
    },
    [key],
  );

  const dismissAll = useCallback(
    (ruleIds: number[]) => {
      setDismissed((prev) => {
        const next = new Set(prev);
        for (const id of ruleIds) next.add(id);
        writeSet(key, next);
        return next;
      });
    },
    [key],
  );

  return { isDismissed, dismiss, dismissAll };
}
