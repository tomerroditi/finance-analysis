import React from "react";
import { useTranslation } from "react-i18next";
import { formatCurrency } from "../../utils/numberFormatting";

interface BudgetSummaryStripProps {
  totalSpent: number;
  totalBudget: number;
  onTrackCount: number;
  overCount: number;
  biggestOverspend?: { name: string; percentage: number };
  daysLeft: number;
  monthLabel: string;
}

/**
 * Redesigned KPI strip: one primary headline card (spent of total budget with
 * an inline progress bar) above three compact stat tiles. Pure presentation —
 * all figures are computed by the parent.
 */
export const BudgetSummaryStrip: React.FC<BudgetSummaryStripProps> = ({
  totalSpent,
  totalBudget,
  onTrackCount,
  overCount,
  biggestOverspend,
  daysLeft,
  monthLabel,
}) => {
  const { t } = useTranslation();
  const percent =
    totalBudget > 0 ? Math.min((totalSpent / totalBudget) * 100, 100) : 0;
  const over = totalSpent > totalBudget && totalBudget > 0;
  const near = !over && totalBudget > 0 && totalSpent > totalBudget * 0.9;
  const barColor = over ? "bg-rose-500" : near ? "bg-amber-500" : "bg-emerald-500";
  const remaining = totalBudget - totalSpent;

  return (
    <div className="space-y-3">
      {/* Primary headline card */}
      <div className="bg-[var(--surface)] rounded-2xl p-4 md:p-5 border-s-4 border-[var(--primary)] border border-[var(--surface-light)] shadow-sm">
        <div className="flex items-end justify-between gap-3 flex-wrap">
          <div>
            <p className="text-[10px] sm:text-xs text-[var(--text-muted)] uppercase tracking-wide">
              {t("budget.totalSpent")}
            </p>
            <p className="text-2xl md:text-3xl font-bold mt-0.5" dir="ltr">
              {formatCurrency(totalSpent)}
            </p>
            <p className="text-xs text-[var(--text-muted)] mt-0.5">
              {t("budget.ofBudget", { amount: formatCurrency(totalBudget) })}
            </p>
          </div>
          <p
            className={`text-sm font-semibold ${
              over ? "text-rose-400" : "text-[var(--text-muted)]"
            }`}
          >
            {totalBudget > 0
              ? over
                ? t("budget.overByAmount", {
                    amount: formatCurrency(Math.abs(remaining)),
                  })
                : t("budget.remainingAmount", {
                    amount: formatCurrency(remaining),
                  })
              : null}
          </p>
        </div>
        <div className="w-full bg-[var(--surface-light)] rounded-full h-2.5 overflow-hidden mt-3">
          <div
            className={`h-2.5 rounded-full ${barColor} transition-all duration-500 ease-out`}
            style={{ width: `${percent}%` }}
          />
        </div>
      </div>

      {/* Compact stat tiles */}
      <div className="grid grid-cols-3 gap-2 md:gap-3">
        <div className="bg-[var(--surface)] rounded-xl p-3 border border-[var(--surface-light)]">
          <p className="text-[10px] sm:text-xs text-[var(--text-muted)] uppercase tracking-wide truncate">
            {t("budget.budgetHealth")}
          </p>
          <div className="flex items-baseline gap-1 mt-1 flex-wrap">
            <span className="text-lg md:text-xl font-bold text-emerald-400">
              {onTrackCount}
            </span>
            <span className="text-[10px] sm:text-xs text-[var(--text-muted)]">
              {t("budget.onTrackLabel")}
            </span>
            {overCount > 0 && (
              <>
                <span className="text-[10px] sm:text-xs text-[var(--text-muted)]">·</span>
                <span className="text-lg md:text-xl font-bold text-rose-400">
                  {overCount}
                </span>
                <span className="text-[10px] sm:text-xs text-[var(--text-muted)]">
                  {t("budget.overBudgetLabel")}
                </span>
              </>
            )}
          </div>
        </div>

        <div className="bg-[var(--surface)] rounded-xl p-3 border border-[var(--surface-light)]">
          <p className="text-[10px] sm:text-xs text-[var(--text-muted)] uppercase tracking-wide truncate">
            {t("budget.biggestOverspend")}
          </p>
          {biggestOverspend ? (
            <>
              <p className="text-sm md:text-base font-bold mt-1 text-rose-400 truncate" dir="auto">
                {biggestOverspend.name}
              </p>
              <p className="text-[10px] sm:text-xs text-[var(--text-muted)]" dir="ltr">
                {Math.round(biggestOverspend.percentage * 100)}%
              </p>
            </>
          ) : (
            <p className="text-sm md:text-base font-bold mt-1 text-emerald-400">
              {t("budget.allGood")}
            </p>
          )}
        </div>

        <div className="bg-[var(--surface)] rounded-xl p-3 border border-[var(--surface-light)]">
          <p className="text-[10px] sm:text-xs text-[var(--text-muted)] uppercase tracking-wide truncate">
            {t("budget.daysLeft")}
          </p>
          <p className="text-lg md:text-xl font-bold mt-1">{daysLeft}</p>
          <p className="text-[10px] sm:text-xs text-[var(--text-muted)] truncate">
            {t("budget.inMonth", { month: monthLabel })}
          </p>
        </div>
      </div>
    </div>
  );
};
