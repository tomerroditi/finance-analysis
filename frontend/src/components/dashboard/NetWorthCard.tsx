import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import Plot from "../common/LazyPlot";
import { analyticsApi } from "../../services/api";
import { useDemoMode } from "../../context/DemoModeContext";
import { useTranslation } from "react-i18next";
import { formatCurrency, formatChange, formatPercentChange } from "../../utils/numberFormatting";
import { chartTheme, plotlyConfig, barMarker } from "../../utils/plotlyLocale";

type NetWorthView = "all" | "bank_balance" | "investments" | "net_worth" | "debt_payments";

/** Net Worth analytics dashboard card (period chips + bank/investments/net-worth/debt toggle). */
export function NetWorthCard() {
  const { t } = useTranslation();
  const { isDemoMode } = useDemoMode();
  const [netWorthView, setNetWorthView] = useState<NetWorthView>("all");

  const { data: debtPaymentsData } = useQuery({
    queryKey: ["debt-payments", isDemoMode],
    queryFn: async () => (await analyticsApi.getDebtPaymentsOverTime()).data,
  });

  const { data: netWorthData } = useQuery({
    queryKey: ["net-worth-over-time", isDemoMode],
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

  const getNetWorthTraces = (): Plotly.Data[] => {
    if (!netWorthData || netWorthData.length === 0) return [];
    if (netWorthView === "debt_payments") return [];

    if (netWorthView === "all") {
      return [
        {
          x: netWorthData.map((d) => d.month),
          y: netWorthData.map((d) => d.bank_balance),
          name: t("dashboard.bankBalance"),
          type: "scatter",
          mode: "lines",
          line: { color: "#f59e0b", width: 2.5, shape: "spline" },
        },
        {
          x: netWorthData.map((d) => d.month),
          y: netWorthData.map((d) => d.investment_value),
          name: t("dashboard.investmentValue"),
          type: "scatter",
          mode: "lines",
          line: { color: "#6366f1", width: 2.5, shape: "spline" },
        },
        {
          x: netWorthData.map((d) => d.month),
          y: netWorthData.map((d) => d.net_worth),
          name: t("dashboard.netWorth"),
          type: "scatter",
          mode: "lines",
          line: { color: "#10b981", width: 3, shape: "spline" },
        },
      ];
    }

    if (!netWorthDeltas) return [];
    const config = seriesConfig[netWorthView];

    return [
      {
        x: netWorthDeltas.map((d) => d.month),
        y: netWorthDeltas.map((d) => d[config.deltaKey]),
        name: t("dashboard.monthlyChange"),
        type: "bar",
        marker: barMarker(
          netWorthDeltas.map((d) =>
            d[config.deltaKey] >= 0 ? "#10b981" : "#ef4444",
          ),
        ),
      },
      {
        x: netWorthDeltas.map((d) => d.month),
        y: netWorthDeltas.map((d) => d[config.dataKey]),
        name: config.label,
        type: "scatter",
        mode: "lines",
        line: { color: config.color, width: 3, shape: "spline" },
        yaxis: "y2",
      },
    ];
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
              <div className="flex-1 min-h-0">
                {netWorthView === "debt_payments" ? (
                  debtPaymentsData && debtPaymentsData.length > 0 ? (() => {
                    const allTags = Array.from(
                      new Set(debtPaymentsData.flatMap((d) => Object.keys(d.tags))),
                    ).sort();
                    const colors = [
                      "#f43f5e", "#3b82f6", "#f59e0b", "#8b5cf6",
                      "#06b6d4", "#ec4899", "#10b981", "#f97316",
                    ];
                    return (
                      <Plot
                        data={allTags.map((tag, i) => ({
                          x: debtPaymentsData.map((d) => d.month),
                          y: debtPaymentsData.reduce((acc: number[], d) => {
                            acc.push((acc.length > 0 ? acc[acc.length - 1] : 0) + (d.tags[tag] || 0));
                            return acc;
                          }, []),
                          type: "scatter" as const,
                          mode: "lines" as const,
                          line: { color: colors[i % colors.length], width: 2, shape: "spline" as const },
                          name: tag,
                          stackgroup: "debt",
                        }))}
                        layout={{
                          ...chartTheme,
                          autosize: true,
                          xaxis: { ...chartTheme.xaxis, type: "category" },
                          legend: { orientation: "h", y: -0.15, x: 0.5, xanchor: "center" },
                        }}
                        style={{ width: "100%", height: "100%" }}
                        config={plotlyConfig()}
                      />
                    );
                  })() : (
                    <p className="text-[var(--text-muted)]">{t("dashboard.noData")}</p>
                  )
                ) : (
                  <Plot
                    data={getNetWorthTraces()}
                    layout={{
                      ...chartTheme,
                      autosize: true,
                      xaxis: { ...chartTheme.xaxis, type: "date" },
                      yaxis: {
                        ...chartTheme.yaxis,
                        title: {
                          text: netWorthView === "all" ? t("dashboard.amountILS") : t("dashboard.monthlyChange"),
                          font: { color: "#94a3b8" },
                        },
                        tickfont: { color: "#94a3b8" },
                        automargin: true,
                      },
                      ...(netWorthView !== "all" && {
                        yaxis2: {
                          title: {
                            text: seriesConfig[netWorthView].label,
                            font: { color: seriesConfig[netWorthView].color },
                          },
                          tickfont: { color: seriesConfig[netWorthView].color },
                          overlaying: "y" as const,
                          side: "right" as const,
                          showgrid: false,
                          automargin: true,
                        },
                      }),
                      legend: { orientation: "h", y: -0.15, x: 0.5, xanchor: "center" },
                    }}
                    style={{ width: "100%", height: "100%" }}
                    config={plotlyConfig()}
                  />
                )}
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
