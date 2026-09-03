import React from "react";
import { useTranslation } from "react-i18next";
import { ChevronLeft, ChevronRight } from "lucide-react";
import i18n from "../../i18n";

interface PeriodNavProps {
  /** Rendered inside the `h2` — "July 2026" for a month, "2026" for a year. */
  label: React.ReactNode;
  isCurrent: boolean;
  onPrev: () => void;
  onNext: () => void;
  onToday: () => void;
  todayTitle: string;
  /** Year labels are numerals only and need an explicit LTR run under RTL. */
  ltr?: boolean;
  widthClass?: string;
}

const NAV_BUTTON =
  "p-2 rounded-lg text-[var(--text-muted)] hover:text-[var(--text-default)] hover:bg-[var(--surface-light)] transition-colors";

/** Prev / label / next, shared by the monthly and yearly command bars. */
export const PeriodNav: React.FC<PeriodNavProps> = ({
  label,
  isCurrent,
  onPrev,
  onNext,
  onToday,
  todayTitle,
  ltr = false,
  widthClass = "w-28 md:w-40",
}) => {
  const { t } = useTranslation();
  const isRtl = i18n.language === "he";

  return (
    <div className="flex items-center gap-1 md:gap-2 min-w-0">
      <div className="flex items-center min-w-0 rounded-xl border border-[var(--surface-light)] bg-[var(--surface-light)]/30">
        <button
          onClick={onPrev}
          aria-label={t("common.previous")}
          className={`${NAV_BUTTON} shrink-0`}
        >
          {isRtl ? <ChevronRight size={20} /> : <ChevronLeft size={20} />}
        </button>
        <h2
          // Fixed width keeps the arrows from jumping between months, but it
          // must still be able to shrink: at a narrow width the whole nav
          // group is otherwise un-shrinkable and pushes the page sideways.
          className={`px-1 text-center text-sm md:text-base font-semibold text-[var(--text-default)] select-none truncate max-w-full ${widthClass}`}
          {...(ltr ? { dir: "ltr" } : {})}
        >
          {label}
        </h2>
        <button
          onClick={onNext}
          aria-label={t("common.next")}
          className={`${NAV_BUTTON} shrink-0`}
        >
          {isRtl ? <ChevronLeft size={20} /> : <ChevronRight size={20} />}
        </button>
      </div>
      {!isCurrent && (
        <button
          onClick={onToday}
          title={todayTitle}
          className="inline-flex items-center px-2.5 py-1.5 text-xs font-medium text-[var(--primary)] bg-[var(--primary)]/10 hover:bg-[var(--primary)]/20 rounded-lg transition-colors whitespace-nowrap"
        >
          {t("common.today")}
        </button>
      )}
    </div>
  );
};

interface BudgetCommandBarProps {
  /** The Monthly / Yearly / Projects tab group, owned by the page. */
  tabs: React.ReactNode;
  /** Period navigation (monthly, yearly) or the project picker. */
  children?: React.ReactNode;
  /** Freshness chip, shown beside the primary action. */
  freshnessBadge?: React.ReactNode;
  /** Primary action(s) — "Add Rule", "New Project", … */
  actions?: React.ReactNode;
}

/**
 * One control row for the whole page: tabs, period navigation, freshness and
 * the primary action.
 *
 * Replaces the tab bar plus a per-tab header card (MonthHeader / YearHeader /
 * ProjectSelectorHeader), which between them cost three stacked full-width
 * blocks before any budget figure appeared.
 *
 * On mobile the bar stacks: tabs scroll on their own row (they must never
 * squish — see frontend_responsive.md → "Tab Bars & Button Groups"), controls
 * follow underneath.
 */
export const BudgetCommandBar: React.FC<BudgetCommandBarProps> = ({
  tabs,
  children,
  freshnessBadge,
  actions,
}) => (
  /* `flex-wrap` on the row layout as well as the column one: the bar packs
     tabs + period nav + actions onto a single line from `md:` up, and at the
     narrow end of that range (or while the sidebar margin animates after a
     resize) they don't fit. Without wrapping, the bar grows past `main` and
     scrolls the page sideways. */
  <div className="bg-[var(--surface)] p-2 md:p-3 rounded-2xl shadow-sm border border-[var(--surface-light)] flex flex-col md:flex-row md:flex-wrap md:items-center gap-2 md:gap-3">
    {/* `max-w-full` matters as much as the scroll container: with `md:w-auto`
        alone the strip is content-sized, so at a width where the labels don't
        fit (including mid-transition, while the sidebar margin animates) it
        grows past its parent and scrolls the page instead of itself. */}
    <div className="flex w-full md:w-auto max-w-full min-w-0 gap-1 bg-[var(--surface-light)]/40 p-1 rounded-xl overflow-x-auto scrollbar-auto-hide">
      {tabs}
    </div>

    {/* `flex-wrap` is load-bearing: period nav + freshness chip + the primary
        action are all `whitespace-nowrap`, so without it they push the bar —
        and the whole page — past a 375px viewport. */}
    <div className="flex flex-wrap items-center justify-between md:justify-start gap-2 md:gap-3 flex-1 min-w-0">
      {children}
      <div className="flex items-center gap-2 md:ms-auto shrink-0">
        {freshnessBadge}
        {actions}
      </div>
    </div>
  </div>
);
