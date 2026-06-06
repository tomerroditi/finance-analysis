import React, { useState, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { PenSquare, Trash2, ChevronDown, ChevronUp } from "lucide-react";
import i18n from "../../i18n";
import { budgetApi, pendingRefundsApi, budgetMonthOverridesApi, type PendingRefund, type RefundLink, type BudgetMonthOverride } from "../../services/api";
import { formatCurrency } from "../../utils/numberFormatting";
import { Skeleton } from "../common/Skeleton";
import { EmptyState } from "../common/EmptyState";
import { DemoModeConfirmPopover } from "../common/DemoModeConfirmPopover";
import { BudgetRuleModal } from "../modals/BudgetRuleModal";
import { TransactionCollapsibleList } from "./TransactionCollapsibleList";
import type { Transaction } from "../../types/transaction";
import { PendingRefundsSection } from "./PendingRefundsSection";
import { useConfirm } from "../../context/DialogContext";
import { MonthHeader } from "./MonthHeader";
import { BudgetAlertsBanner } from "./BudgetAlertsBanner";
import { BudgetSummaryStrip } from "./BudgetSummaryStrip";
import { DataFreshnessBadge } from "./DataFreshnessBadge";
import { BudgetFreshnessBanner } from "./BudgetFreshnessBanner";
import { useBudgetFreshness } from "../../hooks/useBudgetFreshness";
import { useScraping } from "../../hooks/useScraping";
import { BudgetTrendChart } from "./BudgetTrendChart";
import { BudgetRuleRow } from "./BudgetRuleRow";
import { ProjectsThisMonthSummary } from "./ProjectsThisMonthSummary";

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
}

