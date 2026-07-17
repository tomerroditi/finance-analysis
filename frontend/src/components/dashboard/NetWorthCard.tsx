import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ResponsiveContainer,
  ComposedChart,
  LineChart,
  AreaChart,
  Line,
  Bar,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  Cell,
} from "recharts";
import { analyticsApi } from "../../services/api";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { useTranslation } from "react-i18next";
import { formatCurrency, formatChange, formatPercentChange } from "../../utils/numberFormatting";
import {
  AXIS_DEFAULTS,
  BAR_RADIUS,
  CHART_TEXT_COLOR,
  formatAxisNumber,
  hexToRgba,
} from "../../utils/chartStyle";
import { ChartTooltip } from "../charts/ChartTooltip";
import { ChartLegend } from "../charts/ChartLegend";
import { formatMonthCompact, formatMonthYear } from "../../utils/dateFormatting";

type NetWorthView = "all" | "bank_balance" | "investments" | "net_worth" | "debt_payments";

const DEBT_COLORS = [
  "#f43f5e", "#3b82f6", "#f59e0b", "#8b5cf6",
  "#06b6d4", "#ec4899", "#10b981", "#f97316",
];


/** Net Worth analytics dashboard card (period chips + bank/investments/net-worth/debt toggle). */
export function NetWorthCard() {
  const { t } = useTranslation();
  const qk = useQueryKeys();
  const [netWorthView, setNetWorthView] = useState<NetWorthView>("all");

  const { data: debtPaymentsData } = useQuery({
    queryKey: qk.analytics.debtPayments(),
    queryFn: async () => (await analyticsApi.getDebtPaymentsOverTime()).data,
  });

  const { data: netWorthData } = useQuery({
    queryKey: qk.analytics.netWorthOverTime(),
    queryFn: async () => (await analyticsApi.getNetWorthOverTime()).data,
  });

  const netWorthDeltas = useMemo(() => {
    if (!netWorthData || netWorthData.length < 2) return null;
    return netWorthData.slice(1).map((d, i) => ({
      month: d.month,
      bank_balance: d.bank_balance,
      investment_value: d.investment_value,
      net_worth: d.net_worth,
      bank_balance_delta: d.bank_balance - netWorthData[i].bank_balance,
      investment_value_delta: d.investment_value - netWorthData[i].investment_value,
      net_worth_delta: d.net_worth - netWorthData[i].net_worth,
    }));
  }, [netWorthData]);

  // Stacked cumulative debt payments: one row per month, one key per tag.
  const debtStacked = useMemo(() => {
    if (!debtPaymentsData || debtPaymentsData.length === 0) return null;
    const allTags = Array.from(
      new Set(debtPaymentsData.flatMap((d: { tags: Record<string, number> }) => Object.keys(d.tags))),
    ).sort() as string[];
    const running: Record<string, number> = {};
    const rows = debtPaymentsData.map((d: { month: string; tags: Record<string, number> }) => {
      const row: Record<string, number | string> = { month: d.month };
      for (const tag of allTags) {
        running[tag] = (running[tag] ?? 0) + (d.tags[tag] || 0);
        row[tag] = running[tag];
      }
      return row;
    });
    return { allTags, rows };
  }, [debtPaymentsData]);

  const seriesConfig = {
    bank_balance: {
      label: t("dashboard.bankBalance"),
      color: "#f59e0b",
      dataKey: "bank_balance" as const,
      deltaKey: "bank_balance_delta" as const,
    },
    investments: {
      label: t("dashboard.investmentValue"),
      color: "#6366f1",
      dataKey: "investment_value" as const,
      deltaKey: "investment_value_delta" as const,
    },
    net_worth: {
      label: t("dashboard.netWorth"),
      color: "#ef4444",
      dataKey: "net_worth" as const,
      deltaKey: "net_worth_delta" as const,
    },
  };

  const chartTooltip = (
    <ChartTooltip labelFormatter={(m) => formatMonthYear(String(m) + "-01")} />
  );

  const renderChart = () => {
    if (netWorthView === "debt_payments") {
      if (!debtStacked) {
        return <p className="text-[var(--text-muted)]">{t("dashboard.noData")}</p>;
      }
      return (
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={debtStacked.rows} margin={{ top: 8, bottom: 4, left: 0, right: 8 }}>
            <XAxis dataKey="month" {...AXIS_DEFAULTS} tickFormatter={formatMonthCompact} />
            <YAxis {...AXIS_DEFAULTS} tickFormatter={formatAxisNumber} width={48} />
            <Tooltip content={chartTooltip} />
            <Legend content={<ChartLegend />} />
            {debtStacked.allTags.map((tag, i) => {
              const color = DEBT_COLORS[i % DEBT_COLORS.length];
              return (
                <Area
                  key={tag}
                  dataKey={tag}
                  name={tag}
                  stackId="debt"
                  type="monotone"
                  stroke={color}
                  strokeWidth={2}
                  fill={hexToRgba(color, 0.25)}
                  isAnimationActive={false}
                />
              );
            })}
          </AreaChart>
        </ResponsiveContainer>
      );
    }

    if (!netWorthData || netWorthData.length === 0) return null;

    if (netWorthView === "all") {
      const series = [
        { dataKey: "bank_balance", name: t("dashboard.bankBalance"), color: "#f59e0b", width: 2.5 },
        { dataKey: "investment_value", name: t("dashboard.investmentValue"), color: "#6366f1", width: 2.5 },
        { dataKey: "net_worth", name: t("dashboard.netWorth"), color: "#10b981", width: 3 },
      ];
      return (
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={netWorthData} margin={{ top: 8, bottom: 4, left: 0, right: 8 }}>
            <XAxis dataKey="month" {...AXIS_DEFAULTS} tickFormatter={formatMonthCompact} />
            <YAxis
              {...AXIS_DEFAULTS}
              tickFormatter={formatAxisNumber}
              width={56}
              label={{
                value: t("dashboard.amountILS"),
                angle: -90,
                position: "insideLeft",
                style: { fill: CHART_TEXT_COLOR, fontSize: 11 },
              }}
            />
            <Tooltip content={chartTooltip} />
            <Legend content={<ChartLegend />} />
            {series.map((s) => (
              <Line
                key={s.dataKey}
                dataKey={s.dataKey}
                name={s.name}
                type="monotone"
                stroke={s.color}
                strokeWidth={s.width}
                dot={false}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      );
    }

    if (!netWorthDeltas) return null;
    const config = seriesConfig[netWorthView];
    return (
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={netWorthDeltas} margin={{ top: 8, bottom: 4, left: 0, right: 0 }}>
          <XAxis dataKey="month" {...AXIS_DEFAULTS} tickFormatter={formatMonthCompact} />
          <YAxis
            yAxisId="left"
            {...AXIS_DEFAULTS}
            tickFormatter={formatAxisNumber}
            width={56}
            label={{
              value: t("dashboard.monthlyChange"),
              angle: -90,
              position: "insideLeft",
              style: { fill: CHART_TEXT_COLOR, fontSize: 11 },
            }}
          />
          <YAxis
            yAxisId="right"
            orientation="right"
            axisLine={false}
            tickLine={false}
            tick={{ fill: config.color, fontSize: 11 }}
            tickFormatter={formatAxisNumber}
            width={56}
            label={{
              value: config.label,
              angle: 90,
              position: "insideRight",
              style: { fill: config.color, fontSize: 11 },
            }}
          />
          <Tooltip content={chartTooltip} />
          <Legend content={<ChartLegend />} />
          <Bar
            yAxisId="left"
            dataKey={config.deltaKey}
            name={t("dashboard.monthlyChange")}
            radius={BAR_RADIUS}
            isAnimationActive={false}
          >
            {netWorthDeltas.map((d) => (
              <Cell
                key={d.month}
                fill={d[config.deltaKey] >= 0 ? "#10b981" : "#ef4444"}
              />
            ))}
          </Bar>
          <Line
            yAxisId="right"
            dataKey={config.dataKey}
            name={config.label}
            type="monotone"
            stroke={config.color}
            strokeWidth={3}
            dot={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    );
  };

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] overflow-hidden flex flex-col">
      <div className="px-3 md:px-6 pt-4 md:pt-5">
        <h2 className="text-sm md:text-base font-bold">{t("dashboard.netWorth")}</h2>
      </div>
      <div className="px-3 md:px-6 pb-4 md:pb-6 pt-4 min-h-[400px] md:h-[600px] overflow-y-auto flex flex-col">
        <div className="flex flex-col flex-1 min-h-0">
          {netWorthData && netWorthData.length > 0 ? (
            <>
              <div className="flex flex-wrap items-center gap-2 md:gap-3 mb-3">
                {(() => {
                  const latest = netWorthData[netWorthData.length - 1];
                  const findMonthsAgo = (n: number) => {
                    const d = new Date();
                    d.setMonth(d.getMonth() - n);
                    const target = d.toISOString().slice(0, 7);
                    return [...netWorthData].reverse().find((d) => d.month <= target) ?? netWorthData[0];
                  };
                  const periods = [
                    { label: t("dashboard.change5Y"), months: 60 },
                    { label: t("dashboard.change3Y"), months: 36 },
                    { label: t("dashboard.change1Y"), months: 12 },
                    { label: t("dashboard.change6M"), months: 6 },
                    { label: t("dashboard.change1M"), months: 1 },
                  ];
                  return periods.map(({ label, months }) => {
                    const past = findMonthsAgo(months);
                    const delta = latest.net_worth - past.net_worth;
                    const pct = past.net_worth !== 0 ? (delta / Math.abs(past.net_worth)) * 100 : null;
                    const isPositive = delta >= 0;
                    return (
                      <div key={label} className="bg-[var(--surface-light)] rounded-lg px-2.5 py-1.5 text-center shrink-0 whitespace-nowrap" title={`${isPositive ? "+" : ""}${formatCurrency(delta)}`}>
                        <p className="text-[var(--text-muted)] text-[9px] leading-tight">{label}</p>
                        <p dir="ltr" className={`text-xs font-bold leading-tight ${isPositive ? "text-emerald-400" : "text-rose-400"}`}>
                          {formatChange(delta)}
                        </p>
                        {pct !== null && (
                          <p dir="ltr" className={`text-[9px] leading-tight ${isPositive ? "text-emerald-400" : "text-rose-400"}`}>
                            {formatPercentChange(pct)}
                          </p>
                        )}
                      </div>
                    );
                  });
                })()}
                <div className="w-full md:w-auto md:ms-auto flex bg-[var(--surface-light)] p-1 rounded-xl overflow-x-auto scrollbar-auto-hide">
                  {(
                    [
                      { key: "all", label: t("dashboard.all") },
                      { key: "bank_balance", label: t("dashboard.bankBalance") },
                      { key: "investments", label: t("dashboard.investmentValue") },
                      { key: "net_worth", label: t("dashboard.netWorth") },
                      { key: "debt_payments", label: t("dashboard.debtPayments") },
                    ] as const
                  ).map(({ key, label }) => (
                    <button
                      key={key}
                      onClick={() => setNetWorthView(key)}
                      className={`px-2 md:px-3 py-1.5 rounded-lg text-xs md:text-sm font-bold transition-all whitespace-nowrap ${
                        netWorthView === key
                          ? "bg-[var(--surface)] text-[var(--primary)] shadow-sm"
                          : "text-[var(--text-muted)] hover:text-[var(--text-default)]"
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="flex-1 min-h-0" data-testid="net-worth-chart">
                {renderChart()}
              </div>
            </>
          ) : (
            <p className="text-[var(--text-muted)] text-sm">📭 {t("dashboard.noNetWorthData")}</p>
          )}
        </div>
      </div>
    </div>
  );
}
