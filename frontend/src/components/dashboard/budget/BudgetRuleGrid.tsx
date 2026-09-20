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
 * One envelope per line, scrolling inside whatever height the card's row allows.
 *
 * Replaces the two-column tile (name + percentage pill, figures, full-width
 * bar, remaining — four stacked rows per rule, ~110px) with a single line per
 * rule in one column. The tile spent its height on layout rather than signal:
 * four rules filled the box, so the card showed a quarter of a typical month's
 * envelopes. The same box now holds roughly eight. Nothing was dropped — name,
 * spend, ceiling, bar, remaining and percentage all still render; the
 * percentage moved out of its colored pill and rides the remaining figure as a
 * muted suffix, since the color already says how close the envelope is.
 *
 * The four cells sit on a `subgrid`, so the bar, the figures and the
 * remainder line up down the whole list instead of each row sizing its own
 * columns — a column of ragged figures is the thing that makes a dense list
 * hard to scan. The name column (`minmax(0,1fr)`) absorbs the slack and
 * truncates, with the full name on hover.
 *
 * Below `sm:` the percentage suffix is dropped: a phone-width card cannot fit
 * the whole line, and the percentage is the one part the bar already draws.
 * The word ("left" / "over") stays at every width — an unlabelled trailing
 * figure beside "spent / budget" is a guess.
 *
 * `flex-1` rather than a fixed height: the dashboard grid stretches half-cards
 * to their row-mate, so a pinned height turns reclaimed space into padding on
 * desktop. The explicit `min-h-[16rem]` does double duty — it overrides a flex
 * child's default `min-height: auto` (without which the grid refuses to shrink
 * below its content and never scrolls) and sets the floor that keeps a short
 * row from crushing it. Do not add `min-h-0` alongside it: both compile to
 * `min-height` and the winner would come down to stylesheet order.
 *
 * `max-h-[16rem] lg:max-h-none` bounds the same box below `lg`: the dashboard
 * row only gets a definite height at `lg` (Dashboard.tsx's `--dash-card-h`
 * cap is `lg:`-scoped), so below that breakpoint the flex parent's height is
 * indefinite and `flex-1` has nothing to fill — the list would otherwise grow
 * to its full content (every rule, no scroll). Capping it below `lg` restores
 * the scrolling box; `lg:max-h-none` hands control back to `flex-1` once the
 * parent height is definite again.
 */
export const BudgetRuleGrid: React.FC<BudgetRuleGridProps> = ({
  rules,
  categoryIcons,
}) => {
  const { t } = useTranslation();
  return (
    <div
      data-testid="budget-rule-grid"
      className="flex-1 min-h-[16rem] max-h-[16rem] lg:max-h-none overflow-y-auto scrollbar-auto-hide mb-4"
    >
      <div className="grid grid-cols-[minmax(0,1fr)_auto_auto_auto] gap-y-1">
        {rules.map((rule) => {
          // budget_amount can be 0 (e.g., "Other Expenses" when the user has
          // allocated their full Total Budget across explicit rules). Treat any
          // spend in a zero-budget rule as fully over budget so the bar fills
          // rose instead of staying empty.
          const isUnbudgetedSpend =
            rule.budget_amount <= 0 && rule.spent_amount > 0;
          // A net refund leaves the envelope negative. That is not spending:
          // the bar floors at empty and the percentage reads 0%, rather than
          // a negative width the browser drops and a "-19%" nobody can act on.
          const spent = Math.max(rule.spent_amount, 0);
          const pct =
            rule.budget_amount > 0
              ? (spent / rule.budget_amount) * 100
              : isUnbudgetedSpend
                ? 100
                : 0;
          const remaining = rule.budget_amount - rule.spent_amount;
          const over = remaining < 0;
          const icon = categoryIcons?.[rule.category] ?? "";
          return (
            <div
              key={rule.id}
              data-testid="budget-rule-row"
              className="col-span-4 grid grid-cols-subgrid items-center gap-2 sm:gap-3 rounded-lg bg-[var(--surface-light)] px-2.5 py-2"
            >
              <span className="flex min-w-0 items-center gap-1.5">
                {icon && <span className="text-sm flex-shrink-0">{icon}</span>}
                <span
                  className="text-xs font-semibold truncate"
                  dir="auto"
                  title={rule.name}
                >
                  {rule.name}
                </span>
              </span>

              <span className="h-1.5 w-8 sm:w-20 rounded-full bg-[var(--surface)] overflow-hidden">
                <span
                  className={`block h-full rounded-full transition-all ${getProgressColor(pct, isUnbudgetedSpend)}`}
                  style={{ width: `${Math.min(pct, 100)}%` }}
                />
              </span>

              <span className="text-xs font-bold tabular-nums text-end">
                {formatCurrency(rule.spent_amount)}
                <span className="text-[10px] font-normal text-[var(--text-muted)]">
                  {" "}
                  / {formatCurrency(rule.budget_amount)}
                </span>
              </span>

              <span
                className={`text-[10px] font-medium tabular-nums text-end ${
                  over ? "text-rose-400" : "text-[var(--text-muted)]"
                }`}
              >
                {over
                  ? t("budget.overByAmount", {
                      amount: formatCurrency(Math.abs(remaining)),
                    })
                  : t("budget.leftAmount", {
                      amount: formatCurrency(remaining),
                    })}
                <span className="hidden text-[var(--text-muted)] sm:inline">
                  {" "}
                  · {Math.round(pct)}%
                </span>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};
