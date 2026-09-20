import React from "react";
import { useTranslation } from "react-i18next";
import { formatAmount, formatCurrency } from "../../utils/numberFormatting";

interface BudgetTotalBarProps {
  spent: number;
  total: number;
  /** Dims the figures when the underlying scrape is stale. */
  muted?: boolean;
}

/**
 * "How am I doing" in one line: the figure, the gap, and a bar.
 *
 * Shared by the Budget page's status band and the dashboard's budget card so
 * the two cannot drift apart on where amber starts or on how an overspend is
 * worded.
 *
 * One ₪ on the line, carried by the ceiling — "11,185 / 28,000 ₪" with a bare
 * remainder in the pill. Three signs across three figures that are obviously
 * the same currency is decoration, and the envelope rows under this bar read
 * the same way.
 */
export const BudgetTotalBar: React.FC<BudgetTotalBarProps> = ({
  spent,
  total,
  muted = false,
}) => {
  const { t } = useTranslation();

  // A net refund can push a category negative; the bar floors at empty.
  const clamped = Math.max(spent, 0);
  // A zero total with spend against it is fully over, not healthy — nothing
  // was budgeted, so every shekel is unbudgeted.
  const over = clamped > total || (total <= 0 && clamped > 0);
  const percent = total > 0 ? Math.min((clamped / total) * 100, 100) : over ? 100 : 0;
  const near = !over && total > 0 && clamped > total * 0.9;
  const barColor = over ? "bg-rose-500" : near ? "bg-amber-500" : "bg-emerald-500";
  const remaining = total - clamped;
  const dimmed = muted ? "opacity-60" : "";

  return (
    <div data-testid="budget-total-bar">
      <div className={`flex items-baseline flex-wrap gap-2 mb-2 ${dimmed}`}>
        {/* Spent and ceiling are ONE left-to-right run, not two flex items.
            As siblings they are laid out in the container's direction, so
            under RTL they swap and the slash lands at the far left of the
            line, detached from the figures it divides: "/ 28,000 ₪ 11,185".
            Grouping them makes the pair read the same in both languages —
            the same reason the envelope rows below carry `dir="ltr"` on the
            span that holds both figures. */}
        <span className="flex items-baseline flex-wrap gap-2" dir="ltr">
          <span className="text-xl md:text-2xl font-bold font-mono">
            {formatAmount(clamped)}
          </span>
          <span className="text-xs md:text-sm text-[var(--text-muted)] font-mono">
            / {formatCurrency(total)}
          </span>
        </span>
        {(total > 0 || over) && (
          <span
            className={`text-[10px] sm:text-xs font-medium px-2 py-0.5 rounded-full ${
              over ? "bg-rose-500/10 text-rose-400" : "bg-emerald-500/10 text-emerald-400"
            }`}
          >
            {over
              ? t("budget.overByAmount", { amount: formatAmount(Math.abs(remaining)) })
              : t("budget.remainingAmount", { amount: formatAmount(remaining) })}
          </span>
        )}
      </div>

      <div className="relative h-2 rounded-full bg-[var(--surface-light)] overflow-hidden">
        <div
          data-testid="budget-total-bar-fill"
          className={`absolute inset-y-0 start-0 rounded-full ${barColor} transition-all duration-500 ease-out`}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
};
