import React from "react";
import { useTranslation } from "react-i18next";
import { ChevronLeft, ChevronRight, Plus, Copy } from "lucide-react";
import i18n from "../../i18n";

interface MonthHeaderProps {
  monthLabel: string;
  isCurrentMonth: boolean;
  replicatePending: boolean;
  onPrev: () => void;
  onNext: () => void;
  onToday: () => void;
  onReplicate: () => void;
  onAddRule: () => void;
}

/** Month navigation + replicate-previous-month + add-rule controls. */
export const MonthHeader: React.FC<MonthHeaderProps> = ({
  monthLabel,
  isCurrentMonth,
  replicatePending,
  onPrev,
  onNext,
  onToday,
  onReplicate,
  onAddRule,
}) => {
  const { t } = useTranslation();
  const isRtl = i18n.language === "he";

  return (
    <div className="bg-[var(--surface)] p-4 rounded-2xl shadow-sm border border-[var(--surface-light)] flex flex-col md:flex-row md:items-center md:justify-between gap-3">
      <div className="flex items-center justify-center md:justify-start gap-1 md:gap-2">
        <button
          onClick={onPrev}
          aria-label={t("common.previous")}
          className="p-2 hover:bg-[var(--surface-light)] rounded-full text-[var(--text-muted)] hover:text-[var(--text-default)] transition-colors"
        >
          {isRtl ? <ChevronRight size={24} /> : <ChevronLeft size={24} />}
        </button>
        <h2 className="text-lg md:text-2xl font-bold w-36 md:w-48 text-center bg-gradient-to-r from-[var(--primary)] to-blue-600 bg-clip-text text-transparent">
          {monthLabel}
        </h2>
        <button
          onClick={onNext}
          aria-label={t("common.next")}
          className="p-2 hover:bg-[var(--surface-light)] rounded-full text-[var(--text-muted)] hover:text-[var(--text-default)] transition-colors"
        >
          {isRtl ? <ChevronLeft size={24} /> : <ChevronRight size={24} />}
        </button>
        {!isCurrentMonth && (
          <button
            onClick={onToday}
            title={t("budget.currentMonth")}
            className="ms-1 md:ms-2 inline-flex items-center px-2.5 py-1 text-xs font-medium text-[var(--primary)] bg-[var(--primary)]/10 hover:bg-[var(--primary)]/20 rounded-full transition-colors"
          >
            {t("common.today")}
          </button>
        )}
      </div>
      <div className="grid grid-cols-2 gap-2 md:flex md:items-center md:gap-2">
        <button
          onClick={onReplicate}
          disabled={replicatePending}
          className="inline-flex items-center justify-center gap-2 px-3 md:px-4 py-2 text-xs md:text-sm bg-[var(--surface)] border border-[var(--surface-light)] text-[var(--text-default)] rounded-lg hover:bg-[var(--surface-light)] transition-colors shadow-sm font-medium disabled:opacity-50"
        >
          <Copy size={18} className="shrink-0" />
          <span className="truncate md:hidden">
            {t("budget.replicatePreviousMonthShort")}
          </span>
          <span className="truncate hidden md:inline">
            {t("budget.replicatePreviousMonth")}
          </span>
        </button>
        <button
          onClick={onAddRule}
          className="inline-flex items-center justify-center gap-2 px-3 md:px-4 py-2 text-xs md:text-sm bg-[var(--primary)] text-white rounded-lg hover:bg-[var(--primary-dark)] transition-colors shadow-lg shadow-[var(--primary)]/20 font-medium"
        >
          <Plus size={18} className="shrink-0" />
          {t("budget.addRule")}
        </button>
      </div>
    </div>
  );
};
