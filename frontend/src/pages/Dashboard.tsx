import { useState, useMemo, useRef, useCallback, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  TrendingUp,
  TrendingDown,
  ChevronDown,
  Calculator,
  Split,
  RefreshCw,
  Tag,
  Wand2,
  Link2,
} from "lucide-react";
import Plot from "react-plotly.js";
import {
  analyticsApi,
  bankBalancesApi,
  cashBalancesApi,
  investmentsApi,
  budgetApi,
  transactionsApi,
  taggingApi,
  pendingRefundsApi,
  type TaggingRule,
  type ConditionNode,
} from "../services/api";
import { SplitTransactionModal } from "../components/modals/SplitTransactionModal";
import { LinkRefundModal } from "../components/modals/LinkRefundModal";
import { SelectDropdown } from "../components/common/SelectDropdown";
import { useCategoryTagCreate } from "../hooks/useCategoryTagCreate";
import { SankeyChart } from "../components/SankeyChart";
import { Sparkline } from "../components/common/Sparkline";
import { SemiGauge } from "../components/common/SemiGauge";
import { Skeleton } from "../components/common/Skeleton";
import { useDemoMode } from "../context/DemoModeContext";
import { isToday, isYesterday, format } from "date-fns";

type NetWorthView = "all" | "bank_balance" | "investments" | "net_worth";

const formatCurrency = (val: number) =>
  new Intl.NumberFormat("he-IL", {
    style: "currency",
    currency: "ILS",
    maximumFractionDigits: 0,
  }).format(val || 0);

const chartTheme = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  font: { color: "#94a3b8", family: "Inter, sans-serif" },
  margin: { t: 40, b: 40, l: 40, r: 20 },
};

/* ------------------------------------------------------------------ */
/*  Section 1 — Financial Health Header                               */
/* ------------------------------------------------------------------ */

