import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Calculator } from "lucide-react";
import { analyticsApi } from "../../services/api";
import { useDemoMode } from "../../context/DemoModeContext";
import { useTranslation } from "react-i18next";
import { formatCurrency, formatCompactCurrency, formatChange } from "../../utils/numberFormatting";
import { formatMonthShort } from "../../utils/dateFormatting";
import { CHART_COLORS } from "../../utils/plotlyLocale";

const INCOME_COLOR = "#10b981";
const EXPENSE_COLOR = "#f43f5e";
const EXPENSE_LIGHT = "#fda4af";

/** Warm→cool palette for the expense-category composition bars. */
const CATEGORY_COLORS = [
  "#f43f5e", "#f97316", "#f59e0b", "#eab308",
  "#84cc16", "#22c55e", "#14b8a6", "#06b6d4",
  "#3b82f6", "#6366f1", "#8b5cf6", "#a855f7",
  "#d946ef", "#ec4899", "#fb7185", "#ef4444",
];

type LabelMode = "pct" | "amt";

/**
 * Robust upper bound for bar scaling: the p-th percentile of the positive
 * values (default 90th). Scaling decorative bars to this instead of the raw
 * max stops a single outlier month (a bonus, a renovation) from squashing
 * every normal month into a 2% sliver — the outlier's bar just caps out while
 * its exact ₪ label still tells the true story.
 */
function robustMax(values: number[], p = 0.9): number {
  const positives = values.filter((v) => v > 0).sort((a, b) => a - b);
  if (positives.length === 0) return 1;
  const idx = Math.min(positives.length - 1, Math.floor(p * (positives.length - 1)));
  return positives[idx] || positives[positives.length - 1] || 1;
}

