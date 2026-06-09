import React, { useMemo } from "react";
import { useTranslation } from "react-i18next";
import Plot from "../common/LazyPlot";
import { BarChart3 } from "lucide-react";
import i18n from "../../i18n";
import { chartTheme, plotlyConfig, barMarker, CHART_COLORS } from "../../utils/plotlyLocale";
import type { Transaction } from "../../types/transaction";

interface ProjectSpendChartProps {
  /** Deduped union of all transactions belonging to the project. */
  transactions: Transaction[];
}

/**
 * Per-month spend for a project (not cumulative, not averaged). Buckets each
 * transaction into its calendar month, fills gaps so the time axis stays
 * continuous, and renders a bar per month. Project tab only.
 */
export const ProjectSpendChart: React.FC<ProjectSpendChartProps> = ({
  transactions,
}) => {
  const { t } = useTranslation();
  const locale = i18n.language === "he" ? "he-IL" : "en-US";

  const points = useMemo(() => {
    const byMonth = new Map<number, number>(); // months-since-epoch -> spend
    let min: number | null = null;
    let max: number | null = null;
    for (const tx of transactions) {
      const d = tx.date ? new Date(tx.date) : null;
      if (!d || Number.isNaN(d.getTime())) continue;
      const m = d.getFullYear() * 12 + d.getMonth();
      byMonth.set(m, (byMonth.get(m) || 0) + Math.abs(tx.amount || 0));
      if (min === null || m < min) min = m;
      if (max === null || m > max) max = m;
    }
    if (min === null || max === null) return [];
    const out: { label: string; amount: number }[] = [];
    for (let m = min; m <= max; m++) {
      const date = new Date(Math.floor(m / 12), m % 12, 1);
      out.push({
        label: date.toLocaleString(locale, { month: "short", year: "2-digit" }),
        amount: byMonth.get(m) || 0,
      });
    }
    return out;
  }, [transactions, locale]);

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] shadow-sm overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-[var(--surface-light)]">
        <BarChart3 size={18} className="text-[var(--primary)] shrink-0" />
        <span className="font-semibold text-sm text-[var(--text-default)]">
          {t("budget.spendOverTime")}
        </span>
        <span className="text-xs text-[var(--text-muted)] hidden sm:inline">
          {t("budget.spendOverTimeSubtitle")}
        </span>
      </div>
      <div className="px-2 pb-3 pt-1">
        {points.length > 0 ? (
          <div className="w-full h-[240px] md:h-[300px]">
            <Plot
              data={[
                {
                  x: points.map((p) => p.label),
                  y: points.map((p) => p.amount),
                  type: "bar" as const,
                  marker: barMarker(CHART_COLORS[0]),
                },
              ]}
              layout={{
                ...chartTheme,
                autosize: true,
                bargap: 0.3,
                showlegend: false,
                margin: { t: 10, b: 40, l: 56, r: 16 },
              }}
              style={{ width: "100%", height: "100%" }}
              config={plotlyConfig()}
              useResizeHandler
            />
          </div>
        ) : (
          <p className="text-sm text-[var(--text-muted)] text-center py-8">
            {t("budget.spendOverTimeEmpty")}
          </p>
        )}
      </div>
    </div>
  );
};
