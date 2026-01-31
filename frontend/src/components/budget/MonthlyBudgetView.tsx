import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ChevronLeft,
  ChevronRight,
  Plus,
  PenSquare,
  Trash2,
  Copy,
} from "lucide-react";
import { budgetApi } from "../../services/api";
import { BudgetProgressBar } from "../BudgetProgressBar";
import { BudgetRuleModal } from "../modals/BudgetRuleModal";
import { TransactionCollapsibleList } from "./TransactionCollapsibleList";
import { PendingRefundsSection } from "./PendingRefundsSection";

export const MonthlyBudgetView: React.FC = () => {
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [isRuleModalOpen, setIsRuleModalOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<any>(null);
  const [expandedRuleId, setExpandedRuleId] = useState<string | null>(null);

  const queryClient = useQueryClient();

  const { data: analysis, isLoading } = useQuery({
    queryKey: ["budgetAnalysis", year, month],
    queryFn: () => budgetApi.getAnalysis(year, month).then((res) => res.data),
  });

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
      <div className="p-8 text-center text-[var(--text-muted)]">
        Loading budget data...
      </div>
    );

  const { rules = [], project_spending } = analysis || {};

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

      {/* Budget Rules */}
      <div className="space-y-4">
        {rules.map((item: any) => (
          <BudgetProgressBar
            key={item.rule.id}
            label={item.rule.name}
            subLabel={
              item.rule.category !== item.rule.name
                ? item.rule.category
                : undefined
            }
            current={item.current_amount}
            total={item.rule.amount}
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
                        confirm("Are you sure you want to delete this rule?")
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
                queryClient.invalidateQueries({ queryKey: ["budgetAnalysis"] })
              }
            />
          </BudgetProgressBar>
        ))}
      </div>

      {/* Pending Refunds Section */}
      {analysis?.pending_refunds && (
        <PendingRefundsSection
          pendingRefunds={analysis.pending_refunds}
          year={year}
          month={month}
        />
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
