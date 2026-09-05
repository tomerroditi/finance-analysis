import React from "react";
import { useTranslation } from "react-i18next";
import { formatCurrency } from "../../../utils/numberFormatting";
import type { BudgetRule } from "./types";

interface BudgetRuleGridProps {
  rules: BudgetRule[];
  categoryIcons: Record<string, string> | undefined;
}

function getProgressColor(pct: number, isUnbudgetedSpend: boolean): string {
  if (isUnbudgetedSpend || pct > 100) return "bg-rose-500";
  if (pct >= 75) return "bg-amber-500";
  return "bg-emerald-500";
}

/**
 * Per-category tiles, scrolling inside whatever height the card's row allows.
 *
 * `flex-1` rather than a fixed height: the dashboard grid stretches half-cards
 * to their row-mate, so a pinned height turns reclaimed space into padding on
 * desktop. The explicit `min-h-[16rem]` does double duty — it overrides a flex
 * child's default `min-height: auto` (without which the grid refuses to shrink
 * below its content and never scrolls) and sets the four-tile floor that keeps
 * a short row, or the content-sized single-column mobile grid, from crushing
 * it. Do not add `min-h-0` alongside it: both compile to `min-height` and the
 * winner would come down to stylesheet order.
 */
export const BudgetRuleGrid: React.FC<BudgetRuleGridProps> = ({
  rules,
  categoryIcons,
}) => {
  const { t } = useTranslation();
  return (
    <div
      data-testid="budget-rule-grid"
      className="flex-1 min-h-[16rem] overflow-y-auto scrollbar-auto-hide mb-4"
    >
      <div className="grid grid-cols-2 gap-3">
        {rules.map((rule) => {
          // budget_amount can be 0 (e.g., "Other Expenses" when the user has
          // allocated their full Total Budget across explicit rules). Treat any
          // spend in a zero-budget rule as fully over budget so the bar fills
          // rose instead of staying empty.
          const isUnbudgetedSpend = rule.budget_amount <= 0 && rule.spent_amount > 0;
          const pct =
            rule.budget_amount > 0
              ? (rule.spent_amount / rule.budget_amount) * 100
              : isUnbudgetedSpend
                ? 100
                : 0;
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
                  <span className="text-xs font-semibold truncate" dir="auto">
                    {rule.name}
                  </span>
                </div>
                <span
                  className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full flex-shrink-0 ${
                    isUnbudgetedSpend || pct > 100
                      ? "bg-rose-500/20 text-rose-400"
                      : pct >= 75
                        ? "bg-amber-500/20 text-amber-400"
                        : "bg-emerald-500/20 text-emerald-400"
                  }`}
                >
                  {Math.round(pct)}%
                </span>
              </div>
              <p className="text-sm font-bold">
                {formatCurrency(rule.spent_amount)}
                <span className="text-xs font-normal text-[var(--text-muted)]">
                  {" "}
                  / {formatCurrency(rule.budget_amount)}
                </span>
              </p>
              <div className="h-1.5 w-full rounded-full bg-[var(--surface)] overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${getProgressColor(pct, isUnbudgetedSpend)}`}
                  style={{ width: `${Math.min(pct, 100)}%` }}
                />
              </div>
              <p
                className={`text-[10px] font-medium ${
                  remaining >= 0 ? "text-[var(--text-muted)]" : "text-rose-400"
                }`}
              >
                {remaining >= 0
                  ? `${formatCurrency(remaining)} ${t("budget.remaining").toLowerCase()}`
                  : `${formatCurrency(Math.abs(remaining))} ${t("budget.overBudget").toLowerCase()}`}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
};
