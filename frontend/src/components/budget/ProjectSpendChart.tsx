import React, { useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";
import { BarChart3 } from "lucide-react";
import { AXIS_DEFAULTS, BAR_RADIUS, CHART_COLORS, formatAxisNumber } from "../../utils/chartStyle";
import { ChartTooltip } from "../charts/ChartTooltip";
import { formatMonthCompact, formatMonthYear } from "../../utils/dateFormatting";
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
    const out: { month: string; amount: number }[] = [];
    for (let m = min; m <= max; m++) {
      out.push({
        month: `${Math.floor(m / 12)}-${String((m % 12) + 1).padStart(2, "0")}`,
        amount: byMonth.get(m) || 0,
      });
    }
    return out;
  }, [transactions]);

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
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={points} barCategoryGap="30%" margin={{ top: 8, bottom: 4, left: 0, right: 8 }}>
                <XAxis dataKey="month" {...AXIS_DEFAULTS} tickFormatter={formatMonthCompact} />
                <YAxis {...AXIS_DEFAULTS} tickFormatter={formatAxisNumber} width={48} />
                <Tooltip
                  cursor={false}
                  content={
                    <ChartTooltip labelFormatter={(m) => formatMonthYear(String(m) + "-01")} />
                  }
                />
                <Bar
                  dataKey="amount"
                  name={t("budget.spendOverTime")}
                  fill={CHART_COLORS[0]}
                  radius={BAR_RADIUS}
                  isAnimationActive={false}
                />
              </BarChart>
            </ResponsiveContainer>
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
