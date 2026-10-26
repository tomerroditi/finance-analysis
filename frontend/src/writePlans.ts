import type { QueryClient, QueryKey } from "@tanstack/react-query";
import type { Transaction } from "./types/transaction";
import type { BudgetMonthOverride } from "./services/api";
import { qkPrefix } from "./services/queryKeys";
import { UNCHANGED_BY_RETAG } from "./components/budget/budgetOptimistic";
import type { RefreshPlan } from "./queryInvalidation";

/**
 * Reads a transaction-row write (create, edit, delete) cannot change: the
 * rules, categories and accounts themselves. {@link UNCHANGED_BY_RETAG} less
 * the two a row's existence does reach — the month overrides that point at
 * it, and whether the database holds any transactions at all.
 */
export const UNCHANGED_BY_ROW_WRITE: readonly QueryKey[] = UNCHANGED_BY_RETAG.filter(
  (key) => key[1] !== "month-overrides" && key[0] !== "onboardingStatus",
);

/**
 * The refresh after a write to a pending refund or a refund link (mark,
 * cancel, close, link, unlink): the refund list and the budget months it
 * nets into first; never the static reads, the holdings, or the retirement
 * plan, none of which read refund state.
 */
export const REFUND_WRITE_PLAN: RefreshPlan = {
  first: [qkPrefix.pendingRefunds, qkPrefix.budgetAnalysis],
  skip: [
    ...UNCHANGED_BY_RETAG,
    qkPrefix.investments,
    qkPrefix.liabilities,
    qkPrefix.cashBalances,
    qkPrefix.fire,
  ],
};

/**
 * The refresh after a link between a refund and its purchase is made or
 * repaired: as {@link REFUND_WRITE_PLAN}, except that a link may retag the
 * refund, which the retirement plan's spending figures do read.
 */
export const REFUND_LINK_PLAN: RefreshPlan = {
  first: REFUND_WRITE_PLAN.first,
  skip: [...UNCHANGED_BY_RETAG, qkPrefix.investments, qkPrefix.liabilities, qkPrefix.cashBalances],
};

/** What a write puts on a row; `undefined` keeps a field, `""` clears it. */
export interface RowEdit {
  source: string;
  unique_id: string | number;
  category?: string | null;
  tag?: string | null;
}

const sameRow = (edit: { source?: string; unique_id?: string | number }) => (row: Transaction) =>
  row.split_id == null &&
  (row.source ?? "") === (edit.source ?? "") &&
  String(row.unique_id ?? row.id ?? "") === String(edit.unique_id ?? "");

/** Restore every cached list to what it held before a patch. */
function snapshotLists(client: QueryClient): () => void {
  const before = client.getQueriesData<Transaction[]>({ queryKey: qkPrefix.transactionsList });
  return () => {
    for (const [key, data] of before) client.setQueryData(key, data);
  };
}

/**
 * Show a category/tag write on every cached transaction list, now.
 *
 * Only whole rows are patched — a split part carries its own tag, and a write
 * addressed to its parent's `(source, unique_id)` does not change it — so the
 * patch matches exactly the rows `patchBudgetForRetag` moves.
 *
 * @param client - The app's query client.
 * @param edits - The writes being sent.
 * @returns A function that puts every list back, for a failed write.
 */
export function patchTransactionLists(client: QueryClient, edits: readonly RowEdit[]): () => void {
  const restore = snapshotLists(client);
  if (edits.length === 0) return restore;
  client.setQueriesData<Transaction[]>({ queryKey: qkPrefix.transactionsList }, (old) => {
    if (!Array.isArray(old)) return old;
    let changed = false;
    const next = old.map((row) => {
      const edit = edits.find((candidate) => sameRow(candidate)(row));
      if (!edit) return row;
      changed = true;
      const category = edit.category === undefined ? row.category : edit.category || undefined;
      const tag = edit.tag === undefined ? row.tag : edit.tag || undefined;
      return { ...row, category, tag };
    });
    return changed ? next : old;
  });
  return restore;
}

