import React, { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import { ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { budgetApi, type YearlyAnalysis } from "../../../services/api";
import { BudgetTotalBar } from "../../common/BudgetTotalBar";
import { Skeleton } from "../../common/Skeleton";
import { YearlyRuleModal } from "../../modals/YearlyRuleModal";
import { useConfirm, useNotify } from "../../../context/DialogContext";
import { useQueryKeys } from "../../../hooks/useQueryKeys";
import { qkPrefix } from "../../../services/queryKeys";
import { BudgetRuleGrid } from "./BudgetRuleGrid";
import { RuleRowAction } from "./RuleRowAction";
import type { BudgetRule } from "./types";
import { budgetLink } from "../../../utils/budgetNavigation";

interface YearlyBudgetTabProps {
  year: number;
  onYearChange: (year: number) => void;
  categoryIcons: Record<string, string> | undefined;
}

export const YearlyBudgetTab: React.FC<YearlyBudgetTabProps> = ({
  year,
  onYearChange,
  categoryIcons,
}) => {
  const { t, i18n } = useTranslation();
  const isRtl = i18n.language === "he";
  const confirm = useConfirm();
  const notify = useNotify();
  const qk = useQueryKeys();
  const queryClient = useQueryClient();
  const [editRule, setEditRule] = useState<
    YearlyAnalysis["rules"][number]["rule"] | null
  >(null);

  const { data, isLoading } = useQuery({
    queryKey: qk.budget.yearly(year),
    queryFn: () => budgetApi.getYearlyAnalysis(year).then((r) => r.data as YearlyAnalysis),
  });

  // The whole budget prefix, not just this year's key: the card's own
  // Overview tab builds its envelope list from these rules and their closed
  // flag, so it has to refetch too.
  const invalidateBudget = () =>
    queryClient.invalidateQueries({ queryKey: qkPrefix.budget });

  const closedMutation = useMutation({
    mutationFn: ({ id, closed }: { id: number; closed: boolean }) =>
      budgetApi.setYearlyRuleClosed(id, closed),
    onSuccess: invalidateBudget,
    onError: () => notify.error(t("budget.yearly.closeFailed")),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => budgetApi.deleteYearlyRule(id),
    onSuccess: invalidateBudget,
    onError: () => notify.error(t("budget.yearly.deleteFailed")),
  });

  // Reopening is a plain undo, so only closing asks first — same as the
  // Budget page's yearly tab.
  const handleToggleClosed = async (rule: BudgetRule) => {
    if (rule.closed) {
      closedMutation.mutate({ id: rule.id, closed: false });
      return;
    }
    const ok = await confirm({
      title: t("budget.yearly.closeRule"),
      message: t("budget.yearly.confirmClose", { name: rule.name }),
      confirmLabel: t("budget.yearly.closeRule"),
    });
    if (ok) closedMutation.mutate({ id: rule.id, closed: true });
  };

  const handleDelete = async (rule: BudgetRule) => {
    const ok = await confirm({
      title: t("budget.deleteRule"),
      message: t("budget.yearly.confirmDelete", { name: rule.name }),
      confirmLabel: t("common.delete"),
      isDestructive: true,
    });
    if (ok) deleteMutation.mutate(rule.id);
  };

  // The grid renders the normalized row shape; editing and the permission
  // flags need the analysis entry the row was built from.
  const entryById = useMemo(
    () => new Map((data?.rules ?? []).map((item) => [item.rule.id, item])),
    [data],
  );

  const renderRowActions = (rule: BudgetRule) => {
    const entry = entryById.get(rule.id);
    return (
      <>
        <RuleRowAction
          kind="edit"
          label={t("budget.editRule")}
          testId={`card-rule-edit-${rule.id}`}
          onClick={
            entry?.allow_edit ? () => setEditRule(entry.rule) : undefined
          }
        />
        <RuleRowAction
          kind={rule.closed ? "reopen" : "close"}
          label={
            rule.closed
              ? t("budget.yearly.reopenRule")
              : t("budget.yearly.closeRule")
          }
          testId={`card-rule-closed-toggle-${rule.id}`}
          onClick={
            closedMutation.isPending
              ? undefined
              : () => handleToggleClosed(rule)
          }
        />
        <RuleRowAction
          kind="delete"
          label={t("budget.deleteRule")}
          testId={`card-rule-delete-${rule.id}`}
          onClick={
            entry?.allow_delete ? () => handleDelete(rule) : undefined
          }
        />
      </>
    );
  };

  // Yearly analysis emits no "Total Budget" pseudo-rule — the roll-up sums the
  // view — so every row here is a real rule and the totals come from summary.
  //
  // Closed envelopes sink below the open ones: they are kept for their
  // history, and leaving a settled commitment among the ones still being
  // spent from is exactly the noise closing removes. Within each group the
  // heaviest spend leads, as before.
  const rules: BudgetRule[] = useMemo(
    () =>
      (data?.rules ?? [])
        .map((item) => ({
          id: item.rule.id,
          name: item.rule.name,
          category: item.rule.category,
          budget_amount: item.rule.amount,
          spent_amount: item.current_amount,
          closed: item.closed,
        }))
        .sort(
          (a, b) =>
            Number(a.closed) - Number(b.closed) ||
            b.spent_amount - a.spent_amount,
        ),
    [data],
  );

  const nav = (
    <div className="h-9 flex items-center w-full mb-4">
      <div className="flex items-center gap-2">
        <button
          onClick={() => onYearChange(year - 1)}
          aria-label={t("common.previous")}
          className="p-1 rounded-lg hover:bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
        >
          {isRtl ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
        <p
          className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)] w-36 text-center"
          dir="ltr"
        >
          {year}
        </p>
        <button
          onClick={() => onYearChange(year + 1)}
          aria-label={t("common.next")}
          className="p-1 rounded-lg hover:bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
        >
          {isRtl ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
        </button>
      </div>
    </div>
  );

  if (isLoading) {
    return (
      <div className="flex flex-1 flex-col min-h-0">
        {nav}
        <Skeleton variant="chart" className="h-16" />
      </div>
    );
  }

  // Editing is reached from a row, so the modal only ever opens where rows
  // exist — but it is rendered beside both returns so a delete that empties
  // the year cannot unmount it mid-flight.
  const modal = (
    <YearlyRuleModal
      isOpen={editRule !== null}
      onClose={() => setEditRule(null)}
      year={year}
      editRule={editRule}
    />
  );

  if (rules.length === 0) {
    return (
      <div className="flex flex-1 flex-col min-h-0">
        {nav}
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <p className="text-sm text-[var(--text-muted)] mb-3">{t("budget.yearly.empty")}</p>
          <Link
            to={budgetLink("yearly", { year })}
            className="flex items-center gap-2 text-sm font-medium text-[var(--primary)] hover:text-[var(--primary-dark)] transition-colors cursor-pointer"
          >
            <Plus size={16} />
            {t("budget.yearly.addRule")}
          </Link>
        </div>
        {modal}
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col min-h-0">
      {nav}
      <div className="mb-4">
        <BudgetTotalBar
          spent={data?.summary.total_spent ?? 0}
          total={data?.summary.total_allocated ?? 0}
        />
      </div>
      <BudgetRuleGrid
        rules={rules}
        categoryIcons={categoryIcons}
        renderRowActions={renderRowActions}
      />
      <div className="text-end">
        <Link
          to={budgetLink("yearly", { year })}
          className="text-sm font-medium text-[var(--primary)] hover:underline"
        >
          {t("dashboard.viewAllBudgetRules")} &rarr;
        </Link>
      </div>
      {modal}
    </div>
  );
};
