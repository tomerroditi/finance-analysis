import React, { useState, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import i18n from "../../i18n";
import { budgetApi, pendingRefundsApi, budgetMonthOverridesApi, type PendingRefund, type RefundLink, type BudgetMonthOverride } from "../../services/api";
import { formatMonthCompact } from "../../utils/dateFormatting";
import { Skeleton } from "../common/Skeleton";
import { EmptyState } from "../common/EmptyState";
import { DemoModeConfirmPopover } from "../common/DemoModeConfirmPopover";
import { BudgetRuleModal } from "../modals/BudgetRuleModal";
import { TransactionCollapsibleList } from "./TransactionCollapsibleList";
import type { Transaction } from "../../types/transaction";
import { PendingRefundsSection } from "./PendingRefundsSection";
import { SavingsGoalsBudgetSection } from "./SavingsGoalsBudgetSection";
import { useConfirm } from "../../context/DialogContext";
import { BAR_CONTROL, BudgetCommandBar, PeriodNav } from "./BudgetCommandBar";
import { BudgetStatusBand, type BandStat } from "./BudgetStatusBand";
import { BudgetNoticeLine } from "./BudgetNoticeLine";
import { BudgetLedgerRow, LedgerRowAction } from "./BudgetLedgerRow";
import { BudgetRail } from "./BudgetRail";
import { RuleSparkline } from "./RuleSparkline";
import { DataFreshnessBadge } from "./DataFreshnessBadge";
import { useBudgetFreshness } from "../../hooks/useBudgetFreshness";
import { useScraping } from "../../hooks/useScraping";
import { useBudgetTrend } from "../../hooks/useBudgetTrend";
import { ProjectsThisMonthSummary } from "./ProjectsThisMonthSummary";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { qkPrefix } from "../../services/queryKeys";

/**
 * Months in the summary band's budget-vs-actual figure. It spans the stats
 * row now (~330px), so six bars read as fat blocks rather than a trend.
 * Costs one `budget/analysis` request per month — the trailing few are warm
 * from the ±2 prefetch, the rest are cold on first load.
 */
const TREND_MONTHS = 12;

/** Per-rule sparklines live in a 78px column; 12 bars there is a smear. */
const ROW_TREND_MONTHS = 6;

interface BudgetRule {
  id: number;
  name: string;
  category: string;
  amount: number;
}

interface BudgetAnalysisItem {
  rule: BudgetRule;
  current_amount: number;
  data: Transaction[];
  allow_edit: boolean;
  allow_delete: boolean;
}

interface ProjectSpendingItem {
  category: string;
  spent: number;
  transactions: Transaction[];
}

interface MonthlyBudgetViewProps {
  onViewProjects: () => void;
  /** Tab group rendered into the shared command bar. */
  tabs: React.ReactNode;
}

export const MonthlyBudgetView: React.FC<MonthlyBudgetViewProps> = ({
  onViewProjects,
  tabs,
}) => {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [isRuleModalOpen, setIsRuleModalOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<BudgetRule | null>(null);
  const [expandedRuleId, setExpandedRuleId] = useState<string | null>(null);
  const [rulesCollapsed, setRulesCollapsed] = useState(false);
  const [showTotalTransactions, setShowTotalTransactions] = useState(false);
  const [includeSplitParents, setIncludeSplitParents] = useState(false);
  const [showDemoConfirm, setShowDemoConfirm] = useState(false);
  const [dismissedCopyMonths, setDismissedCopyMonths] = useState<Set<string>>(
    new Set(),
  );

  const queryClient = useQueryClient();
  const qk = useQueryKeys();
  const freshness = useBudgetFreshness();
  const { isAnyScraping } = useScraping();

  const { data: analysis, isLoading } = useQuery({
    queryKey: qk.budget.analysis(year, month, includeSplitParents),
    queryFn: () =>
      budgetApi.getAnalysis(year, month, includeSplitParents).then((res) => res.data),
    placeholderData: keepPreviousData,
  });

  // Per-rule trend series. This reuses the trailing per-month analyses the
  // trend chart already fetches, so the sparklines cost no extra requests.
  const trend = useBudgetTrend(year, month, TREND_MONTHS, includeSplitParents);
  const trendLabels = useMemo(
    () => trend.data.map((point) => formatMonthCompact(`${point.key}-01`)),
    [trend.data],
  );
  const rowTrendLabels = useMemo(
    () => trendLabels.slice(-ROW_TREND_MONTHS),
    [trendLabels],
  );

  // Prefetch adjacent months (prev 2 + next 2) for instant navigation
  useEffect(() => {
    const offsets = [-2, -1, 1, 2];
    for (const offset of offsets) {
      const date = new Date(year, month - 1 + offset);
      const prefetchYear = date.getFullYear();
      const prefetchMonth = date.getMonth() + 1;
      queryClient.prefetchQuery({
        queryKey: qk.budget.analysis(prefetchYear, prefetchMonth, includeSplitParents),
        queryFn: () =>
          budgetApi.getAnalysis(prefetchYear, prefetchMonth, includeSplitParents).then((res) => res.data),
      });
    }
  }, [year, month, includeSplitParents, queryClient, qk]);

  // When the active month's analysis reports an auto-fill, sibling months
  // may have prefetched in parallel and cached an empty result before the
  // fill committed. Refetch the others so navigation shows the rules
  // without a hard refresh.
  useEffect(() => {
    if (!analysis?.copied_from) return;
    queryClient.refetchQueries({
      queryKey: qkPrefix.budgetAnalysis,
      predicate: (query) => {
        const [, , qYear, qMonth] = query.queryKey as [string, string, number, number, boolean, boolean];
        return qYear !== year || qMonth !== month;
      },
    });
  }, [analysis?.copied_from, year, month, queryClient]);

  // Pending refunds — for transaction badges/links across rule lists.
  const { data: pendingRefunds } = useQuery({
    queryKey: qk.pendingRefunds.all(),
    queryFn: () => pendingRefundsApi.getAll().then((res) => res.data),
  });

  const pendingRefundsMap = useMemo(() => {
    const map = new Map<string, PendingRefund>();
    pendingRefunds?.forEach((pr: PendingRefund) => {
      map.set(`${pr.source_table}_${pr.source_id}`, pr);
    });
    return map;
  }, [pendingRefunds]);

  const refundLinksMap = useMemo(() => {
    const map = new Map<string, RefundLink[]>();
    pendingRefunds?.forEach((pr: PendingRefund) => {
      pr.links?.forEach((link: RefundLink) => {
        const key = `${link.refund_source}_${link.refund_transaction_id}`;
        const existing = map.get(key);
        if (existing) {
          existing.push(link);
        } else {
          map.set(key, [link]);
        }
      });
    });
    return map;
  }, [pendingRefunds]);

  // Budget month overrides — for the per-row "move to prev/next month" actions.
  const { data: budgetMonthOverrides } = useQuery({
    queryKey: qk.budget.monthOverrides(),
    queryFn: () => budgetMonthOverridesApi.getAll().then((res) => res.data),
  });

  const budgetMonthOverridesMap = useMemo(() => {
    const map = new Map<string, BudgetMonthOverride>();
    budgetMonthOverrides?.forEach((o: BudgetMonthOverride) => {
      map.set(`${o.source_table}_${o.source_id}`, o);
    });
    return map;
  }, [budgetMonthOverrides]);

  const invalidateBudget = () => {
    queryClient.invalidateQueries({ queryKey: qkPrefix.budget });
  };

  const createMutation = useMutation({
    mutationFn: budgetApi.createRule,
    onSuccess: invalidateBudget,
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, rule }: { id: number; rule: object }) =>
      budgetApi.updateRule(id, rule),
    onSuccess: invalidateBudget,
  });

  const deleteMutation = useMutation({
    mutationFn: budgetApi.deleteRule,
    onSuccess: invalidateBudget,
  });

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

  const handleCurrentMonth = () => {
    setMonth(today.getMonth() + 1);
    setYear(today.getFullYear());
  };

  const handleSaveRule = async (ruleData: object) => {
    if (editingRule) {
      await updateMutation.mutateAsync({ id: editingRule.id, rule: ruleData });
    } else {
      await createMutation.mutateAsync(ruleData);
    }
    setEditingRule(null);
    setIsRuleModalOpen(false);
  };

  const openAddModal = () => {
    setEditingRule(null);
    setIsRuleModalOpen(true);
  };

  const toggleExpand = (id: string) =>
    setExpandedRuleId((prev) => (prev === id ? null : id));

  const locale = i18n.language === "he" ? "he-IL" : "en-US";
  const monthLabel = new Date(year, month - 1).toLocaleString(locale, {
    month: "long",
    year: "numeric",
  });
  const isCurrentMonth =
    year === today.getFullYear() && month === today.getMonth() + 1;

  // Freshness applies to the current month and any earlier month whose data
  // could still be missing transactions — i.e. months ending on/after the
  // oldest sync. Fully-settled history (before the last sync) stays clean.
  // Future months and never-synced accounts only flag the live month.
  const viewedIndex = year * 12 + (month - 1);
  const currentIndex = today.getFullYear() * 12 + today.getMonth();
  const monthEnd = new Date(year, month, 0, 23, 59, 59, 999).getTime();
  const monthCouldBeIncomplete =
    viewedIndex <= currentIndex &&
    (isCurrentMonth ||
      (freshness.oldestSyncDate !== null &&
        monthEnd >= new Date(freshness.oldestSyncDate).getTime()));
  const showFreshness =
    freshness.hasScrapableAccounts && monthCouldBeIncomplete;
  const isBudgetStale =
    showFreshness &&
    !isAnyScraping &&
    (freshness.tier === "stale" ||
      freshness.tier === "veryStale" ||
      freshness.tier === "never");

  const commandBar = (
    <BudgetCommandBar
      tabs={tabs}
      freshnessBadge={
        showFreshness ? (
          <DataFreshnessBadge
            tier={freshness.tier}
            oldestSyncDate={freshness.oldestSyncDate}
            staleAccounts={freshness.staleAccounts}
            isSyncing={isAnyScraping}
            year={year}
            month={month}
          />
        ) : undefined
      }
      actions={
        <button
          onClick={openAddModal}
          className={`inline-flex items-center justify-center gap-2 px-3 md:px-4 text-xs md:text-sm bg-[var(--primary)] text-white rounded-lg hover:bg-[var(--primary-dark)] transition-colors shadow-sm font-medium whitespace-nowrap ${BAR_CONTROL}`}
        >
          <Plus size={18} className="shrink-0" />
          {t("budget.addRule")}
        </button>
      }
    >
      <PeriodNav
        label={monthLabel}
        isCurrent={isCurrentMonth}
        onPrev={handlePreviousMonth}
        onNext={handleNextMonth}
        onToday={handleCurrentMonth}
        todayTitle={t("budget.currentMonth")}
      />
    </BudgetCommandBar>
  );

  if (isLoading)
    return (
      <div className="space-y-3 md:space-y-4">
        {commandBar}
        <Skeleton variant="card" className="h-28" />
        <Skeleton variant="card" className="h-12" />
        <Skeleton variant="card" className="h-12" />
        <Skeleton variant="card" className="h-12" />
      </div>
    );

  const { rules = [], project_spending } = analysis || {};

  // Summary calculations (exclude the Total Budget anchor row)
  const budgetRules = rules.filter(
    (item: BudgetAnalysisItem) => item.rule.name !== "Total Budget",
  );
  // A rule's net can be negative when refunds exceed spend for the period.
  // Clamp to 0 (net spend) so a refund is never counted as overspend or
  // ranked as the "biggest overspend".
  const onTrackCount = budgetRules.filter(
    (item: BudgetAnalysisItem) =>
      Math.max(item.current_amount || 0, 0) <= (item.rule.amount || 0),
  ).length;
  const overCount = budgetRules.length - onTrackCount;
  const biggestOverspendItem = budgetRules
    .filter(
      (item: BudgetAnalysisItem) =>
        item.rule.amount > 0 &&
        Math.max(item.current_amount || 0, 0) > item.rule.amount,
    )
    .sort(
      (a: BudgetAnalysisItem, b: BudgetAnalysisItem) =>
        Math.max(b.current_amount, 0) / b.rule.amount -
        Math.max(a.current_amount, 0) / a.rule.amount,
    )[0];
  const daysInMonth = new Date(year, month, 0).getDate();
  const daysLeft = isCurrentMonth ? daysInMonth - today.getDate() : daysInMonth;

  const currentMonthKey = `${year}-${month}`;
  const copiedFromForThisMonth =
    analysis?.copied_from && !dismissedCopyMonths.has(currentMonthKey)
      ? analysis.copied_from
      : null;

  // SavingsGoalsBudgetSection self-hides when there is nothing to show, so the
  // row needs the same test to decide whether the goals half exists at all.
  const hasGoalAllocations = (analysis?.savings_goals?.goals?.length ?? 0) > 0;
  const monthProjects = (project_spending?.projects ?? []) as ProjectSpendingItem[];

  const totalItem = rules.find(
    (i: BudgetAnalysisItem) => i.rule.name === "Total Budget",
  );
  const childItems = rules.filter(
    (i: BudgetAnalysisItem) => i.rule.name !== "Total Budget",
  );

  const stats: BandStat[] = [
    {
      key: "health",
      label: t("budget.budgetHealth"),
      value: (
        <span className="flex items-baseline gap-1 flex-wrap">
          <span className="text-lg md:text-xl font-bold text-emerald-400">{onTrackCount}</span>
          <span className="text-[10px] sm:text-xs text-[var(--text-muted)]">
            {t("budget.onTrackLabel")}
          </span>
          {overCount > 0 && (
            <>
              <span className="text-[10px] sm:text-xs text-[var(--text-muted)]">·</span>
              <span className="text-lg md:text-xl font-bold text-rose-400">{overCount}</span>
              <span className="text-[10px] sm:text-xs text-[var(--text-muted)]">
                {t("budget.overBudgetLabel")}
              </span>
            </>
          )}
        </span>
      ),
    },
    {
      key: "worst",
      label: t("budget.biggestOverspend"),
      value: biggestOverspendItem ? (
        <span className="block min-w-0">
          <span className="block text-sm md:text-base font-bold text-rose-400 truncate" dir="auto">
            {biggestOverspendItem.rule.name}
          </span>
          <span className="text-[10px] sm:text-xs text-[var(--text-muted)]" dir="ltr">
            {Math.round(
              (Math.max(biggestOverspendItem.current_amount, 0) /
                biggestOverspendItem.rule.amount) *
                100,
            )}
            %
          </span>
        </span>
      ) : (
        <span className="text-sm md:text-base font-bold text-emerald-400">
          {t("budget.allGood")}
        </span>
      ),
    },
    {
      key: "daysLeft",
      label: t("budget.daysLeft"),
      value: <span className="text-lg md:text-xl font-bold">{daysLeft}</span>,
    },
    {
      key: "trend",
      label: t("budget.trend.title"),
      grow: true,
      trend: trend.hasData ? (
        <RuleSparkline
          variant="bars"
          series={trend.data.map((point) => point.actual)}
          labels={trendLabels}
          budget={trend.data[trend.data.length - 1]?.budget ?? 0}
          width={220}
          height={44}
          fluid
        />
      ) : (
        <span className="text-[10px] text-[var(--text-muted)]">—</span>
      ),
    },
  ];

  // Both slots always render — a row that omitted them got a wider grid and
  // fell out of line with its neighbours (see LedgerRowAction).
  const buildActions = (item: BudgetAnalysisItem) => (
    <>
      <LedgerRowAction
        kind="edit"
        label={t("budget.editRule")}
        onClick={
          item.allow_edit
            ? () => {
                setEditingRule(item.rule);
                setIsRuleModalOpen(true);
              }
            : undefined
        }
      />
      <LedgerRowAction
        kind="delete"
        label={t("budget.deleteRule")}
        onClick={
          item.allow_delete
            ? async () => {
                const ok = await confirm({
                  title: t("budget.deleteRule"),
                  message: t("budget.confirmDeleteRule"),
                  confirmLabel: t("common.delete"),
                  isDestructive: true,
                });
                if (ok) deleteMutation.mutate(item.rule.id);
              }
            : undefined
        }
      />
    </>
  );

  const renderRow = (item: BudgetAnalysisItem) => (
    <BudgetLedgerRow
      key={item.rule.id}
      label={item.rule.name}
      current={item.current_amount}
      total={item.rule.amount}
      isExpanded={expandedRuleId === String(item.rule.id)}
      onToggleExpand={() => toggleExpand(String(item.rule.id))}
      actions={buildActions(item)}
      trend={
        <RuleSparkline
          variant="bars"
          series={(trend.byRule[item.rule.name] ?? []).slice(-ROW_TREND_MONTHS)}
          labels={rowTrendLabels}
          budget={item.rule.amount}
        />
      }
    >
      <TransactionCollapsibleList
        transactions={item.data}
        isOpen={expandedRuleId === String(item.rule.id)}
        showActions
        onTransactionUpdated={invalidateBudget}
        pendingRefundsMap={pendingRefundsMap}
        refundLinksMap={refundLinksMap}
        budgetMonthOverridesMap={budgetMonthOverridesMap}
        budgetViewYear={year}
        budgetViewMonth={month}
        showSplitParentsFilter
        includeSplitParents={includeSplitParents}
        onIncludeSplitParentsChange={setIncludeSplitParents}
      />
    </BudgetLedgerRow>
  );

  return (
    <div className="space-y-3 md:space-y-4">
      {commandBar}

      <BudgetNoticeLine
        copiedFrom={copiedFromForThisMonth}
        onDismissCopied={() =>
          setDismissedCopyMonths((prev) => new Set(prev).add(currentMonthKey))
        }
      />

      {totalItem && (
        <BudgetStatusBand
          label={t("budget.totalBudget")}
          spent={totalItem.current_amount}
          total={totalItem.rule.amount}
          stats={stats}
          onToggleRules={() => setRulesCollapsed((v) => !v)}
          rulesCollapsed={rulesCollapsed}
          isStale={isBudgetStale}
          footer={
            <button
              onClick={() => setShowTotalTransactions((v) => !v)}
              className="py-2 text-xs font-medium text-[var(--primary)] hover:text-[var(--primary-dark)] transition-colors"
            >
              {showTotalTransactions
                ? t("budget.hideTransactions")
                : t("budget.viewMonthTransactions")}
            </button>
          }
        >
          {showTotalTransactions && (
            <TransactionCollapsibleList
              transactions={totalItem.data}
              isOpen
              showActions
              onTransactionUpdated={invalidateBudget}
              pendingRefundsMap={pendingRefundsMap}
              refundLinksMap={refundLinksMap}
              budgetMonthOverridesMap={budgetMonthOverridesMap}
              budgetViewYear={year}
              budgetViewMonth={month}
              showSplitParentsFilter
              includeSplitParents={includeSplitParents}
              onIncludeSplitParentsChange={setIncludeSplitParents}
            />
          )}
        </BudgetStatusBand>
      )}

      {budgetRules.length === 0 && (
        <EmptyState
          title={t("emptyStates.budget.title")}
          description={t("emptyStates.budget.description")}
          cta={{ label: t("budget.addRule"), onClick: () => setIsRuleModalOpen(true) }}
          secondary={{
            label: t("emptyStates.tryDemoMode"),
            onClick: () => setShowDemoConfirm(true),
          }}
          footer={
            showDemoConfirm ? (
              <DemoModeConfirmPopover onClose={() => setShowDemoConfirm(false)} />
            ) : undefined
          }
        />
      )}

      {rules.length > 0 && !rulesCollapsed && (
        <div className="w-full space-y-2">{childItems.map(renderRow)}</div>
      )}

      {/* Goals and projects share one row. Both are month summaries that sit
          beside the ledger rather than in it, and the projects card is far too
          short to earn a full row of its own — it used to ride in the rail
          next to the ledger, leaving a tall column of empty space under it. */}
      {(hasGoalAllocations || monthProjects.length > 0) && (
        <div className="flex flex-col xl:flex-row items-start gap-3 md:gap-4">
          {hasGoalAllocations && (
            <div className="flex-1 min-w-0 w-full">
              <SavingsGoalsBudgetSection allocations={analysis?.savings_goals} />
            </div>
          )}
          {monthProjects.length > 0 && (
            <BudgetRail>
              <ProjectsThisMonthSummary
                projects={monthProjects}
                onViewAll={onViewProjects}
              />
            </BudgetRail>
          )}
        </div>
      )}

      {analysis?.pending_refunds && (
        <PendingRefundsSection pendingRefunds={analysis.pending_refunds} />
      )}

      <BudgetRuleModal
        isOpen={isRuleModalOpen}
        onClose={() => {
          setIsRuleModalOpen(false);
          setEditingRule(null);
        }}
        onSave={handleSaveRule}
        initialData={editingRule}
        selectedYear={year}
        selectedMonth={month}
      />
    </div>
  );
};
