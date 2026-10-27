import type { QueryClient, QueryKey } from "@tanstack/react-query";
import type { Transaction } from "../../types/transaction";
import type { PendingRefund, ProjectStatus } from "../../services/api";
import { qkPrefix } from "../../services/queryKeys";
import type { RefreshPlan } from "../../queryInvalidation";

/**
 * A category/tag write, in the shape `transactionsApi.bulkTag` sends it.
 *
 * `undefined` keeps the row's current value and `""` clears it, exactly as
 * the backend's `_filter_updates_for_source` reads the same fields.
 */
export interface RetagEdit {
  source: string;
  unique_id: string | number;
  category?: string | null;
  tag?: string | null;
}

/** What a monthly analysis row carries on top of a plain transaction. */
export type AnalysisRow = Transaction & {
  split_id?: number | null;
  net_amount?: number | null;
  budget_year?: number;
  budget_month?: number;
};

interface AnalysisRule {
  id: number | string;
  name: string;
  amount: number;
  category: string;
  tags?: string | string[];
}

interface AnalysisItem {
  rule: AnalysisRule;
  current_amount: number;
  data: AnalysisRow[];
  allow_edit: boolean;
  allow_delete: boolean;
}

interface ProjectSpending {
  category: string;
  spent: number;
  transactions?: AnalysisRow[];
}

/** The parts of `GET /budget/analysis/{y}/{m}` a retag moves money between. */
export interface MonthlyAnalysis {
  rules?: AnalysisItem[] | null;
  project_spending?: { projects?: ProjectSpending[]; total_spent?: number };
  uncategorized_count?: number;
  uncategorized_amount?: number;
  pending_refunds?: { items?: PendingRefund[]; total_expected?: number };
  [key: string]: unknown;
}

/** The rules outside this month's analysis that can claim a row before it. */
export interface ClaimContext {
  /** Every project category — a project owns its category whatever the tag. */
  projectCategories: ReadonlySet<string>;
  /** Yearly rules by year — they claim before any monthly rule. */
  yearlyRules: ReadonlyMap<number, { category: string; tags?: string | string[] }[]>;
}

const TOTAL_BUDGET = "Total Budget";
const OTHER_EXPENSES = "Other Expenses";
const ALL_TAGS = "all_tags";

/**
 * Categories the budget never counts (`NON_EXPENSE_CATEGORIES` in
 * `backend/services/transaction_views.py`): retagging a row into one takes it
 * out of every pool.
 */
const NON_EXPENSE = new Set([
  "Investments",
  "Liabilities",
  "Credit Cards",
  "Ignore",
  "Salary",
  "Other Income",
]);

const rowKey = (source: string | undefined, uniqueId: string | number | undefined) =>
  `${source ?? ""}_${uniqueId ?? ""}`;

const parseTags = (tags: string | string[] | undefined): string[] =>
  typeof tags === "string" ? tags.split(";") : (tags ?? []);

const isAllTags = (tags: string | string[] | undefined) => {
  const list = parseTags(tags);
  return list.length === 1 && list[0].trim().toLowerCase() === ALL_TAGS;
};

const matches = (
  rule: { category: string; tags?: string | string[] },
  category: string,
  tag: string | null,
) =>
  rule.category === category &&
  (isAllTags(rule.tags) || (tag !== null && parseTags(rule.tags).includes(tag)));

const isTotal = (item: AnalysisItem) => item.rule.name === TOTAL_BUDGET;
const isOther = (item: AnalysisItem) =>
  typeof item.rule.id === "string" && item.rule.id.endsWith("_Other_Expenses");

/** What a row counts for in its pool: net of refunds, as a positive cost. */
const costOf = (row: AnalysisRow) => -(row.net_amount ?? row.amount ?? 0);

type Owner =
  | { kind: "none" }
  | { kind: "elsewhere" }
  | { kind: "project"; category: string }
  | { kind: "rule"; index: number }
  | { kind: "other" }
  | { kind: "total" };

