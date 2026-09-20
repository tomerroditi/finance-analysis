/**
 * The Budget page's tab identity, shared by the page and by every link that
 * wants to land on a particular tab.
 *
 * The dashboard budget card mirrors the page's four tabs, so "open the budget"
 * from the card's Yearly tab has to arrive on the page's Yearly tab — and on
 * the same year the card was showing. The tab and its period cursor therefore
 * travel in the query string rather than being re-derived from today's date.
 */
export const BUDGET_TABS = ["overview", "monthly", "yearly", "projects"] as const;

export type BudgetTabId = (typeof BUDGET_TABS)[number];

interface BudgetLinkParams {
  year?: number;
  month?: number;
  project?: string | null;
}

/** Build a `/budget` link that opens `tab` on the given period or project. */
export function budgetLink(tab: BudgetTabId, params: BudgetLinkParams = {}): string {
  const search = new URLSearchParams({ tab });
  if (params.year !== undefined) search.set("year", String(params.year));
  if (params.month !== undefined) search.set("month", String(params.month));
  if (params.project) search.set("project", params.project);
  return `/budget?${search.toString()}`;
}

export interface BudgetEntry {
  tab: BudgetTabId;
  /** Only set when the incoming value is a plausible year. */
  year?: number;
  month?: number;
  project?: string;
}

function readInt(raw: string | null, min: number, max: number): number | undefined {
  if (raw === null) return undefined;
  const value = Number(raw);
  if (!Number.isInteger(value) || value < min || value > max) return undefined;
  return value;
}

/**
 * Read the entry intent out of `/budget`'s query string.
 *
 * Anything unrecognised falls back to the page's own defaults — a hand-typed
 * `?tab=groceries` or `?month=13` opens the Overview on today's month rather
 * than rendering nothing.
 */
export function parseBudgetEntry(params: URLSearchParams): BudgetEntry {
  const rawTab = params.get("tab");
  const tab = BUDGET_TABS.find((candidate) => candidate === rawTab) ?? "overview";
  const project = params.get("project")?.trim();
  return {
    tab,
    year: readInt(params.get("year"), 1970, 2999),
    month: readInt(params.get("month"), 1, 12),
    ...(project ? { project } : {}),
  };
}
