import React from "react";
import { useTranslation } from "react-i18next";
import { formatCurrency } from "../../utils/numberFormatting";
import type { YearlyRollup } from "../../services/api";

interface Props {
  summary: YearlyRollup;
}

/** Computed, display-only roll-up tiles for the yearly view. */
export const YearlySummaryStrip: React.FC<Props> = ({ summary }) => {
  const { t } = useTranslation();
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 md:gap-3">
      <div className="bg-[var(--surface)] rounded-xl p-3 border border-[var(--surface-light)]">
        <p className="text-[10px] sm:text-xs text-[var(--text-muted)] uppercase tracking-wide truncate">
          {t("budget.yearly.allocated")}
        </p>
        <p className="text-lg md:text-xl font-bold mt-1">{formatCurrency(summary.total_allocated)}</p>
      </div>
      <div className="bg-[var(--surface)] rounded-xl p-3 border border-[var(--surface-light)]">
        <p className="text-[10px] sm:text-xs text-[var(--text-muted)] uppercase tracking-wide truncate">
          {t("budget.yearly.spentYtd")}
        </p>
        <p className="text-lg md:text-xl font-bold mt-1">{formatCurrency(summary.total_spent)}</p>
      </div>
      <div className="bg-[var(--surface)] rounded-xl p-3 border border-[var(--surface-light)]">
        <p className="text-[10px] sm:text-xs text-[var(--text-muted)] uppercase tracking-wide truncate">
          {t("budget.yearly.remaining")}
        </p>
        <p className={`text-lg md:text-xl font-bold mt-1 ${summary.remaining < 0 ? "text-rose-400" : "text-emerald-400"}`}>
          {formatCurrency(summary.remaining)}
        </p>
      </div>
      <div className="bg-[var(--surface)] rounded-xl p-3 border border-[var(--surface-light)]">
        <p className="text-[10px] sm:text-xs text-[var(--text-muted)] uppercase tracking-wide truncate">
          {t("budget.yearly.health")}
        </p>
        <div className="flex items-baseline gap-1 mt-1 flex-wrap">
          <span className="text-lg md:text-xl font-bold text-emerald-400">{summary.on_track}</span>
          <span className="text-[10px] sm:text-xs text-[var(--text-muted)]">{t("budget.onTrackLabel")}</span>
          {summary.over > 0 && (
            <>
              <span className="text-[10px] sm:text-xs text-[var(--text-muted)]">·</span>
              <span className="text-lg md:text-xl font-bold text-rose-400">{summary.over}</span>
              <span className="text-[10px] sm:text-xs text-[var(--text-muted)]">{t("budget.overBudgetLabel")}</span>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