/**
 * Who claims a row with this category and tag — `backend/services/budget/ledger.py`
 * `assign_claims`, run for one row: a project category first, then a yearly
 * rule of the row's budget year, then the month's most specific monthly rule
 * (fewer tags first, all-tags last), else Other Expenses.
 */
function claim(
  items: AnalysisItem[],
  category: string | null,
  tag: string | null,
  year: number | undefined,
  ctx: ClaimContext,
): Owner {
  if (category && NON_EXPENSE.has(category)) return { kind: "none" };
  if (!category) return { kind: "other" };
  if (ctx.projectCategories.has(category)) return { kind: "project", category };
  const yearly = year === undefined ? undefined : ctx.yearlyRules.get(year);
  if (yearly?.some((rule) => matches(rule, category, tag))) return { kind: "elsewhere" };

  const order = items
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => !isTotal(item) && !isOther(item))
    .sort(
      (a, b) =>
        Number(isAllTags(a.item.rule.tags)) - Number(isAllTags(b.item.rule.tags)) ||
        parseTags(a.item.rule.tags).length - parseTags(b.item.rule.tags).length ||
        a.index - b.index,
    );
  const owner = order.find(({ item }) => matches(item.rule, category, tag));
  return owner ? { kind: "rule", index: owner.index } : { kind: "other" };
}

const inPool = (owner: Owner) =>
  owner.kind === "rule" || owner.kind === "other" || owner.kind === "total";

/** A row's identity in a month: its table and id, and its split part if it is one. */
const identity = (row: AnalysisRow) => `${rowKey(row.source, row.unique_id)}#${row.split_id ?? ""}`;

/**
 * What becomes of a row a write reaches: the rows it turns into in this
 * month (`[]` takes it out), or `undefined` for a row the write leaves alone.
 */
export type RowChange = (row: AnalysisRow) => AnalysisRow[] | undefined;

/**
 * Re-derive a month's analysis as if a write had landed.
 *
 * Every write that moves money between the month's pools comes down to this:
 * some listed rows leave where they were and become other rows (a retag gives
 * a row a new category, a split turns it into its parts, a pending refund
 * changes what it costs, a delete or a move to another month removes it), and
 * rows may arrive from elsewhere (a move into this month). Each arriving row
 * goes to the owner the backend's claim order would give it, with its cost,
 * so the tab answers on click; the refetch that follows either agrees or
 * corrects it.
 *
 * @param analysis - The cached month to re-derive.
 * @param change - What the write does to each listed row.
 * @param ctx - The project categories and yearly rules known to the client.
 * @param arriving - Rows the write brings into this month.
 * @returns A new analysis, or the input itself when the write touches nothing
 *   in it.
 */
