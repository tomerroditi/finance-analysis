import { useEffect } from "react";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatCurrency } from "../../utils/numberFormatting";
import {
  barCap,
  formatPeriodLabel,
  type CompositionRow,
  type Scope,
} from "./incomeExpensesScope";

/**
 * One series, over time — what a breakdown row can never show.
 *
 * The composition rows answer "what did this period consist of"; they cannot
 * answer "what has this one category been doing", because following a single
 * colour down a stack of differently-ordered bars is exactly the comparison
 * the eye is worst at. Focusing pulls that series out: one row per period with
 * its own money, its own bar scale, and its share of what the period spent or
 * earned — the share is what keeps the two readings honest, since a category
 * can grow in shekels while shrinking as a slice of a bigger month.
 *
 * Reached by clicking a composition slice, a donut slice, or a legend row —
 * the chart itself is the control, so nothing has to be added around it.
 */
export function IncomeExpensesFocus({
  rows,
  series,
  color,
  scope,
  limit,
  allLabel,
  onClear,
}: {
  /** Breakdown rows at the active scope, oldest period first. */
  rows: CompositionRow[];
  /** The focused series name. */
  series: string;
  /** Its colour in the breakdown it was picked from. */
  color: string;
  scope: Scope;
  /** How many of the most recent periods to show. */
  limit: number;
  /** Label for the all-scope period key. */
  allLabel: string;
  onClear: () => void;
}) {
  const { t } = useTranslation();

  // Escape clears the filter. The chip's ✕ is the visible control; this is
  // the one people try without looking, and the focused view has no other
  // dismissal (it is not a dialog, so nothing traps focus to key off).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClear();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClear]);

  const points = rows.map((row) => {
    const value = row.values[series] ?? 0;
    const periodTotal = Object.values(row.values).reduce((s, v) => s + v, 0);
    return { month: row.month, value, share: periodTotal > 0 ? value / periodTotal : 0 };
  });

  const total = points.reduce((s, p) => s + p.value, 0);
  // Averaged over the periods the series actually appears in, not over every
  // period on file: a subscription started in March averages over March
  // onward, or the figure says more about when tracking began than about the
  // series.
  const active = points.filter((p) => p.value > 0).length;
  const windowTotal = rows.reduce(
    (s, row) => s + Object.values(row.values).reduce((inner, v) => inner + v, 0),
    0,
  );
  const cap = barCap(points.map((p) => p.value));
  const visible = points.slice(-limit).reverse();

  return (
    <div className="min-w-[300px]">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 mb-3">
        <button
          type="button"
          data-testid="series-focus-chip"
          onClick={onClear}
          className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--surface-light)] bg-[var(--surface-light)] px-2 py-1 text-xs font-bold hover:border-[var(--primary)]/40 transition-colors"
        >
          <span className="inline-block w-2.5 h-2.5 rounded-sm flex-none" style={{ background: color }} />
          <span className="max-w-[12rem] truncate" dir="auto">
            {series}
          </span>
          <X size={13} aria-label={t("dashboard.clearFilter")} />
        </button>
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-[11px] text-[var(--text-muted)]">
          <span className="font-bold tabular-nums text-[var(--text-default)]">{formatCurrency(total)}</span>
          <span>
            {t(scope === "yearly" ? "dashboard.focusPerYear" : "dashboard.focusPerMonth")}{" "}
            <span className="font-bold tabular-nums text-[var(--text-default)]">
              {formatCurrency(active ? total / active : 0)}
            </span>
          </span>
          <span>
            {t("dashboard.focusShareOfTotal", {
              percent: windowTotal > 0 ? ((total / windowTotal) * 100).toFixed(1) : "0.0",
            })}
          </span>
        </div>
      </div>

      <div className="grid gap-x-2" style={{ gridTemplateColumns: "max-content 1fr max-content" }}>
        <div className="col-span-3 grid grid-cols-subgrid px-1 pb-2 text-[10px] font-bold uppercase tracking-wide text-[var(--text-muted)]">
          <div>
            {t(
              scope === "yearly"
                ? "dashboard.ledgerYear"
                : scope === "all"
                  ? "dashboard.scopeAll"
                  : "dashboard.ledgerMonth",
            )}
          </div>
          <div>{t("dashboard.breakdownAmount")}</div>
          <div className="text-end">{t("dashboard.breakdownShare")}</div>
        </div>
        {visible.map((point) => (
          <div
            key={point.month}
            data-testid="series-focus-row"
            data-month={point.month}
            className="col-span-3 grid grid-cols-subgrid items-center px-1 py-1.5 rounded-lg"
          >
            <div className="text-xs font-bold text-[var(--text-muted)] whitespace-nowrap">
              {formatPeriodLabel(point.month, allLabel)}
            </div>
            <div className="flex items-center gap-1.5">
              <div
                data-testid="series-focus-bar"
                data-capped={point.value > cap ? "true" : "false"}
                title={point.value > cap ? t("dashboard.barAboveScale") : undefined}
                className="h-[22px] rounded-md flex items-center justify-start"
                style={{
                  // A period the series never appeared in still needs a
                  // visible row, so the bar floors at a sliver rather than
                  // collapsing to nothing.
                  width: `${Math.min(Math.max((point.value / cap) * 100, 2), 100)}%`,
                  background: `color-mix(in srgb, ${color} 18%, transparent)`,
                  borderWidth: 1,
                  borderStyle: "solid",
                  borderColor: `color-mix(in srgb, ${color} 50%, transparent)`,
                  // Past the cap every bar is full width, so without a marked
                  // tip a record month and an ordinary one draw identically.
                  borderInlineEndStyle: point.value > cap ? "dashed" : "solid",
                  borderInlineEndColor:
                    point.value > cap ? color : `color-mix(in srgb, ${color} 50%, transparent)`,
                }}
              >
                {/* The label rides inside the bar only while the bar is wide
                    enough to hold it; on a sliver it would paint straight
                    through the border and out the other side. */}
                {labelFits(point.value, cap) && <BarLabel value={point.value} color={color} />}
              </div>
              {!labelFits(point.value, cap) && <BarLabel value={point.value} color={color} />}
            </div>
            <div className="text-xs font-bold text-end whitespace-nowrap tabular-nums text-[var(--text-muted)]">
              {(point.share * 100).toFixed(1)}%
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Whether a bar is wide enough to carry its own ₪ label inside it. */
function labelFits(value: number, cap: number): boolean {
  return (value / cap) * 100 >= 25;
}

/** A bar's exact figure — inside the bar when it fits, beside it when not. */
function BarLabel({ value, color }: { value: number; color: string }) {
  return (
    <span
      className="text-[11px] font-bold px-2 whitespace-nowrap tabular-nums"
      style={{ color }}
    >
      {formatCurrency(value)}
    </span>
  );
}
