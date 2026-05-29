import React from "react";
import { useTranslation } from "react-i18next";
import { ChevronLeft, ChevronRight, Plus } from "lucide-react";
import i18n from "../../i18n";

interface MonthHeaderProps {
  monthLabel: string;
  isCurrentMonth: boolean;
  onPrev: () => void;
  onNext: () => void;
  onToday: () => void;
  onAddRule: () => void;
}

/** Month navigation + add-rule control. */
export const MonthHeader: React.FC<MonthHeaderProps> = ({
  monthLabel,
  isCurrentMonth,
  onPrev,
  onNext,
  onToday,
  onAddRule,
}) => {
  const { t } = useTranslation();
  const isRtl = i18n.language === "he";

  const navButton =
    "p-2 rounded-lg text-[var(--text-muted)] hover:text-[var(--text-default)] hover:bg-[var(--surface-light)] transition-colors";

  return (
    <div className="bg-[var(--surface)] p-3 md:p-4 rounded-2xl shadow-sm border border-[var(--surface-light)] flex items-center justify-between gap-3">
      <div className="flex items-center gap-1 md:gap-2">
        <div className="flex items-center rounded-xl border border-[var(--surface-light)] bg-[var(--surface-light)]/30">
          <button onClick={onPrev} aria-label={t("common.previous")} className={navButton}>
            {isRtl ? <ChevronRight size={20} /> : <ChevronLeft size={20} />}
          </button>
          <h2 className="px-1 text-center text-base md:text-lg font-semibold text-[var(--text-default)] w-32 md:w-44 select-none">
            {monthLabel}
          </h2>
          <button onClick={onNext} aria-label={t("common.next")} className={navButton}>
            {isRtl ? <ChevronLeft size={20} /> : <ChevronRight size={20} />}
          </button>
        </div>
        {!isCurrentMonth && (
          <button
            onClick={onToday}
            title={t("budget.currentMonth")}
            className="inline-flex items-center px-2.5 py-1.5 text-xs font-medium text-[var(--primary)] bg-[var(--primary)]/10 hover:bg-[var(--primary)]/20 rounded-lg transition-colors"
          >
            {t("common.today")}
          </button>
        )}
      </div>

      <button
        onClick={onAddRule}
        className="inline-flex items-center justify-center gap-2 px-3 md:px-4 py-2 text-xs md:text-sm bg-[var(--primary)] text-white rounded-lg hover:bg-[var(--primary-dark)] transition-colors shadow-sm font-medium"
      >
        <Plus size={18} className="shrink-0" />
        {t("budget.addRule")}
      </button>
    </div>
  );
};