export const MonthlyBudgetView: React.FC<MonthlyBudgetViewProps> = ({
  onViewProjects,
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
  const freshness = useBudgetFreshness();
  const { isAnyScraping } = useScraping();

  const { data: analysis, isLoading } = useQuery({
    queryKey: ["budgetAnalysis", year, month, includeSplitParents],
    queryFn: () =>
      budgetApi.getAnalysis(year, month, includeSplitParents).then((res) => res.data),
    placeholderData: keepPreviousData,
  });

  // Prefetch adjacent months (prev 2 + next 2) for instant navigation
  useEffect(() => {
    const offsets = [-2, -1, 1, 2];
    for (const offset of offsets) {
      const date = new Date(year, month - 1 + offset);
      const prefetchYear = date.getFullYear();
      const prefetchMonth = date.getMonth() + 1;
      queryClient.prefetchQuery({
        queryKey: ["budgetAnalysis", prefetchYear, prefetchMonth, includeSplitParents],
        queryFn: () =>
          budgetApi.getAnalysis(prefetchYear, prefetchMonth, includeSplitParents).then((res) => res.data),
      });
    }
  }, [year, month, includeSplitParents, queryClient]);

  // When the active month's analysis reports an auto-fill, sibling months
  // may have prefetched in parallel and cached an empty result before the
  // fill committed. Refetch the others so navigation shows the rules
  // without a hard refresh.
  useEffect(() => {
    if (!analysis?.copied_from) return;
    queryClient.refetchQueries({
      queryKey: ["budgetAnalysis"],
      predicate: (query) => {
        const [, qYear, qMonth] = query.queryKey as [string, number, number, boolean];
        return qYear !== year || qMonth !== month;
      },
    });
  }, [analysis?.copied_from, year, month, queryClient]);

  // Pending refunds — for transaction badges/links across rule lists.
  const { data: pendingRefunds } = useQuery({
    queryKey: ["pendingRefunds", "all"],
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
    const map = new Map<string, number>();
    pendingRefunds?.forEach((pr: PendingRefund) => {
      pr.links?.forEach((link: RefundLink) => {
        map.set(`${link.refund_source}_${link.refund_transaction_id}`, link.id);
      });
    });
    return map;
  }, [pendingRefunds]);

  // Budget month overrides — for the per-row "move to prev/next month" actions.
  const { data: budgetMonthOverrides } = useQuery({
    queryKey: ["budgetMonthOverrides"],
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
    queryClient.invalidateQueries({ queryKey: ["budgetAnalysis"] });
    queryClient.invalidateQueries({ queryKey: ["budgetAlerts"] });
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
  const monthShortLabel = new Date(year, month - 1).toLocaleString(locale, {
    month: "long",
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

  if (isLoading)
    return (
      <div className="space-y-4 md:space-y-6">
        <Skeleton variant="card" className="h-16" />
        <Skeleton variant="card" className="h-28" />
        <div className="grid grid-cols-3 gap-3">
          <Skeleton variant="card" className="h-20" />
          <Skeleton variant="card" className="h-20" />
          <Skeleton variant="card" className="h-20" />
        </div>
        <Skeleton variant="card" className="h-16" />
        <Skeleton variant="card" className="h-16" />
      </div>
    );

  const { rules = [], project_spending } = analysis || {};

  // Summary calculations (exclude the Total Budget anchor row)
  const budgetRules = rules.filter(
    (item: BudgetAnalysisItem) => item.rule.name !== "Total Budget",
  );
  const onTrackCount = budgetRules.filter(
    (item: BudgetAnalysisItem) =>
      Math.abs(item.current_amount || 0) <= (item.rule.amount || 0),
  ).length;
  const overCount = budgetRules.length - onTrackCount;
  const biggestOverspendItem = budgetRules
    .filter(
      (item: BudgetAnalysisItem) =>
        item.rule.amount > 0 && Math.abs(item.current_amount || 0) > item.rule.amount,
    )
    .sort(
      (a: BudgetAnalysisItem, b: BudgetAnalysisItem) =>
        Math.abs(b.current_amount) / b.rule.amount -
        Math.abs(a.current_amount) / a.rule.amount,
    )[0];
  const biggestOverspend = biggestOverspendItem
    ? {
        name: biggestOverspendItem.rule.name,
        percentage:
          Math.abs(biggestOverspendItem.current_amount) /
          biggestOverspendItem.rule.amount,
      }
    : undefined;
  const daysInMonth = new Date(year, month, 0).getDate();
  const daysLeft = isCurrentMonth ? daysInMonth - today.getDate() : daysInMonth;

  const currentMonthKey = `${year}-${month}`;
  const copiedFromForThisMonth =
    analysis?.copied_from && !dismissedCopyMonths.has(currentMonthKey)
      ? analysis.copied_from
      : null;

  return (
    <div className="space-y-4 md:space-y-6">
      <MonthHeader
        monthLabel={monthLabel}
        isCurrentMonth={isCurrentMonth}
        onPrev={handlePreviousMonth}
        onNext={handleNextMonth}
        onToday={handleCurrentMonth}
        onAddRule={openAddModal}
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
      />

      <BudgetFreshnessBanner
        freshness={freshness}
        isSyncing={isAnyScraping}
        show={showFreshness}
        year={year}
        month={month}
      />

      {copiedFromForThisMonth && (
        <div className="flex items-start justify-between gap-3 bg-blue-500/10 border border-blue-500/20 text-blue-400 px-4 py-3 rounded-xl text-sm font-medium">
          <span>{t("budget.rulesCopiedFrom", { month: copiedFromForThisMonth })}</span>
          <button
            onClick={() =>
              setDismissedCopyMonths((prev) => new Set(prev).add(currentMonthKey))
            }
            aria-label={t("common.dismiss")}
            className="shrink-0 text-blue-400/60 hover:text-blue-400 transition-colors"
          >
            ✕
          </button>
        </div>
      )}

      <BudgetAlertsBanner year={year} month={month} />

      {budgetRules.length > 0 && (
        <>
          <BudgetSummaryStrip
            onTrackCount={onTrackCount}
            overCount={overCount}
            biggestOverspend={biggestOverspend}
            daysLeft={daysLeft}
            monthLabel={monthShortLabel}
            isStale={isBudgetStale}
          />
          <BudgetTrendChart
            year={year}
            month={month}
            includeSplitParents={includeSplitParents}
          />
        </>
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

      {rules.length > 0 &&
        (() => {
          const totalItem = rules.find(
            (i: BudgetAnalysisItem) => i.rule.name === "Total Budget",
          );
          const childItems = rules.filter(
            (i: BudgetAnalysisItem) => i.rule.name !== "Total Budget",
          );

          const buildActions = (item: BudgetAnalysisItem) =>
            item.allow_edit || item.allow_delete ? (
              <>
                {item.allow_edit && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setEditingRule(item.rule);
                      setIsRuleModalOpen(true);
                    }}
                    className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50/50 rounded-lg transition-all"
                    title={t("budget.editRule")}
                  >
                    <PenSquare size={16} />
                  </button>
                )}
                {item.allow_delete && (
                  <button
                    onClick={async (e) => {
                      e.stopPropagation();
                      const ok = await confirm({
                        title: t("budget.deleteRule"),
                        message: t("budget.confirmDeleteRule"),
                        confirmLabel: t("common.delete"),
                        isDestructive: true,
                      });
                      if (ok) deleteMutation.mutate(item.rule.id);
                    }}
                    className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50/50 rounded-lg transition-all"
                    title={t("budget.deleteRule")}
                  >
                    <Trash2 size={16} />
                  </button>
                )}
              </>
            ) : undefined;

          // "Other Expenses" is a synthetic catch-all rule that can't be
          // edited or deleted — show disabled buttons so the row keeps the
          // same trailing width (and the bars stay aligned with real rules).
          const disabledActions = (
            <>
              <button
                disabled
                title={t("budget.editRule")}
                className="p-1.5 text-[var(--text-muted)] opacity-40 cursor-not-allowed"
              >
                <PenSquare size={16} />
              </button>
              <button
                disabled
                title={t("budget.deleteRule")}
                className="p-1.5 text-[var(--text-muted)] opacity-40 cursor-not-allowed"
              >
                <Trash2 size={16} />
              </button>
            </>
          );

          const renderRow = (item: BudgetAnalysisItem) => (
            <BudgetRuleRow
              key={item.rule.id}
              label={item.rule.name}
              current={item.current_amount}
              total={item.rule.amount}
              isExpanded={expandedRuleId === String(item.rule.id)}
              onToggleExpand={() => toggleExpand(String(item.rule.id))}
              actions={
                item.rule.name === "Other Expenses"
                  ? disabledActions
                  : buildActions(item)
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
            </BudgetRuleRow>
          );

          if (!totalItem) {
            return <div className="space-y-3">{childItems.map(renderRow)}</div>;
          }

          // Total Budget is the container card. Clicking its title/header
          // collapses or expands the per-rule breakdown; a separate "view
          // month transactions" toggle reveals every transaction for the
          // month. Each rule row still expands its own transactions too.
          const spentT = Math.abs(totalItem.current_amount);
          const totalT = totalItem.rule.amount;
          const percentT =
            totalT > 0
              ? Math.min((spentT / totalT) * 100, 100)
              : spentT > 0
                ? 100
                : 0;
          const overT = spentT > totalT && totalT > 0;
          const nearT = !overT && totalT > 0 && spentT > totalT * 0.9;
          const barColorT = overT
            ? "bg-rose-500"
            : nearT
              ? "bg-amber-500"
              : "bg-emerald-500";
          const remainingT = totalT - spentT;
          const totalHint =
            totalT > 0
              ? overT
                ? t("budget.overByAmount", {
                    amount: formatCurrency(Math.abs(remainingT)),
                  })
                : t("budget.remainingAmount", {
                    amount: formatCurrency(remainingT),
                  })
              : null;
          const totalActions = buildActions(totalItem);

          return (
            <div className="w-full rounded-xl border border-[var(--surface-light)] bg-[var(--surface)] shadow-sm p-3 md:p-4 group">
              <div className="flex flex-wrap justify-between items-center gap-2">
                <button
                  onClick={() => setRulesCollapsed((v) => !v)}
                  aria-expanded={!rulesCollapsed}
                  className="flex items-center gap-2 md:gap-3 min-w-0 text-start"
                >
                  <span className="text-[var(--text-muted)] shrink-0">
                    {rulesCollapsed ? (
                      <ChevronDown size={20} />
                    ) : (
                      <ChevronUp size={20} />
                    )}
                  </span>
                  <span className="font-semibold text-[var(--text-default)] truncate">
                    {totalItem.rule.name}
                  </span>
                </button>
                <div className="font-bold font-mono text-sm md:text-base shrink-0" dir="ltr">
                  {formatCurrency(spentT)}{" "}
                  <span className="text-[var(--text-muted)] text-xs md:text-sm font-normal">
                    / {formatCurrency(totalT)}
                  </span>
                </div>
              </div>

              {/* Progress bar (with remaining/over written inside) + actions */}
              <div className="flex items-center gap-2 mt-3">
                <div className="relative flex-1 bg-[var(--surface-light)] rounded-full h-5 overflow-hidden">
                  <div
                    className={`absolute inset-y-0 start-0 rounded-full ${barColorT} transition-all duration-500 ease-out`}
                    style={{ width: `${percentT}%` }}
                  />
                  {totalHint && (
                    <span
                      className="absolute inset-y-0 end-2 flex items-center text-[10px] font-medium whitespace-nowrap text-white"
                      dir="ltr"
                    >
                      {totalHint}
                    </span>
                  )}
                </div>
                {totalActions && (
                  <div className="flex items-center gap-1 shrink-0">
                    {totalActions}
                  </div>
                )}
              </div>

              <button
                onClick={() => setShowTotalTransactions((v) => !v)}
                className="text-xs font-medium text-[var(--primary)] hover:text-[var(--primary-dark)] transition-colors mt-2"
              >
                {showTotalTransactions
                  ? t("budget.hideTransactions")
                  : t("budget.viewMonthTransactions")}
              </button>

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

              {!rulesCollapsed && (
                <div className="space-y-3 mt-3">{childItems.map(renderRow)}</div>
              )}
            </div>
          );
        })()}

      {analysis?.pending_refunds && (
        <PendingRefundsSection pendingRefunds={analysis.pending_refunds} />
      )}

      {project_spending?.projects?.length > 0 && (
        <ProjectsThisMonthSummary
          projects={project_spending.projects as ProjectSpendingItem[]}
          onViewAll={onViewProjects}
          expandedRuleId={expandedRuleId}
          toggleExpand={toggleExpand}
          pendingRefundsMap={pendingRefundsMap}
          onTransactionUpdated={invalidateBudget}
        />
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
