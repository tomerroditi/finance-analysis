import React, { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import { ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { budgetApi, type YearlyAnalysis } from "../../../services/api";
import { BudgetTotalBar } from "../../common/BudgetTotalBar";
import { Skeleton } from "../../common/Skeleton";
import { useConfirm, useNotify } from "../../../context/DialogContext";
import { usePendingRows } from "../../../hooks/usePendingRows";
import { useQueryKeys } from "../../../hooks/useQueryKeys";
import { qkPrefix } from "../../../services/queryKeys";
import { BudgetRuleGrid } from "./BudgetRuleGrid";
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
  // Per row: one mutation serves every envelope's toggle, so its own
  // `isPending` would disable the whole list for one row's write.
  const writing = usePendingRows<number>();

  const { data, isLoading } = useQuery({
    queryKey: qk.budget.yearly(year),
    queryFn: () => budgetApi.getYearlyAnalysis(year).then((r) => r.data as YearlyAnalysis),
  });

  const closedMutation = useMutation({
    mutationFn: ({ id, closed }: { id: number; closed: boolean }) =>
      budgetApi.setYearlyRuleClosed(id, closed),
    onMutate: ({ id }) => {
      writing.begin(id);
    },
    onSettled: (_data, _error, { id }) => writing.end(id),
    onSuccess: () => {
      // The whole budget prefix: this card's own Overview tab builds its
      // envelope list from the flag, so it has to refetch too.
      queryClient.invalidateQueries({ queryKey: qkPrefix.budget });
    },
    onError: () => notify.error(t("budget.yearly.closeFailed")),
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
        onToggleClosed={handleToggleClosed}
        isTogglePending={(rule) => writing.isPending(rule.id)}
      />
      <div className="text-end">
        <Link
          to={budgetLink("yearly", { year })}
          className="text-sm font-medium text-[var(--primary)] hover:underline"
        >
          {t("dashboard.viewAllBudgetRules")} &rarr;
        </Link>
      </div>
    </div>
  );
};