export function applyRowChanges(
  analysis: MonthlyAnalysis,
  change: RowChange,
  ctx: ClaimContext,
  arriving: AnalysisRow[] = [],
): MonthlyAnalysis {
  if (!analysis) return analysis;
  const rulesIn = analysis.rules ?? [];
  const projectsIn = analysis.project_spending?.projects ?? [];
  if (rulesIn.length === 0 && projectsIn.length === 0) return analysis;

  const items: AnalysisItem[] = rulesIn.map((item) => ({ ...item, data: [...item.data] }));
  let projects: ProjectSpending[] = projectsIn.map((p) => ({
    ...p,
    transactions: [...(p.transactions ?? [])],
  }));
  let projectsTotal = analysis.project_spending?.total_spent ?? 0;
  const total = items.find(isTotal);
  // With no rule beside it, the Total lists the month's pool itself and the
  // backend shows no Other Expenses entry.
  const totalLists = !!total && !items.some((item) => !isTotal(item) && !isOther(item));

  const leaving: { row: AnalysisRow; from: Owner; into: AnalysisRow[] }[] = [];
  const listed = new Set<string>();
  const visit = (row: AnalysisRow, from: Owner) => {
    const id = identity(row);
    if (listed.has(id)) return;
    listed.add(id);
    const into = change(row);
    if (into) leaving.push({ row, from, into });
  };
  items.forEach((item, index) => {
    if (isTotal(item)) {
      if (totalLists) item.data.forEach((row) => visit(row, { kind: "total" }));
      return;
    }
    item.data.forEach((row) => visit(row, isOther(item) ? { kind: "other" } : { kind: "rule", index }));
  });
  projects.forEach((project) =>
    (project.transactions ?? []).forEach((row) =>
      visit(row, { kind: "project", category: project.category }),
    ),
  );
  const arrivals = arriving.filter((row) => !listed.has(identity(row)));
  if (leaving.length === 0 && arrivals.length === 0) return analysis;

  let uncategorizedCount = analysis.uncategorized_count;
  let uncategorizedAmount = analysis.uncategorized_amount;
  const countUncategorized = (row: AnalysisRow, sign: 1 | -1) => {
    if (row.category || typeof uncategorizedCount !== "number") return;
    uncategorizedCount += sign;
    uncategorizedAmount = (uncategorizedAmount ?? 0) + sign * Math.abs(row.amount ?? 0);
  };
  const otherIndex = () => items.findIndex(isOther);

  const remove = (row: AnalysisRow, from: Owner) => {
    const id = identity(row);
    const cost = costOf(row);
    if (from.kind === "rule" || from.kind === "other") {
      const item = items[from.kind === "rule" ? from.index : otherIndex()];
      item.data = item.data.filter((r) => identity(r) !== id);
      item.current_amount -= cost;
    } else if (from.kind === "total") {
      total!.data = total!.data.filter((r) => identity(r) !== id);
    } else if (from.kind === "project") {
      const project = projects.find((p) => p.category === from.category)!;
      project.transactions = (project.transactions ?? []).filter((r) => identity(r) !== id);
      project.spent -= cost;
      projectsTotal -= cost;
    }
    if (inPool(from)) {
      if (total) total.current_amount -= cost;
      countUncategorized(row, -1);
    }
  };

  const add = (row: AnalysisRow) => {
    const category = row.category || null;
    const tag = row.tag || null;
    let to = claim(items, category, tag, row.budget_year, ctx);
    const cost = costOf(row);
    if (to.kind === "other" && totalLists) to = { kind: "total" };

    if (to.kind === "rule") {
      items[to.index].data.push(row);
      items[to.index].current_amount += cost;
    } else if (to.kind === "total") {
      total!.data.push(row);
    } else if (to.kind === "other") {
      let index = otherIndex();
      if (index === -1 && total) {
        const allocated = items
          .filter((item) => !isTotal(item) && !isOther(item))
          .reduce((sum, item) => sum + (item.rule.amount ?? 0), 0);
        items.push({
          rule: {
            name: OTHER_EXPENSES,
            amount: Math.max((total.rule.amount ?? 0) - allocated, 0),
            category: OTHER_EXPENSES,
            tags: OTHER_EXPENSES,
            id: `${row.budget_year ?? ""}${row.budget_month ?? ""}_Other_Expenses`,
          },
          current_amount: 0,
          data: [],
          allow_edit: false,
          allow_delete: false,
        });
        index = items.length - 1;
      }
      if (index === -1) return;
      items[index].data.push(row);
      items[index].current_amount += cost;
    } else if (to.kind === "project") {
      let project = projects.find((p) => p.category === to.category);
      if (!project) {
        project = { category: to.category, spent: 0, transactions: [] };
        projects.push(project);
      }
      project.transactions = [...(project.transactions ?? []), row];
      project.spent += cost;
      projectsTotal += cost;
    }
    // The Total Budget totals the whole monthly pool, so it moves with every
    // row that enters it, whichever rule takes the row.
    if (inPool(to)) {
      if (total) total.current_amount += cost;
      countUncategorized(row, 1);
    }
  };

  for (const { row, from, into } of leaving) {
    remove(row, from);
    into.forEach(add);
  }
  arrivals.forEach(add);

  // The backend lists Other Expenses only while it holds something.
  const rules = items.filter((item) => !isOther(item) || item.data.length > 0);
  projects = projects.filter((p) => (p.transactions ?? []).length > 0);

  return {
    ...analysis,
    rules,
    project_spending: {
      ...analysis.project_spending,
      projects,
      ...(projects.length > 0 ? { total_spent: projectsTotal } : { total_spent: undefined }),
    },
    ...(typeof uncategorizedCount === "number"
      ? { uncategorized_count: uncategorizedCount, uncategorized_amount: uncategorizedAmount }
      : {}),
  };
}

