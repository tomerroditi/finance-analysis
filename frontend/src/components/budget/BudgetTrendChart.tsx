import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  Cell,
} from "recharts";
import { ChevronDown, ChevronUp, TrendingUp } from "lucide-react";
import { AXIS_DEFAULTS, BAR_RADIUS, formatAxisNumber } from "../../utils/chartStyle";
import { ChartTooltip } from "../charts/ChartTooltip";
import { ChartLegend } from "../charts/ChartLegend";
import { formatMonthCompact, formatMonthYear } from "../../utils/dateFormatting";
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

  const rows = data.map((d) => ({
    ...d,
    monthKey: `${d.year}-${String(d.month).padStart(2, "0")}`,
  }));
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
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={rows} barCategoryGap="30%" margin={{ top: 8, bottom: 4, left: 0, right: 8 }}>
                  <XAxis dataKey="monthKey" {...AXIS_DEFAULTS} tickFormatter={formatMonthCompact} />
                  <YAxis {...AXIS_DEFAULTS} tickFormatter={formatAxisNumber} width={48} />
                  <Tooltip
                    content={
                      <ChartTooltip labelFormatter={(m) => formatMonthYear(String(m) + "-01")} />
                    }
                  />
                  <Legend content={<ChartLegend />} />
                  <Bar
                    dataKey="budget"
                    name={t("budget.trend.budget")}
                    fill="rgba(148, 163, 184, 0.35)"
                    radius={BAR_RADIUS}
                    isAnimationActive={false}
                  />
                  <Bar
                    dataKey="actual"
                    name={t("budget.trend.actual")}
                    fill="#10b981"
                    radius={BAR_RADIUS}
                    isAnimationActive={false}
                  >
                    {rows.map((row, i) => (
                      <Cell key={row.monthKey} fill={actualColors[i]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
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
