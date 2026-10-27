import type { QueryClient, QueryKey } from "@tanstack/react-query";
import type { Transaction } from "./types/transaction";
import type { BudgetMonthOverride, PendingRefund, RefundLink } from "./services/api";
import { qkPrefix } from "./services/queryKeys";
import {
  UNCHANGED_BY_RETAG,
  patchBudgetForMonthMove,
  patchBudgetNets,
  splitRows,
  type AnalysisRow,
  type MonthlyAnalysis,
  type SplitPart,
} from "./components/budget/budgetOptimistic";
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

/**
 * Show a split on every cached transaction list, now: the parent gives way to
 * its parts, or — in a list that keeps split parents — is marked as one with
 * its parts after it.
 *
 * @param client - The app's query client.
 * @param parent - The row being split.
 * @param parts - The parts being sent.
 * @returns A function that puts every list back, for a failed write.
 */
export function splitInTransactionLists(
  client: QueryClient,
  parent: { source?: string; unique_id?: string | number },
  parts: readonly SplitPart[],
): () => void {
  const restore = snapshotLists(client);
  for (const [key, old] of client.getQueriesData<Transaction[]>({
    queryKey: qkPrefix.transactionsList,
  })) {
    if (!Array.isArray(old)) continue;
    const index = old.findIndex(sameRow(parent));
    if (index === -1) continue;
    const row = old[index];
    const keepsParents = key[3] === true;
    const replacement = keepsParents
      ? [{ ...row, type: "split_parent" }, ...splitRows(row, parts)]
      : splitRows(row, parts);
    client.setQueryData<Transaction[]>(key, [
      ...old.slice(0, index),
      ...replacement,
      ...old.slice(index + 1),
    ]);
  }
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
 * The row's badge moves, and so does the row itself: out of the month it was
 * counted in and into the rule that claims it in the other one, with its
 * cost, in every cached analysis of either month.
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
  const budget = patchBudgetForMonthMove(client, { tx, fromYear, fromMonth, year, month });
  return {
    restore: () => {
      client.setQueryData(overridesKey, before);
      budget.restore();
    },
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

/** What an open refund still expects: its expectation less what came back. */
const stillExpected = (refund: PendingRefund | undefined) =>
  refund && (refund.status === "pending" || refund.status === "partial")
    ? Math.max(0, refund.expected_amount - (refund.total_refunded ?? 0))
    : 0;

/** A refund's totals and status after its links change, as the backend recomputes them. */
function withLinks(refund: PendingRefund, links: RefundLink[]): PendingRefund {
  const refunded = links.reduce((sum, link) => sum + link.amount, 0);
  const status: PendingRefund["status"] =
    refund.status === "closed"
      ? "closed"
      : refunded <= 0
        ? "pending"
        : refunded >= refund.expected_amount
          ? "resolved"
          : "partial";
  return {
    ...refund,
    links,
    status,
    total_refunded: refunded,
    remaining: Math.max(0, refund.expected_amount - refunded),
  };
}

let nextStandInId = 0;
/** A negative id no stored record can carry, until the refetch brings the real one. */
const standInId = () => --nextStandInId;

/**
 * Put a refund write on every cached copy of the refund list, now: the full
 * list behind every row's badge, and each monthly analysis' "awaiting
 * refunds" section (the open `pending` ones and what they still expect).
 */
function patchRefundCaches(
  client: QueryClient,
  listKey: QueryKey,
  before: PendingRefund | undefined,
  after: PendingRefund | null,
): () => void {
  const list = client.getQueryData<PendingRefund[]>(listKey);
  const months = client.getQueriesData<MonthlyAnalysis>({ queryKey: qkPrefix.budgetAnalysis });
  if (list) {
    const listed = before !== undefined && list.some((refund) => refund.id === before.id);
    client.setQueryData<PendingRefund[]>(
      listKey,
      listed
        ? list.flatMap((refund) => (refund.id !== before.id ? [refund] : after ? [after] : []))
        : after
          ? [...list, after]
          : list,
    );
  }
  const shift = stillExpected(after ?? undefined) - stillExpected(before);
  for (const [key, data] of months) {
    const section = data?.pending_refunds;
    if (!section) continue;
    const shown = after?.status === "pending" ? after : undefined;
    const current = section.items ?? [];
    const items = current.some((refund) => refund.id === before?.id)
      ? current.flatMap((refund) => (refund.id !== before?.id ? [refund] : shown ? [shown] : []))
      : shown
        ? [...current, shown]
        : current;
    client.setQueryData<MonthlyAnalysis>(key, {
      ...data,
      pending_refunds: { ...section, items, total_expected: (section.total_expected ?? 0) + shift },
    });
  }
  return () => {
    client.setQueryData(listKey, list);
    for (const [key, data] of months) client.setQueryData(key, data);
  };
}

/** A refund by id from the cached list, or as the caller already holds it. */
const findRefund = (client: QueryClient, listKey: QueryKey, target: number | PendingRefund) => {
  const id = typeof target === "number" ? target : target.id;
  return (
    client.getQueryData<PendingRefund[]>(listKey)?.find((refund) => refund.id === id) ??
    (typeof target === "number" ? undefined : target)
  );
};

/** The `rowKey` the budget lists a refund's purchase under, for a whole-row refund. */
const purchaseKey = (refund: PendingRefund) =>
  refund.source_type === "transaction" ? `${refund.source_table}_${refund.source_id}` : undefined;

/**
 * Show a new pending refund at once: the row's badge, the budget's
 * awaiting-refunds section, and the purchase's cost, which drops by what is
 * now expected back.
 *
 * @param client - The app's query client.
 * @param listKey - The cached refund list's key (`qk.pendingRefunds.all()`).
 * @param tx - The purchase being marked.
 * @param expected - The amount expected back (positive).
 * @returns A function that puts every cache back, for a failed write.
 */
export function markPendingRefund(
  client: QueryClient,
  listKey: QueryKey,
  tx: Transaction,
  expected: number,
): () => void {
  const refund: PendingRefund = {
    id: standInId(),
    source_type: "transaction",
    source_id: tx.unique_id ?? "",
    source_table: tx.source ?? "",
    expected_amount: expected,
    status: "pending",
    links: [],
    total_refunded: 0,
    remaining: expected,
    date: tx.date,
    description: tx.description ?? tx.desc,
    account_name: tx.account_name,
    provider: tx.provider,
    category: tx.category,
    tag: tx.tag,
  };
  const budget = patchBudgetNets(
    client,
    new Map([[purchaseKey(refund)!, (row: AnalysisRow) => Math.min(0, row.amount + expected)]]),
  );
  const restore = patchRefundCaches(client, listKey, undefined, refund);
  return () => {
    restore();
    budget.restore();
  };
}

/**
 * Show a cancelled pending refund at once: the badge goes, and the purchase
 * counts in full again.
 *
 * @param client - The app's query client.
 * @param listKey - The cached refund list's key (`qk.pendingRefunds.all()`).
 * @param target - The refund being cancelled, or its id when the list holds it.
 * @returns A function that puts every cache back, for a failed write.
 */
export function cancelPendingRefund(
  client: QueryClient,
  listKey: QueryKey,
  target: number | PendingRefund,
): () => void {
  const refund = findRefund(client, listKey, target);
  if (!refund) return () => {};
  const key = purchaseKey(refund);
  const budget = key ? patchBudgetNets(client, new Map([[key, () => null]])) : undefined;
  const restore = patchRefundCaches(client, listKey, refund, null);
  return () => {
    restore();
    budget?.restore();
  };
}

/**
 * Show a closed pending refund at once: what never came back is an expense
 * for good, so the purchase counts net of the refunds actually linked only.
 *
 * @param client - The app's query client.
 * @param listKey - The cached refund list's key (`qk.pendingRefunds.all()`).
 * @param target - The refund being closed, or its id when the list holds it.
 * @returns A function that puts every cache back, for a failed write.
 */
export function closePendingRefund(
  client: QueryClient,
  listKey: QueryKey,
  target: number | PendingRefund,
): () => void {
  const refund = findRefund(client, listKey, target);
  if (!refund) return () => {};
  const refunded = refund.total_refunded ?? 0;
  const key = purchaseKey(refund);
  const budget = key
    ? patchBudgetNets(client, new Map([[key, (row: AnalysisRow) => Math.min(0, row.amount + refunded)]]))
    : undefined;
  const restore = patchRefundCaches(client, listKey, refund, { ...refund, status: "closed" });
  return () => {
    restore();
    budget?.restore();
  };
}

/**
 * Show a refund link made or removed at once: the refund's totals and status
 * move with its links. The purchase's cost does not — an open refund already
 * counts what it expects back, linked or not — and the refund transaction's
 * own netting is left to the refetch.
 *
 * @param client - The app's query client.
 * @param listKey - The cached refund list's key (`qk.pendingRefunds.all()`).
 * @param change - The link to remove (by id), or the one to add to a refund.
 * @returns A function that puts every cache back, for a failed write.
 */
export function patchRefundLink(
  client: QueryClient,
  listKey: QueryKey,
  change:
    | { unlink: number }
    | {
        pendingId: number;
        link: Pick<RefundLink, "refund_transaction_id" | "refund_source" | "amount"> &
          Partial<RefundLink>;
      },
): () => void {
  const list = client.getQueryData<PendingRefund[]>(listKey);
  const refund =
    "unlink" in change
      ? list?.find((r) => r.links?.some((link) => link.id === change.unlink))
      : list?.find((r) => r.id === change.pendingId);
  if (!refund) return () => {};
  const links =
    "unlink" in change
      ? (refund.links ?? []).filter((link) => link.id !== change.unlink)
      : [
          ...(refund.links ?? []),
          { id: standInId(), pending_refund_id: refund.id, ...change.link } as RefundLink,
        ];
  return patchRefundCaches(client, listKey, refund, withLinks(refund, links));
}