/**
 * Take deleted rows off every cached transaction list, now.
 *
 * @param client - The app's query client.
 * @param rows - The rows being deleted.
 * @returns A function that puts every list back, for a failed write.
 */
export function removeFromTransactionLists(
  client: QueryClient,
  rows: readonly { source?: string; unique_id?: string | number; id?: number }[],
): () => void {
  const restore = snapshotLists(client);
  const targets = rows.map((row) => ({ source: row.source, unique_id: row.unique_id ?? row.id }));
  client.setQueriesData<Transaction[]>({ queryKey: qkPrefix.transactionsList }, (old) => {
    if (!Array.isArray(old)) return old;
    const next = old.filter((row) => !targets.some((target) => sameRow(target)(row)));
    return next.length === old.length ? old : next;
  });
  return restore;
}

/** A row moved to another budget month: from where it is counted now, to where. */
export interface MonthMove {
  tx: Transaction;
  fromYear: number;
  fromMonth: number;
  year: number;
  month: number;
}

/**
 * Show a budget month override at once and plan the refresh after it.
 *
 * An override only re-months a row for the budget, so the refresh is the
 * budget — the two months it moved between and the override list first —
 * plus the two analytics reads built on budget months.
 *
 * @param client - The app's query client.
 * @param overridesKey - The cached override list's key
 *   (`qk.budget.monthOverrides()`), patched so the row's badge moves now.
 * @param move - The move being sent.
 * @returns `restore` for a failed write, and the refresh plan.
 */
export function planMonthMove(
  client: QueryClient,
  overridesKey: QueryKey,
  { tx, fromYear, fromMonth, year, month }: MonthMove,
): { restore: () => void; refresh: RefreshPlan } {
  const before = client.getQueryData<BudgetMonthOverride[]>(overridesKey);
  if (before) {
    const date = new Date(tx.date);
    const ownMonth = date.getFullYear() === year && date.getMonth() + 1 === month;
    const source = tx.source || "unknown";
    const others = before.filter(
      (o) => !(o.source_table === source && String(o.source_id) === String(tx.unique_id)),
    );
    client.setQueryData<BudgetMonthOverride[]>(
      overridesKey,
      ownMonth
        ? others
        : [
            ...others,
            {
              id: -1,
              source_type: "transaction",
              source_id: tx.unique_id || "",
              source_table: source,
              override_year: year,
              override_month: month,
            },
          ],
    );
  }
  return {
    restore: () => client.setQueryData(overridesKey, before),
    refresh: {
      first: [
        [...qkPrefix.budgetAnalysis, fromYear, fromMonth],
        [...qkPrefix.budgetAnalysis, year, month],
        [...qkPrefix.budget, "month-overrides"],
      ],
      only: [
        qkPrefix.budget,
        [...qkPrefix.analytics, "insights"],
        [...qkPrefix.analytics, "cash-flow-forecast"],
      ],
    },
  };
}

/**
 * The transaction table each filter on the Transactions page shows: the
 * `source` a row of that service carries in the merged list, split parts
 * included (they carry their parent's table).
 */
export const SERVICE_SOURCE: Readonly<Record<string, string>> = {
  credit_cards: "credit_card_transactions",
  banks: "bank_transactions",
  cash: "cash_transactions",
  manual_investments: "manual_investment_transactions",
};

/**
 * Narrow the merged transaction list to one service, the way
 * `GET /transactions/?service=` would answer.
 *
 * @param rows - The merged list (every service but insurance).
 * @param service - A Transactions-page filter, or `"all"`.
 * @returns The rows of that service; the input itself for `"all"`.
 */
export function rowsOfService<T extends { source?: string }>(rows: T[], service: string): T[] {
  const source = SERVICE_SOURCE[service];
  return source === undefined ? rows : rows.filter((row) => row.source === source);
}
