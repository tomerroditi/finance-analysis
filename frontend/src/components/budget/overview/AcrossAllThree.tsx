import React from "react";
import { useTranslation } from "react-i18next";
import { Calendar, CalendarRange, Layers } from "lucide-react";
import type { BudgetOverview } from "../../../services/api";
import { formatCurrency } from "../../../utils/numberFormatting";
import { envelopeColor } from "./envelopeMath";

interface AcrossAllThreeProps {
  overview: BudgetOverview;
  /** Month label, e.g. "September". */
  monthLabel: string;
}

/**
 * The month's spending across the three kinds of budget, stated as three pools.
 *
 * This card replaced a "by budget kind" card that stacked three bars in a
 * column, which read as three slices of one budget. They are not: the backend's
 * ``get_filtered_expenses`` drops project categories and
 * ``_exclude_yearly_claimed`` drops yearly-claimed spend, so neither is inside
 * the monthly budget at all. Only the monthly row gets a bar and a percentage,
 * because only it has a limit for the month. The other two report what the
 * month put in, and the footer gives the figure none of them gave before: what
 * actually left the accounts.
 */
export const AcrossAllThree: React.FC<AcrossAllThreeProps> = ({
  overview,
  monthLabel,
}) => {
  const { t } = useTranslation();
  const {
    monthly_spent: spent,
    monthly_budget: budget,
    projects_month_spent: projects,
    yearly_month_spent: yearly,
    total_out: totalOut,
  } = overview;

  const percent =
    budget > 0 ? Math.round((Math.max(spent, 0) / budget) * 100) : 0;

  const row = (
    key: string,
    Icon: typeof Calendar,
    label: string,
    middle: React.ReactNode,
    figure: React.ReactNode,
  ) => (
    <div
      key={key}
      className="grid grid-cols-[104px_minmax(0,1fr)_auto] gap-3 items-center py-2 border-b border-[var(--surface-light)] last:border-b-0"
    >
      <span className="inline-flex items-center gap-2 font-semibold text-sm">
        <Icon size={16} className="shrink-0 text-[var(--primary)]" />
        {label}
      </span>
      {middle}
      <span className="text-end">{figure}</span>
    </div>
  );

  return (
    <div
      data-testid="budget-across-all-three"
      className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] shadow-sm p-4 md:p-5 flex flex-col gap-3 h-full"
    >
      <p className="font-bold text-sm md:text-base">
        {t("budget.overview.acrossAllThree", { month: monthLabel })}
      </p>

      <div className="flex flex-col">
        {row(
          "monthly",
          Calendar,
          t("budget.monthlyBudget"),
          <span className="relative block h-1.5 w-full rounded-full bg-[var(--surface-light)] overflow-hidden">
            <span
              className={`absolute inset-y-0 start-0 rounded-full ${envelopeColor(percent)}`}
              style={{ width: `${Math.min(percent, 100)}%` }}
            />
          </span>,
          <span dir="ltr" className="text-xs font-mono font-bold whitespace-nowrap">
            {formatCurrency(spent)}
            <span className="text-[var(--text-muted)] font-normal">
              {" / "}
              {budget > 0 ? formatCurrency(budget) : "—"}
            </span>
          </span>,
        )}
        {row(
          "projects",
          Layers,
          t("budget.projectBudgets"),
          <span className="text-xs text-[var(--text-muted)]">
            {t("budget.overview.noMonthlyLimit")}
          </span>,
          <span dir="ltr" className="text-xs font-mono font-bold whitespace-nowrap">
            {formatCurrency(projects)}
          </span>,
        )}
        {row(
          "yearly",
          CalendarRange,
          t("budget.yearly.tab"),
          <span className="text-xs text-[var(--text-muted)]">
            {t("budget.overview.noMonthlyLimit")}
          </span>,
          <span dir="ltr" className="text-xs font-mono font-bold whitespace-nowrap">
            {formatCurrency(yearly)}
          </span>,
        )}
      </div>

      <div className="border-t border-[var(--surface-light)] pt-2.5 flex items-baseline gap-2 flex-wrap">
        <span className="text-xs text-[var(--text-muted)]">
          {t("budget.overview.leftYourAccounts", { month: monthLabel })}
        </span>
        <span dir="ltr" className="text-base font-mono font-bold">
          {formatCurrency(totalOut)}
        </span>
      </div>

      <p className="text-[11px] text-[var(--text-muted)] text-pretty">
        {t("budget.overview.separatePools", {
          amount: formatCurrency(budget),
        })}
      </p>
    </div>
  );
};
