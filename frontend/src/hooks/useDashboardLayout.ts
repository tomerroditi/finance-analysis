import { useCallback, useSyncExternalStore } from "react";

/**
 * Dashboard layout preferences (card order + which cards are hidden),
 * persisted to localStorage. Mirrors the useBudgetAlertSettings pub-sub
 * pattern so the Settings tab and the Dashboard page stay in sync live.
 *
 * The top KPI header (FinancialHealthHeader) is pinned and NOT part of this
 * set — only the cards below it are orderable/hideable.
 *
 * Cards flagged `beta` are experimental and ship **hidden by default**; the
 * user opts into them from the Settings → Dashboard tab.
 */

const STORAGE_KEY = "fa.dashboard.layout";
// Bump when the default visibility policy changes so a one-time migration can
// run against older stored layouts (see `normalize`).
const LAYOUT_VERSION = 2;

/** A card's width on the dashboard grid. */
export type DashboardCardSize = "half" | "full";

/** Canonical card id union. Order here is the default top-to-bottom order. */
export const DASHBOARD_CARDS = [
  { id: "forecast", labelKey: "dashboard.cards.forecast", size: "full", beta: true },
  { id: "insights", labelKey: "dashboard.cards.insights", size: "full", beta: true },
  { id: "budget", labelKey: "dashboard.cards.budget", size: "half" },
  { id: "recent", labelKey: "dashboard.cards.recent", size: "half" },
  { id: "recurring", labelKey: "dashboard.cards.recurring", size: "half", beta: true },
  { id: "goals", labelKey: "dashboard.cards.goals", size: "half", beta: true },
  { id: "heatmap", labelKey: "dashboard.cards.heatmap", size: "half" },
  { id: "charts", labelKey: "dashboard.cards.charts", size: "full" },
] as const;

export type DashboardCardId = (typeof DASHBOARD_CARDS)[number]["id"];

const SIZE_BY_ID = new Map<DashboardCardId, DashboardCardSize>(
  DASHBOARD_CARDS.map((c) => [c.id, c.size]),
);

/** The fixed grid width of a card. Half cards pair two-per-row on wide screens. */
export function cardSize(id: DashboardCardId): DashboardCardSize {
  return SIZE_BY_ID.get(id) ?? "full";
}

const ALL_IDS: DashboardCardId[] = DASHBOARD_CARDS.map((c) => c.id);
const KNOWN = new Set<string>(ALL_IDS);
const BETA_IDS = new Set<DashboardCardId>(
  DASHBOARD_CARDS.filter((c) => "beta" in c && c.beta).map((c) => c.id),
);

/** Whether a card is flagged experimental/beta. */
export function isBetaCard(id: DashboardCardId): boolean {
  return BETA_IDS.has(id);
}

export interface DashboardLayout {
  /** Visible cards, in display order. */
  order: DashboardCardId[];
  /** Hidden cards (not rendered on the dashboard). */
  hidden: DashboardCardId[];
}

// Defaults: non-beta cards visible (in declared order), beta cards hidden.
const DEFAULT_ORDER: DashboardCardId[] = ALL_IDS.filter((id) => !BETA_IDS.has(id));
const DEFAULT_HIDDEN: DashboardCardId[] = ALL_IDS.filter((id) => BETA_IDS.has(id));
const DEFAULT_LAYOUT: DashboardLayout = {
  order: [...DEFAULT_ORDER],
  hidden: [...DEFAULT_HIDDEN],
};

interface StoredLayout extends Partial<DashboardLayout> {
  v?: number;
}

const listeners = new Set<() => void>();
// Cached, referentially-stable snapshot for useSyncExternalStore. Recomputed
// only on write (or first read), never per-render.
let cache: DashboardLayout | null = null;

function normalize(raw: StoredLayout): DashboardLayout {
  const version = typeof raw.v === "number" ? raw.v : 0;
  let rawHidden = Array.isArray(raw.hidden) ? [...raw.hidden] : [];
  let rawOrder = Array.isArray(raw.order) ? [...raw.order] : [];

  // One-time migration: layouts written before LAYOUT_VERSION 2 shipped beta
  // cards visible. Move any beta card that's currently visible into hidden so
  // the new "beta hidden by default" policy applies to existing users too.
  if (version < 2) {
    const movedToHidden = rawOrder.filter((id) => BETA_IDS.has(id as DashboardCardId));
    rawHidden = [...rawHidden, ...movedToHidden];
    rawOrder = rawOrder.filter((id) => !BETA_IDS.has(id as DashboardCardId));
  }

  const hidden = Array.from(
    new Set(rawHidden.filter((id): id is DashboardCardId => KNOWN.has(id))),
  );
  const hiddenSet = new Set<string>(hidden);

  // Keep stored order (known ids, not hidden), then append any known cards the
  // stored layout never saw so future-added cards still surface: beta ones go
  // to hidden, the rest to the end of the visible order.
  const order = rawOrder.filter(
    (id): id is DashboardCardId => KNOWN.has(id) && !hiddenSet.has(id),
  );
  const seen = new Set<string>([...order, ...hidden]);
  for (const id of ALL_IDS) {
    if (seen.has(id)) continue;
    if (BETA_IDS.has(id)) hidden.push(id);
    else order.push(id);
  }
  return { order, hidden };
}

function read(): DashboardLayout {
  if (cache) return cache;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    cache = raw ? normalize(JSON.parse(raw)) : { ...DEFAULT_LAYOUT };
  } catch {
    cache = { ...DEFAULT_LAYOUT };
  }
  return cache;
}

function write(next: DashboardLayout) {
  cache = normalize({ ...next, v: LAYOUT_VERSION });
  try {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ ...cache, v: LAYOUT_VERSION }),
    );
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
 * end of the visible order); `reset` restores the default (beta cards hidden).
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
    write({ order: [...DEFAULT_ORDER], hidden: [...DEFAULT_HIDDEN] });
  }, []);

  return { layout, setOrder, toggleHidden, reset };
}
