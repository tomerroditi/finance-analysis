import { useCallback, useSyncExternalStore } from "react";

/**
 * Dashboard layout preferences (card order + which cards are hidden),
 * persisted to localStorage. Mirrors the useBudgetAlertSettings pub-sub
 * pattern so the Settings tab and the Dashboard page stay in sync live.
 *
 * The top KPI header (FinancialHealthHeader) is pinned and NOT part of this
 * set — only the cards below it are orderable/hideable.
 */

const STORAGE_KEY = "fa.dashboard.layout";

/** Canonical card id union. Order here is the default top-to-bottom order. */
export const DASHBOARD_CARDS = [
  { id: "forecast", labelKey: "dashboard.cards.forecast" },
  { id: "insights", labelKey: "dashboard.cards.insights" },
  { id: "budget", labelKey: "dashboard.cards.budget" },
  { id: "recent", labelKey: "dashboard.cards.recent" },
  { id: "recurring", labelKey: "dashboard.cards.recurring" },
  { id: "goals", labelKey: "dashboard.cards.goals" },
  { id: "heatmap", labelKey: "dashboard.cards.heatmap" },
  { id: "charts", labelKey: "dashboard.cards.charts" },
] as const;

export type DashboardCardId = (typeof DASHBOARD_CARDS)[number]["id"];

const ALL_IDS: DashboardCardId[] = DASHBOARD_CARDS.map((c) => c.id);
const KNOWN = new Set<string>(ALL_IDS);

export interface DashboardLayout {
  /** Visible cards, in display order. */
  order: DashboardCardId[];
  /** Hidden cards (not rendered on the dashboard). */
  hidden: DashboardCardId[];
}

const DEFAULT_LAYOUT: DashboardLayout = { order: [...ALL_IDS], hidden: [] };

const listeners = new Set<() => void>();
// Cached, referentially-stable snapshot for useSyncExternalStore. Recomputed
// only on write (or first read), never per-render.
let cache: DashboardLayout | null = null;

function normalize(raw: unknown): DashboardLayout {
  const parsed = (raw ?? {}) as Partial<DashboardLayout>;
  const rawHidden = Array.isArray(parsed.hidden) ? parsed.hidden : [];
  const rawOrder = Array.isArray(parsed.order) ? parsed.order : [];

  const hidden = rawHidden.filter((id): id is DashboardCardId => KNOWN.has(id));
  const hiddenSet = new Set<string>(hidden);

  // Keep stored order (known ids, not hidden), then append any known cards the
  // stored layout never saw (e.g. a card added in a later release) so upgrades
  // surface new cards instead of silently dropping them.
  const order = rawOrder.filter(
    (id): id is DashboardCardId => KNOWN.has(id) && !hiddenSet.has(id),
  );
  const seen = new Set<string>([...order, ...hidden]);
  for (const id of ALL_IDS) {
    if (!seen.has(id)) order.push(id);
  }
  return { order, hidden };
}

function read(): DashboardLayout {
  if (cache) return cache;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    cache = normalize(raw ? JSON.parse(raw) : DEFAULT_LAYOUT);
  } catch {
    cache = { order: [...ALL_IDS], hidden: [] };
  }
  return cache;
}

function write(next: DashboardLayout) {
  cache = normalize(next);
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(cache));
  } catch {
    // ignore (private mode / quota)
  }
  listeners.forEach((l) => l());
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

/**
 * Returns the current dashboard layout plus mutators. `setOrder` replaces the
 * visible order; `toggleHidden` moves a card between the visible and hidden
 * lists (hiding appends to hidden and drops from order; showing appends to the
 * end of the visible order); `reset` restores the default.
 */
export function useDashboardLayout() {
  const layout = useSyncExternalStore(subscribe, read, () => DEFAULT_LAYOUT);

  const setOrder = useCallback((order: DashboardCardId[]) => {
    write({ ...read(), order });
  }, []);

  const toggleHidden = useCallback((id: DashboardCardId) => {
    const cur = read();
    if (cur.hidden.includes(id)) {
      write({
        order: [...cur.order.filter((x) => x !== id), id],
        hidden: cur.hidden.filter((x) => x !== id),
      });
    } else {
      write({
        order: cur.order.filter((x) => x !== id),
        hidden: [...cur.hidden, id],
      });
    }
  }, []);

  const reset = useCallback(() => {
    write({ order: [...ALL_IDS], hidden: [] });
  }, []);

  return { layout, setOrder, toggleHidden, reset };
}
