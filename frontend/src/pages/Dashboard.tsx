import { useState, useMemo, useRef, useCallback, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  TrendingDown,
  ChevronLeft,
  ChevronRight,
  Calculator,
  Split,
  RefreshCw,
  Tag,
  Wand2,
  Link2,
  Plus,
} from "lucide-react";
import Plot from "react-plotly.js";
import {
  analyticsApi,
  cashBalancesApi,
  bankBalancesApi,
  investmentsApi,
  budgetApi,
  transactionsApi,
  taggingApi,
  pendingRefundsApi,
  type TaggingRule,
  type ConditionNode,
  type BankBalance,
} from "../services/api";
import { SplitTransactionModal } from "../components/modals/SplitTransactionModal";
import { LinkRefundModal } from "../components/modals/LinkRefundModal";
import { ProjectModal } from "../components/modals/ProjectModal";
import { SelectDropdown } from "../components/common/SelectDropdown";
import { useCategoryTagCreate } from "../hooks/useCategoryTagCreate";
import { SankeyChart } from "../components/SankeyChart";
import { SemiGauge } from "../components/common/SemiGauge";
import { Skeleton } from "../components/common/Skeleton";
import { useDemoMode } from "../context/DemoModeContext";
import { isToday, isYesterday } from "date-fns";
import { useTranslation } from "react-i18next";
import { formatMonthYear, formatShortDate } from "../utils/dateFormatting";
import { chartTheme, plotlyConfig, isTouchDevice } from "../utils/plotlyLocale";
import i18n from "../i18n";

type NetWorthView = "all" | "bank_balance" | "investments" | "net_worth" | "debt_payments";

const formatCurrency = (val: number) =>
  new Intl.NumberFormat("he-IL", {
    style: "currency",
    currency: "ILS",
    maximumFractionDigits: 0,
  }).format(val || 0);

const formatCompactCurrency = (val: number) => {
  const abs = Math.abs(val || 0);
  if (abs >= 1_000_000) return `₪${(val / 1_000_000).toFixed(1)}M`;
  if (abs >= 10_000) return `₪${(val / 1_000).toFixed(0)}K`;
  if (abs >= 1_000) return `₪${(val / 1_000).toFixed(1)}K`;
  return formatCurrency(val);
};


/* ------------------------------------------------------------------ */
/*  Helper sub-components (extracted to avoid creating during render)  */
/* ------------------------------------------------------------------ */

function MomBadge({ mom }: { mom: { delta: number; percent: number | null } | null }) {
  if (!mom) return null;
  const { delta, percent } = mom;
  const color = delta >= 0 ? "text-emerald-400" : "text-rose-400";
  const sign = delta >= 0 ? "+" : "";
  return (
    <span dir="ltr" className={`text-[10px] font-semibold ${color}`}>
      {sign}{formatCompactCurrency(delta)} {percent !== null && `(${sign}${percent.toFixed(1)}%)`}
    </span>
  );
}

