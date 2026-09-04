import React from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronUp, Clock } from "lucide-react";
import { formatCurrency } from "../../utils/numberFormatting";

export interface BandStat {
  key: string;
  label: string;
  value?: React.ReactNode;
  /** Trend cell — rendered under the label instead of a value. */
  trend?: React.ReactNode;
}

interface BudgetStatusBandProps {
  /** Accessible name of the collapse control — keep it short and stable. */
  label: string;
  spent: number;
  total: number;
  stats: BandStat[];
  /** When provided, the label becomes a button that collapses the rule list. */
  onToggleRules?: () => void;
  rulesCollapsed?: boolean;
  /** Secondary control row (e.g. "View month transactions"). */
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
  onToggleRules,
  rulesCollapsed = false,
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
    <span className="flex items-center gap-1.5 text-[10px] sm:text-xs text-[var(--text-muted)] uppercase tracking-wide">
      {onToggleRules && (
        <span className="text-[var(--text-muted)]">
          {rulesCollapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
        </span>
      )}
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
      <div className="flex flex-col lg:flex-row lg:items-center gap-3 lg:gap-5">
        <div className="flex-1 min-w-0">
          {onToggleRules ? (
            <button
              type="button"
              onClick={onToggleRules}
              aria-expanded={!rulesCollapsed}
              className="text-start max-w-full"
            >
              {heading}
            </button>
          ) : (
            heading
          )}

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

        <div className="grid grid-cols-3 lg:flex gap-2 lg:gap-5 lg:border-s lg:border-[var(--surface-light)] lg:ps-5">
          {stats.map((stat) => (
            <div key={stat.key} className="min-w-0">
              <p className="text-[10px] sm:text-xs text-[var(--text-muted)] uppercase tracking-wide truncate">
                {stat.label}
              </p>
              <div className={`mt-1 ${staleValue}`}>{stat.trend ?? stat.value}</div>
            </div>
          ))}
        </div>
      </div>

      {footer && <div className="mt-1">{footer}</div>}
      {children}
    </div>
  );
};
