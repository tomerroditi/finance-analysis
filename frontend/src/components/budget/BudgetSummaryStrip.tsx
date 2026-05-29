import React from "react";
import { useTranslation } from "react-i18next";

interface BudgetSummaryStripProps {
  onTrackCount: number;
  overCount: number;
  biggestOverspend?: { name: string; percentage: number };
  daysLeft: number;
  monthLabel: string;
}

/**
 * Quick-stat tiles for the monthly view: Budget Health, Biggest Overspend,
 * Days Left. The spent-vs-budget gauge lives on the Total Budget card, so it
 * is intentionally not duplicated here. Pure presentation.
 */
export const BudgetSummaryStrip: React.FC<BudgetSummaryStripProps> = ({
  onTrackCount,
  overCount,
  biggestOverspend,
  daysLeft,
  monthLabel,
}) => {
  const { t } = useTranslation();

  return (
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
  );
};
