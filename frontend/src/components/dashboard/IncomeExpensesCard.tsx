import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { TrendingUp, TrendingDown, ArrowUp, ArrowDown, Minus, ChevronDown, ChevronUp } from "lucide-react";
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

/** How many recent months the ledger / breakdown views show before "Show earlier months". */
const DEFAULT_VISIBLE_MONTHS = 12;

/** The three rolling averages + a monthly series, feeding one KPI summary card. */
type KpiSeries = { avg3: number; avg6: number; avg12: number; series: number[] };

/** Mean of a numeric field over a slice of months (0 when empty). */
function avgOf(rows: { income: number }[] | undefined): number {
  if (!rows || rows.length === 0) return 0;
  return rows.reduce((s, d) => s + d.income, 0) / rows.length;
}

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
  const [visibleMonths, setVisibleMonths] = useState(DEFAULT_VISIBLE_MONTHS);
  const showMore = () => setVisibleMonths((v) => v + DEFAULT_VISIBLE_MONTHS);
  const showLess = () => setVisibleMonths(DEFAULT_VISIBLE_MONTHS);
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
          <KpiCards
            income={{
              avg3: avgOf(incomeOutcome?.slice(-3)),
              avg6: avgOf(incomeOutcome?.slice(-6)),
              avg12: avgOf(incomeOutcome?.slice(-12)),
              series: (incomeOutcome ?? []).slice(-12).map((d) => d.income),
            }}
            expenses={{
              avg3: monthlyExpenses?.avg_3_months ?? 0,
              avg6: monthlyExpenses?.avg_6_months ?? 0,
              avg12: monthlyExpenses?.avg_12_months ?? 0,
              series: (incomeOutcome ?? []).slice(-12).map((d) => Math.abs(d.expenses)),
            }}
          />

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
              <LedgerView rows={incomeOutcome ?? []} limit={visibleMonths} onShowMore={showMore} onShowLess={showLess} />
            </div>
          )}
          {incomeView === "by_source" && (
            <div className="flex-1 min-h-0 overflow-y-auto">
              {incomeBySourceData && incomeBySourceData.length > 0 ? (
                <CompositionView
                  rows={incomeBySourceData.map((d) => ({ month: d.month, values: d.sources }))}
                  palette={CHART_COLORS}
                  labelMode={labelMode}
                  limit={visibleMonths}
                  onShowMore={showMore}
                  onShowLess={showLess}
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
                  limit={visibleMonths}
                  onShowMore={showMore}
                  onShowLess={showLess}
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
 * The two KPI summary cards above the chart — one for income, one for expenses.
 * Each consolidates the 3/6/12-month rolling averages (12-month leads, 3M/6M
 * beside it), a 12-month sparkline for shape, and a trend chip comparing the
 * recent 3-month average to the 12-month baseline.
 */
function KpiCards({ income, expenses }: { income: KpiSeries; expenses: KpiSeries }) {
  const { t } = useTranslation();
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 md:gap-3 mb-3">
      <KpiCard label={t("dashboard.income")} kind="income" data={income} color={INCOME_COLOR} />
      <KpiCard label={t("dashboard.expenses")} kind="expense" data={expenses} color={EXPENSE_COLOR} />
    </div>
  );
}

function KpiCard({
  label,
  kind,
  data,
  color,
}: {
  label: string;
  kind: "income" | "expense";
  data: KpiSeries;
  color: string;
}) {
  const { t } = useTranslation();
  const Icon = kind === "income" ? TrendingUp : TrendingDown;
  const gradient =
    kind === "income"
      ? "linear-gradient(160deg, rgba(16,185,129,0.14), transparent 62%)"
      : "linear-gradient(160deg, rgba(244,63,94,0.14), transparent 62%)";
  return (
    <div
      data-testid={`kpi-${kind}`}
      className="rounded-xl border border-[var(--surface-light)] p-3 md:p-3.5"
      style={{ background: gradient }}
    >
      <div className="flex items-center gap-2 mb-2.5">
        <div
          className="p-1.5 rounded-lg"
          style={{ background: kind === "income" ? "rgba(16,185,129,0.16)" : "rgba(244,63,94,0.16)", color }}
        >
          <Icon size={15} />
        </div>
        <span className="text-xs font-bold text-[var(--text-muted)]">{label}</span>
        <div className="flex-1" />
        <TrendChip value={data.avg3} baseline={data.avg12} kind={kind} title={t("dashboard.avgTrendTitle")} />
      </div>
      <div className="flex items-end justify-between gap-3">
        <div>
          <div className="text-xl md:text-2xl font-extrabold tabular-nums leading-none">{formatCurrency(data.avg12)}</div>
          <div className="text-[10px] text-slate-500 mt-1">{t("dashboard.avg12mo")}</div>
        </div>
        <Sparkline series={data.series} color={color} />
      </div>
      <div className="flex gap-4 mt-2.5 pt-2.5 border-t border-[var(--surface-light)]">
        <div className="flex items-baseline gap-1.5">
          <span className="text-[10px] text-slate-500 font-semibold">{t("dashboard.mo3")}</span>
          <span className="text-xs font-bold tabular-nums">{formatCurrency(data.avg3)}</span>
        </div>
        <div className="flex items-baseline gap-1.5">
          <span className="text-[10px] text-slate-500 font-semibold">{t("dashboard.mo6")}</span>
          <span className="text-xs font-bold tabular-nums">{formatCurrency(data.avg6)}</span>
        </div>
      </div>
    </div>
  );
}

/**
 * Trend pill comparing a recent average to a baseline. "Good" is direction-aware:
 * rising income is good, falling expenses is good — both render green.
 */
function TrendChip({
  value,
  baseline,
  kind,
  title,
}: {
  value: number;
  baseline: number;
  kind: "income" | "expense";
  title: string;
}) {
  const d = baseline ? ((value - baseline) / baseline) * 100 : 0;
  const up = d >= 0.5;
  const down = d <= -0.5;
  const good = kind === "expense" ? down : up;
  const bad = kind === "expense" ? up : down;
  const Icon = up ? ArrowUp : down ? ArrowDown : Minus;
  const cls = good
    ? "text-emerald-400 bg-emerald-500/15"
    : bad
      ? "text-rose-400 bg-rose-500/15"
      : "text-slate-400 bg-[var(--surface-light)]";
  return (
    <span
      title={title}
      dir="ltr"
      className={`inline-flex items-center gap-0.5 text-[10px] font-bold px-1.5 py-0.5 rounded-full tabular-nums ${cls}`}
    >
      <Icon size={11} strokeWidth={2.5} />
      {Math.abs(d).toFixed(1)}%
    </span>
  );
}

/** Minimal filled sparkline (12-month trend) — no axes, just the shape + a last-point dot. */
function Sparkline({ series, color, width = 84, height = 32 }: { series: number[]; color: string; width?: number; height?: number }) {
  const clean = series.filter((v) => Number.isFinite(v));
  // Drop trailing zero-activity months (typically the current, still-partial
  // month) so the line doesn't nose-dive to 0 every time a new month starts.
  while (clean.length > 2 && clean[clean.length - 1] === 0) clean.pop();
  if (clean.length < 2) return null;
  const pad = 3;
  const mx = Math.max(...clean);
  const mn = Math.min(...clean);
  const rng = mx - mn || 1;
  const pts = clean.map((v, i) => {
    const x = pad + (i / (clean.length - 1)) * (width - 2 * pad);
    const y = height - pad - ((v - mn) / rng) * (height - 2 * pad);
    return [x, y] as const;
  });
  const line = pts.map((p) => p.join(",")).join(" ");
  const area = `${pad},${height - pad} ${line} ${width - pad},${height - pad}`;
  const last = pts[pts.length - 1];
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="flex-none" aria-hidden="true">
      <polygon points={area} fill={color} opacity={0.12} />
      <polyline points={line} fill="none" stroke={color} strokeWidth={1.8} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={last[0]} cy={last[1]} r={2.4} fill={color} />
    </svg>
  );
}

/**
 * Totals view — a statement-style ledger, newest month on top. Each row shows
 * the income bar (grows toward the centre), the expense bar (mirrored), and the
 * net for the month. Bars share one scale (widest of any income/|expense|) so
 * magnitudes stay comparable; the exact ₪ sits on every bar so nothing needs a
 * hover. Vertical layout keeps the month labels always visible (no bottom axis).
 */
function LedgerView({
  rows,
  limit,
  onShowMore,
  onShowLess,
}: {
  rows: { month: string; income: number; expenses: number }[];
  limit: number;
  onShowMore: () => void;
  onShowLess: () => void;
}) {
  const { t } = useTranslation();
  if (rows.length === 0) return <p className="text-[var(--text-muted)] text-sm">{t("common.noData")}</p>;

  // Robust scale over the FULL history so bar widths don't shift when the user
  // expands earlier months; only the *displayed* rows are capped to `limit`.
  const scaleMax = robustMax(rows.flatMap((d) => [d.income, Math.abs(d.expenses)]));
  const width = (v: number) => `${Math.min(Math.max((Math.abs(v) / scaleMax) * 100, 2), 100)}%`;
  const lastMonth = rows[rows.length - 1]?.month;
  const visible = rows.slice(-limit).reverse();

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
      {visible.map((d) => {
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
      <MonthPager total={rows.length} visible={visible.length} onShowMore={onShowMore} onShowLess={onShowLess} />
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
  limit,
  onShowMore,
  onShowLess,
}: {
  rows: { month: string; values: Record<string, number> }[];
  palette: string[];
  labelMode: LabelMode;
  sortSeries?: boolean;
  limit: number;
  onShowMore: () => void;
  onShowLess: () => void;
}) {
  // Stable series order + colour, shared by the legend and every row so a
  // category keeps its colour month to month.
  let series = Array.from(new Set(rows.flatMap((d) => Object.keys(d.values))));
  if (sortSeries) series = series.sort();
  const colorOf = (name: string) => palette[series.indexOf(name) % palette.length];

  const totalOf = (v: Record<string, number>) => series.reduce((s, name) => s + (v[name] || 0), 0);
  // Robust meter scale over the FULL history so widths stay stable across "Show
  // earlier months"; only the *displayed* rows are capped to `limit`.
  const meterMax = robustMax(rows.map((d) => totalOf(d.values)));
  const lastMonth = rows[rows.length - 1]?.month;
  const visible = rows.slice(-limit).reverse();

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
      {visible.map((d) => {
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
      <MonthPager total={rows.length} visible={visible.length} onShowMore={onShowMore} onShowLess={onShowLess} />
    </div>
  );
}

/**
 * "Show earlier months" / "Show less" control shown under a capped month list.
 * Hidden entirely when everything already fits in the default window.
 */
function MonthPager({
  total,
  visible,
  onShowMore,
  onShowLess,
}: {
  total: number;
  visible: number;
  onShowMore: () => void;
  onShowLess: () => void;
}) {
  const { t } = useTranslation();
  const hasMore = total > visible;
  const canCollapse = visible > DEFAULT_VISIBLE_MONTHS;
  if (!hasMore && !canCollapse) return null;
  return (
    <div className="flex items-center justify-center gap-4 pt-3 pb-1">
      {hasMore && (
        <button
          onClick={onShowMore}
          className="inline-flex items-center gap-1 text-xs font-bold text-[var(--primary)] hover:underline"
        >
          <ChevronDown size={14} />
          {t("dashboard.showEarlierMonths", { count: total - visible })}
        </button>
      )}
      {canCollapse && (
        <button
          onClick={onShowLess}
          className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--text-muted)] hover:text-[var(--text)]"
        >
          <ChevronUp size={14} />
          {t("dashboard.showLess")}
        </button>
      )}
    </div>
  );
}