/** Income & Expenses dashboard card (KPI averages, refund/project filters, Totals/Income/Expenses sub-views). */
export function IncomeExpensesCard() {
  const { t } = useTranslation();
  const { isDemoMode } = useDemoMode();
  const [incomeView, setIncomeView] = useState<"overview" | "by_source" | "by_category">("overview");
  const [labelMode, setLabelMode] = useState<LabelMode>("pct");
  const [excludePendingRefunds, setExcludePendingRefunds] = useState(true);
  const [includeProjects, setIncludeProjects] = useState(false);
  const [excludeRefunds, setExcludeRefunds] = useState(false);

  const { data: incomeOutcome } = useQuery({
    queryKey: ["income-outcome", includeProjects, excludeRefunds, isDemoMode],
    queryFn: async () => (await analyticsApi.getIncomeExpensesOverTime(!includeProjects, false, excludeRefunds)).data,
  });
  const { data: expensesByCategoryOverTime } = useQuery({
    queryKey: ["expenses-by-category-over-time", isDemoMode],
    queryFn: async () => (await analyticsApi.getExpensesByCategoryOverTime()).data,
  });
  const { data: incomeBySourceData } = useQuery({
    queryKey: ["income-by-source", isDemoMode],
    queryFn: async () => (await analyticsApi.getIncomeBySourceOverTime()).data,
  });
  const { data: monthlyExpenses } = useQuery({
    queryKey: ["monthly-expenses", excludePendingRefunds, includeProjects, isDemoMode],
    queryFn: async () => (await analyticsApi.getMonthlyExpenses(excludePendingRefunds, includeProjects)).data,
  });

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] overflow-hidden flex flex-col">
      <div className="px-3 md:px-6 pt-4 md:pt-5">
        <h2 className="text-sm md:text-base font-bold">{t("dashboard.incomeAndExpenses")}</h2>
      </div>
      <div className="px-3 md:px-6 pb-4 md:pb-6 pt-4 min-h-[400px] md:h-[600px] overflow-y-auto flex flex-col">
        <div className="flex flex-col flex-1 min-h-0">
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2 md:gap-3 mb-3">
            {(() => {
              const recent3 = incomeOutcome?.slice(-3) || [];
              const recent6 = incomeOutcome?.slice(-6) || [];
              const recent12 = incomeOutcome?.slice(-12) || [];
              const avgIncome3 = recent3.length ? recent3.reduce((s, d) => s + d.income, 0) / recent3.length : 0;
              const avgIncome6 = recent6.length ? recent6.reduce((s, d) => s + d.income, 0) / recent6.length : 0;
              const avgIncome12 = recent12.length ? recent12.reduce((s, d) => s + d.income, 0) / recent12.length : 0;
              return (
                <>
                  <div className="bg-[var(--surface-light)] rounded-xl px-3 py-2 flex items-center gap-2">
                    <div className="p-1.5 rounded-lg bg-emerald-500/20 text-emerald-400"><Calculator size={14} /></div>
                    <div>
                      <p className="text-[var(--text-muted)] text-[10px]">{t("dashboard.avgIncome3Months")}</p>
                      <p className="text-sm font-bold">{formatCurrency(avgIncome3)}</p>
                    </div>
                  </div>
                  <div className="bg-[var(--surface-light)] rounded-xl px-3 py-2 flex items-center gap-2">
                    <div className="p-1.5 rounded-lg bg-emerald-500/20 text-emerald-400"><Calculator size={14} /></div>
                    <div>
                      <p className="text-[var(--text-muted)] text-[10px]">{t("dashboard.avgIncome6Months")}</p>
                      <p className="text-sm font-bold">{formatCurrency(avgIncome6)}</p>
                    </div>
                  </div>
                  <div className="bg-[var(--surface-light)] rounded-xl px-3 py-2 flex items-center gap-2">
                    <div className="p-1.5 rounded-lg bg-emerald-500/20 text-emerald-400"><Calculator size={14} /></div>
                    <div>
                      <p className="text-[var(--text-muted)] text-[10px]">{t("dashboard.avgIncome12Months")}</p>
                      <p className="text-sm font-bold">{formatCurrency(avgIncome12)}</p>
                    </div>
                  </div>
                  <div className="bg-[var(--surface-light)] rounded-xl px-3 py-2 flex items-center gap-2">
                    <div className="p-1.5 rounded-lg bg-rose-500/20 text-rose-400"><Calculator size={14} /></div>
                    <div>
                      <p className="text-[var(--text-muted)] text-[10px]">{t("dashboard.avgExpenses3Months")}</p>
                      <p className="text-sm font-bold">{formatCurrency(monthlyExpenses?.avg_3_months ?? 0)}</p>
                    </div>
                  </div>
                  <div className="bg-[var(--surface-light)] rounded-xl px-3 py-2 flex items-center gap-2">
                    <div className="p-1.5 rounded-lg bg-rose-500/20 text-rose-400"><Calculator size={14} /></div>
                    <div>
                      <p className="text-[var(--text-muted)] text-[10px]">{t("dashboard.avgExpenses6Months")}</p>
                      <p className="text-sm font-bold">{formatCurrency(monthlyExpenses?.avg_6_months ?? 0)}</p>
                    </div>
                  </div>
                  <div className="bg-[var(--surface-light)] rounded-xl px-3 py-2 flex items-center gap-2">
                    <div className="p-1.5 rounded-lg bg-rose-500/20 text-rose-400"><Calculator size={14} /></div>
                    <div>
                      <p className="text-[var(--text-muted)] text-[10px]">{t("dashboard.avgExpenses12Months")}</p>
                      <p className="text-sm font-bold">{formatCurrency(monthlyExpenses?.avg_12_months ?? 0)}</p>
                    </div>
                  </div>
                </>
              );
            })()}
          </div>

          <div className="flex flex-col md:flex-row md:items-center justify-between gap-2 mb-3">
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => setExcludePendingRefunds(!excludePendingRefunds)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium border transition-colors ${
                  excludePendingRefunds
                    ? "bg-[var(--primary)]/10 border-[var(--primary)]/20 text-[var(--primary)]"
                    : "bg-[var(--surface-light)] border-[var(--surface-light)] text-[var(--text-muted)]"
                }`}
              >
                {excludePendingRefunds
                  ? t("dashboard.pendingRefundsExcluded")
                  : t("dashboard.pendingRefundsIncluded")}
              </button>
              <button
                onClick={() => setExcludeRefunds(!excludeRefunds)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium border transition-colors ${
                  excludeRefunds
                    ? "bg-cyan-500/10 border-cyan-500/20 text-cyan-400"
                    : "bg-[var(--surface-light)] border-[var(--surface-light)] text-[var(--text-muted)]"
                }`}
              >
                {excludeRefunds
                  ? t("dashboard.refundsExcluded")
                  : t("dashboard.refundsIncluded")}
              </button>
              <button
                onClick={() => setIncludeProjects(!includeProjects)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium border transition-colors ${
                  includeProjects
                    ? "bg-indigo-500/10 border-indigo-500/20 text-indigo-400"
                    : "bg-[var(--surface-light)] border-[var(--surface-light)] text-[var(--text-muted)]"
                }`}
              >
                {includeProjects
                  ? t("dashboard.projectExpensesIncluded")
                  : t("dashboard.projectExpensesExcluded")}
              </button>
            </div>
            <div className="flex items-center gap-2">
              {incomeView !== "overview" && (
                <div className="flex bg-[var(--surface-light)] p-1 rounded-xl">
                  {([
                    { key: "pct" as const, label: "%", aria: t("dashboard.showShare") },
                    { key: "amt" as const, label: "₪", aria: t("dashboard.showAmount") },
                  ]).map(({ key, label, aria }) => (
                    <button
                      key={key}
                      onClick={() => setLabelMode(key)}
                      aria-label={aria}
                      aria-pressed={labelMode === key}
                      className={`px-2.5 py-1.5 rounded-lg text-xs font-bold transition-all ${
                        labelMode === key
                          ? "bg-[var(--surface)] text-[var(--primary)] shadow-sm"
                          : "text-[var(--text-muted)] hover:text-[var(--text-default)]"
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              )}
              <div className="flex bg-[var(--surface-light)] p-1 rounded-xl overflow-x-auto scrollbar-auto-hide">
                {([
                  { key: "overview" as const, label: t("dashboard.totals") },
                  { key: "by_source" as const, label: t("dashboard.incomeBreakdown") },
                  { key: "by_category" as const, label: t("dashboard.expensesBreakdown") },
                ]).map(({ key, label }) => (
                  <button
                    key={key}
                    onClick={() => setIncomeView(key)}
                    className={`px-2 md:px-3 py-1.5 rounded-lg text-xs md:text-sm font-bold transition-all whitespace-nowrap ${
                      incomeView === key
                        ? "bg-[var(--surface)] text-[var(--primary)] shadow-sm"
                        : "text-[var(--text-muted)] hover:text-[var(--text-default)]"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {incomeView === "overview" && (
            <div className="flex-1 min-h-0 overflow-y-auto">
              <LedgerView rows={incomeOutcome ?? []} />
            </div>
          )}
          {incomeView === "by_source" && (
            <div className="flex-1 min-h-0 overflow-y-auto">
              {incomeBySourceData && incomeBySourceData.length > 0 ? (
                <CompositionView
                  rows={incomeBySourceData.map((d) => ({ month: d.month, values: d.sources }))}
                  palette={CHART_COLORS}
                  labelMode={labelMode}
                />
              ) : (
                <p className="text-[var(--text-muted)] text-sm">📭 {t("dashboard.noIncomeSourceData")}</p>
              )}
            </div>
          )}
          {incomeView === "by_category" && (
            <div className="flex-1 min-h-0 overflow-y-auto">
              {expensesByCategoryOverTime && expensesByCategoryOverTime.length > 0 ? (
                <CompositionView
                  rows={expensesByCategoryOverTime.map((d) => ({ month: d.month, values: d.categories }))}
                  palette={CATEGORY_COLORS}
                  labelMode={labelMode}
                  sortSeries
                />
              ) : (
                <p className="text-[var(--text-muted)]">{t("common.noData")}</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Totals view — a statement-style ledger, newest month on top. Each row shows
 * the income bar (grows toward the centre), the expense bar (mirrored), and the
 * net for the month. Bars share one scale (widest of any income/|expense|) so
 * magnitudes stay comparable; the exact ₪ sits on every bar so nothing needs a
 * hover. Vertical layout keeps the month labels always visible (no bottom axis).
 */
function LedgerView({ rows }: { rows: { month: string; income: number; expenses: number }[] }) {
  const { t } = useTranslation();
  if (rows.length === 0) return <p className="text-[var(--text-muted)] text-sm">{t("common.noData")}</p>;

  // Robust scale so one outlier month doesn't squash the rest to slivers.
  const scaleMax = robustMax(rows.flatMap((d) => [d.income, Math.abs(d.expenses)]));
  const width = (v: number) => `${Math.min(Math.max((Math.abs(v) / scaleMax) * 100, 2), 100)}%`;
  const lastMonth = rows[rows.length - 1]?.month;

  return (
    <div className="min-w-[300px]">
      <div
        className="grid gap-3 px-1 pb-2 text-[10px] font-bold uppercase tracking-wide text-[var(--text-muted)]"
        style={{ gridTemplateColumns: "60px 1fr 1fr 92px" }}
      >
        <div>{t("dashboard.ledgerMonth")}</div>
        <div className="text-end">{t("dashboard.income")}</div>
        <div>{t("dashboard.expenses")}</div>
        <div className="text-end">{t("dashboard.ledgerNet")}</div>
      </div>
      {rows.slice().reverse().map((d) => {
        const net = d.income - Math.abs(d.expenses);
        const isCurrent = d.month === lastMonth;
        const expenseColor = d.expenses < 0 ? EXPENSE_LIGHT : EXPENSE_COLOR;
        return (
          <div
            key={d.month}
            data-testid="ledger-row"
            data-month={d.month}
            className={`grid gap-3 items-center px-1 py-1.5 rounded-lg ${isCurrent ? "bg-[var(--primary)]/10" : ""}`}
            style={{ gridTemplateColumns: "60px 1fr 1fr 92px" }}
          >
            <div className="text-xs font-bold text-[var(--text-muted)] whitespace-nowrap">
              {formatMonthShort(d.month)}
            </div>
            {/* income — grows toward the centre */}
            <div className="flex justify-end">
              <div
                className="h-[22px] rounded-md flex items-center justify-end"
                style={{
                  width: width(d.income),
                  background: "rgba(16,185,129,0.16)",
                  border: "1px solid rgba(16,185,129,0.5)",
                }}
              >
                <span className="text-[11px] font-bold px-2 whitespace-nowrap tabular-nums" style={{ color: INCOME_COLOR }}>
                  {formatCurrency(d.income)}
                </span>
              </div>
            </div>
            {/* expenses — mirrored, grows from the centre outward */}
            <div className="flex justify-start">
              <div
                className="h-[22px] rounded-md flex items-center justify-start"
                style={{
                  width: width(d.expenses),
                  background: "rgba(244,63,94,0.16)",
                  border: "1px solid rgba(244,63,94,0.5)",
                }}
              >
                <span className="text-[11px] font-bold px-2 whitespace-nowrap tabular-nums" style={{ color: expenseColor }}>
                  {formatCurrency(Math.abs(d.expenses))}
                </span>
              </div>
            </div>
            <div
              className="text-xs font-extrabold text-end whitespace-nowrap tabular-nums"
              style={{ color: net >= 0 ? INCOME_COLOR : EXPENSE_COLOR }}
            >
              {formatChange(net, { compact: false })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/**
 * Breakdown view — one composition row per month, newest on top. Each bar is
 * normalised to full width and split by share, so the *mix* is directly
 * comparable and an outlier month can never dwarf the others. The month total
 * sits on the right with a thin magnitude meter beneath it (relative to the
 * biggest month), so absolute size is still legible. Segment labels show the
 * share (%) or exact amount (₪) per `labelMode`, printed only where the slice
 * is wide enough to hold them; every slice reveals its value on hover.
 */
function CompositionView({
  rows,
  palette,
  labelMode,
  sortSeries = false,
}: {
  rows: { month: string; values: Record<string, number> }[];
  palette: string[];
  labelMode: LabelMode;
  sortSeries?: boolean;
}) {
  // Stable series order + colour, shared by the legend and every row so a
  // category keeps its colour month to month.
  let series = Array.from(new Set(rows.flatMap((d) => Object.keys(d.values))));
  if (sortSeries) series = series.sort();
  const colorOf = (name: string) => palette[series.indexOf(name) % palette.length];

  const totalOf = (v: Record<string, number>) => series.reduce((s, name) => s + (v[name] || 0), 0);
  // Robust scale for the magnitude meter so an outlier month doesn't flatten it.
  const meterMax = robustMax(rows.map((d) => totalOf(d.values)));
  const lastMonth = rows[rows.length - 1]?.month;

  // amounts need more room than a "42%" — raise the label threshold accordingly.
  const threshold = labelMode === "amt" ? 16 : 11;

  return (
    <div className="min-w-[320px]">
      <div className="flex flex-wrap gap-x-3.5 gap-y-2 mb-3">
        {series.map((name) => (
          <span key={name} className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)]">
            <i className="w-2.5 h-2.5 rounded-sm flex-none" style={{ background: colorOf(name) }} />
            {name}
          </span>
        ))}
      </div>
      {rows.slice().reverse().map((d) => {
        const total = totalOf(d.values);
        const isCurrent = d.month === lastMonth;
        return (
          <div
            key={d.month}
            data-testid="composition-row"
            data-month={d.month}
            className={`grid gap-3 items-center px-1 py-2 rounded-lg ${isCurrent ? "bg-[var(--primary)]/10" : ""}`}
            style={{ gridTemplateColumns: "56px 1fr 112px" }}
          >
            <div className="text-xs font-bold text-[var(--text-muted)] whitespace-nowrap">
              {formatMonthShort(d.month)}
            </div>
            <div className="flex h-6 rounded-md overflow-hidden bg-[var(--background)]">
              {series.map((name) => {
                const val = d.values[name] || 0;
                if (val <= 0) return null;
                const pct = (val / total) * 100;
                const label = labelMode === "amt" ? formatCompactCurrency(val) : `${Math.round(pct)}%`;
                return (
                  <div
                    key={name}
                    className="h-full flex items-center justify-center overflow-hidden"
                    style={{ width: `${pct}%`, background: colorOf(name) }}
                    title={`${name}: ${formatCurrency(val)} (${Math.round(pct)}%)`}
                  >
                    {pct >= threshold && (
                      <span
                        className="text-[9px] font-extrabold whitespace-nowrap tabular-nums"
                        style={{ color: "#fff", textShadow: "0 1px 2px rgba(0,0,0,0.35)" }}
                      >
                        {label}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
            <div className="text-end">
              <div className="text-xs font-extrabold whitespace-nowrap tabular-nums">{formatCurrency(total)}</div>
              <div className="h-[3px] rounded-sm bg-[var(--surface-light)] mt-1 overflow-hidden">
                <div className="h-full rounded-sm bg-[var(--text-muted)]" style={{ width: `${Math.min((total / meterMax) * 100, 100)}%` }} />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
