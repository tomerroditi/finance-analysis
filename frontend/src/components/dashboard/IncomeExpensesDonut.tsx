import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatCompactCurrency, formatCurrency } from "../../utils/numberFormatting";
import { DonutChart } from "../charts/DonutChart";
import { useScrollCap } from "../../hooks/useScrollCap";
import { isTouchDevice } from "../../utils/chartStyle";

/**
 * The all-scope breakdown: one hollow pie over the whole window plus a
 * collapsible legend table.
 *
 * The monthly and yearly scopes draw a composition bar per period, which says
 * how the mix *moved*. Over a single all-time period there is no movement to
 * show, so the same bar would be one anonymous band the width of the card —
 * a donut states the same shares in a form the eye can actually compare, and
 * frees the centre for the total.
 *
 * Every legend row is a button: a slice is hard to hit once its share drops
 * under a few percent, so the legend is the reachable way to the same filter —
 * by keyboard, and on a phone.
 *
 * On a pointer device the legend starts closed (the donut is the headline; the
 * per-series figures are detail the reader opts into) and a slice can be
 * clicked to filter. On a touch device it starts open and the slices are not
 * clickable at all: a tap is the same gesture that opens Recharts' own
 * tooltip, so a tap-to-filter slice would both name a series and navigate away
 * from it at once. The legend gives a phone both readings — every amount and
 * share in text — and one deliberate tap per row to filter.
 */
export function IncomeExpensesDonut({
  values,
  colorOf,
  seriesHeading,
  onSelect,
}: {
  values: Record<string, number>;
  /** Series colour, shared with the composition rows so a name keeps its hue. */
  colorOf: (name: string) => string;
  /** What the legend's first column is called ("Source" / "Category"). */
  seriesHeading: string;
  /** Focus one series over time. */
  onSelect: (name: string) => void;
}) {
  const { t } = useTranslation();
  const [legendOpen, setLegendOpen] = useState(isTouchDevice);

  const slices = Object.entries(values)
    .filter(([, value]) => value > 0)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);
  const total = slices.reduce((sum, s) => sum + s.value, 0);

  // Capped only once the cap hides a row: a table that scrolls by a hair
  // swallows the drag meant for the page (see `useScrollCap`). Re-measured
  // when the legend opens, since it has no height while collapsed.
  const [legendRef, legendCapped] = useScrollCap(320, legendOpen ? slices.length : 0);

  if (slices.length === 0) return <p className="text-[var(--text-muted)] text-sm">{t("common.noData")}</p>;

  return (
    <div className="flex flex-col gap-4">
      <div className="w-full min-h-[240px]">
        <DonutChart
          data={slices}
          colors={slices.map((s) => colorOf(s.name))}
          height={240}
          onSliceClick={isTouchDevice ? undefined : onSelect}
          centerLabel={
            <span className="text-base font-semibold text-[var(--text-default)]">
              {formatCompactCurrency(total)}
            </span>
          }
        />
      </div>

      <div className="w-full">
        <button
          type="button"
          onClick={() => setLegendOpen((open) => !open)}
          aria-expanded={legendOpen}
          className="flex items-center gap-1 mb-2 text-xs font-bold text-[var(--text-muted)] hover:text-[var(--text-default)] transition-colors"
        >
          {legendOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          {t("dashboard.breakdownLegend")}
        </button>
        {legendOpen && (
          /* The radius and border belong to the wrapper and the scrolling
             happens on the child, so the scrollbar cannot paint over the
             rounded corners. The header and Total rows stay put via sticky
             cells (sticky on <thead>/<tfoot> itself is patchier across
             browsers), and their separators are inset box-shadows — a
             collapsed-border <tr> border does not paint while scrolling under
             a sticky row. */
          <div className="rounded-xl border border-[var(--surface-light)] overflow-hidden">
            <div
              ref={legendRef}
              data-testid="breakdown-legend-scroll"
              className={`overflow-x-auto ${
                legendCapped ? "max-h-[20rem] overflow-y-auto overscroll-contain" : ""
              }`}
            >
              <table className="w-full min-w-[240px] text-sm">
                <thead>
                  <tr className="text-[10px] uppercase tracking-widest text-[var(--text-muted)]">
                    <th className="sticky top-0 z-10 bg-[var(--surface)] text-start px-2 py-2 font-bold whitespace-nowrap shadow-[inset_0_-1px_0_var(--surface-light)]">
                      {seriesHeading}
                    </th>
                    <th className="sticky top-0 z-10 bg-[var(--surface)] text-center px-2 py-2 font-bold whitespace-nowrap shadow-[inset_0_-1px_0_var(--surface-light)]">
                      {t("dashboard.breakdownAmount")}
                    </th>
                    <th className="sticky top-0 z-10 bg-[var(--surface)] text-center px-2 py-2 font-bold whitespace-nowrap shadow-[inset_0_-1px_0_var(--surface-light)]">
                      {t("dashboard.breakdownShare")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {slices.map((slice) => (
                    <tr key={slice.name} className="border-b border-[var(--surface-light)]/50">
                      <td className="text-start px-2 py-2 w-full max-w-0">
                        <button
                          type="button"
                          data-testid="breakdown-legend-row"
                          onClick={() => onSelect(slice.name)}
                          title={t("dashboard.clickToFilter")}
                          className="flex items-center gap-2 w-full text-start hover:text-[var(--primary)] transition-colors"
                        >
                          <span
                            className="inline-block w-2.5 h-2.5 rounded-full shrink-0"
                            style={{ backgroundColor: colorOf(slice.name) }}
                          />
                          <span className="min-w-0 truncate" dir="auto">
                            {slice.name}
                          </span>
                        </button>
                      </td>
                      <td className="text-center px-2 py-2 whitespace-nowrap tabular-nums">
                        {formatCurrency(slice.value)}
                      </td>
                      <td className="text-center px-2 py-2 whitespace-nowrap tabular-nums text-[var(--text-muted)]">
                        {((slice.value / total) * 100).toFixed(1)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="font-bold">
                    <td className="sticky bottom-0 z-10 bg-[var(--surface)] text-start px-2 py-2 whitespace-nowrap shadow-[inset_0_2px_0_var(--surface-light)]">
                      {t("dashboard.breakdownTotal")}
                    </td>
                    <td className="sticky bottom-0 z-10 bg-[var(--surface)] text-center px-2 py-2 whitespace-nowrap tabular-nums shadow-[inset_0_2px_0_var(--surface-light)]">
                      {formatCurrency(total)}
                    </td>
                    <td className="sticky bottom-0 z-10 bg-[var(--surface)] text-center px-2 py-2 whitespace-nowrap tabular-nums text-[var(--text-muted)] shadow-[inset_0_2px_0_var(--surface-light)]">
                      100.0%
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
