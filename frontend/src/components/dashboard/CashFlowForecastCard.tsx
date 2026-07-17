import { useQuery } from "@tanstack/react-query";
import Plot from "../common/LazyPlot";
import { TrendingUp, Wallet, CalendarClock } from "lucide-react";
import { useTranslation } from "react-i18next";
import { analyticsApi } from "../../services/api";
import { Skeleton } from "../common/Skeleton";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { formatCurrency } from "../../utils/numberFormatting";
import { chartTheme, plotlyConfig, gradientFill, CHART_COLORS } from "../../utils/plotlyLocale";

/**
 * "This Month" cash-flow forecast hero.
 *
 * Surfaces the projected month-end bank balance and the "safe to spend"
 * figure — the headline numbers Israeli budgeting apps lead with — backed by
 * a trend-based projection of the rest of the month. Reads from
 * ``/analytics/cash-flow-forecast``.
 */
export function CashFlowForecastSection() {
  const { t, i18n } = useTranslation();
  const qk = useQueryKeys();

  const { data, isLoading } = useQuery({
    queryKey: qk.analytics.cashFlowForecast(),
    queryFn: async () => {
      const res = await analyticsApi.getCashFlowForecast();
      return res.data;
    },
  });

  if (isLoading) {
    return <Skeleton variant="card" className="h-48" />;
  }

  if (!data) return null;

  const monthLabel = new Date(data.month + "-01").toLocaleDateString(
    i18n.language === "he" ? "he-IL" : "en-US",
    { month: "long", year: "numeric" },
  );

  const endPositive = data.projected_end_balance >= 0;
  const netPositive = data.projected_net >= 0;
  const elapsedPct = data.days_in_month
    ? Math.round((data.day_of_month / data.days_in_month) * 100)
    : 0;

  const actualDays = data.daily.filter((d) => d.actual_balance !== null);
  const projectedDays = data.daily.filter((d) => d.projected_balance !== null);

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] p-4 md:p-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-[var(--primary)]/15 text-[var(--primary)]">
            <CalendarClock size={16} />
          </div>
          <div>
            <p className="text-sm md:text-base font-bold leading-tight">{t("dashboard.forecast.title")}</p>
            <p className="text-[10px] md:text-xs text-[var(--text-muted)]" dir="auto">{monthLabel}</p>
          </div>
        </div>
        <span className="text-[10px] md:text-xs text-[var(--text-muted)] whitespace-nowrap">
          {t("dashboard.forecast.daysLeft", { count: data.days_remaining })}
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6">
        {/* Left: headline stats */}
        <div className="space-y-3">
          {/* Safe to spend */}
          <div className="bg-[var(--surface-light)] rounded-xl px-4 py-3">
            <div className="flex items-center gap-1.5 text-[var(--text-muted)]">
              <Wallet size={13} />
              <p className="text-[10px] md:text-xs uppercase tracking-wider">{t("dashboard.forecast.safeToSpend")}</p>
            </div>
            <p dir="ltr" className="text-2xl md:text-3xl font-bold mt-1 text-emerald-400 text-start">
              {formatCurrency(data.safe_to_spend)}
            </p>
            <p className="text-[10px] md:text-xs text-[var(--text-muted)] mt-0.5">
              {t("dashboard.forecast.perDay", { amount: formatCurrency(data.safe_to_spend_daily) })}
            </p>
          </div>

          {/* Projected end-of-month balance */}
          <div className="bg-[var(--surface-light)] rounded-xl px-4 py-3">
            <div className="flex items-center gap-1.5 text-[var(--text-muted)]">
              <TrendingUp size={13} />
              <p className="text-[10px] md:text-xs uppercase tracking-wider">{t("dashboard.forecast.projectedEndBalance")}</p>
            </div>
            <p
              dir="ltr"
              className={`text-2xl md:text-3xl font-bold mt-1 text-start ${endPositive ? "text-[var(--text-primary)]" : "text-rose-400"}`}
            >
              {formatCurrency(data.projected_end_balance)}
            </p>
            <p className="text-[10px] md:text-xs text-[var(--text-muted)] mt-0.5">
              {t("dashboard.forecast.fromBalance", { amount: formatCurrency(data.current_bank_balance) })}
            </p>
          </div>

          {/* Month progress */}
          <div>
            <div className="flex justify-between text-[10px] md:text-xs text-[var(--text-muted)] mb-1">
              <span>{t("dashboard.forecast.monthProgress")}</span>
              <span dir="ltr">{elapsedPct}%</span>
            </div>
            <div className="h-1.5 bg-[var(--surface-light)] rounded-full overflow-hidden">
              <div className="h-full bg-[var(--primary)] rounded-full transition-all" style={{ width: `${elapsedPct}%` }} />
            </div>
          </div>
        </div>

        {/* Right: trajectory chart + projected income/expenses */}
        <div className="flex flex-col">
          <div className="h-36 md:h-40 min-h-0">
            <Plot
              data={[
                {
                  x: actualDays.map((d) => d.date),
                  y: actualDays.map((d) => d.actual_balance as number),
                  name: t("dashboard.forecast.actual"),
                  type: "scatter",
                  mode: "lines",
                  line: { color: CHART_COLORS[0], width: 3, shape: "spline" },
                  ...gradientFill(CHART_COLORS[0]),
                },
                {
                  x: projectedDays.map((d) => d.date),
                  y: projectedDays.map((d) => d.projected_balance as number),
                  name: t("dashboard.forecast.projected"),
                  type: "scatter",
                  mode: "lines",
                  line: { color: netPositive ? "#10b981" : "#f43f5e", width: 2, dash: "dash", shape: "spline" },
                },
              ]}
              layout={{
                ...chartTheme,
                autosize: true,
                showlegend: false,
                margin: { l: 50, r: 12, t: 8, b: 24 },
                xaxis: { ...chartTheme.xaxis, type: "date", tickformat: "%d" },
                yaxis: { ...chartTheme.yaxis, automargin: true },
              }}
              style={{ width: "100%", height: "100%" }}
              config={plotlyConfig()}
            />
          </div>
          <div className="grid grid-cols-3 gap-2 mt-3">
            <div className="bg-[var(--surface-light)] rounded-lg px-2.5 py-2">
              <p className="text-[9px] md:text-[10px] text-[var(--text-muted)] truncate">{t("dashboard.forecast.expectedIncome")}</p>
              <p dir="ltr" className="text-xs md:text-sm font-bold text-emerald-400 text-start truncate">{formatCurrency(data.expected_income)}</p>
            </div>
            <div className="bg-[var(--surface-light)] rounded-lg px-2.5 py-2">
              <p className="text-[9px] md:text-[10px] text-[var(--text-muted)] truncate">{t("dashboard.forecast.expectedExpenses")}</p>
              <p dir="ltr" className="text-xs md:text-sm font-bold text-rose-400 text-start truncate">{formatCurrency(data.expected_expenses)}</p>
            </div>
            <div className="bg-[var(--surface-light)] rounded-lg px-2.5 py-2">
              <p className="text-[9px] md:text-[10px] text-[var(--text-muted)] truncate">{t("dashboard.forecast.projectedNet")}</p>
              <p dir="ltr" className={`text-xs md:text-sm font-bold text-start truncate ${netPositive ? "text-emerald-400" : "text-rose-400"}`}>
                {formatCurrency(data.projected_net)}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