/**
 * Re-derive a month's analysis as if a batch of category/tag writes had
 * landed.
 *
 * A retag invalidates the whole budget, and the analysis behind the Monthly
 * tab is the slowest read on the page, so waiting for it left the row in its
 * old rule for seconds after the click. This moves each written row — and its
 * cost — to the rule the backend's claim order would give it.
 *
 * Rows a retag cannot place from here are left alone for the server: split
 * parts (their write lands on the parent) and rows no list of this month
 * shows (a yearly envelope's rows live in the Yearly tab's analysis).
 *
 * @param analysis - The cached month to re-derive.
 * @param edits - The writes being sent.
 * @param ctx - The project categories and yearly rules known to the client.
 * @returns A new analysis; the input is left untouched.
 */
export function applyRetag(
  analysis: MonthlyAnalysis,
  edits: RetagEdit[],
  ctx: ClaimContext,
): MonthlyAnalysis {
  if (!analysis?.rules?.length || edits.length === 0) return analysis;
  return applyRowChanges(analysis, retagChange(edits), ctx);
}

function retagChange(edits: RetagEdit[]): RowChange {
  const pending = new Map(edits.map((edit) => [rowKey(edit.source, edit.unique_id), edit]));
  return (row) => {
    const edit = pending.get(rowKey(row.source, row.unique_id));
    if (!edit || row.split_id != null) return undefined;
    const category = edit.category === undefined ? (row.category ?? null) : edit.category || null;
    const tag = edit.tag === undefined ? (row.tag ?? null) : edit.tag || null;
    return [{ ...row, category: category ?? undefined, tag: tag ?? undefined }];
  };
}

/** Gather what the client already knows about project and yearly rules. */
function claimContext(client: QueryClient): ClaimContext {
  const projectCategories = new Set<string>();
  for (const [, data] of client.getQueriesData<ProjectStatus[]>({
    queryKey: [...qkPrefix.budget, "projects-status"],
  })) {
    data?.forEach((project) => projectCategories.add(project.name));
  }
  for (const [, data] of client.getQueriesData<MonthlyAnalysis>({
    queryKey: qkPrefix.budgetAnalysis,
  })) {
    data?.project_spending?.projects?.forEach((p) => projectCategories.add(p.category));
  }

  const yearlyRules = new Map<number, { category: string; tags?: string | string[] }[]>();
  for (const [key, data] of client.getQueriesData<{
    rules?: { rule: { category: string; tags?: string | string[] } }[];
  }>({ queryKey: [...qkPrefix.budget, "yearly"] })) {
    const year = key[2];
    if (typeof year !== "number" || !data?.rules) continue;
    yearlyRules.set(
      year,
      data.rules.map(({ rule }) => rule),
    );
  }
  return { projectCategories, yearlyRules };
}

/**
 * Reads a category/tag write cannot change, which the refresh after it
 * leaves alone: the rules, categories and accounts themselves, and the
 * app's own status. A retag only moves money between pools, so refetching
 * these after every one was pure queueing in front of the month the user is
 * looking at.
 */
