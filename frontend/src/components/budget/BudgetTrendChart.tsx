import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import Plot from "../common/LazyPlot";
import { ChevronDown, ChevronUp, TrendingUp } from "lucide-react";
import i18n from "../../i18n";
import { chartTheme, plotlyConfig, barMarker } from "../../utils/plotlyLocale";
import { useBudgetTrend } from "../../hooks/useBudgetTrend";

interface BudgetTrendChartProps {
  year: number;
  month: number;
  includeSplitParents?: boolean;
  months?: number;
}

/**
 * Budget-vs-actual trend over the trailing N months. Assembled client-side
 * from the cached per-month analysis queries (no dedicated endpoint).
 * Collapsible: expanded on desktop, collapsed by default on mobile.
 */
export const BudgetTrendChart: React.FC<BudgetTrendChartProps> = ({
  year,
  month,
  includeSplitParents = false,
  months = 6,
}) => {
  const { t } = useTranslation();
  const [open, setOpen] = useState(
    typeof window !== "undefined" ? window.innerWidth >= 768 : true,
  );
  const { data, hasData } = useBudgetTrend(year, month, months, includeSplitParents);

  const locale = i18n.language === "he" ? "he-IL" : "en-US";
  const labels = data.map((d) =>
    new Date(d.year, d.month - 1).toLocaleString(locale, { month: "short" }),
  );
  const actualColors = data.map((d) =>
    d.budget > 0 && d.actual > d.budget ? "#f43f5e" : "#10b981",
  );

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-2 px-4 py-3 hover:bg-[var(--surface-light)]/40 transition-colors"
      >
        <span className="flex items-center gap-2 min-w-0">
          <TrendingUp size={18} className="text-[var(--primary)] shrink-0" />
          <span className="font-semibold text-sm text-[var(--text-default)]">
            {t("budget.trend.title")}
          </span>
          <span className="text-xs text-[var(--text-muted)] hidden sm:inline">
            {t("budget.trend.subtitle", { count: months })}
          </span>
        </span>
        <span className="flex items-center gap-2 shrink-0 text-[var(--text-muted)]">
          <span className="text-xs font-medium hidden md:inline">
            {open ? t("budget.trend.hide") : t("budget.trend.show")}
          </span>
          {open ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
        </span>
      </button>

      {open && (
        <div className="px-2 pb-3 animate-in fade-in duration-300">
          {hasData ? (
            <div className="w-full h-[240px] md:h-[300px]">
              <Plot
                data={[
                  {
                    x: labels,
                    y: data.map((d) => d.budget),
                    type: "bar" as const,
                    name: t("budget.trend.budget"),
                    marker: barMarker("rgba(148, 163, 184, 0.35)"),
                  },
                  {
                    x: labels,
                    y: data.map((d) => d.actual),
                    type: "bar" as const,
                    name: t("budget.trend.actual"),
                    marker: barMarker(actualColors),
                  },
                ]}
                layout={{
                  ...chartTheme,
                  autosize: true,
                  barmode: "group",
                  bargap: 0.3,
                  margin: { t: 10, b: 40, l: 50, r: 16 },
                  legend: {
                    orientation: "h",
                    y: -0.2,
                    x: 0.5,
                    xanchor: "center",
                    font: { size: 11 },
                  },
                }}
                style={{ width: "100%", height: "100%" }}
                config={plotlyConfig()}
                useResizeHandler
              />
            </div>
          ) : (
            <p className="text-sm text-[var(--text-muted)] text-center py-8">
              {t("budget.trend.empty")}
            </p>
          )}
        </div>
      )}
    </div>
  );
};
