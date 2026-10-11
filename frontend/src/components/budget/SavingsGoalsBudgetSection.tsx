import { useTranslation } from "react-i18next";
import { Target } from "lucide-react";
import type { SavingsGoalMonth } from "../../services/api";
import { formatChange, formatCurrency } from "../../utils/numberFormatting";

/**
 * How each savings goal moved during the month: money put in by hand, income
 * its saved-into rule brought in, and spending paid out of it.
 *
 * Sits below the budget ledger rather than inside it: a goal is money set
 * aside, not a spending rule, so it must not read as another budget rule
 * competing for the same shekels.
 *
 * The data arrives on the monthly analysis payload instead of a query of its
 * own — the budget page already refetches that analysis on every change, and
 * a second per-month request only added another straggler to each refresh.
 */
export function SavingsGoalsBudgetSection({ month }: { month?: SavingsGoalMonth }) {
  const { t } = useTranslation();

  // Nothing to say when the user keeps no goals, or none moved this month.
  if (!month || month.goals.length === 0) return null;

  return (
    <div
      className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] p-4 md:p-6"
      data-testid="budget-goals-month"
    >
      <div className="flex items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-2 min-w-0">
          <div className="p-1.5 rounded-lg bg-[var(--primary)]/15 text-[var(--primary)]">
            <Target size={16} />
          </div>
          <p className="text-sm md:text-base font-bold truncate">{t("budget.goals.title")}</p>
        </div>
        <span
          className={`text-xs md:text-sm font-bold tabular-nums shrink-0 ${
            month.total_change < 0 ? "text-amber-400" : ""
          }`}
        >
          {formatChange(month.total_change, { compact: false })}
        </span>
      </div>

      <div className="space-y-2">
        {month.goals.map((row) => (
          <div
            key={row.goal_id}
            className="flex items-center justify-between gap-2 text-sm border border-[var(--surface-light)] rounded-lg px-3 py-2"
          >
            <div className="min-w-0">
              <div className="flex items-center gap-1.5 min-w-0">
                <span className="text-[10px] font-bold text-[var(--text-muted)] tabular-nums shrink-0" dir="ltr">
                  #{row.priority + 1}
                </span>
                <span className="truncate" dir="auto" title={row.name}>{row.name}</span>
              </div>
              <div className="flex flex-wrap gap-x-2 text-[10px] md:text-xs text-[var(--text-muted)]">
                {row.added !== 0 && (
                  <span>{t("budget.goals.added", { amount: formatCurrency(row.added) })}</span>
                )}
                {row.income !== 0 && (
                  <span>{t("budget.goals.income", { amount: formatCurrency(row.income) })}</span>
                )}
                {row.spent !== 0 && (
                  <span>{t("budget.goals.spent", { amount: formatCurrency(row.spent) })}</span>
                )}
              </div>
            </div>
            <span
              className={`font-semibold tabular-nums shrink-0 ${
                row.change < 0 ? "text-amber-400" : ""
              }`}
            >
              {formatChange(row.change, { compact: false })}
            </span>
          </div>
        ))}
      </div>

      <div className="mt-3 pt-3 border-t border-[var(--surface-light)] text-xs text-[var(--text-muted)]">
        {t("budget.goals.totalAdded", { amount: formatCurrency(month.total_added) })}
      </div>
    </div>
  );
}