export const UNCHANGED_BY_RETAG: readonly QueryKey[] = [
  ["budget", "projects"],
  ["budget", "projects-status"],
  ["budget", "available-projects"],
  ["budget", "month-overrides"],
  ["budget", "category-conflicts"],
  qkPrefix.categories,
  qkPrefix.categoryIcons,
  qkPrefix.taggingRules,
  qkPrefix.bankBalances,
  qkPrefix.insuranceAccounts,
  qkPrefix.lastScrapes,
  qkPrefix.credentialsAccounts,
  qkPrefix.providers,
  qkPrefix.backups,
  ["rates"],
  ["onboardingStatus"],
  ["updateCheck"],
  ["versionInfo"],
];

/**
 * Drop a retag plan's month scoping once the reply shows the write reached
 * further than the rows it named.
 *
 * Retagging a purchase moves its linked refunds with it (`refunds_retagged`
 * in the reply), and a refund can sit in a month the patch never saw. Every
 * month's analysis is then fair game; the rest of the plan still holds.
 *
 * @param plan - The plan `patchBudgetForRetag` returned, changed in place so
 *   the mutation cache — which reads it after the write's `onSuccess` — sees
 *   the wider one.
 * @param refundsRetagged - The reply's `refunds_retagged`.
 */
export function widenForCascade(plan: RefreshPlan | undefined, refundsRetagged: number | undefined) {
  if (!plan || !refundsRetagged) return;
  (plan as { skip?: readonly QueryKey[] }).skip = UNCHANGED_BY_RETAG;
}

/** A cached month's analysis key, without the variant and demo parts. */
const monthKey = (year: number, month: number) => [...qkPrefix.budgetAnalysis, year, month] as const;

/** What {@link patchBudget} did across the cache. */
export interface BudgetPatch {
  /** Put every patched month back, for a failed write. */
  restore: () => void;
  /** The months (`"year-month"`) whose analysis the write changed. */
  months: Set<string>;
  /** Whether every row the write names was found in some cached month. */
  placed: boolean;
}

/**
 * Apply a write to every cached monthly analysis, now.
 *
 * Reads still in flight are cancelled first — they were computed before the
 * write and would land on top of the patch. The refetch that follows the write
 * replaces the patch with the server's answer.
 *
 * @param client - The app's query client.
 * @param change - What the write does to each listed row.
 * @param names - `rowKey`s of the rows the write names, to tell whether all
 *   of them were found (a row in no cached month could be in any month).
 * @param arriving - The rows the write brings into a given month.
 */
export function patchBudget(
  client: QueryClient,
  change: RowChange,
  names: readonly string[],
  arriving?: (year: number, month: number) => AnalysisRow[],
): BudgetPatch {
  const cache = client.getQueryCache();
  for (const query of cache.findAll({ queryKey: qkPrefix.budgetAnalysis, fetchStatus: "fetching" })) {
    if (query.state.data !== undefined) void query.cancel({ revert: true });
  }

  const ctx = claimContext(client);
  const before = client.getQueriesData<MonthlyAnalysis>({ queryKey: qkPrefix.budgetAnalysis });
  const found = new Set<string>();
  const months = new Set<string>();
  const tracked: RowChange = (row) => {
    const into = change(row);
    if (into) found.add(rowKey(row.source, row.unique_id));
    return into;
  };
  for (const [key, data] of before) {
    if (!data) continue;
    const year = Number(key[2]);
    const month = Number(key[3]);
    const next = applyRowChanges(data, tracked, ctx, arriving?.(year, month) ?? []);
    if (next === data) continue;
    client.setQueryData(key, next);
    months.add(`${year}-${month}`);
  }
  return {
    restore: () => {
      for (const [key, data] of before) client.setQueryData(key, data);
    },
    months,
    placed: names.every((name) => found.has(name)),
  };
}

