import React, { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import {
  ChevronLeft,
  ChevronRight,
  Plus,
  PenSquare,
  Trash2,
  Copy,
} from "lucide-react";
import { budgetApi, pendingRefundsApi } from "../../services/api";
import { Skeleton } from "../common/Skeleton";
import { BudgetProgressBar } from "../BudgetProgressBar";
import { BudgetRuleModal } from "../modals/BudgetRuleModal";
import { TransactionCollapsibleList } from "./TransactionCollapsibleList";
import { PendingRefundsSection } from "./PendingRefundsSection";
import { useMemo } from "react";

export const MonthlyBudgetView: React.FC = () => {
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [isRuleModalOpen, setIsRuleModalOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<any>(null);
  const [expandedRuleId, setExpandedRuleId] = useState<string | null>(null);
  const [includeSplitParents, setIncludeSplitParents] = useState(false);
  const [copiedFromMsg, setCopiedFromMsg] = useState<string | null>(null);

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

  useEffect(() => {
    if (analysis?.copied_from) {
      setCopiedFromMsg(analysis.copied_from);
      const timer = setTimeout(() => setCopiedFromMsg(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [analysis?.copied_from]);

  // Fetch pending refunds to know which transactions are already marked
  const { data: pendingRefunds } = useQuery({
    queryKey: ["pendingRefunds", "all"],
    queryFn: () => pendingRefundsApi.getAll().then((res) => res.data),
  });

  // Create a map of pending refunds by source ID for quick lookup
  const pendingRefundsMap = useMemo(() => {
    const map = new Map<string, any>();
    if (!pendingRefunds) return map;

    pendingRefunds.forEach((pr: any) => {
      const key = `${pr.source_table}_${pr.source_id}`;
      map.set(key, pr);
    });
    return map;
  }, [pendingRefunds]);

  // Map of linked refunds: transaction_key -> link_id
  const refundLinksMap = useMemo(() => {
    const map = new Map<string, number>();
    if (!pendingRefunds) return map;

    pendingRefunds.forEach((pr: any) => {
      if (pr.links) {
        pr.links.forEach((link: any) => {
          const key = `${link.refund_source}_${link.refund_transaction_id}`;
          map.set(key, link.id);
        });
      }
    });
    return map;
  }, [pendingRefunds]);

  const createMutation = useMutation({
    mutationFn: budgetApi.createRule,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["budgetAnalysis"] }),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, rule }: { id: number; rule: any }) =>
      budgetApi.updateRule(id, rule),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["budgetAnalysis"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: budgetApi.deleteRule,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["budgetAnalysis"] }),
  });

  const copyMutation = useMutation({
    mutationFn: () => budgetApi.copyRules(year, month),
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

  const handleSaveRule = async (ruleData: any) => {
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

  const toggleExpand = (id: string) => {
    setExpandedRuleId((prev) => (prev === id ? null : id));
  };

  if (isLoading)
    return (
      <div className="space-y-6 p-8">
        <Skeleton variant="card" className="h-16" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <Skeleton variant="card" className="h-24" />
          <Skeleton variant="card" className="h-24" />
          <Skeleton variant="card" className="h-24" />
          <Skeleton variant="card" className="h-24" />
        </div>
        <Skeleton variant="card" className="h-20" />
        <Skeleton variant="card" className="h-20" />
        <Skeleton variant="card" className="h-20" />
      </div>
    );

  const { rules = [], project_spending } = analysis || {};

  // Summary calculations (skip Total Budget which is always first if present)
  const budgetRules = rules.filter(
    (item: any) => item.rule.name !== "Total Budget",
  );
  const totalSpent = budgetRules.reduce(
    (sum: number, item: any) => sum + Math.abs(item.current_amount || 0),
    0,
  );
  const totalBudget = budgetRules.reduce(
    (sum: number, item: any) => sum + (item.rule.amount || 0),
    0,
  );
  const onTrackCount = budgetRules.filter(
    (item: any) =>
      Math.abs(item.current_amount || 0) <= (item.rule.amount || 0),
  ).length;
  const overCount = budgetRules.length - onTrackCount;
  const biggestOverspend = budgetRules
    .filter(
      (item: any) =>
        item.rule.amount > 0 &&
        Math.abs(item.current_amount || 0) > item.rule.amount,
    )
    .sort(
      (a: any, b: any) =>
        Math.abs(b.current_amount) / b.rule.amount -
        Math.abs(a.current_amount) / a.rule.amount,
    )[0];
  const daysInMonth = new Date(year, month, 0).getDate();
  const daysLeft =
    year === today.getFullYear() && month === today.getMonth() + 1
      ? daysInMonth - today.getDate()
      : daysInMonth;

  const formatCurrency = (val: number) =>
    new Intl.NumberFormat("he-IL", {
      style: "currency",
      currency: "ILS",
      maximumFractionDigits: 0,
    }).format(val);

  return (
    <div className="space-y-8">
      {/* Month Navigation */}
      <div className="flex items-center justify-between bg-[var(--surface)] p-4 rounded-2xl shadow-sm border border-[var(--surface-light)]">
        <div className="flex items-center space-x-4">
          <button
            onClick={handlePreviousMonth}
            className="p-2 hover:bg-[var(--surface-light)] rounded-full text-[var(--text-muted)] hover:text-[var(--text-default)] transition-colors"
          >
            <ChevronLeft size={24} />
          </button>
          <h2 className="text-2xl font-bold w-48 text-center bg-gradient-to-r from-[var(--primary)] to-blue-600 bg-clip-text text-transparent">
            {new Date(year, month - 1).toLocaleString("default", {
              month: "long",
              year: "numeric",
            })}
          </h2>
          <button
            onClick={handleNextMonth}
            className="p-2 hover:bg-[var(--surface-light)] rounded-full text-[var(--text-muted)] hover:text-[var(--text-default)] transition-colors"
          >
            <ChevronRight size={24} />
          </button>
        </div>
        <div className="flex gap-3">
          <button
            onClick={handleCurrentMonth}
            className="px-4 py-2 text-sm font-medium text-[var(--primary)] hover:bg-[var(--primary)]/10 rounded-lg transition-colors"
          >
            Current Month
          </button>
          <button
            onClick={() => {
              if (
                confirm(
                  "This will delete all current rules for this month and copy rules from the previous month. Continue?",
                )
              ) {
                copyMutation.mutate();
              }
            }}
            disabled={copyMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-[var(--surface)] border border-[var(--surface-light)] text-[var(--text-default)] rounded-lg hover:bg-[var(--surface-light)] transition-colors shadow-sm font-medium disabled:opacity-50"
          >
            <Copy size={20} />
            Replicate Previous Month
          </button>
          <button
            onClick={openAddModal}
            className="flex items-center gap-2 px-4 py-2 bg-[var(--primary)] text-white rounded-lg hover:bg-[var(--primary-dark)] transition-colors shadow-lg shadow-[var(--primary)]/20 font-medium"
          >
            <Plus size={20} />
            Add Rule
          </button>
        </div>
      </div>

      {/* Auto-copy toast */}
      {copiedFromMsg && (
        <div className="flex items-center justify-between bg-blue-500/10 border border-blue-500/20 text-blue-400 px-4 py-3 rounded-xl text-sm font-medium">
          <span>Budget rules copied from {copiedFromMsg}</span>
          <button
            onClick={() => setCopiedFromMsg(null)}
            className="ml-4 text-blue-400/60 hover:text-blue-400 transition-colors"
          >
            ✕
          </button>
        </div>
      )}

      {/* Summary Header Strip */}
      {budgetRules.length > 0 && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
          <div className="bg-[var(--surface)] rounded-xl p-4 border border-[var(--surface-light)]">
            <p className="text-xs text-[var(--text-muted)] uppercase tracking-wide">
              Total Spent
            </p>
            <p className="text-xl font-bold mt-1">
              {formatCurrency(totalSpent)}
            </p>
            <p className="text-xs text-[var(--text-muted)]">
              of {formatCurrency(totalBudget)}
            </p>
          </div>
          <div className="bg-[var(--surface)] rounded-xl p-4 border border-[var(--surface-light)]">
            <p className="text-xs text-[var(--text-muted)] uppercase tracking-wide">
              Budget Health
            </p>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-xl font-bold text-emerald-400">
                {onTrackCount}
              </span>
              <span className="text-xs text-[var(--text-muted)]">on track</span>
              {overCount > 0 && (
                <>
                  <span className="text-xl font-bold text-rose-400">
                    {overCount}
                  </span>
                  <span className="text-xs text-[var(--text-muted)]">over</span>
                </>
              )}
            </div>
          </div>
          <div className="bg-[var(--surface)] rounded-xl p-4 border border-[var(--surface-light)]">
            <p className="text-xs text-[var(--text-muted)] uppercase tracking-wide">
              Biggest Overspend
            </p>
            {biggestOverspend ? (
              <>
                <p className="text-lg font-bold mt-1 text-rose-400">
                  {biggestOverspend.rule.name}
                </p>
                <p className="text-xs text-[var(--text-muted)]">
                  {Math.round(
                    (Math.abs(biggestOverspend.current_amount) /
                      biggestOverspend.rule.amount) *
                      100,
                  )}
                  %
                </p>
              </>
            ) : (
              <p className="text-lg font-bold mt-1 text-emerald-400">
                All good!
              </p>
            )}
          </div>
          <div className="bg-[var(--surface)] rounded-xl p-4 border border-[var(--surface-light)]">
            <p className="text-xs text-[var(--text-muted)] uppercase tracking-wide">
              Days Left
            </p>
            <p className="text-xl font-bold mt-1">{daysLeft}</p>
            <p className="text-xs text-[var(--text-muted)]">
              in{" "}
              {new Date(year, month - 1).toLocaleString("en", {
                month: "long",
              })}
            </p>
          </div>
        </div>
      )}

      {/* Budget Rules */}
      <div className="space-y-4">
        {rules.map((item: any) => {
          const isTotalBudget = item.rule.name === "Total Budget";
          const isOtherExpenses = item.rule.name === "Other Expenses";

          return (
            <div
              key={item.rule.id}
              className={isOtherExpenses ? "opacity-60" : ""}
            >
              <BudgetProgressBar
                label={item.rule.name}
                subLabel={
                  item.rule.category !== item.rule.name
                    ? item.rule.category
                    : undefined
                }
                current={item.current_amount}
                total={item.rule.amount}
                compact={!isTotalBudget}
                onToggleExpand={() => toggleExpand(String(item.rule.id))}
                isExpanded={expandedRuleId === String(item.rule.id)}
                actions={
                  <>
                    {item.allow_edit && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setEditingRule(item.rule);
                          setIsRuleModalOpen(true);
                        }}
                        className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50/50 rounded-lg transition-all"
                        title="Edit Rule"
                      >
                        <PenSquare size={16} />
                      </button>
                    )}
                    {item.allow_delete && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          if (
                            confirm(
                              "Are you sure you want to delete this rule?",
                            )
                          ) {
                            deleteMutation.mutate(item.rule.id);
                          }
                        }}
                        className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50/50 rounded-lg transition-all"
                        title="Delete Rule"
                      >
                        <Trash2 size={16} />
                      </button>
                    )}
                  </>
                }
              >
                <TransactionCollapsibleList
                  transactions={item.data}
                  isOpen={expandedRuleId === String(item.rule.id)}
                  showActions
                  onTransactionUpdated={() =>
                    queryClient.invalidateQueries({
                      queryKey: ["budgetAnalysis"],
                    })
                  }
                  pendingRefundsMap={pendingRefundsMap}
                  refundLinksMap={refundLinksMap}
                  showSplitParentsFilter
                  includeSplitParents={includeSplitParents}
                  onIncludeSplitParentsChange={setIncludeSplitParents}
                />
              </BudgetProgressBar>
            </div>
          );
        })}
      </div>

      {/* Pending Refunds Section */}
      {analysis?.pending_refunds && (
        <PendingRefundsSection pendingRefunds={analysis.pending_refunds} />
      )}

      {/* Project Spending Summary (Moved to bottom) */}
      {project_spending &&
        project_spending.projects &&
        project_spending.projects.length > 0 && (
          <div className="pt-8 border-t border-[var(--surface-light)]">
            <h3 className="text-lg font-bold text-[var(--text-muted)] mb-4 uppercase tracking-wider text-xs">
              Project Spending
            </h3>
            <div className="space-y-4">
              {project_spending.projects.map((project: any) => (
                <BudgetProgressBar
                  key={project.category}
                  label={project.category}
                  subLabel="Project"
                  current={project.spent}
                  total={project.spent}
                  onToggleExpand={() =>
                    toggleExpand(`project_spending_${project.category}`)
                  }
                  isExpanded={
                    expandedRuleId === `project_spending_${project.category}`
                  }
                >
                  <TransactionCollapsibleList
                    transactions={project.transactions}
                    isOpen={
                      expandedRuleId === `project_spending_${project.category}`
                    }
                    showActions
                    onTransactionUpdated={() =>
                      queryClient.invalidateQueries({
                        queryKey: ["budgetAnalysis"],
                      })
                    }
                    pendingRefundsMap={pendingRefundsMap}
                    refundLinksMap={refundLinksMap}
                  />
                </BudgetProgressBar>
              ))}
            </div>
          </div>
        )}

      {/* Modals */}
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
