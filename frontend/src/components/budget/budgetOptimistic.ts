import type { QueryClient, QueryKey } from "@tanstack/react-query";
import type { Transaction } from "../../types/transaction";
import type { ProjectStatus } from "../../services/api";
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
type AnalysisRow = Transaction & {
  split_id?: number | null;
  net_amount?: number | null;
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
  | { kind: "other" };

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

const inPool = (owner: Owner) => owner.kind === "rule" || owner.kind === "other";

/**
 * Re-derive a month's analysis as if a batch of category/tag writes had
 * landed.
 *
 * A retag invalidates the whole budget, and the analysis behind the Monthly
 * tab is the slowest read on the page, so waiting for it left the row in its
 * old rule for seconds after the click. This moves each written row — and its
 * cost — to the rule the backend's claim order would give it, so the tab
 * answers immediately; the refetch that follows either agrees or corrects it.
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
  const pending = new Map(edits.map((edit) => [rowKey(edit.source, edit.unique_id), edit]));

  const items: AnalysisItem[] = analysis.rules.map((item) => ({ ...item, data: [...item.data] }));
  let projects: ProjectSpending[] = (analysis.project_spending?.projects ?? []).map((p) => ({
    ...p,
    transactions: [...(p.transactions ?? [])],
  }));
  let projectsTotal = analysis.project_spending?.total_spent ?? 0;
  const total = items.find(isTotal);

  const found: { row: AnalysisRow; owner: Owner }[] = [];
  const seen = new Set<string>();
  const take = (row: AnalysisRow, owner: Owner) => {
    const key = rowKey(row.source, row.unique_id);
    if (row.split_id != null || !pending.has(key) || seen.has(key)) return;
    seen.add(key);
    found.push({ row, owner });
  };
  items.forEach((item, index) => {
    if (isTotal(item)) return;
    item.data.forEach((row) => take(row, isOther(item) ? { kind: "other" } : { kind: "rule", index }));
  });
  projects.forEach((project) =>
    (project.transactions ?? []).forEach((row) =>
      take(row, { kind: "project", category: project.category }),
    ),
  );
  if (found.length === 0) return analysis;

  const otherIndex = () => items.findIndex(isOther);
  const sameRow = (a: AnalysisRow) => (b: AnalysisRow) =>
    b.split_id == null && rowKey(a.source, a.unique_id) === rowKey(b.source, b.unique_id);

  for (const { row, owner: from } of found) {
    const edit = pending.get(rowKey(row.source, row.unique_id))!;
    const category = edit.category === undefined ? (row.category ?? null) : edit.category || null;
    const tag = edit.tag === undefined ? (row.tag ?? null) : edit.tag || null;
    const moved: AnalysisRow = { ...row, category: category ?? undefined, tag: tag ?? undefined };
    const year = (row as { budget_year?: number }).budget_year;
    const to = claim(items, category, tag, year, ctx);
    const cost = costOf(row);

    // Out of where it was.
    if (from.kind === "rule" || from.kind === "other") {
      const index = from.kind === "rule" ? from.index : otherIndex();
      const item = items[index];
      item.data = item.data.filter((r) => !sameRow(row)(r));
      item.current_amount -= cost;
    } else if (from.kind === "project") {
      const project = projects.find((p) => p.category === from.category)!;
      project.transactions = (project.transactions ?? []).filter((r) => !sameRow(row)(r));
      project.spent -= cost;
      projectsTotal -= cost;
    }

    // Into where the claim order puts it.
    if (to.kind === "rule") {
      items[to.index].data.push(moved);
      items[to.index].current_amount += cost;
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
            id: `${year ?? ""}${(row as { budget_month?: number }).budget_month ?? ""}_Other_Expenses`,
          },
          current_amount: 0,
          data: [],
          allow_edit: false,
          allow_delete: false,
        });
        index = items.length - 1;
      }
      if (index !== -1) {
        items[index].data.push(moved);
        items[index].current_amount += cost;
      }
    } else if (to.kind === "project") {
      let project = projects.find((p) => p.category === to.category);
      if (!project) {
        project = { category: to.category, spent: 0, transactions: [] };
        projects.push(project);
      }
      project.transactions = [...(project.transactions ?? []), moved];
      project.spent += cost;
      projectsTotal += cost;
    }

    // The Total Budget lists the whole monthly pool, so it only gains or
    // loses a row when the retag crosses the pool's edge.
    if (total) {
      const wasIn = inPool(from);
      const nowIn = inPool(to);
      if (wasIn && nowIn) {
        total.data = total.data.map((r) => (sameRow(row)(r) ? moved : r));
      } else if (wasIn) {
        total.data = total.data.filter((r) => !sameRow(row)(r));
        total.current_amount -= cost;
      } else if (nowIn) {
        total.data.push(moved);
        total.current_amount += cost;
      }
    }
  }

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

/**
 * Move retagged rows to their new rule in every cached monthly analysis, now.
 *
 * Reads still in flight are cancelled first — they were computed before the
 * write and would land on top of the patch. The refetch that follows the write
 * replaces the patch with the server's answer.
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
  const cache = client.getQueryCache();
  for (const query of cache.findAll({ queryKey: qkPrefix.budgetAnalysis, fetchStatus: "fetching" })) {
    if (query.state.data !== undefined) void query.cancel({ revert: true });
  }

  const ctx = claimContext(client);
  const before = client.getQueriesData<MonthlyAnalysis>({ queryKey: qkPrefix.budgetAnalysis });
  const wanted = new Set(edits.map((edit) => rowKey(edit.source, edit.unique_id)));
  const found = new Set<string>();
  const months = new Set<string>();
  for (const [key, data] of before) {
    if (!data) continue;
    const next = applyRetag(data, edits, ctx);
    if (next === data) continue;
    client.setQueryData(key, next);
    months.add(`${key[2]}-${key[3]}`);
    for (const row of listedRows(data)) {
      const id = rowKey(row.source, row.unique_id);
      if (wanted.has(id)) found.add(id);
    }
  }

  // Each analysis holds one budget month, so a month whose cached analysis
  // listed none of these rows is one the write did not touch — unless a row
  // was nowhere in the cache, and so could be in any month.
  const placed = found.size === wanted.size;
  const touched = [...months].map((month) => {
    const [year, number] = month.split("-").map(Number);
    return [...qkPrefix.budgetAnalysis, year, number] as const;
  });
  const untouched = placed
    ? before
        .map(([key]) => key)
        .filter((key) => !months.has(`${key[2]}-${key[3]}`))
        .map((key) => key.slice(0, 4))
    : [];

  return {
    restore: () => {
      for (const [key, data] of before) client.setQueryData(key, data);
    },
    refresh: {
      first: placed && touched.length > 0 ? touched : [qkPrefix.budgetAnalysis],
      // A cash balance is a sum over its account's cash rows; only a write
      // to one of those can move it.
      skip: [
        ...UNCHANGED_BY_RETAG,
        ...untouched,
        ...(edits.some((edit) => edit.source.includes("cash")) ? [] : [qkPrefix.cashBalances]),
      ],
    },
  };
}

/** Every row a month's analysis lists, rules and projects alike. */
function listedRows(analysis: MonthlyAnalysis): AnalysisRow[] {
  return [
    ...(analysis.rules ?? []).flatMap((item) => item.data),
    ...(analysis.project_spending?.projects ?? []).flatMap((p) => p.transactions ?? []),
  ].filter((row) => row.split_id == null);
}