/**
 * The refresh after a write {@link patchBudget} placed: the months it touched
 * first, and none of the months it did not — unless a row was nowhere in the
 * cache, and so could be in any month.
 *
 * @param client - The app's query client.
 * @param patch - What the patch did.
 * @param skip - Reads the write cannot change, on top of the untouched months.
 */
export function budgetRefresh(
  client: QueryClient,
  patch: BudgetPatch,
  skip: readonly QueryKey[],
): RefreshPlan {
  const touched = [...patch.months].map((month) => {
    const [year, number] = month.split("-").map(Number);
    return monthKey(year, number);
  });
  const untouched = patch.placed
    ? client
        .getQueriesData<MonthlyAnalysis>({ queryKey: qkPrefix.budgetAnalysis })
        .map(([key]) => key)
        .filter((key) => !patch.months.has(`${key[2]}-${key[3]}`))
        .map((key) => key.slice(0, 4))
    : [];
  return {
    first: patch.placed && touched.length > 0 ? touched : [qkPrefix.budgetAnalysis],
    skip: [...skip, ...untouched],
  };
}

/**
 * Move retagged rows to their new rule in every cached monthly analysis, now.
 *
 * @param client - The app's query client.
 * @param edits - The writes being sent.
 * @returns `restore`, which puts every patched month back for a failed
 *   write, and `refresh`, the plan the mutation cache follows after it: the
 *   touched months first, and neither the months the write cannot have
 *   touched nor the reads in {@link UNCHANGED_BY_RETAG} (nor the cash
 *   balances, unless a cash row is among the edits).
 */
export function patchBudgetForRetag(
  client: QueryClient,
  edits: RetagEdit[],
): { restore: () => void; refresh: RefreshPlan } {
  const patch = patchBudget(
    client,
    retagChange(edits),
    edits.map((edit) => rowKey(edit.source, edit.unique_id)),
  );
  return {
    restore: patch.restore,
    // A cash balance is a sum over its account's cash rows; only a write
    // to one of those can move it.
    refresh: budgetRefresh(client, patch, [
      ...UNCHANGED_BY_RETAG,
      ...(edits.some((edit) => edit.source.includes("cash")) ? [] : [qkPrefix.cashBalances]),
    ]),
  };
}

/** A row named by its table and id, the way a write addresses it. */
export interface RowRef {
  source?: string;
  unique_id?: string | number;
  id?: string | number;
}

const refKey = (ref: RowRef) => rowKey(ref.source, ref.unique_id ?? ref.id);

/**
 * Take deleted rows out of every cached budget month, now.
 *
 * @param client - The app's query client.
 * @param rows - The rows being deleted.
 * @returns What the patch did, for {@link budgetRefresh} and a failed write.
 */
export function patchBudgetForDelete(client: QueryClient, rows: readonly RowRef[]): BudgetPatch {
  const names = new Set(rows.map(refKey));
  return patchBudget(
    client,
    (row) => (row.split_id == null && names.has(rowKey(row.source, row.unique_id)) ? [] : undefined),
    [...names],
  );
}

/** One part of a split being written, as `transactionsApi.split` sends it. */
export interface SplitPart {
  amount: number;
  category: string;
  tag: string;
}

/**
 * The rows a split turns a transaction into, shaped as the merged lists serve
 * split parts (`type: "split_child"`, the parent's fields alongside). Their
 * ids are stand-ins — negative, so no real part can share one — until the
 * refetch brings the real ones.
 *
 * @param parent - The row being split.
 * @param parts - The parts being sent.
 */
export function splitRows<T extends Transaction>(parent: T, parts: readonly SplitPart[]): T[] {
  return parts.map((part, index) => ({
    ...parent,
    unique_id: `split_pending_${parent.unique_id}_${index}`,
    split_id: -(index + 1),
    type: "split_child",
    amount: part.amount,
    category: part.category || undefined,
    tag: part.tag || undefined,
    net_amount: null,
    parent_unique_id: Number(parent.unique_id),
    parent_category: parent.category ?? null,
    parent_tag: parent.tag ?? null,
    parent_amount: parent.amount,
  }));
}

