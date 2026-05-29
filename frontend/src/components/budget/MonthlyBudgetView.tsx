import React, { useState, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { PenSquare, Trash2 } from "lucide-react";
import i18n from "../../i18n";
import { budgetApi, pendingRefundsApi, type PendingRefund, type RefundLink } from "../../services/api";
import { Skeleton } from "../common/Skeleton";
import { EmptyState } from "../common/EmptyState";
import { DemoModeConfirmPopover } from "../common/DemoModeConfirmPopover";
import { BudgetProgressBar } from "../BudgetProgressBar";
import { BudgetRuleModal } from "../modals/BudgetRuleModal";
import { TransactionCollapsibleList } from "./TransactionCollapsibleList";
import type { Transaction } from "../../types/transaction";
import { PendingRefundsSection } from "./PendingRefundsSection";
import { useConfirm } from "../../context/DialogContext";
import { MonthHeader } from "./MonthHeader";
import { BudgetAlertsBanner } from "./BudgetAlertsBanner";
import { BudgetSummaryStrip } from "./BudgetSummaryStrip";
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
  const [includeSplitParents, setIncludeSplitParents] = useState(false);
  const [showDemoConfirm, setShowDemoConfirm] = useState(false);
  const [dismissedCopyMonths, setDismissedCopyMonths] = useState<Set<string>>(
    new Set(),
  );

  const queryClient = useQueryClient();

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

  const copyMutation = useMutation({
    mutationFn: () => budgetApi.copyRules(year, month),
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

  const handleReplicate = async () => {
    const ok = await confirm({
      title: t("budget.replicatePreviousMonth"),
      message: t("budget.confirmCopyRules"),
      confirmLabel: t("common.confirm"),
    });
    if (ok) copyMutation.mutate();
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
  const totalSpent = budgetRules.reduce(
    (sum: number, item: BudgetAnalysisItem) => sum + Math.abs(item.current_amount || 0),
    0,
  );
  const totalBudget = budgetRules.reduce(
    (sum: number, item: BudgetAnalysisItem) => sum + (item.rule.amount || 0),
    0,
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
        replicatePending={copyMutation.isPending}
        onPrev={handlePreviousMonth}
        onNext={handleNextMonth}
        onToday={handleCurrentMonth}
        onReplicate={handleReplicate}
        onAddRule={openAddModal}
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
            totalSpent={totalSpent}
            totalBudget={totalBudget}
            onTrackCount={onTrackCount}
            overCount={overCount}
            biggestOverspend={biggestOverspend}
            daysLeft={daysLeft}
            monthLabel={monthShortLabel}
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

      <div className="space-y-3">
        {rules.map((item: BudgetAnalysisItem) => {
          const isTotalBudget = item.rule.name === "Total Budget";
          const isOtherExpenses = item.rule.name === "Other Expenses";
          const actions = (
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
          );
          const hasActions = item.allow_edit || item.allow_delete;
          const txList = (
            <TransactionCollapsibleList
              transactions={item.data}
              isOpen={expandedRuleId === String(item.rule.id)}
              showActions
              onTransactionUpdated={invalidateBudget}
              pendingRefundsMap={pendingRefundsMap}
              refundLinksMap={refundLinksMap}
              showSplitParentsFilter
              includeSplitParents={includeSplitParents}
              onIncludeSplitParentsChange={setIncludeSplitParents}
            />
          );

          if (isTotalBudget) {
            return (
              <BudgetProgressBar
                key={item.rule.id}
                label={item.rule.name}
                current={item.current_amount}
                total={item.rule.amount}
                onToggleExpand={() => toggleExpand(String(item.rule.id))}
                isExpanded={expandedRuleId === String(item.rule.id)}
                actions={hasActions ? actions : undefined}
              >
                {txList}
              </BudgetProgressBar>
            );
          }

          return (
            <BudgetRuleRow
              key={item.rule.id}
              label={item.rule.name}
              subLabel={
                item.rule.category !== item.rule.name ? item.rule.category : undefined
              }
              current={item.current_amount}
              total={item.rule.amount}
              dimmed={isOtherExpenses}
              isExpanded={expandedRuleId === String(item.rule.id)}
              onToggleExpand={() => toggleExpand(String(item.rule.id))}
              actions={hasActions ? actions : undefined}
            >
              {txList}
            </BudgetRuleRow>
          );
        })}
      </div>

      {analysis?.pending_refunds && (
        <PendingRefundsSection pendingRefunds={analysis.pending_refunds} />
      )}

      {project_spending?.projects?.length > 0 && (
        <ProjectsThisMonthSummary
          projects={project_spending.projects as ProjectSpendingItem[]}
          onViewAll={onViewProjects}
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
