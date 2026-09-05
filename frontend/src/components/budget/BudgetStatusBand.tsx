import React from "react";
import { useTranslation } from "react-i18next";
import { Clock } from "lucide-react";
import { formatCurrency } from "../../utils/numberFormatting";

export interface BandStat {
  key: string;
  label: string;
  value?: React.ReactNode;
  /** Trend cell — rendered under the label instead of a value. */
  trend?: React.ReactNode;
  /**
   * Give this stat the row's leftover width (and the full row on mobile).
   * Used by the budget-vs-actual figure, which is the only stat whose value
   * is a drawing rather than a number and therefore reads better wide.
   */
  grow?: boolean;
}

interface BudgetStatusBandProps {
  /** Name of the band — keep it short and stable. */
  label: string;
  spent: number;
  total: number;
  stats: BandStat[];
  /**
   * Secondary control (e.g. "View month transactions"). Rides on the heading
   * line rather than claiming a row of its own under the gauge.
   */
  footer?: React.ReactNode;
  /** Figures are provisional because the underlying scrape is stale. */
  isStale?: boolean;
  children?: React.ReactNode;
}

/**
 * The one place the page answers "how am I doing".
 *
 * Merges three blocks that each answered it differently: the Total Budget
 * gauge card, the three-tile summary strip, and the always-mounted trend
 * chart. Left side carries the gauge, right side the stats — including the
 * period trend, which used to be a ~300px chart block of its own.
 */
export const BudgetStatusBand: React.FC<BudgetStatusBandProps> = ({
  label,
  spent,
  total,
  stats,
  footer,
  isStale = false,
  children,
}) => {
  const { t } = useTranslation();

  const clamped = Math.max(spent, 0);
  const percent =
    total > 0 ? Math.min((clamped / total) * 100, 100) : clamped > 0 ? 100 : 0;
  const over = clamped > total && total > 0;
  const near = !over && total > 0 && clamped > total * 0.9;
  const barColor = over ? "bg-rose-500" : near ? "bg-amber-500" : "bg-emerald-500";
  const remaining = total - clamped;
  const staleValue = isStale ? "opacity-60" : "";

  const heading = (
    <span className="flex items-center gap-1.5 min-w-0 text-[10px] sm:text-xs text-[var(--text-muted)] uppercase tracking-wide">
      <span className="truncate" dir="auto">
        {label}
      </span>
      {isStale && (
        <Clock
          size={11}
          className="shrink-0 text-amber-400"
          aria-label={t("budget.freshness.provisional")}
        />
      )}
    </span>
  );

  return (
    <div
      data-testid="budget-status-band"
      className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] shadow-sm p-3 md:p-4"
    >
      {/* Side by side only from `xl:`. At 1024 the gauge plus four stats left
          the trend figure a ~50px sliver and truncated its label to "BUDG…";
          stacked, the stats row gets the card's full width instead. */}
      <div className="flex flex-col xl:flex-row xl:items-stretch gap-3 xl:gap-5">
        {/* The gauge is capped rather than greedy: a full-width bar spent the
            row's whole width restating a number already spelled out above it,
            leaving the stats — and the trend figure in particular — squeezed. */}
        <div className="w-full xl:w-[32%] xl:shrink-0 min-w-0">
          {/* Top-aligned, not centred: the heading has to sit on the same line as
              the stat labels across the divider, and the footer control is
              taller than the label it rides beside. */}
          <div className="flex items-start justify-between gap-2 min-w-0">
            {heading}
            {/* `flex`, not a block: a block wrapper gives the control a 24px line
                box and drops it 6px below the heading it sits beside. */}
            {footer && <div className="flex shrink-0">{footer}</div>}
          </div>

          <div className={`flex items-baseline flex-wrap gap-2 mt-1.5 mb-2 ${staleValue}`}>
            <span className="text-xl md:text-2xl font-bold font-mono" dir="ltr">
              {formatCurrency(clamped)}
            </span>
            <span className="text-xs md:text-sm text-[var(--text-muted)] font-mono" dir="ltr">
              / {formatCurrency(total)}
            </span>
            {total > 0 && (
              <span
                className={`text-[10px] sm:text-xs font-medium px-2 py-0.5 rounded-full ${
                  over
                    ? "bg-rose-500/10 text-rose-400"
                    : "bg-emerald-500/10 text-emerald-400"
                }`}
                dir="ltr"
              >
                {over
                  ? t("budget.overByAmount", { amount: formatCurrency(Math.abs(remaining)) })
                  : t("budget.remainingAmount", { amount: formatCurrency(remaining) })}
              </span>
            )}
          </div>

          <div className="relative h-2 rounded-full bg-[var(--surface-light)] overflow-hidden">
            <div
              className={`absolute inset-y-0 start-0 rounded-full ${barColor} transition-all duration-500 ease-out`}
              style={{ width: `${percent}%` }}
            />
          </div>
        </div>

        <div className="grid grid-cols-3 xl:flex xl:flex-1 xl:items-start gap-2 xl:gap-5 min-w-0 xl:border-s xl:border-[var(--surface-light)] xl:ps-5">
          {stats.map((stat) => (
            <div
              key={stat.key}
              className={`min-w-0 ${stat.grow ? "col-span-3 xl:flex-1 xl:min-w-[180px]" : ""}`}
            >
              <p className="text-[10px] sm:text-xs text-[var(--text-muted)] uppercase tracking-wide truncate">
                {stat.label}
              </p>
              <div className={`mt-1 ${staleValue}`}>{stat.trend ?? stat.value}</div>
            </div>
          ))}
        </div>
      </div>

      {children}
    </div>
  );
};