/**
 * Replace a split transaction by its parts in every cached budget month, now:
 * each part goes to the rule that claims its own category and tag.
 *
 * @param client - The app's query client.
 * @param parent - The row being split.
 * @param parts - The parts being sent.
 * @returns What the patch did, for {@link budgetRefresh} and a failed write.
 */
export function patchBudgetForSplit(
  client: QueryClient,
  parent: RowRef,
  parts: readonly SplitPart[],
): BudgetPatch {
  const name = refKey(parent);
  return patchBudget(
    client,
    (row) =>
      row.split_id == null && rowKey(row.source, row.unique_id) === name
        ? splitRows(row, parts)
        : undefined,
    [name],
  );
}

/** A row being re-monthed for the budget, as `planMonthMove` receives it. */
export interface BudgetMonthMove {
  tx: Transaction;
  fromYear: number;
  fromMonth: number;
  year: number;
  month: number;
}

/**
 * Move a row from one budget month to another in every cached analysis, now.
 *
 * The row leaves its old month and arrives in the new one, claimed by that
 * month's rules. The copy that arrives is the one the old month listed when
 * it is cached (it carries what the row nets to), otherwise the row as the
 * caller has it.
 *
 * @param client - The app's query client.
 * @param move - The move being sent.
 * @returns What the patch did, for {@link budgetRefresh} and a failed write.
 */
export function patchBudgetForMonthMove(client: QueryClient, move: BudgetMonthMove): BudgetPatch {
  const { tx, fromYear, fromMonth, year, month } = move;
  const name = refKey(tx);
  const matches = (row: AnalysisRow) =>
    rowKey(row.source, row.unique_id) === name && (row.split_id ?? null) === (tx.split_id ?? null);

  let listed: AnalysisRow | undefined;
  for (const [, data] of client.getQueriesData<MonthlyAnalysis>({
    queryKey: monthKey(fromYear, fromMonth),
  })) {
    if (data) listed ??= listedRows(data).find(matches);
  }
  const moved: AnalysisRow = { ...(listed ?? tx), budget_year: year, budget_month: month };
  // A row no cached month listed is placed only if it can be budget spending
  // at all; anything else waits for the server.
  const arrives = listed !== undefined || (tx.amount < 0 && !NON_EXPENSE.has(tx.category ?? ""));

  return patchBudget(
    client,
    (row) => (matches(row) && (row.budget_year !== year || row.budget_month !== month) ? [] : undefined),
    [name],
    (y, m) => (arrives && y === year && m === month ? [moved] : []),
  );
}

/**
 * Change what rows count for in every cached budget month, now — a pending
 * refund takes its still-expected part off the purchase.
 *
 * @param client - The app's query client.
 * @param nets - The new net amount (negative, as `amount`) by `rowKey`, or
 *   `null` to count a row at its gross amount again.
 * @returns What the patch did, for a failed write.
 */
export function patchBudgetNets(
  client: QueryClient,
  nets: ReadonlyMap<string, (row: AnalysisRow) => number | null>,
): BudgetPatch {
  return patchBudget(
    client,
    (row) => {
      const net = row.split_id == null ? nets.get(rowKey(row.source, row.unique_id)) : undefined;
      if (!net) return undefined;
      const value = net(row);
      return [{ ...row, net_amount: value === null || value === row.amount ? null : value }];
    },
    [...nets.keys()],
  );
}

/** Every row a month's analysis lists, rules and projects alike. */
function listedRows(analysis: MonthlyAnalysis): AnalysisRow[] {
  return [
    ...(analysis.rules ?? []).flatMap((item) => item.data),
    ...(analysis.project_spending?.projects ?? []).flatMap((p) => p.transactions ?? []),
  ];
}