function BreakdownList({ items }: { items: { name: string; amount: number }[] }) {
  return (
    <div className="mt-2 pt-2 border-t border-[var(--surface-light)] space-y-1">
      {items.map((item) => (
        <div key={item.name} className="flex justify-between text-xs">
          <span className="text-[var(--text-muted)] truncate me-2">{item.name}</span>
          <span className="tabular-nums font-medium shrink-0">{formatCurrency(item.amount)}</span>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Section 1 — Financial Health Header                               */
/* ------------------------------------------------------------------ */

function FinancialHealthHeader({
  netWorthData,
  cashBalances,
  bankBalances,
  portfolioAllocation,
  isLoading,
}: {
  netWorthData:
    | { month: string; bank_balance: number; investment_value: number; cash: number; net_worth: number }[]
    | undefined;
  cashBalances: { account_name: string; balance: number }[] | undefined;
  bankBalances: BankBalance[] | undefined;
  portfolioAllocation: { name: string; balance: number }[] | undefined;
  isLoading: boolean;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);

  const latestNetWorth = netWorthData?.length ? netWorthData[netWorthData.length - 1] : null;
  const previousNetWorth =
    netWorthData && netWorthData.length >= 2 ? netWorthData[netWorthData.length - 2] : null;

  const calcMom = (current: number | undefined, previous: number | undefined) => {
    if (current == null || previous == null) return null;
    const delta = current - previous;
    const percent = previous !== 0 ? (delta / Math.abs(previous)) * 100 : null;
    return { delta, percent };
  };

  const netWorthMom = calcMom(latestNetWorth?.net_worth, previousNetWorth?.net_worth);
  const bankMom = calcMom(latestNetWorth?.bank_balance, previousNetWorth?.bank_balance);
  const investmentMom = calcMom(latestNetWorth?.investment_value, previousNetWorth?.investment_value);
  const cashMom = calcMom(latestNetWorth?.cash, previousNetWorth?.cash);

  const totalCash = cashBalances?.reduce((sum, c) => sum + c.balance, 0) ?? 0;
  const openInvestments = portfolioAllocation?.filter((i) => i.balance > 0);

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} variant="card" className="h-16" />
        ))}
      </div>
    );
  }

  return (
    <div
      className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-3 cursor-pointer"
      onClick={() => setExpanded((v) => !v)}
    >
      {/* Net Worth */}
      <div className="bg-[var(--surface)] rounded-xl px-3 sm:px-4 py-2.5 sm:py-3 border border-[var(--surface-light)] overflow-hidden">
        <p className="text-[10px] sm:text-xs text-[var(--text-muted)] truncate">💰 {t("dashboard.netWorth")}</p>
        <p className="text-base sm:text-lg font-bold mt-0.5 truncate">
          {latestNetWorth ? formatCurrency(latestNetWorth.net_worth) : "--"}
        </p>
        <MomBadge mom={netWorthMom} />
      </div>

      {/* Bank Balance */}
      <div className="bg-[var(--surface)] rounded-xl px-3 sm:px-4 py-2.5 sm:py-3 border border-[var(--surface-light)] overflow-hidden">
        <p className="text-[10px] sm:text-xs text-[var(--text-muted)] truncate">🏦 {t("dashboard.bankBalance")}</p>
        <p className="text-base sm:text-lg font-bold mt-0.5 truncate">
          {latestNetWorth ? formatCurrency(latestNetWorth.bank_balance) : "--"}
        </p>
        <MomBadge mom={bankMom} />
        {expanded && bankBalances && bankBalances.length > 0 && (
          <BreakdownList
            items={bankBalances.map((b) => ({ name: b.account_name, amount: b.balance }))}
          />
        )}
      </div>

      {/* Investments */}
      <div className="bg-[var(--surface)] rounded-xl px-3 sm:px-4 py-2.5 sm:py-3 border border-[var(--surface-light)] overflow-hidden">
        <p className="text-[10px] sm:text-xs text-[var(--text-muted)] truncate">📈 {t("dashboard.investmentValue")}</p>
        <p className="text-base sm:text-lg font-bold mt-0.5 truncate">
          {latestNetWorth ? formatCurrency(latestNetWorth.investment_value) : "--"}
        </p>
        <MomBadge mom={investmentMom} />
        {expanded && openInvestments && openInvestments.length > 0 && (
          <BreakdownList
            items={openInvestments.map((i) => ({ name: i.name, amount: i.balance }))}
          />
        )}
      </div>

      {/* Cash */}
      <div className="bg-[var(--surface)] rounded-xl px-3 sm:px-4 py-2.5 sm:py-3 border border-[var(--surface-light)] overflow-hidden">
        <p className="text-[10px] sm:text-xs text-[var(--text-muted)] truncate">💵 {t("dashboard.cashBalance")}</p>
        <p className="text-base sm:text-lg font-bold mt-0.5 truncate">{formatCurrency(totalCash)}</p>
        <MomBadge mom={cashMom} />
        {expanded && cashBalances && cashBalances.length > 0 && (
          <BreakdownList
            items={cashBalances.map((c) => ({ name: c.account_name, amount: c.balance }))}
          />
        )}
      </div>

    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Section 2 — Budget Spending Gauge (Monthly + Projects)            */
/* ------------------------------------------------------------------ */

type BudgetViewMode = "monthly" | "projects";

interface BudgetRule {
  id: number;
  name: string;
  category: string;
  tags: string | null;
  budget_amount: number;
  spent_amount: number;
}

function getProgressColor(pct: number): string {
  if (pct > 100) return "bg-rose-500";
  if (pct >= 75) return "bg-amber-500";
  return "bg-emerald-500";
}

function BudgetRuleCards({
  rules,
  categoryIcons,
}: {
  rules: BudgetRule[];
  categoryIcons: Record<string, string> | undefined;
}) {
  const { t } = useTranslation();
  return (
    <div className="h-[260px] overflow-y-auto scrollbar-auto-hide mb-4">
      {rules.length > 0 && (
        <div className="grid grid-cols-2 gap-3">
          {rules.map((rule) => {
            const pct = rule.budget_amount > 0 ? (rule.spent_amount / rule.budget_amount) * 100 : 0;
            const remaining = rule.budget_amount - rule.spent_amount;
            const icon = categoryIcons?.[rule.category] ?? "";
            return (
              <div
                key={rule.id}
                className="bg-[var(--surface-light)] rounded-xl p-3.5 space-y-2"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 min-w-0">
                    {icon && <span className="text-sm flex-shrink-0">{icon}</span>}
                    <span className="text-xs font-semibold truncate">{rule.name}</span>
                  </div>
                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full flex-shrink-0 ${
                    pct > 100
                      ? "bg-rose-500/20 text-rose-400"
                      : pct >= 75
                        ? "bg-amber-500/20 text-amber-400"
                        : "bg-emerald-500/20 text-emerald-400"
                  }`}>
                    {Math.round(pct)}%
                  </span>
                </div>
                <p className="text-sm font-bold">
                  {formatCurrency(rule.spent_amount)}
                  <span className="text-xs font-normal text-[var(--text-muted)]">
                    {" "}/ {formatCurrency(rule.budget_amount)}
                  </span>
                </p>
                <div className="h-1.5 w-full rounded-full bg-[var(--surface)] overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${getProgressColor(pct)}`}
                    style={{ width: `${Math.min(pct, 100)}%` }}
                  />
                </div>
                <p className={`text-[10px] font-medium ${
                  remaining >= 0 ? "text-[var(--text-muted)]" : "text-rose-400"
                }`}>
                  {remaining >= 0
                    ? `${formatCurrency(remaining)} ${t("budget.remaining").toLowerCase()}`
                    : `${formatCurrency(Math.abs(remaining))} ${t("budget.overBudget").toLowerCase()}`}
                </p>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function BudgetSpendingGauge({
  categoryIcons,
}: {
  categoryIcons: Record<string, string> | undefined;
}) {
  const { t } = useTranslation();
  const now = new Date();
  const currentYear = now.getFullYear();
  const currentMonth = now.getMonth() + 1;
  const [year, setYear] = useState(currentYear);
  const [month, setMonth] = useState(currentMonth);
  const [viewMode, setViewMode] = useState<BudgetViewMode>("monthly");
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  const [isProjectModalOpen, setIsProjectModalOpen] = useState(false);
  const { isDemoMode } = useDemoMode();

  const isCurrentMonth = year === currentYear && month === currentMonth;
  const monthDate = new Date(year, month - 1);
  const monthName = formatMonthYear(monthDate);
  const daysInMonth = new Date(year, month, 0).getDate();
  const daysRemaining = daysInMonth - now.getDate();

  const handlePreviousMonth = () => {
    if (month === 1) {
      setMonth(12);
      setYear(year - 1);
    } else {
      setMonth(month - 1);
    }
  };

  const handleNextMonth = () => {
    if (month === 12) {
      setMonth(1);
      setYear(year + 1);
    } else {
      setMonth(month + 1);
    }
  };

  const queryClient = useQueryClient();

  // Prefetch surrounding 11 months so navigation is instant
  useEffect(() => {
    for (let i = 1; i <= 11; i++) {
      const d = new Date(currentYear, currentMonth - 1 - i);
      const prefetchYear = d.getFullYear();
      const prefetchMonth = d.getMonth() + 1;
      queryClient.prefetchQuery({
        queryKey: ["budget-analysis", prefetchYear, prefetchMonth, isDemoMode],
        queryFn: async () => {
          const res = await budgetApi.getAnalysis(prefetchYear, prefetchMonth, false);
          return res.data;
        },
      });
    }
  }, [isDemoMode, currentYear, currentMonth, queryClient]);

  // --- Monthly budget data ---
  const { data: rawBudgetAnalysis, isLoading: monthlyLoading } = useQuery({
    queryKey: ["budget-analysis", year, month, isDemoMode],
    queryFn: async () => {
      const res = await budgetApi.getAnalysis(year, month, false);
      return res.data;
    },
    enabled: viewMode === "monthly",
  });

  const budgetAnalysis = useMemo(() => {
    if (!rawBudgetAnalysis?.rules) return undefined;
    const rules: BudgetRule[] = rawBudgetAnalysis.rules.map((item: { rule: { id: number; name: string; category: string; tags: string | null; amount: number }; current_amount: number }) => ({
      id: item.rule.id,
      name: item.rule.name,
      category: item.rule.category,
      tags: item.rule.tags,
      budget_amount: item.rule.amount,
      spent_amount: item.current_amount,
    }));
    const totalRule = rules.find((r) => r.name === "Total Budget");
    return {
      rules,
      total_budget: totalRule?.budget_amount,
      total_spent: totalRule?.spent_amount,
    };
  }, [rawBudgetAnalysis]);

  // --- Project budget data ---
  const { data: projects } = useQuery({
    queryKey: ["budget-projects", isDemoMode],
    queryFn: async () => {
      const res = await budgetApi.getProjects();
      return res.data as string[];
    },
    enabled: viewMode === "projects",
  });

  const createProjectMutation = useMutation({
    mutationFn: budgetApi.createProject,
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["budget-projects"] });
      queryClient.invalidateQueries({ queryKey: ["availableProjects"] });
      setSelectedProject(variables.category);
      setIsProjectModalOpen(false);
    },
  });

  // Auto-select first project when projects load
   
  useEffect(() => {
    if (projects && projects.length > 0 && !selectedProject) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelectedProject(projects[0]);
    }
  }, [projects, selectedProject]);

  const { data: rawProjectDetails, isLoading: projectLoading } = useQuery({
    queryKey: ["budget-project-details", selectedProject, isDemoMode],
    queryFn: async () => {
      const res = await budgetApi.getProjectDetails(selectedProject!, false);
      return res.data;
    },
    enabled: viewMode === "projects" && !!selectedProject,
  });

  const projectAnalysis = useMemo(() => {
    if (!rawProjectDetails?.rules) return undefined;
    const rules: BudgetRule[] = rawProjectDetails.rules.map((item: { rule: { id: number; name: string; category: string; tags: string | null; amount: number }; current_amount: number }) => ({
      id: item.rule.id,
      name: item.rule.name,
      category: item.rule.category,
      tags: item.rule.tags,
      budget_amount: item.rule.amount,
      spent_amount: item.current_amount,
    }));
    const totalRule = rules.find((r) => r.name === "Total Budget");
    return {
      rules,
      total_budget: totalRule?.budget_amount,
      total_spent: totalRule?.spent_amount ?? rawProjectDetails.total_spent,
    };
  }, [rawProjectDetails]);

  // --- Computed values ---
  const activeAnalysis = viewMode === "monthly" ? budgetAnalysis : projectAnalysis;
  const isLoading = viewMode === "monthly" ? monthlyLoading : projectLoading;

  const totalBudget =
    activeAnalysis?.total_budget ??
    (activeAnalysis?.rules?.reduce((sum, r) => sum + r.budget_amount, 0) ?? 0);
  const totalSpent =
    activeAnalysis?.total_spent ??
    (activeAnalysis?.rules?.reduce((sum, r) => sum + r.spent_amount, 0) ?? 0);

  const miniRules = useMemo(() => {
    if (!activeAnalysis?.rules) return [];
    return activeAnalysis.rules
      .filter((r) => r.name !== "Total Budget")
      .sort((a, b) => b.spent_amount - a.spent_amount);
  }, [activeAnalysis]);

  // For monthly: hide card entirely if no data at all
  if (viewMode === "monthly" && !monthlyLoading && (!budgetAnalysis || budgetAnalysis.rules.length === 0)) return null;

  const hasNoProjects = viewMode === "projects" && (!projects || projects.length === 0);

  const toggleViewMode = () =>
    setViewMode(viewMode === "monthly" ? "projects" : "monthly");

  const segmentedControlEl = (
    <button
      onClick={toggleViewMode}
      className="flex bg-[var(--surface-light)] p-0.5 rounded-lg cursor-pointer"
    >
      {([
        { key: "monthly" as const, label: t("budget.monthlyBudget") },
        { key: "projects" as const, label: t("budget.projectBudgets") },
      ]).map(({ key, label }) => (
        <span
          key={key}
          className={`px-3 py-1 rounded-md text-xs font-semibold transition-all ${
            viewMode === key
              ? "bg-[var(--surface)] text-[var(--primary)] shadow-sm"
              : "text-[var(--text-muted)]"
          }`}
        >
          {label}
        </span>
      ))}
    </button>
  );

  return (
    <div
      className="bg-[var(--surface)] rounded-2xl p-4 md:p-6 border border-[var(--surface-light)]"
    >
      {/* Header row: segmented control */}
      <div className="flex items-center justify-between mb-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
          🎯 {t("budget.title")}
        </p>
        {segmentedControlEl}
      </div>

      {isLoading ? (
        <>
          <div className="h-9 mb-4">
            <Skeleton variant="text" lines={1} className="h-full" />
          </div>
          <Skeleton variant="chart" className="h-40" />
        </>
      ) : (
        <>
          {/* Sub-header: month nav or project selector — fixed h-9 so gauge stays in place */}
          <div className="h-9 flex items-center mb-4">
            {viewMode === "monthly" ? (
              <div className="flex items-center justify-between w-full">
                <div className="flex items-center gap-2">
                  <button
                    onClick={handlePreviousMonth}
                    className="p-1 rounded-lg hover:bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
                  >
                    <ChevronLeft size={16} />
                  </button>
                  <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)] w-36 text-center">
                    {monthName}
                  </p>
                  <button
                    onClick={handleNextMonth}
                    disabled={isCurrentMonth}
                    className="p-1 rounded-lg hover:bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-[var(--text)] transition-colors disabled:opacity-30 disabled:pointer-events-none"
                  >
                    <ChevronRight size={16} />
                  </button>
                </div>
                {isCurrentMonth && (
                  <span className="text-xs text-[var(--text-muted)]">
                    ⏳ {t("dashboard.daysRemaining", { count: daysRemaining })}
                  </span>
                )}
              </div>
            ) : (
              !hasNoProjects && (
                <div className="w-full flex items-center gap-2">
                  <div className="flex-1">
                    <SelectDropdown
                      options={(projects ?? []).map((p) => ({ label: p, value: p }))}
                      value={selectedProject ?? ""}
                      onChange={setSelectedProject}
                      placeholder="Select project..."
                      size="sm"
                    />
                  </div>
                  <button
                    onClick={() => setIsProjectModalOpen(true)}
                    className="p-1.5 rounded-lg hover:bg-[var(--surface-light)] text-[var(--primary)] transition-colors shrink-0"
                    title={t("tooltips.addNewProject")}
                  >
                    <Plus size={16} />
                  </button>
                </div>
              )
            )}
          </div>

          {/* Empty state for projects */}
          {hasNoProjects ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <p className="text-sm text-[var(--text-muted)] mb-3">{t("dashboard.noProjectBudgets")}</p>
              <button
                onClick={() => setIsProjectModalOpen(true)}
                className="flex items-center gap-2 text-sm font-medium text-[var(--primary)] hover:text-[var(--primary-dark)] transition-colors cursor-pointer"
              >
                <Plus size={16} />
                {t("budget.addProject")}
              </button>
            </div>
          ) : (
            <>
              {/* Gauge */}
              <div className="flex justify-center mb-6">
                <SemiGauge spent={totalSpent} budget={totalBudget} size={240} />
              </div>

              {/* Budget rule cards */}
              <BudgetRuleCards rules={miniRules} categoryIcons={categoryIcons} />

              {/* Link to budget page */}
              <div className="text-end">
                <Link
                  to="/budget"
                  className="text-sm font-medium text-[var(--primary)] hover:underline"
                >
                  {t("dashboard.viewAllBudgetRules")} &rarr;
                </Link>
              </div>
            </>
          )}
        </>
      )}

      <ProjectModal
        isOpen={isProjectModalOpen}
        onClose={() => setIsProjectModalOpen(false)}
        onSubmit={(data) => createProjectMutation.mutate(data)}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Section 3 — Recent Transactions Feed                              */
/* ------------------------------------------------------------------ */

interface Transaction {
  id?: number;
  unique_id?: string;
  date: string;
  description: string;
  amount: number;
  category: string;
  tag: string;
  source: string;
  provider: string;
  account_name: string;
  pending_refund_id?: number;
}

function formatTransactionDate(dateStr: string): string {
  const d = new Date(dateStr);
  if (isToday(d)) return i18n.t("common.today");
  if (isYesterday(d)) return i18n.t("common.yesterday");
  return formatShortDate(d);
}

const TRANSACTIONS_PAGE_SIZE = 20;

/** Evaluate a single condition leaf against a transaction. */
function evalCondition(node: ConditionNode, tx: Transaction): boolean {
  const { field, operator, value } = node;
  if (!field || !operator) return false;

  // Service field: compare against source
  if (field === "service") {
    if (operator !== "equals") return false;
    const svc = String(value).toLowerCase().replace(/\s+/g, "_");
    return (tx.source || "").toLowerCase().includes(svc);
  }

  const fieldMap: Record<string, string | number> = {
    description: tx.description ?? "",
    amount: tx.amount,
    provider: tx.provider ?? "",
    account_name: tx.account_name ?? "",
  };
  const fv = fieldMap[field];
  if (fv === undefined) return false;

  // Numeric operators
  if (field === "amount") {
    const n = Number(fv);
    if (operator === "gt") return n > Number(value);
    if (operator === "lt") return n < Number(value);
    if (operator === "gte") return n >= Number(value);
    if (operator === "lte") return n <= Number(value);
    if (operator === "equals") return n === Number(value);
    if (operator === "between" && Array.isArray(value))
      return n >= Number(value[0]) && n <= Number(value[1]);
    return false;
  }

  // Text operators (case-sensitive, matching backend LIKE behaviour)
  const sv = String(fv);
  const tv = String(value);
  if (operator === "contains") return sv.includes(tv);
  if (operator === "equals") return sv === tv;
  if (operator === "starts_with") return sv.startsWith(tv);
  if (operator === "ends_with") return sv.endsWith(tv);
  return false;
}

/** Recursively evaluate a condition tree against a transaction. */
function evalConditionTree(node: ConditionNode, tx: Transaction): boolean {
  if (node.type === "CONDITION") return evalCondition(node, tx);
  const subs = node.subconditions ?? [];
  if (subs.length === 0) return true; // empty group matches all
  if (node.type === "AND") return subs.every((s) => evalConditionTree(s, tx));
  if (node.type === "OR") return subs.some((s) => evalConditionTree(s, tx));
  return false;
}

/** Find the first tagging rule whose conditions match a transaction. */
function findMatchingRule(
  rules: TaggingRule[],
  tx: Transaction,
): TaggingRule | undefined {
  return rules.find((r) => evalConditionTree(r.conditions, tx));
}

function RecentTransactionsFeed({
  transactions,
  categoryIcons,
  isLoading,
}: {
  transactions: Transaction[] | undefined;
  categoryIcons: Record<string, string> | undefined;
  isLoading: boolean;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { createCategory, createTag } = useCategoryTagCreate();
  const [visibleCount, setVisibleCount] = useState(TRANSACTIONS_PAGE_SIZE);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const [editingTxKey, setEditingTxKey] = useState<string | null>(null);
  const [splittingTransaction, setSplittingTransaction] = useState<Transaction | null>(null);
  const [linkingTransaction, setLinkingTransaction] = useState<Transaction | null>(null);

  // Categories for inline tag editing
  const { data: categories } = useQuery({
    queryKey: ["categories"],
    queryFn: () => taggingApi.getCategories().then((res) => res.data),
    enabled: !!editingTxKey,
  });

  // Tagging rules for match indicators
  const { data: taggingRules } = useQuery({
    queryKey: ["taggingRules"],
    queryFn: () => taggingApi.getRules().then((res) => res.data),
  });

  const invalidateAnalytics = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["income-outcome"] });
    queryClient.invalidateQueries({ queryKey: ["analytics-category"] });
    queryClient.invalidateQueries({ queryKey: ["sankey"] });
    queryClient.invalidateQueries({ queryKey: ["net-worth-over-time"] });
    queryClient.invalidateQueries({ queryKey: ["income-by-source"] });
    queryClient.invalidateQueries({ queryKey: ["monthly-expenses"] });
    queryClient.invalidateQueries({ queryKey: ["budget-analysis"] });
  }, [queryClient]);

  // Tag update mutation
  const tagMutation = useMutation({
    mutationFn: ({ tx, category, tag }: { tx: Transaction; category: string; tag: string }) =>
      transactionsApi.updateTag(
        String(tx.unique_id ?? tx.id),
        category,
        tag,
        tx.source,
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["categories"] });
      invalidateAnalytics();
      setEditingTxKey(null);
    },
  });

  // Mark as pending refund
  const markPendingMutation = useMutation({
    mutationFn: (tx: Transaction) =>
      pendingRefundsApi.create({
        source_type: "transaction",
        source_id: tx.unique_id || "",
        source_table: tx.source,
        expected_amount: Math.abs(tx.amount),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["pendingRefunds"] });
      invalidateAnalytics();
    },
  });

  const sorted = useMemo(() => {
    if (!transactions) return [];
    return [...transactions].sort(
      (a, b) => new Date(b.date).getTime() - new Date(a.date).getTime(),
    );
  }, [transactions]);

  const visible = useMemo(() => sorted.slice(0, visibleCount), [sorted, visibleCount]);
  const hasMore = visibleCount < sorted.length;

  // IntersectionObserver to auto-load more when sentinel enters viewport
  const handleObserver = useCallback(
    (entries: IntersectionObserverEntry[]) => {
      const [entry] = entries;
      if (entry.isIntersecting && hasMore) {
        setVisibleCount((prev) => Math.min(prev + TRANSACTIONS_PAGE_SIZE, sorted.length));
      }
    },
    [hasMore, sorted.length],
  );

  useEffect(() => {
    const node = sentinelRef.current;
    if (!node) return;
    const observer = new IntersectionObserver(handleObserver, {
      root: node.closest("[data-scroll-root]"),
      rootMargin: "200px",
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [handleObserver]);

  // Reset visible count when transactions change (e.g. demo mode toggle)
   
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setVisibleCount(TRANSACTIONS_PAGE_SIZE);
  }, [transactions]);

  // Group by date label
  const grouped = useMemo(() => {
    const groups: { label: string; items: Transaction[] }[] = [];
    let currentLabel = "";
    for (const tx of visible) {
      const label = formatTransactionDate(tx.date);
      if (label !== currentLabel) {
        groups.push({ label, items: [] });
        currentLabel = label;
      }
      groups[groups.length - 1].items.push(tx);
    }
    return groups;
  }, [visible]);

  // Precompute which tagging rule matches each visible transaction
  const ruleMatchMap = useMemo(() => {
    if (!taggingRules || !visible.length) return new Map<string, TaggingRule>();
    const map = new Map<string, TaggingRule>();
    for (let i = 0; i < visible.length; i++) {
      const tx = visible[i];
      const key = `${tx.source}_${tx.unique_id ?? tx.id ?? `${tx.date}-${i}`}`;
      const match = findMatchingRule(taggingRules, tx);
      if (match) map.set(key, match);
    }
    return map;
  }, [taggingRules, visible]);

  const getTxKey = (tx: Transaction, i: number) =>
    `${tx.source}_${tx.unique_id ?? tx.id ?? `${tx.date}-${i}`}`;

  if (isLoading) {
    return (
      <div className="bg-[var(--surface)] rounded-2xl p-6 border border-[var(--surface-light)]">
        <Skeleton variant="text" lines={1} className="mb-4" />
        <Skeleton variant="text" lines={5} />
      </div>
    );
  }

  if (sorted.length === 0) return null;

  return (
    <div className="bg-[var(--surface)] rounded-2xl p-4 md:p-6 border border-[var(--surface-light)]">
      <div className="flex items-center justify-between mb-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
          🧾 {t("dashboard.recentTransactions")}
        </p>
        <Link
          to="/transactions"
          className="text-sm font-medium text-[var(--primary)] hover:underline"
        >
          {t("dashboard.viewAll")} &rarr;
        </Link>
      </div>

      <div
        data-scroll-root=""
        className="max-h-[500px] overflow-y-auto space-y-4 scrollbar-auto-hide"
      >
        {grouped.map((group) => (
          <div key={group.label}>
            <p className="text-xs font-semibold text-[var(--text-muted)] mb-2 sticky top-0 bg-[var(--surface)] py-1 z-10">
              {group.label}
            </p>
            <div className="space-y-1">
              {group.items.map((tx, i) => {
                const icon = categoryIcons?.[tx.category] ?? "";
                const isPositive = tx.amount >= 0;
                const txKey = getTxKey(tx, i);
                const isEditing = editingTxKey === txKey;
                const matchedRule = ruleMatchMap.get(txKey);

                return (
                  <div key={txKey}>
                    <div
                      className="flex items-center gap-2 py-2 px-2 rounded-lg hover:bg-[var(--surface-light)]/40 transition-colors cursor-default"
                    >
                      <span className="text-lg flex-shrink-0 w-7 text-center">{icon || "?"}</span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-baseline gap-1.5">
                          <span className="text-sm truncate">
                            {tx.description.length > 40
                              ? tx.description.slice(0, 40) + "..."
                              : tx.description}
                          </span>
                          <span className="text-[11px] text-[var(--text-muted)] flex-shrink-0">
                            {tx.category}{tx.tag ? ` / ${tx.tag}` : ""}
                          </span>
                        </div>
                        {matchedRule && (
                          <span
                            className="inline-flex items-center gap-0.5 mt-0.5 px-1.5 py-px rounded-full bg-violet-500/15 text-violet-400 text-[10px]"
                            title={`${t("tooltips.matchedRule")}: ${matchedRule.name}`}
                          >
                            <Wand2 size={9} />
                            {matchedRule.name}
                          </span>
                        )}
                      </div>
                      {/* Action buttons — hidden on small mobile, visible on sm+ */}
                      <div className="hidden sm:grid grid-cols-3 flex-shrink-0 w-[96px]">
                        <button
                          className={`w-[32px] h-[32px] flex items-center justify-center rounded-md transition-colors ${isEditing ? "bg-[var(--primary)]/20 text-[var(--primary)]" : "text-[var(--text-muted)]/40 hover:text-white hover:bg-[var(--surface-light)]"}`}
                          title={t("tooltips.editCategoryTag")}
                          onClick={() => setEditingTxKey(isEditing ? null : txKey)}
                        >
                          <Tag size={13} />
                        </button>
                        <button
                          className="w-[32px] h-[32px] flex items-center justify-center rounded-md text-[var(--text-muted)]/40 hover:text-white hover:bg-[var(--surface-light)] transition-colors"
                          title={t("tooltips.splitTransaction")}
                          onClick={() => setSplittingTransaction(tx)}
                        >
                          <Split size={13} />
                        </button>
                        {tx.amount < 0 ? (
                          tx.pending_refund_id ? (
                            <span className="w-[32px] h-[32px] flex items-center justify-center text-amber-400" title={t("tooltips.pendingRefund")}>
                              <RefreshCw size={13} className="animate-pulse" />
                            </span>
                          ) : (
                            <button
                              className="w-[32px] h-[32px] flex items-center justify-center rounded-md text-amber-400/40 hover:text-amber-400 hover:bg-amber-500/20 transition-colors"
                              title={t("tooltips.markPendingRefund")}
                              onClick={() => markPendingMutation.mutate(tx)}
                              disabled={markPendingMutation.isPending}
                            >
                              <RefreshCw size={13} />
                            </button>
                          )
                        ) : (
                          <button
                            className="w-[32px] h-[32px] flex items-center justify-center rounded-md text-emerald-400/40 hover:text-emerald-400 hover:bg-emerald-500/20 transition-colors"
                            title={t("tooltips.linkAsRefund")}
                            onClick={() => setLinkingTransaction(tx)}
                          >
                            <Link2 size={13} />
                          </button>
                        )}
                      </div>
                      <span
                        className={`text-sm font-semibold flex-shrink-0 tabular-nums text-end w-[80px] ${
                          isPositive ? "text-emerald-400" : "text-rose-400"
                        }`}
                      >
                        {isPositive ? "+" : ""}
                        {formatCurrency(tx.amount)}
                      </span>
                    </div>

                    {/* Inline tag editing panel */}
                    {isEditing && categories && (
                      <div className="mx-2 mb-2 ms-11 rounded-lg border border-[var(--surface-light)] bg-[var(--surface-light)]/20 overflow-hidden">
                        <div className="flex items-center gap-3 px-3 py-2">
                          <div className="flex-1 min-w-0">
                            <label className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] mb-1 block">{t("common.category")}</label>
                            <SelectDropdown
                              options={Object.keys(categories).map((c) => ({ label: c, value: c }))}
                              value={tx.category || ""}
                              onChange={(cat) => tagMutation.mutate({ tx, category: cat, tag: "" })}
                              placeholder="Select..."
                              size="sm"
                              onCreateNew={async (name) => { await createCategory(name); }}
                            />
                          </div>
                          <div className="flex-1 min-w-0">
                            <label className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] mb-1 block">{t("common.tag")}</label>
                            <SelectDropdown
                              options={
                                tx.category && categories[tx.category]
                                  ? categories[tx.category].map((t: string) => ({ label: t, value: t }))
                                  : []
                              }
                              value={tx.tag || ""}
                              onChange={(tag) => tagMutation.mutate({ tx, category: tx.category, tag })}
                              placeholder="Select..."
                              size="sm"
                              onCreateNew={
                                tx.category
                                  ? async (name) => { await createTag(tx.category, name); }
                                  : undefined
                              }
                            />
                          </div>
                          <button
                            className="self-end mb-0.5 px-2.5 py-1 text-[11px] font-medium rounded-md bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white hover:bg-[var(--surface-light)]/80 transition-colors"
                            onClick={() => setEditingTxKey(null)}
                          >
                            {t("dashboard.done")}
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}

        {/* Sentinel element for infinite scroll */}
        <div ref={sentinelRef} className="h-1" />

        {hasMore && (
          <div className="flex justify-center py-2">
            <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
              <div className="w-4 h-4 border-2 border-[var(--primary)]/30 border-t-[var(--primary)] rounded-full animate-spin" />
              {t("common.loading")}
            </div>
          </div>
        )}
      </div>

      {/* Split Transaction Modal */}
      {splittingTransaction && (
        <SplitTransactionModal
          transaction={splittingTransaction}
          onClose={() => setSplittingTransaction(null)}
          onSuccess={() => {
            setSplittingTransaction(null);
            queryClient.invalidateQueries({ queryKey: ["transactions"] });
            invalidateAnalytics();
          }}
        />
      )}

      {/* Link Refund Modal (for positive/income transactions) */}
      {linkingTransaction && (
        <LinkRefundModal
          isOpen={!!linkingTransaction}
          onClose={() => setLinkingTransaction(null)}
          refundTransaction={{
            id: linkingTransaction.unique_id || linkingTransaction.id || 0,
            source: linkingTransaction.source || "unknown",
            amount: linkingTransaction.amount,
            description: linkingTransaction.description,
          }}
        />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Section 4 — Tabbed Insights                                       */
/* ------------------------------------------------------------------ */

/* ================================================================== */
/*  Main Dashboard Component                                          */
/* ================================================================== */

export function Dashboard() {
  const { t } = useTranslation();
  const { isDemoMode } = useDemoMode();
  const [netWorthView, setNetWorthView] = useState<NetWorthView>("all");
  const [incomeView, setIncomeView] = useState<"overview" | "by_source" | "by_category">("overview");
  const [excludePendingRefunds, setExcludePendingRefunds] = useState(true);
  const [includeProjects, setIncludeProjects] = useState(false);
  const [excludeRefunds, setExcludeRefunds] = useState(false);
  const [insightTab, setInsightTab] = useState<
    "income_expenses" | "net_worth" | "cash_flow" | "category"
  >("income_expenses");

  // ---- Existing queries (kept) ----

  const { data: incomeOutcome } = useQuery({
    queryKey: ["income-outcome", includeProjects, excludeRefunds, isDemoMode],
    queryFn: async () => {
      const res = await analyticsApi.getIncomeExpensesOverTime(!includeProjects, false, excludeRefunds);
      return res.data;
    },
  });

  const { data: debtPaymentsData } = useQuery({
    queryKey: ["debt-payments", isDemoMode],
    queryFn: async () => {
      const res = await analyticsApi.getDebtPaymentsOverTime();
      return res.data;
    },
  });

  const { data: expensesByCategoryOverTime } = useQuery({
    queryKey: ["expenses-by-category-over-time", isDemoMode],
    queryFn: async () => {
      const res = await analyticsApi.getExpensesByCategoryOverTime();
      return res.data;
    },
  });

  const { data: categoryData } = useQuery({
    queryKey: ["analytics-category", isDemoMode],
    queryFn: async () => {
      const res = await analyticsApi.getByCategory();
      return res.data;
    },
  });

  const { data: sankeyData, isLoading: sankeyLoading } = useQuery({
    queryKey: ["sankey", isDemoMode],
    queryFn: async () => {
      const res = await analyticsApi.getSankeyData();
      return res.data;
    },
  });

  const { data: cashBalances } = useQuery({
    queryKey: ["cash-balances", isDemoMode],
    queryFn: () => cashBalancesApi.getAll().then((res) => res.data),
  });

  const { data: bankBalances } = useQuery({
    queryKey: ["bank-balances", isDemoMode],
    queryFn: () => bankBalancesApi.getAll().then((res) => res.data),
  });

  const { data: portfolioData } = useQuery({
    queryKey: ["portfolio-analysis", isDemoMode],
    queryFn: () => investmentsApi.getPortfolioAnalysis().then((res) => res.data),
  });

  const { data: netWorthData, isLoading: netWorthLoading } = useQuery({
    queryKey: ["net-worth-over-time", isDemoMode],
    queryFn: async () => {
      const res = await analyticsApi.getNetWorthOverTime();
      return res.data;
    },
  });

  const { data: incomeBySourceData } = useQuery({
    queryKey: ["income-by-source", isDemoMode],
    queryFn: async () => {
      const res = await analyticsApi.getIncomeBySourceOverTime();
      return res.data;
    },
  });


  const { data: monthlyExpenses } = useQuery({
    queryKey: ["monthly-expenses", excludePendingRefunds, includeProjects, isDemoMode],
    queryFn: async () => {
      const res = await analyticsApi.getMonthlyExpenses(excludePendingRefunds, includeProjects);
      return res.data;
    },
  });

  const { data: allTransactions, isLoading: transactionsLoading } = useQuery({
    queryKey: ["all-transactions", isDemoMode],
    queryFn: async () => {
      const res = await transactionsApi.getAll(undefined, false);
      return res.data;
    },
  });

  const { data: categoryIcons } = useQuery({
    queryKey: ["category-icons", isDemoMode],
    queryFn: async () => {
      const res = await taggingApi.getIcons();
      return res.data;
    },
  });

  // ---- Computed values for charts (kept) ----

  const netWorthDeltas = useMemo(() => {
    if (!netWorthData || netWorthData.length < 2) return null;
    return netWorthData.slice(1).map((d, i) => ({
      month: d.month,
      bank_balance: d.bank_balance,
      investment_value: d.investment_value,
      net_worth: d.net_worth,
      bank_balance_delta: d.bank_balance - netWorthData[i].bank_balance,
      investment_value_delta: d.investment_value - netWorthData[i].investment_value,
      net_worth_delta: d.net_worth - netWorthData[i].net_worth,
    }));
  }, [netWorthData]);

  const seriesConfig = {
    bank_balance: {
      label: t("dashboard.bankBalance"),
      color: "#f59e0b",
      dataKey: "bank_balance" as const,
      deltaKey: "bank_balance_delta" as const,
    },
    investments: {
      label: t("dashboard.investmentValue"),
      color: "#6366f1",
      dataKey: "investment_value" as const,
      deltaKey: "investment_value_delta" as const,
    },
    net_worth: {
      label: t("dashboard.netWorth"),
      color: "#ef4444",
      dataKey: "net_worth" as const,
      deltaKey: "net_worth_delta" as const,
    },
  };

  const getNetWorthTraces = (): Plotly.Data[] => {
    if (!netWorthData || netWorthData.length === 0) return [];
    if (netWorthView === "debt_payments") return [];

    if (netWorthView === "all") {
      return [
        {
          x: netWorthData.map((d) => d.month),
          y: netWorthData.map((d) => d.bank_balance),
          name: t("dashboard.bankBalance"),
          type: "scatter",
          mode: "lines+markers",
          line: { color: "#f59e0b", width: 2 },
          marker: { size: 4, color: "#f59e0b" },
        },
        {
          x: netWorthData.map((d) => d.month),
          y: netWorthData.map((d) => d.investment_value),
          name: t("dashboard.investmentValue"),
          type: "scatter",
          mode: "lines+markers",
          line: { color: "#6366f1", width: 2 },
          marker: { size: 4, color: "#6366f1" },
        },
        {
          x: netWorthData.map((d) => d.month),
          y: netWorthData.map((d) => d.net_worth),
          name: t("dashboard.netWorth"),
          type: "scatter",
          mode: "lines+markers",
          line: { color: "#ef4444", width: 3 },
          marker: { size: 5, color: "#ef4444" },
        },
      ];
    }

    if (!netWorthDeltas) return [];
    const config = seriesConfig[netWorthView];

    return [
      {
        x: netWorthDeltas.map((d) => d.month),
        y: netWorthDeltas.map((d) => d[config.deltaKey]),
        name: t("dashboard.monthlyChange"),
        type: "bar",
        marker: {
          color: netWorthDeltas.map((d) =>
            d[config.deltaKey] >= 0 ? "#10b981" : "#ef4444",
          ),
        },
      },
      {
        x: netWorthDeltas.map((d) => d.month),
        y: netWorthDeltas.map((d) => d[config.dataKey]),
        name: config.label,
        type: "scatter",
        mode: "lines+markers",
        line: { color: config.color, width: 3 },
        marker: { size: 8, color: config.color },
        yaxis: "y2",
      },
    ];
  };

  // ================================================================
  //  Render
  // ================================================================

  return (
    <div className="space-y-4 md:space-y-8 animate-in fade-in duration-500">
      <div>
        <h1 className="text-2xl md:text-3xl font-bold">📊 {t("dashboard.title")}</h1>
        <p className="text-[var(--text-muted)] mt-1 text-sm md:text-base">✨ {t("dashboard.subtitle")}</p>
      </div>

      {/* Section 1: Financial Health Header */}
      <FinancialHealthHeader
        netWorthData={netWorthData}
        cashBalances={cashBalances}
        bankBalances={bankBalances}
        portfolioAllocation={portfolioData?.allocation}
        isLoading={netWorthLoading}
      />

      {/* Section 2 & 3: Spending Gauge + Recent Transactions — side by side on large screens */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-8">
        <BudgetSpendingGauge
          categoryIcons={categoryIcons}
        />
        <RecentTransactionsFeed
          transactions={allTransactions}
          categoryIcons={categoryIcons}
          isLoading={transactionsLoading}
        />
      </div>

      {/* Section 4: Tabbed Insights */}
      <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] overflow-hidden">
        {/* Tab bar */}
        <div className="px-3 md:px-6 pt-4 md:pt-5 pb-0">
          <div className="flex bg-[var(--surface-light)] p-1 rounded-xl gap-1 overflow-x-auto scrollbar-auto-hide">
            {([
              { key: "income_expenses" as const, label: `⚖️ ${t("dashboard.incomeAndExpenses")}` },
              { key: "net_worth" as const, label: `📈 ${t("dashboard.netWorth")}` },
              { key: "cash_flow" as const, label: `🌊 ${t("dashboard.cashFlow")}` },
              { key: "category" as const, label: `🍕 ${t("dashboard.categories")}` },
            ]).map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setInsightTab(key)}
                className={`sm:flex-1 text-center px-2 md:px-3 py-1.5 rounded-lg text-xs md:text-sm font-bold transition-all whitespace-nowrap shrink-0 ${
                  insightTab === key
                    ? "bg-[var(--surface)] text-[var(--primary)] shadow-sm"
                    : "text-[var(--text-muted)] hover:text-[var(--text-default)]"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Tab content */}
        <div className="px-3 md:px-6 pb-4 md:pb-6 pt-4 min-h-[400px] md:h-[600px] overflow-y-auto flex flex-col">
          {/* Net Worth Over Time */}
          {insightTab === "net_worth" && (
            <div className="flex flex-col flex-1 min-h-0">
              {netWorthData && netWorthData.length > 0 ? (
                <>
                  {/* Net Worth Change KPIs + View Buttons */}
                  <div className="flex flex-wrap items-center gap-2 md:gap-3 mb-3">
                    {(() => {
                      const latest = netWorthData[netWorthData.length - 1];
                      const findMonthsAgo = (n: number) => {
                        const d = new Date();
                        d.setMonth(d.getMonth() - n);
                        const target = d.toISOString().slice(0, 7);
                        return [...netWorthData].reverse().find((d) => d.month <= target) ?? netWorthData[0];
                      };
                      const periods = [
                        { label: t("dashboard.change5Y"), months: 60 },
                        { label: t("dashboard.change3Y"), months: 36 },
                        { label: t("dashboard.change1Y"), months: 12 },
                        { label: t("dashboard.change6M"), months: 6 },
                        { label: t("dashboard.change1M"), months: 1 },
                      ];
                      return periods.map(({ label, months }) => {
                        const past = findMonthsAgo(months);
                        const delta = latest.net_worth - past.net_worth;
                        const pct = past.net_worth !== 0 ? (delta / Math.abs(past.net_worth)) * 100 : null;
                        const isPositive = delta >= 0;
                        return (
                          <div key={label} className="bg-[var(--surface-light)] rounded-lg px-2.5 py-1.5 text-center shrink-0 whitespace-nowrap" title={`${isPositive ? "+" : ""}${formatCurrency(delta)}`}>
                            <p className="text-[var(--text-muted)] text-[9px] leading-tight">{label}</p>
                            <p dir="ltr" className={`text-xs font-bold leading-tight ${isPositive ? "text-emerald-400" : "text-rose-400"}`}>
                              {isPositive ? "+" : ""}{formatCompactCurrency(delta)}
                            </p>
                            {pct !== null && (
                              <p className={`text-[9px] leading-tight ${isPositive ? "text-emerald-400" : "text-rose-400"}`}>
                                {isPositive ? "+" : ""}{pct.toFixed(1)}%
                              </p>
                            )}
                          </div>
                        );
                      });
                    })()}
                    <div className="w-full md:w-auto md:ms-auto flex bg-[var(--surface-light)] p-1 rounded-xl overflow-x-auto scrollbar-auto-hide">
                      {(
                        [
                          { key: "all", label: t("dashboard.all") },
                          { key: "bank_balance", label: t("dashboard.bankBalance") },
                          { key: "investments", label: t("dashboard.investmentValue") },
                          { key: "net_worth", label: t("dashboard.netWorth") },
                          { key: "debt_payments", label: t("dashboard.debtPayments") },
                        ] as const
                      ).map(({ key, label }) => (
                        <button
                          key={key}
                          onClick={() => setNetWorthView(key)}
                          className={`px-2 md:px-3 py-1.5 rounded-lg text-xs md:text-sm font-bold transition-all whitespace-nowrap ${
                            netWorthView === key
                              ? "bg-[var(--surface)] text-[var(--primary)] shadow-sm"
                              : "text-[var(--text-muted)] hover:text-[var(--text-default)]"
                          }`}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="flex-1 min-h-0">
                    {netWorthView === "debt_payments" ? (
                      debtPaymentsData && debtPaymentsData.length > 0 ? (() => {
                        const allTags = Array.from(
                          new Set(debtPaymentsData.flatMap((d) => Object.keys(d.tags))),
                        ).sort();
                        const colors = [
                          "#f43f5e", "#3b82f6", "#f59e0b", "#8b5cf6",
                          "#06b6d4", "#ec4899", "#10b981", "#f97316",
                        ];
                        return (
                          <Plot
                            data={allTags.map((tag, i) => ({
                              x: debtPaymentsData.map((d) => d.month),
                              y: debtPaymentsData.reduce((acc: number[], d) => {
                                acc.push((acc.length > 0 ? acc[acc.length - 1] : 0) + (d.tags[tag] || 0));
                                return acc;
                              }, []),
                              type: "scatter" as const,
                              mode: "lines+markers" as const,
                              line: { color: colors[i % colors.length], width: 2 },
                              marker: { size: 5, color: colors[i % colors.length] },
                              name: tag,
                              stackgroup: "debt",
                            }))}
                            layout={{
                              ...chartTheme,
                              autosize: true,
                              xaxis: { ...chartTheme.xaxis, type: "category" },
                              legend: {
                                orientation: "h",
                                y: -0.15,
                                x: 0.5,
                                xanchor: "center",
                              },
                            }}
                            style={{ width: "100%", height: "100%" }}
                            config={plotlyConfig()}
                          />
                        );
                      })() : (
                        <p className="text-[var(--text-muted)]">{t("dashboard.noData")}</p>
                      )
                    ) : (
                      <Plot
                        data={getNetWorthTraces()}
                        layout={{
                          ...chartTheme,
                          autosize: true,
                          xaxis: { ...chartTheme.xaxis, type: "date" },
                          yaxis: {
                            title: {
                              text: netWorthView === "all" ? t("dashboard.amountILS") : t("dashboard.monthlyChange"),
                              font: { color: "#94a3b8" },
                            },
                            tickfont: { color: "#94a3b8" },
                            automargin: true,
                          },
                          ...(netWorthView !== "all" && {
                            yaxis2: {
                              title: {
                                text: seriesConfig[netWorthView].label,
                                font: { color: seriesConfig[netWorthView].color },
                              },
                              tickfont: { color: seriesConfig[netWorthView].color },
                              overlaying: "y" as const,
                              side: "right" as const,
                              showgrid: false,
                              automargin: true,
                            },
                          }),
                          legend: {
                            orientation: "h",
                            y: -0.15,
                            x: 0.5,
                            xanchor: "center",
                          },
                        }}
                        style={{ width: "100%", height: "100%" }}
                        config={plotlyConfig()}
                      />
                    )}
                  </div>
                </>
              ) : (
                <p className="text-[var(--text-muted)] text-sm">📭 {t("dashboard.noNetWorthData")}</p>
              )}
            </div>
          )}

          {/* Cash Flow (Sankey) */}
          {insightTab === "cash_flow" && (
            <div className="flex flex-col flex-1 min-h-0">
              {sankeyLoading ? (
                <Skeleton variant="chart" className="flex-1" />
              ) : (
                <div className="flex-1 min-h-0">
                  <SankeyChart data={sankeyData} height={560} />
                </div>
              )}
            </div>
          )}

          {/* Income & Expenses */}
          {insightTab === "income_expenses" && (
            <div className="flex flex-col flex-1 min-h-0">
              {/* KPI Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2 md:gap-3 mb-3">
                {(() => {
                  const recent3 = incomeOutcome?.slice(-3) || [];
                  const recent6 = incomeOutcome?.slice(-6) || [];
                  const recent12 = incomeOutcome?.slice(-12) || [];
                  const avgIncome3 = recent3.length ? recent3.reduce((s, d) => s + d.income, 0) / recent3.length : 0;
                  const avgIncome6 = recent6.length ? recent6.reduce((s, d) => s + d.income, 0) / recent6.length : 0;
                  const avgIncome12 = recent12.length ? recent12.reduce((s, d) => s + d.income, 0) / recent12.length : 0;
                  return (
                    <>
                      <div className="bg-[var(--surface-light)] rounded-xl px-3 py-2 flex items-center gap-2">
                        <div className="p-1.5 rounded-lg bg-emerald-500/20 text-emerald-400"><Calculator size={14} /></div>
                        <div>
                          <p className="text-[var(--text-muted)] text-[10px]">{t("dashboard.avgIncome3Months")}</p>
                          <p className="text-sm font-bold">{formatCurrency(avgIncome3)}</p>
                        </div>
                      </div>
                      <div className="bg-[var(--surface-light)] rounded-xl px-3 py-2 flex items-center gap-2">
                        <div className="p-1.5 rounded-lg bg-emerald-500/20 text-emerald-400"><Calculator size={14} /></div>
                        <div>
                          <p className="text-[var(--text-muted)] text-[10px]">{t("dashboard.avgIncome6Months")}</p>
                          <p className="text-sm font-bold">{formatCurrency(avgIncome6)}</p>
                        </div>
                      </div>
                      <div className="bg-[var(--surface-light)] rounded-xl px-3 py-2 flex items-center gap-2">
                        <div className="p-1.5 rounded-lg bg-emerald-500/20 text-emerald-400"><Calculator size={14} /></div>
                        <div>
                          <p className="text-[var(--text-muted)] text-[10px]">{t("dashboard.avgIncome12Months")}</p>
                          <p className="text-sm font-bold">{formatCurrency(avgIncome12)}</p>
                        </div>
                      </div>
                      <div className="bg-[var(--surface-light)] rounded-xl px-3 py-2 flex items-center gap-2">
                        <div className="p-1.5 rounded-lg bg-rose-500/20 text-rose-400"><Calculator size={14} /></div>
                        <div>
                          <p className="text-[var(--text-muted)] text-[10px]">{t("dashboard.avgExpenses3Months")}</p>
                          <p className="text-sm font-bold">{formatCurrency(monthlyExpenses?.avg_3_months ?? 0)}</p>
                        </div>
                      </div>
                      <div className="bg-[var(--surface-light)] rounded-xl px-3 py-2 flex items-center gap-2">
                        <div className="p-1.5 rounded-lg bg-rose-500/20 text-rose-400"><Calculator size={14} /></div>
                        <div>
                          <p className="text-[var(--text-muted)] text-[10px]">{t("dashboard.avgExpenses6Months")}</p>
                          <p className="text-sm font-bold">{formatCurrency(monthlyExpenses?.avg_6_months ?? 0)}</p>
                        </div>
                      </div>
                      <div className="bg-[var(--surface-light)] rounded-xl px-3 py-2 flex items-center gap-2">
                        <div className="p-1.5 rounded-lg bg-rose-500/20 text-rose-400"><Calculator size={14} /></div>
                        <div>
                          <p className="text-[var(--text-muted)] text-[10px]">{t("dashboard.avgExpenses12Months")}</p>
                          <p className="text-sm font-bold">{formatCurrency(monthlyExpenses?.avg_12_months ?? 0)}</p>
                        </div>
                      </div>
                    </>
                  );
                })()}
              </div>

              {/* Sub-tabs + Filter Toggles */}
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-2 mb-3">
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => setExcludePendingRefunds(!excludePendingRefunds)}
                    className={`rounded-lg px-3 py-1.5 text-xs font-medium border transition-colors ${
                      excludePendingRefunds
                        ? "bg-[var(--primary)]/10 border-[var(--primary)]/20 text-[var(--primary)]"
                        : "bg-[var(--surface-light)] border-[var(--surface-light)] text-[var(--text-muted)]"
                    }`}
                  >
                    {excludePendingRefunds
                      ? t("dashboard.pendingRefundsExcluded")
                      : t("dashboard.pendingRefundsIncluded")}
                  </button>
                  <button
                    onClick={() => setExcludeRefunds(!excludeRefunds)}
                    className={`rounded-lg px-3 py-1.5 text-xs font-medium border transition-colors ${
                      excludeRefunds
                        ? "bg-cyan-500/10 border-cyan-500/20 text-cyan-400"
                        : "bg-[var(--surface-light)] border-[var(--surface-light)] text-[var(--text-muted)]"
                    }`}
                  >
                    {excludeRefunds
                      ? t("dashboard.refundsExcluded")
                      : t("dashboard.refundsIncluded")}
                  </button>
                  <button
                    onClick={() => setIncludeProjects(!includeProjects)}
                    className={`rounded-lg px-3 py-1.5 text-xs font-medium border transition-colors ${
                      includeProjects
                        ? "bg-indigo-500/10 border-indigo-500/20 text-indigo-400"
                        : "bg-[var(--surface-light)] border-[var(--surface-light)] text-[var(--text-muted)]"
                    }`}
                  >
                    {includeProjects
                      ? t("dashboard.projectExpensesIncluded")
                      : t("dashboard.projectExpensesExcluded")}
                  </button>
                </div>
                <div className="flex bg-[var(--surface-light)] p-1 rounded-xl overflow-x-auto scrollbar-auto-hide">
                  {([
                    { key: "overview" as const, label: `📊 ${t("dashboard.totals")}` },
                    { key: "by_source" as const, label: `💼 ${t("dashboard.incomeBreakdown")}` },
                    { key: "by_category" as const, label: `🍕 ${t("dashboard.expensesBreakdown")}` },
                  ]).map(({ key, label }) => (
                    <button
                      key={key}
                      onClick={() => setIncomeView(key)}
                      className={`px-2 md:px-3 py-1.5 rounded-lg text-xs md:text-sm font-bold transition-all whitespace-nowrap ${
                        incomeView === key
                          ? "bg-[var(--surface)] text-[var(--primary)] shadow-sm"
                          : "text-[var(--text-muted)] hover:text-[var(--text-default)]"
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
              {incomeView === "overview" && (
                <div className="flex-1 min-h-0 overflow-y-auto">
                  <Plot
                    data={[
                      {
                        y: incomeOutcome?.map((d: { month: string }) => d.month) || [],
                        x: incomeOutcome?.map((d: { income: number }) => d.income) || [],
                        name: t("dashboard.income"),
                        type: "bar",
                        orientation: "h",
                        marker: { color: "#059669" },
                      },
                      {
                        y: incomeOutcome?.map((d: { month: string }) => d.month) || [],
                        x: incomeOutcome?.map((d: { expenses: number }) => Math.abs(d.expenses)) || [],
                        name: t("dashboard.expenses"),
                        type: "bar",
                        orientation: "h",
                        marker: {
                          color: incomeOutcome?.map((d: { expenses: number }) =>
                            d.expenses >= 0 ? "#f43f5e" : "#fda4af"
                          ) || "#f43f5e",
                        },
                      },
                    ]}
                    layout={{
                      ...chartTheme,
                      barmode: "group",
                      autosize: true,
                      height: Math.max(400, (incomeOutcome?.length ?? 0) * 25),
                      legend: {
                        orientation: "h",
                        y: -0.15,
                        x: 0.5,
                        xanchor: "center",
                      },
                      yaxis: { automargin: true, type: "category", dtick: 1, ticksuffix: "  " },
                      margin: { ...chartTheme.margin, l: 80, r: 20 },
                    }}
                    style={{ width: "100%", height: "100%" }}
                    config={plotlyConfig()}
                  />
                </div>
              )}
              {incomeView === "by_source" && (
                <div className="flex-1 min-h-0 overflow-y-auto">
                  {incomeBySourceData && incomeBySourceData.length > 0 ? (() => {
                    const allSources = Array.from(
                      new Set(
                        incomeBySourceData.flatMap((d) => Object.keys(d.sources)),
                      ),
                    );
                    const colors = [
                      "#10b981", "#3b82f6", "#f59e0b", "#8b5cf6",
                      "#06b6d4", "#ec4899", "#14b8a6", "#f97316",
                    ];
                    const maxStack = Math.max(...incomeBySourceData.map((d) => Object.values(d.sources).reduce((s, v) => s + v, 0)));
                    return (
                      <Plot
                        data={allSources.map((source, i) => ({
                          y: incomeBySourceData.map((d) => d.month),
                          x: incomeBySourceData.map(
                            (d) => d.sources[source] || 0,
                          ),
                          name: source,
                          type: "bar" as const,
                          orientation: "h" as const,
                          marker: { color: colors[i % colors.length], line: { width: 0 } },
                          hovertemplate: "%{data.name}: %{x:,.0f}<extra></extra>",
                        }))}
                        layout={{
                          ...chartTheme,
                          barmode: "stack",
                          autosize: true,
                          height: Math.max(400, incomeBySourceData.length * 25),
                          hovermode: isTouchDevice ? "closest" : "y unified",
                          xaxis: {
                            range: [0, maxStack * 1.05],
                            fixedrange: true,
                            showspikes: false,
                          },
                          yaxis: { automargin: true, type: "category", dtick: 1, ticksuffix: "  ", showspikes: false },
                          legend: {
                            orientation: "h",
                            y: -0.15,
                            x: 0.5,
                            xanchor: "center",
                          },
                          margin: { ...chartTheme.margin, l: 80, r: 20 },
                        }}
                        style={{ width: "100%", height: "100%" }}
                        config={plotlyConfig()}
                      />
                    );
                  })() : (
                    <p className="text-[var(--text-muted)] text-sm">📭 {t("dashboard.noIncomeSourceData")}</p>
                  )}
                </div>
              )}
              {incomeView === "by_category" && (
                <div className="flex-1 min-h-0 overflow-y-auto">
                  {expensesByCategoryOverTime && expensesByCategoryOverTime.length > 0 ? (() => {
                    const allCategories = Array.from(
                      new Set(
                        expensesByCategoryOverTime.flatMap((d) => Object.keys(d.categories)),
                      ),
                    ).sort();
                    const colors = [
                      "#f43f5e", "#ef4444", "#f97316", "#f59e0b",
                      "#eab308", "#84cc16", "#22c55e", "#14b8a6",
                      "#06b6d4", "#3b82f6", "#6366f1", "#8b5cf6",
                      "#a855f7", "#d946ef", "#ec4899", "#fb7185",
                    ];
                    const maxStackTotal = Math.max(
                      ...expensesByCategoryOverTime.map((d) =>
                        Object.values(d.categories).reduce((s, v) => s + v, 0),
                      ),
                    );
                    return (
                      <Plot
                        data={allCategories.map((cat, i) => ({
                          y: expensesByCategoryOverTime.map((d) => d.month),
                          x: expensesByCategoryOverTime.map((d) => d.categories[cat] || 0),
                          name: cat,
                          type: "bar" as const,
                          orientation: "h" as const,
                          marker: { color: colors[i % colors.length], line: { width: 0 } },
                          hovertemplate: "%{data.name}: %{x:,.0f}<extra></extra>",
                        }))}
                        layout={{
                          ...chartTheme,
                          barmode: "stack",
                          autosize: true,
                          height: Math.max(400, expensesByCategoryOverTime.length * 25),
                          hovermode: isTouchDevice ? "closest" : "y unified",
                          xaxis: { range: [0, maxStackTotal * 1.05], fixedrange: true, showspikes: false },
                          yaxis: { automargin: true, type: "category", dtick: 1, ticksuffix: "  ", showspikes: false },
                          legend: {
                            orientation: "h",
                            y: -0.15,
                            x: 0.5,
                            xanchor: "center",
                          },
                          margin: { ...chartTheme.margin, l: 80, r: 20 },
                        }}
                        style={{ width: "100%", height: "100%" }}
                        config={plotlyConfig()}
                      />
                    );
                  })() : (
                    <p className="text-[var(--text-muted)]">{t("dashboard.noData")}</p>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Category Breakdown */}
          {insightTab === "category" && (() => {
            const expenses = categoryData?.expenses
              ?.slice()
              .sort((a: { amount: number }, b: { amount: number }) => b.amount - a.amount) || [];
            const refunds = categoryData?.refunds
              ?.slice()
              .sort((a: { amount: number }, b: { amount: number }) => b.amount - a.amount) || [];
            const totalExpenses = expenses.reduce((s: number, d: { amount: number }) => s + d.amount, 0);
            const totalRefunds = refunds.reduce((s: number, d: { amount: number }) => s + d.amount, 0);
            const topCategory = expenses[0];
            const maxExpense = topCategory?.amount || 1;
            const maxRefund = refunds[0]?.amount || 1;

            return (
              <div className="flex flex-col flex-1 min-h-0 space-y-5">
                {/* Summary strip */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 md:gap-4">
                  <div className="bg-[var(--surface-light)] rounded-xl px-3 md:px-4 py-2.5 md:py-3 flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-rose-500/20 text-rose-400">
                      <TrendingDown size={18} />
                    </div>
                    <div>
                      <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">{t("dashboard.totalExpenses")}</p>
                      <p className="text-lg font-bold text-rose-400">{formatCurrency(totalExpenses)}</p>
                    </div>
                  </div>
                  <div className="bg-[var(--surface-light)] rounded-xl px-3 md:px-4 py-2.5 md:py-3 flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-amber-500/20 text-amber-400 text-lg">
                      {topCategory ? (categoryIcons?.[topCategory.category] || "📊") : "—"}
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">{t("dashboard.topCategory")}</p>
                      <p className="text-sm font-bold truncate">{topCategory?.category || "—"}</p>
                    </div>
                  </div>
                  <div className="bg-[var(--surface-light)] rounded-xl px-3 md:px-4 py-2.5 md:py-3 flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-blue-500/20 text-blue-400">
                      <Tag size={18} />
                    </div>
                    <div>
                      <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">{t("dashboard.categories")}</p>
                      <p className="text-lg font-bold">{expenses.length}</p>
                    </div>
                  </div>
                </div>

                {/* Expenses bars */}
                <div>
                  <p className="text-sm font-bold text-rose-400 uppercase tracking-wider mb-3">{t("dashboard.expenses")}</p>
                  <div className="space-y-1.5 max-h-[350px] overflow-y-auto pr-1">
                    {expenses.map((d: { category: string; amount: number }, i: number) => {
                      const pct = totalExpenses > 0 ? (d.amount / totalExpenses) * 100 : 0;
                      const barWidth = (d.amount / maxExpense) * 100;
                      const icon = categoryIcons?.[d.category] ?? "";
                      return (
                        <div key={d.category} className="group flex items-center gap-2 py-1.5 px-2 rounded-lg hover:bg-[var(--surface-light)] transition-colors">
                          <span className="text-base w-6 text-center shrink-0">{icon || (d.category === "Uncategorized" ? "❓" : `${i + 1}.`)}</span>
                          <span className="text-xs md:text-sm font-medium w-20 md:w-28 truncate shrink-0" title={d.category}>{d.category}</span>
                          <div className="flex-1 h-5 bg-[var(--surface-light)] rounded-full overflow-hidden">
                            <div
                              className="h-full rounded-full bg-gradient-to-r from-rose-600 to-rose-400 transition-all duration-500"
                              style={{ width: `${barWidth}%` }}
                            />
                          </div>
                          <span className="text-xs md:text-sm font-bold tabular-nums w-16 md:w-24 text-end shrink-0">{formatCurrency(d.amount)}</span>
                          <span className="text-[10px] md:text-xs text-[var(--text-muted)] w-10 md:w-12 text-end shrink-0">{pct.toFixed(1)}%</span>
                        </div>
                      );
                    })}
                    {expenses.length === 0 && (
                      <p className="text-[var(--text-muted)] text-sm py-4 text-center">{t("dashboard.noExpenseData")}</p>
                    )}
                  </div>
                </div>

                {/* Refunds bars (conditional) */}
                {refunds.length > 0 && (
                  <div>
                    <p className="text-sm font-bold text-emerald-400 uppercase tracking-wider mb-3">{t("dashboard.refunds")}</p>
                    <div className="space-y-1.5 max-h-[200px] overflow-y-auto pr-1">
                      {refunds.map((d: { category: string; amount: number }, i: number) => {
                        const pct = totalRefunds > 0 ? (d.amount / totalRefunds) * 100 : 0;
                        const barWidth = (d.amount / maxRefund) * 100;
                        const icon = categoryIcons?.[d.category] ?? "";
                        return (
                          <div key={d.category} className="group flex items-center gap-2 py-1.5 px-2 rounded-lg hover:bg-[var(--surface-light)] transition-colors">
                            <span className="text-base w-6 text-center shrink-0">{icon || `${i + 1}.`}</span>
                            <span className="text-xs md:text-sm font-medium w-20 md:w-28 truncate shrink-0" title={d.category}>{d.category}</span>
                            <div className="flex-1 h-5 bg-[var(--surface-light)] rounded-full overflow-hidden">
                              <div
                                className="h-full rounded-full bg-gradient-to-r from-emerald-600 to-emerald-400 transition-all duration-500"
                                style={{ width: `${barWidth}%` }}
                              />
                            </div>
                            <span className="text-xs md:text-sm font-bold tabular-nums w-16 md:w-24 text-end shrink-0">{formatCurrency(d.amount)}</span>
                            <span className="text-[10px] md:text-xs text-[var(--text-muted)] w-10 md:w-12 text-end shrink-0">{pct.toFixed(1)}%</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            );
          })()}
        </div>
      </div>

    </div>
  );
}