function FinancialHealthHeader({
  netWorthData,
  bankBalances,
  cashBalances,
  portfolioAnalysis,
  isLoading,
}: {
  netWorthData:
    | { month: string; bank_balance: number; investment_value: number; net_worth: number }[]
    | undefined;
  bankBalances: { provider: string; account_name: string; balance: number }[] | undefined;
  cashBalances: { account_name: string; balance: number }[] | undefined;
  portfolioAnalysis: { total_value: number; allocation: { name: string; balance: number }[] } | undefined;
  isLoading: boolean;
}) {
  const [expanded, setExpanded] = useState(false);

  const latestNetWorth = netWorthData?.length ? netWorthData[netWorthData.length - 1] : null;
  const previousNetWorth =
    netWorthData && netWorthData.length >= 2 ? netWorthData[netWorthData.length - 2] : null;

  const momDelta = latestNetWorth && previousNetWorth ? latestNetWorth.net_worth - previousNetWorth.net_worth : null;
  const momPercent =
    momDelta !== null && previousNetWorth && previousNetWorth.net_worth !== 0
      ? (momDelta / Math.abs(previousNetWorth.net_worth)) * 100
      : null;

  const last6Bank = netWorthData?.slice(-6).map((d) => d.bank_balance) ?? [];
  const last6Investments = netWorthData?.slice(-6).map((d) => d.investment_value) ?? [];

  const toggleExpanded = () => setExpanded((prev) => !prev);

  if (isLoading) {
    return (
      <div className="bg-[var(--surface)] rounded-2xl p-6 border border-[var(--surface-light)]">
        <Skeleton variant="text" lines={2} className="mb-4" />
        <div className="grid grid-cols-3 gap-4">
          <Skeleton variant="card" className="h-20" />
          <Skeleton variant="card" className="h-20" />
          <Skeleton variant="card" className="h-20" />
        </div>
      </div>
    );
  }

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] overflow-hidden">
      {/* Hero row */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 px-6 pt-6 pb-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
            💰 Net Worth
          </p>
          <p className="text-3xl font-bold mt-0.5">
            {latestNetWorth ? formatCurrency(latestNetWorth.net_worth) : "--"}
          </p>
        </div>
        {momDelta !== null && (
          <div
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold ${
              momDelta >= 0
                ? "bg-emerald-500/10 text-emerald-400"
                : "bg-rose-500/10 text-rose-400"
            }`}
          >
            {momDelta >= 0 ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
            <span dir="ltr">
              {`${momDelta >= 0 ? "+" : "-"}${new Intl.NumberFormat("en", { maximumFractionDigits: 0 }).format(Math.abs(momDelta))} \u20AA${momPercent !== null ? ` (${momPercent >= 0 ? "+" : ""}${momPercent.toFixed(1)}%)` : ""}`}
            </span>
          </div>
        )}
      </div>

      {/* Sub-cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-[var(--surface-light)] border-t border-[var(--surface-light)]">
        {/* Bank Balance */}
        <button
          onClick={toggleExpanded}
          className="text-left px-5 py-4 hover:bg-[var(--surface-light)]/40 transition-colors"
        >
          <div className="flex items-center justify-between">
            <div className="min-w-0">
              <p className="text-xs text-[var(--text-muted)]">🏦 Bank Balance</p>
              <p className="text-lg font-bold mt-0.5">
                {latestNetWorth ? formatCurrency(latestNetWorth.bank_balance) : "--"}
              </p>
            </div>
            {last6Bank.length >= 2 && <Sparkline data={last6Bank} color="#f59e0b" />}
          </div>
          {expanded && bankBalances && bankBalances.length > 0 && (
            <div className="mt-3 pt-3 border-t border-[var(--surface-light)] space-y-1.5">
              {bankBalances.map((b) => (
                <div
                  key={`${b.provider}-${b.account_name}`}
                  className="flex items-center justify-between text-sm"
                >
                  <span className="text-[var(--text-muted)]">{b.account_name}</span>
                  <span className="font-medium">{formatCurrency(b.balance)}</span>
                </div>
              ))}
            </div>
          )}
        </button>

        {/* Investments */}
        <button
          onClick={toggleExpanded}
          className="text-left px-5 py-4 hover:bg-[var(--surface-light)]/40 transition-colors"
        >
          <div className="flex items-center justify-between">
            <div className="min-w-0">
              <p className="text-xs text-[var(--text-muted)]">📈 Investments</p>
              <p className="text-lg font-bold mt-0.5">
                {latestNetWorth ? formatCurrency(latestNetWorth.investment_value) : "--"}
              </p>
            </div>
            {last6Investments.length >= 2 && <Sparkline data={last6Investments} color="#6366f1" />}
          </div>
          {expanded &&
            portfolioAnalysis?.allocation &&
            portfolioAnalysis.allocation.length > 0 && (
              <div className="mt-3 pt-3 border-t border-[var(--surface-light)] space-y-1.5">
                {portfolioAnalysis.allocation.map((inv) => (
                  <div key={inv.name} className="flex items-center justify-between text-sm">
                    <span className="text-[var(--text-muted)]">{inv.name}</span>
                    <span className="font-medium">{formatCurrency(inv.balance)}</span>
                  </div>
                ))}
              </div>
            )}
        </button>

        {/* Cash */}
        {(() => {
          const totalCash = cashBalances?.reduce((sum, c) => sum + c.balance, 0) ?? 0;
          const hasCash = cashBalances && cashBalances.length > 0;
          return hasCash ? (
            <button
              onClick={toggleExpanded}
              className="text-left px-5 py-4 hover:bg-[var(--surface-light)]/40 transition-colors"
            >
              <div className="flex items-center justify-between">
                <div className="min-w-0">
                  <p className="text-xs text-[var(--text-muted)]">💵 Cash</p>
                  <p className="text-lg font-bold mt-0.5">{formatCurrency(totalCash)}</p>
                </div>
              </div>
              {expanded && cashBalances.length > 0 && (
                <div className="mt-3 pt-3 border-t border-[var(--surface-light)] space-y-1.5">
                  {cashBalances.map((c) => (
                    <div key={c.account_name} className="flex items-center justify-between text-sm">
                      <span className="text-[var(--text-muted)]">{c.account_name}</span>
                      <span className="font-medium">{formatCurrency(c.balance)}</span>
                    </div>
                  ))}
                </div>
              )}
            </button>
          ) : (
            <div className="px-5 py-4">
              <p className="text-xs text-[var(--text-muted)]">💵 Cash</p>
              <p className="text-lg font-bold mt-0.5">{formatCurrency(0)}</p>
              <p className="text-xs text-[var(--text-muted)] mt-1">📭 (no data)</p>
            </div>
          );
        })()}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Section 2 — Monthly Spending Gauge                                */
/* ------------------------------------------------------------------ */

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

function MonthlySpendingGauge({
  budgetAnalysis,
  categoryIcons,
  isLoading,
}: {
  budgetAnalysis: { rules: BudgetRule[]; total_budget?: number; total_spent?: number } | undefined;
  categoryIcons: Record<string, string> | undefined;
  isLoading: boolean;
}) {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth() + 1;
  const monthName = format(now, "MMMM yyyy");
  const daysInMonth = new Date(year, month, 0).getDate();
  const daysRemaining = daysInMonth - now.getDate();

  const totalBudget =
    budgetAnalysis?.total_budget ??
    (budgetAnalysis?.rules?.reduce((sum, r) => sum + r.budget_amount, 0) ?? 0);
  const totalSpent =
    budgetAnalysis?.total_spent ??
    (budgetAnalysis?.rules?.reduce((sum, r) => sum + r.spent_amount, 0) ?? 0);

  // Filter out "Total Budget" special rule, sort by spent descending
  const miniRules = useMemo(() => {
    if (!budgetAnalysis?.rules) return [];
    return budgetAnalysis.rules
      .filter((r) => r.name !== "Total Budget")
      .sort((a, b) => b.spent_amount - a.spent_amount);
  }, [budgetAnalysis]);

  if (isLoading) {
    return (
      <div className="bg-[var(--surface)] rounded-2xl p-6 border border-[var(--surface-light)]">
        <Skeleton variant="text" lines={1} className="mb-4" />
        <Skeleton variant="chart" className="h-40" />
      </div>
    );
  }

  if (!budgetAnalysis || budgetAnalysis.rules.length === 0) return null;

  return (
    <div className="bg-[var(--surface)] rounded-2xl p-6 border border-[var(--surface-light)]">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
            🎯 This Month &mdash; {monthName}
          </p>
        </div>
        <span className="text-xs text-[var(--text-muted)]">
          ⏳ {daysRemaining} day{daysRemaining !== 1 ? "s" : ""} remaining
        </span>
      </div>

      {/* Gauge */}
      <div className="flex justify-center mb-6">
        <SemiGauge spent={totalSpent} budget={totalBudget} size={240} />
      </div>

      {/* Budget rule cards */}
      {miniRules.length > 0 && (
        <div className="grid grid-cols-2 gap-3 mb-4 max-h-[340px] overflow-y-auto scrollbar-auto-hide">
          {miniRules.map((rule) => {
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
                {/* Progress bar */}
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
                    ? `${formatCurrency(remaining)} left`
                    : `${formatCurrency(Math.abs(remaining))} over budget`}
                </p>
              </div>
            );
          })}
        </div>
      )}

      {/* Link to budget page */}
      <div className="text-right">
        <Link
          to="/budget"
          className="text-sm font-medium text-[var(--primary)] hover:underline"
        >
          📋 View All Budget Rules &rarr;
        </Link>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Section 3 — Recent Transactions Feed                              */
/* ------------------------------------------------------------------ */

interface Transaction {
  id?: any;
  unique_id?: any;
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
  if (isToday(d)) return "Today";
  if (isYesterday(d)) return "Yesterday";
  return format(d, "d MMM");
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

  const fieldMap: Record<string, any> = {
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
      queryClient.invalidateQueries({ queryKey: ["budgetAnalysis"] });
      setEditingTxKey(null);
    },
  });

  // Mark as pending refund
  const markPendingMutation = useMutation({
    mutationFn: (tx: Transaction) =>
      pendingRefundsApi.create({
        source_type: "transaction",
        source_id: tx.unique_id,
        source_table: tx.source,
        expected_amount: Math.abs(tx.amount),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["budgetAnalysis"] });
      queryClient.invalidateQueries({ queryKey: ["pendingRefunds"] });
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
    <div className="bg-[var(--surface)] rounded-2xl p-6 border border-[var(--surface-light)]">
      <div className="flex items-center justify-between mb-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
          🧾 Recent Transactions
        </p>
        <Link
          to="/transactions"
          className="text-sm font-medium text-[var(--primary)] hover:underline"
        >
          👀 View All &rarr;
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
                            title={`Matched rule: ${matchedRule.name}`}
                          >
                            <Wand2 size={9} />
                            {matchedRule.name}
                          </span>
                        )}
                      </div>
                      {/* Action buttons — fixed grid, each cell is 25px */}
                      <div className="grid grid-cols-3 flex-shrink-0 w-[75px]">
                        <button
                          className={`w-[25px] h-[25px] flex items-center justify-center rounded-md transition-colors ${isEditing ? "bg-[var(--primary)]/20 text-[var(--primary)]" : "text-[var(--text-muted)]/40 hover:text-white hover:bg-[var(--surface-light)]"}`}
                          title="Edit category / tag"
                          onClick={() => setEditingTxKey(isEditing ? null : txKey)}
                        >
                          <Tag size={13} />
                        </button>
                        <button
                          className="w-[25px] h-[25px] flex items-center justify-center rounded-md text-[var(--text-muted)]/40 hover:text-white hover:bg-[var(--surface-light)] transition-colors"
                          title="Split transaction"
                          onClick={() => setSplittingTransaction(tx)}
                        >
                          <Split size={13} />
                        </button>
                        {tx.amount < 0 ? (
                          tx.pending_refund_id ? (
                            <span className="w-[25px] h-[25px] flex items-center justify-center text-amber-400" title="Pending refund">
                              <RefreshCw size={13} className="animate-pulse" />
                            </span>
                          ) : (
                            <button
                              className="w-[25px] h-[25px] flex items-center justify-center rounded-md text-amber-400/40 hover:text-amber-400 hover:bg-amber-500/20 transition-colors"
                              title="Mark as pending refund"
                              onClick={() => markPendingMutation.mutate(tx)}
                              disabled={markPendingMutation.isPending}
                            >
                              <RefreshCw size={13} />
                            </button>
                          )
                        ) : (
                          <button
                            className="w-[25px] h-[25px] flex items-center justify-center rounded-md text-emerald-400/40 hover:text-emerald-400 hover:bg-emerald-500/20 transition-colors"
                            title="Link as refund to pending"
                            onClick={() => setLinkingTransaction(tx)}
                          >
                            <Link2 size={13} />
                          </button>
                        )}
                      </div>
                      <span
                        className={`text-sm font-semibold flex-shrink-0 tabular-nums text-right w-[80px] ${
                          isPositive ? "text-emerald-400" : "text-rose-400"
                        }`}
                      >
                        {isPositive ? "+" : ""}
                        {formatCurrency(tx.amount)}
                      </span>
                    </div>

                    {/* Inline tag editing panel */}
                    {isEditing && categories && (
                      <div className="mx-2 mb-2 ml-11 rounded-lg border border-[var(--surface-light)] bg-[var(--surface-light)]/20 overflow-hidden">
                        <div className="flex items-center gap-3 px-3 py-2">
                          <div className="flex-1 min-w-0">
                            <label className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] mb-1 block">Category</label>
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
                            <label className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] mb-1 block">Tag</label>
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
                            Done
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
              Loading more...
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
            queryClient.invalidateQueries({ queryKey: ["budgetAnalysis"] });
          }}
        />
      )}

      {/* Link Refund Modal (for positive/income transactions) */}
      {linkingTransaction && (
        <LinkRefundModal
          isOpen={!!linkingTransaction}
          onClose={() => setLinkingTransaction(null)}
          refundTransaction={{
            id: linkingTransaction.unique_id,
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
/*  Section 4 — Collapsible Insights (accordion wrapper)              */
/* ------------------------------------------------------------------ */

function AccordionSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] overflow-hidden">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-6 py-4 hover:bg-[var(--surface-light)]/40 transition-colors"
      >
        <h3 className="text-lg font-bold">{title}</h3>
        <ChevronDown
          size={20}
          className={`text-[var(--text-muted)] transition-transform duration-200 ${
            isOpen ? "rotate-180" : ""
          }`}
        />
      </button>
      {isOpen && <div className="px-6 pb-6">{children}</div>}
    </div>
  );
}

/* ================================================================== */
/*  Main Dashboard Component                                          */
/* ================================================================== */

export function Dashboard() {
  const { isDemoMode } = useDemoMode();
  const [netWorthView, setNetWorthView] = useState<NetWorthView>("all");
  const [incomeView, setIncomeView] = useState<"overview" | "by_source">("overview");
  const [excludePendingRefunds, setExcludePendingRefunds] = useState(true);

  // ---- Existing queries (kept) ----

  const { data: incomeOutcome } = useQuery({
    queryKey: ["income-outcome", isDemoMode],
    queryFn: async () => {
      const res = await analyticsApi.getIncomeExpensesOverTime();
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

  const { data: bankBalances } = useQuery({
    queryKey: ["bank-balances", isDemoMode],
    queryFn: () => bankBalancesApi.getAll().then((res) => res.data),
  });

  const { data: cashBalances } = useQuery({
    queryKey: ["cash-balances", isDemoMode],
    queryFn: () => cashBalancesApi.getAll().then((res) => res.data),
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

  const { data: portfolioAnalysis } = useQuery({
    queryKey: ["portfolio-analysis", isDemoMode],
    queryFn: () => investmentsApi.getPortfolioAnalysis().then((res) => res.data),
  });

  const { data: monthlyExpenses } = useQuery({
    queryKey: ["monthly-expenses", excludePendingRefunds, isDemoMode],
    queryFn: async () => {
      const res = await analyticsApi.getMonthlyExpenses(excludePendingRefunds);
      return res.data;
    },
  });

  // ---- New queries ----

  const now = new Date();
  const currentYear = now.getFullYear();
  const currentMonth = now.getMonth() + 1;

  const { data: rawBudgetAnalysis, isLoading: budgetLoading } = useQuery({
    queryKey: ["budget-analysis", currentYear, currentMonth, isDemoMode],
    queryFn: async () => {
      const res = await budgetApi.getAnalysis(currentYear, currentMonth, false);
      return res.data;
    },
  });

  // Transform nested API response into flat BudgetRule objects
  const budgetAnalysis = useMemo(() => {
    if (!rawBudgetAnalysis?.rules) return undefined;
    const rules: BudgetRule[] = rawBudgetAnalysis.rules.map((item: any) => ({
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
      label: "Bank Balance",
      color: "#f59e0b",
      dataKey: "bank_balance",
      deltaKey: "bank_balance_delta",
    },
    investments: {
      label: "Investments",
      color: "#6366f1",
      dataKey: "investment_value",
      deltaKey: "investment_value_delta",
    },
    net_worth: {
      label: "Net Worth",
      color: "#10b981",
      dataKey: "net_worth",
      deltaKey: "net_worth_delta",
    },
  } as const;

  const getNetWorthTraces = (): Plotly.Data[] => {
    if (!netWorthData || netWorthData.length === 0) return [];

    if (netWorthView === "all") {
      return [
        {
          x: netWorthData.map((d) => d.month),
          y: netWorthData.map((d) => d.bank_balance),
          name: "Bank Balance",
          type: "scatter",
          mode: "lines+markers",
          line: { color: "#f59e0b", width: 2 },
          marker: { size: 4, color: "#f59e0b" },
        },
        {
          x: netWorthData.map((d) => d.month),
          y: netWorthData.map((d) => d.investment_value),
          name: "Investments",
          type: "scatter",
          mode: "lines+markers",
          line: { color: "#6366f1", width: 2 },
          marker: { size: 4, color: "#6366f1" },
        },
        {
          x: netWorthData.map((d) => d.month),
          y: netWorthData.map((d) => d.net_worth),
          name: "Net Worth",
          type: "scatter",
          mode: "lines+markers",
          line: { color: "#10b981", width: 3 },
          marker: { size: 5, color: "#10b981" },
        },
      ];
    }

    if (!netWorthDeltas) return [];
    const config = seriesConfig[netWorthView];

    return [
      {
        x: netWorthDeltas.map((d) => d.month),
        y: netWorthDeltas.map((d) => d[config.deltaKey]),
        name: "Monthly Change",
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
      },
    ];
  };

  // ================================================================
  //  Render
  // ================================================================

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div>
        <h1 className="text-3xl font-bold">📊 Dashboard</h1>
        <p className="text-[var(--text-muted)] mt-1">✨ Your financial snapshot at a glance</p>
      </div>

      {/* Section 1: Financial Health Header */}
      <FinancialHealthHeader
        netWorthData={netWorthData}
        bankBalances={bankBalances}
        cashBalances={cashBalances}
        portfolioAnalysis={portfolioAnalysis}
        isLoading={netWorthLoading}
      />

      {/* Section 2 & 3: Spending Gauge + Recent Transactions — side by side on large screens */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <MonthlySpendingGauge
          budgetAnalysis={budgetAnalysis}
          categoryIcons={categoryIcons}
          isLoading={budgetLoading}
        />
        <RecentTransactionsFeed
          transactions={allTransactions}
          categoryIcons={categoryIcons}
          isLoading={transactionsLoading}
        />
      </div>

      {/* Section 4: Collapsible Insights */}
      <div>
        <h2 className="text-xl font-bold mb-4 text-[var(--text-muted)]">🔍 More Insights</h2>
        <div className="space-y-4">
          {/* Monthly Expenses */}
          <AccordionSection title="💸 Monthly Expenses">
            {monthlyExpenses && monthlyExpenses.months.length > 0 ? (
              <>
                <div className="flex items-center justify-end mb-4">
                  <button
                    onClick={() => setExcludePendingRefunds(!excludePendingRefunds)}
                    className={`px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors ${
                      excludePendingRefunds
                        ? "bg-[var(--primary)]/10 border-[var(--primary)]/20 text-[var(--primary)]"
                        : "bg-[var(--surface-light)] border-[var(--surface-light)] text-[var(--text-muted)]"
                    }`}
                  >
                    {excludePendingRefunds
                      ? "🚫 Pending Refunds Excluded"
                      : "✅ Pending Refunds Included"}
                  </button>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                  <div className="bg-[var(--surface-light)] rounded-xl px-4 py-3 flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-rose-500/20 text-rose-400">
                      <Calculator size={18} />
                    </div>
                    <div>
                      <p className="text-[var(--text-muted)] text-xs">🔥 Avg 3 Months</p>
                      <p className="text-lg font-bold">
                        {formatCurrency(monthlyExpenses.avg_3_months)}
                      </p>
                    </div>
                  </div>
                  <div className="bg-[var(--surface-light)] rounded-xl px-4 py-3 flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-orange-500/20 text-orange-400">
                      <Calculator size={18} />
                    </div>
                    <div>
                      <p className="text-[var(--text-muted)] text-xs">📊 Avg 6 Months</p>
                      <p className="text-lg font-bold">
                        {formatCurrency(monthlyExpenses.avg_6_months)}
                      </p>
                    </div>
                  </div>
                  <div className="bg-[var(--surface-light)] rounded-xl px-4 py-3 flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-amber-500/20 text-amber-400">
                      <Calculator size={18} />
                    </div>
                    <div>
                      <p className="text-[var(--text-muted)] text-xs">📅 Avg 12 Months</p>
                      <p className="text-lg font-bold">
                        {formatCurrency(monthlyExpenses.avg_12_months)}
                      </p>
                    </div>
                  </div>
                </div>
                <div className="h-[350px]">
                  <Plot
                    data={[
                      {
                        x: monthlyExpenses.months.map((d) => d.month),
                        y: monthlyExpenses.months.map((d) => d.expenses),
                        type: "bar",
                        marker: { color: "#f43f5e" },
                        name: "Expenses",
                      },
                    ]}
                    layout={{
                      ...chartTheme,
                      autosize: true,
                      height: 350,
                      yaxis: {
                        title: {
                          text: "Amount (ILS)",
                          font: { color: "#94a3b8" },
                        },
                        tickfont: { color: "#94a3b8" },
                      },
                    }}
                    style={{ width: "100%", height: "100%" }}
                    config={{ displayModeBar: false, responsive: true }}
                  />
                </div>
              </>
            ) : (
              <p className="text-[var(--text-muted)] text-sm">📭 No expense data available.</p>
            )}
          </AccordionSection>

          {/* Net Worth Over Time */}
          <AccordionSection title="📈 Net Worth Over Time">
            {netWorthData && netWorthData.length > 0 ? (
              <>
                <div className="flex justify-end mb-4">
                  <div className="flex bg-[var(--surface-light)] p-1 rounded-xl">
                    {(
                      [
                        { key: "all", label: "All" },
                        { key: "bank_balance", label: "Bank Balance" },
                        { key: "investments", label: "Investments" },
                        { key: "net_worth", label: "Net Worth" },
                      ] as const
                    ).map(({ key, label }) => (
                      <button
                        key={key}
                        onClick={() => setNetWorthView(key)}
                        className={`px-3 py-1.5 rounded-lg text-sm font-bold transition-all ${
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
                <div className="h-[350px]">
                  <Plot
                    data={getNetWorthTraces()}
                    layout={{
                      ...chartTheme,
                      autosize: true,
                      height: 350,
                      yaxis: {
                        title: {
                          text: "Amount (ILS)",
                          font: { color: "#94a3b8" },
                        },
                        tickfont: { color: "#94a3b8" },
                      },
                      legend: {
                        orientation: "h",
                        y: -0.15,
                        x: 0.5,
                        xanchor: "center",
                      },
                    }}
                    style={{ width: "100%", height: "100%" }}
                    config={{ displayModeBar: false, responsive: true }}
                  />
                </div>
              </>
            ) : (
              <p className="text-[var(--text-muted)] text-sm">📭 No net worth data available.</p>
            )}
          </AccordionSection>

          {/* Cash Flow (Sankey) */}
          <AccordionSection title="🌊 Cash Flow">
            {sankeyLoading ? (
              <Skeleton variant="chart" className="h-[500px]" />
            ) : (
              <div className="h-[500px]">
                <SankeyChart data={sankeyData} height={500} />
              </div>
            )}
          </AccordionSection>

          {/* Monthly Income & Expenses (merged with Income by Source) */}
          <AccordionSection title="⚖️ Income & Expenses">
            <div className="flex justify-end mb-4">
              <div className="flex bg-[var(--surface-light)] p-1 rounded-xl">
                {([
                  { key: "overview" as const, label: "📊 Overview" },
                  { key: "by_source" as const, label: "💼 By Source" },
                ]).map(({ key, label }) => (
                  <button
                    key={key}
                    onClick={() => setIncomeView(key)}
                    className={`px-3 py-1.5 rounded-lg text-sm font-bold transition-all ${
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
            {incomeView === "overview" ? (
              <div className="h-[350px]">
                <Plot
                  data={[
                    {
                      x: incomeOutcome?.map((d: any) => d.month) || [],
                      y: incomeOutcome?.map((d: any) => d.income) || [],
                      name: "💚 Income",
                      type: "bar",
                      marker: { color: "#059669" },
                    },
                    {
                      x: incomeOutcome?.map((d: any) => d.month) || [],
                      y: incomeOutcome?.map((d: any) => d.expenses) || [],
                      name: "🔴 Expenses",
                      type: "bar",
                      marker: { color: "#f43f5e" },
                    },
                  ]}
                  layout={{
                    ...chartTheme,
                    barmode: "group",
                    autosize: true,
                    height: 350,
                    legend: {
                      orientation: "h",
                      y: -0.15,
                      x: 0.5,
                      xanchor: "center",
                    },
                  }}
                  style={{ width: "100%", height: "100%" }}
                  config={{ displayModeBar: false, responsive: true }}
                />
              </div>
            ) : (
              <div className="h-[350px]">
                {incomeBySourceData && incomeBySourceData.length > 0 ? (() => {
                  const allSources = Array.from(
                    new Set(
                      incomeBySourceData.flatMap((d) => Object.keys(d.sources)),
                    ),
                  );
                  const colors = [
                    "#059669", "#10b981", "#34d399", "#6ee7b7",
                    "#a7f3d0", "#047857", "#065f46", "#064e3b",
                  ];
                  return (
                    <Plot
                      data={allSources.map((source, i) => ({
                        x: incomeBySourceData.map((d) => d.month),
                        y: incomeBySourceData.map(
                          (d) => d.sources[source] || 0,
                        ),
                        name: source,
                        type: "bar" as const,
                        marker: { color: colors[i % colors.length] },
                      }))}
                      layout={{
                        ...chartTheme,
                        barmode: "stack",
                        autosize: true,
                        height: 350,
                        yaxis: {
                          title: {
                            text: "Amount (ILS)",
                            font: { color: "#94a3b8" },
                          },
                          tickfont: { color: "#94a3b8" },
                        },
                        legend: {
                          orientation: "h",
                          y: -0.15,
                          x: 0.5,
                          xanchor: "center",
                        },
                      }}
                      style={{ width: "100%", height: "100%" }}
                      config={{ displayModeBar: false, responsive: true }}
                    />
                  );
                })() : (
                  <p className="text-[var(--text-muted)] text-sm">📭 No income source data available.</p>
                )}
              </div>
            )}
          </AccordionSection>

          {/* Category Breakdown */}
          <AccordionSection title="🍕 Category Breakdown">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8 h-[350px]">
              {/* Expenses Chart */}
              <div className="relative">
                <p className="text-sm font-bold text-center text-red-400 mb-2 uppercase tracking-wider">
                  🔴 Expenses
                </p>
                <div className="h-full">
                  <Plot
                    data={[
                      {
                        values:
                          categoryData?.expenses?.map((d: any) => d.amount) ||
                          [],
                        labels:
                          categoryData?.expenses?.map(
                            (d: any) => d.category,
                          ) || [],
                        type: "pie",
                        hole: 0.4,
                        marker: {
                          colors: [
                            "#ef4444",
                            "#f87171",
                            "#fca5a5",
                            "#fecaca",
                            "#fee2e2",
                          ],
                        },
                        textinfo: "label+percent",
                        hoverinfo: "label+value+percent",
                      },
                    ]}
                    layout={{
                      ...chartTheme,
                      autosize: true,
                      showlegend: false,
                      margin: { t: 0, b: 0, l: 0, r: 0 },
                    }}
                    style={{ width: "95%", height: "95%" }}
                    config={{ displayModeBar: false, responsive: true }}
                  />
                </div>
              </div>

              {/* Refunds Chart */}
              <div className="relative">
                <p className="text-sm font-bold text-center text-emerald-400 mb-2 uppercase tracking-wider">
                  🟢 Refunds
                </p>
                <div className="h-full">
                  <Plot
                    data={[
                      {
                        values:
                          categoryData?.refunds?.map((d: any) => d.amount) ||
                          [],
                        labels:
                          categoryData?.refunds?.map(
                            (d: any) => d.category,
                          ) || [],
                        type: "pie",
                        hole: 0.4,
                        marker: {
                          colors: [
                            "#10b981",
                            "#34d399",
                            "#6ee7b7",
                            "#a7f3d0",
                            "#d1fae5",
                          ],
                        },
                        textinfo: "label+percent",
                        hoverinfo: "label+value+percent",
                      },
                    ]}
                    layout={{
                      ...chartTheme,
                      autosize: true,
                      showlegend: false,
                      margin: { t: 0, b: 0, l: 0, r: 0 },
                    }}
                    style={{ width: "95%", height: "95%" }}
                    config={{ displayModeBar: false, responsive: true }}
                  />
                </div>
              </div>
            </div>
          </AccordionSection>
        </div>
      </div>

    </div>
  );
}
