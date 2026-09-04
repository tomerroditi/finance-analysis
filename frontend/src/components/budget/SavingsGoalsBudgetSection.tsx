import { useTranslation } from "react-i18next";
import { Target, Info } from "lucide-react";
import type { SavingsGoalMonthAllocations } from "../../services/api";
import { formatCurrency } from "../../utils/numberFormatting";

/**
 * Where the month's leftover money went.
 *
 * Sits below the budget ledger rather than inside it: a goal is an earmark
 * over money that survived the month's spending, not a spending envelope, so
 * it must not read as another budget rule competing for the same shekels.
 *
 * The data arrives on the monthly analysis payload instead of a query of its
 * own — the budget page already refetches that analysis on every change, and
 * a second per-month request only added another straggler to each refresh.
 */
export function SavingsGoalsBudgetSection({
  allocations,
}: {
  allocations?: SavingsGoalMonthAllocations;
}) {
  const { t } = useTranslation();

  // Nothing to say when the user keeps no goals, or none were funded.
  if (!allocations || allocations.goals.length === 0) return null;

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] p-4 md:p-6">
      <div className="flex items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-[var(--primary)]/15 text-[var(--primary)]">
            <Target size={16} />
          </div>
          <p className="text-sm md:text-base font-bold">{t("budget.goals.title")}</p>
          {!!allocations.is_provisional && (
            <span
              className="flex items-center gap-1 text-[10px] md:text-xs font-medium text-[var(--text-muted)] bg-[var(--surface-light)] rounded-full px-2 py-0.5"
              title={t("budget.goals.provisionalHint")}
            >
              <Info size={11} />
              {t("budget.goals.provisional")}
            </span>
          )}
        </div>
        <span dir="ltr" className="text-xs md:text-sm font-bold tabular-nums">
          {formatCurrency(allocations.total_allocated)}
        </span>
      </div>

      <div className="space-y-2">
        {allocations.goals.map((row) => (
          <div
            key={row.goal_id}
            className="flex items-center justify-between gap-2 text-sm border border-[var(--surface-light)] rounded-lg px-3 py-2"
          >
            <div className="flex items-center gap-1.5 min-w-0">
              <span className="text-[10px] font-bold text-[var(--text-muted)] tabular-nums shrink-0" dir="ltr">
                #{row.priority + 1}
              </span>
              <span className="truncate" dir="auto" title={row.name}>{row.name}</span>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {row.contributed > 0 && (
                <span className="text-[10px] md:text-xs text-[var(--text-muted)]" dir="ltr">
                  {t("budget.goals.contributed", {
                    amount: formatCurrency(row.contributed),
                  })}
                </span>
              )}
              <span dir="ltr" className="font-semibold tabular-nums">
                {formatCurrency(row.total)}
              </span>
            </div>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap justify-between gap-x-4 gap-y-1 mt-3 pt-3 border-t border-[var(--surface-light)] text-xs text-[var(--text-muted)]">
        <span>
          {t("budget.goals.surplus", { amount: formatCurrency(allocations.surplus) })}
        </span>
        <span>
          {t("budget.goals.unallocated", {
            amount: formatCurrency(allocations.unallocated),
          })}
        </span>
      </div>
    </div>
  );
}
