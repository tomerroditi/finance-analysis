import { useMemo, useState, type MouseEvent as ReactMouseEvent } from "react";
import { createPortal } from "react-dom";
import { useQuery } from "@tanstack/react-query";
import { TrendingUp, TrendingDown, ArrowUp, ArrowDown, Minus, ChevronDown, ChevronUp } from "lucide-react";
import { analyticsApi } from "../../services/api";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { useTranslation } from "react-i18next";
import { formatCurrency, formatChange } from "../../utils/numberFormatting";
import { CHART_COLORS } from "../../utils/chartStyle";
import {
  formatPeriodLabel,
  toYearlyComposition,
  toYearlyLedger,
  yearlyKpi,
  type CompositionRow,
  type LedgerRow,
  type Scope,
  type YearlyKpi,
} from "./incomeExpensesScope";

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

/**
 * Fill for a month meter whose total runs past the chart scale.
 *
 * The stripes are vertical rather than diagonal because the meter is 3px tall
 * with a 2px rounded cap. Across three pixels a 45° stripe is already almost
 * vertical, so the diagonal bought nothing and the rounding sheared both ends
 * into ragged points — beside a clean solid meter the bar read as torn rather
 * than deliberately hatched, and which rows showed it changed with every
 * filter toggle. Vertical stripes do not depend on the height at all, so they
 * stay crisp here and the rounded cap clips a full-height dash cleanly.
 */
const OVER_SCALE_HATCH =
  "repeating-linear-gradient(90deg, var(--text-muted) 0 3px, transparent 3px 6px)";

/** How many recent periods the ledger / breakdown views show before "Show earlier". */
const DEFAULT_VISIBLE_PERIODS = 12;

/**
 * Ledger grid: period label, income bar, expense bar, net.
 *
 * The two fixed columns are sized to their own widest content and no wider —
 * a bar grows toward the label beside it, so every spare pixel in the label
 * column reads as a gap between the bar's tip and the text it belongs to.
 * 56px fits "Sep '26" at text-xs/bold, 88px fits a six-figure net with its
 * sign and ₪. Both grids that use this (header + rows) must share it or the
 * column headings drift off their columns.
 */
const LEDGER_COLUMNS = "56px 1fr 1fr 88px";

/**
 * What one KPI summary card shows: a headline figure with its caption, up to
 * two secondary figures, and the baseline its trend chip measures against.
 * Both scopes fill the same shape — monthly with rolling averages, yearly
 * with per-year totals.
 */
type KpiSummary = {
  primary: number;
  primaryLabel: string;
  stats: { label: string; value: number }[];
  trendBaseline: number;
  trendTitle: string;
};

/** Mean of a numeric field over a slice of months (0 when empty). */
function avgOf(rows: { income: number }[] | undefined): number {
  if (!rows || rows.length === 0) return 0;
  return rows.reduce((s, d) => s + d.income, 0) / rows.length;
}

/**
 * Bar-scale cap = median(positive values) × `multiplier`. Anchoring to the
 * median (not the max or a high percentile) keeps typical months in the
 * mid-range with headroom, even when the data clusters on one value (e.g. a
 * constant salary) where a percentile would collapse onto the cluster and max
 * out every bar. Values above the cap are drawn full-width and flagged as
 * outliers — their exact ₪ label still tells the true story.
 */
function barCap(values: number[], multiplier = 1.6): number {
  const positives = values.filter((v) => v > 0).sort((a, b) => a - b);
  if (positives.length === 0) return 1;
  const median = positives[Math.floor(positives.length / 2)];
  return (median || positives[positives.length - 1] || 1) * multiplier;
}

/** Income & Expenses dashboard card (monthly/yearly scope, KPI summaries, refund/project filters, Totals/Income/Expenses sub-views). */
export function IncomeExpensesCard() {
  const { t } = useTranslation();
  const qk = useQueryKeys();
  const [incomeView, setIncomeView] = useState<"overview" | "by_source" | "by_category">("overview");
  const [scope, setScope] = useState<Scope>("monthly");
  const [visiblePeriods, setVisiblePeriods] = useState(DEFAULT_VISIBLE_PERIODS);
  const showMore = () => setVisiblePeriods((v) => v + DEFAULT_VISIBLE_PERIODS);
  const showLess = () => setVisiblePeriods(DEFAULT_VISIBLE_PERIODS);
  // A window measured in months means nothing once the rows are years, so a
  // scope switch starts the pager over.
  const changeScope = (next: Scope) => {
    setScope(next);
    setVisiblePeriods(DEFAULT_VISIBLE_PERIODS);
  };
  const [excludePendingRefunds, setExcludePendingRefunds] = useState(true);
  const [includeProjects, setIncludeProjects] = useState(false);

  const { data: incomeOutcome } = useQuery({
    queryKey: qk.analytics.incomeExpensesOverTime(includeProjects, excludePendingRefunds),
    queryFn: async () =>
      (await analyticsApi.getIncomeExpensesOverTime(!includeProjects, false, excludePendingRefunds)).data,
  });
  const { data: expensesByCategoryOverTime } = useQuery({
    queryKey: qk.analytics.expensesByCategoryOverTime(excludePendingRefunds),
    queryFn: async () =>
      (await analyticsApi.getExpensesByCategoryOverTime(excludePendingRefunds)).data,
  });
  const { data: incomeBySourceData } = useQuery({
    queryKey: qk.analytics.incomeBySourceOverTime(excludePendingRefunds),
    queryFn: async () =>
      (await analyticsApi.getIncomeBySourceOverTime(excludePendingRefunds)).data,
  });
  const { data: monthlyExpenses } = useQuery({
    queryKey: qk.analytics.monthlyExpenses(excludePendingRefunds, includeProjects),
    queryFn: async () => (await analyticsApi.getMonthlyExpenses(excludePendingRefunds, includeProjects)).data,
  });

  const yearly = scope === "yearly";
  const ledgerRows: LedgerRow[] = useMemo(
    () => (yearly ? toYearlyLedger(incomeOutcome ?? []) : (incomeOutcome ?? [])),
    [yearly, incomeOutcome],
  );
  const sourceRows: CompositionRow[] = useMemo(() => {
    const rows = (incomeBySourceData ?? []).map((d) => ({ month: d.month, values: d.sources }));
    return yearly ? toYearlyComposition(rows) : rows;
  }, [yearly, incomeBySourceData]);
  const categoryRows: CompositionRow[] = useMemo(() => {
    const rows = (expensesByCategoryOverTime ?? []).map((d) => ({ month: d.month, values: d.categories }));
    return yearly ? toYearlyComposition(rows) : rows;
  }, [yearly, expensesByCategoryOverTime]);

  const yearlyIncome = useMemo(
    () => yearlyKpi((incomeOutcome ?? []).map((d) => ({ month: d.month, value: d.income }))),
    [incomeOutcome],
  );
  // The yearly expense KPI folds the very series the monthly one averages, so
  // the two scopes can never disagree about a year; project spend arrives as
  // its own field there and is only counted when the chip asks for it.
  const yearlyExpenses = useMemo(
    () =>
      yearlyKpi(
        (monthlyExpenses?.months ?? []).map((m) => ({
          month: m.month,
          value: m.expenses + (includeProjects ? (m.project_expenses ?? 0) : 0),
        })),
      ),
    [monthlyExpenses, includeProjects],
  );

  const monthlySummary = (avg3: number, avg6: number, avg12: number): KpiSummary => ({
    primary: avg3,
    primaryLabel: t("dashboard.avg3mo"),
    stats: [
      { label: t("dashboard.mo6"), value: avg6 },
      { label: t("dashboard.mo12"), value: avg12 },
    ],
    trendBaseline: avg12,
    trendTitle: t("dashboard.avgTrendTitle"),
  });

  const yearlySummary = (kpi: YearlyKpi | null): KpiSummary => ({
    primary: kpi?.latest.value ?? 0,
    primaryLabel: kpi
      ? kpi.partial
        ? t("dashboard.yearToDateLabel", { year: kpi.latest.year })
        : kpi.latest.year
      : t("dashboard.scopeYearly"),
    stats: (kpi?.earlier ?? []).map((y) => ({ label: y.year, value: y.value })),
    trendBaseline: kpi?.baseline ?? 0,
    trendTitle: kpi?.partial ? t("dashboard.yearTrendTitleYtd") : t("dashboard.yearTrendTitle"),
  });

  const incomeSummary = yearly
    ? yearlySummary(yearlyIncome)
    : monthlySummary(
        avgOf(incomeOutcome?.slice(-3)),
        avgOf(incomeOutcome?.slice(-6)),
        avgOf(incomeOutcome?.slice(-12)),
      );
  const expenseSummary = yearly
    ? yearlySummary(yearlyExpenses)
    : monthlySummary(
        monthlyExpenses?.avg_3_months ?? 0,
        monthlyExpenses?.avg_6_months ?? 0,
        monthlyExpenses?.avg_12_months ?? 0,
      );

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] overflow-hidden flex flex-col">
      <div className="px-3 md:px-6 pt-4 md:pt-5 flex items-center justify-between gap-2">
        <h2 className="text-sm md:text-base font-bold">{t("dashboard.incomeAndExpenses")}</h2>
        <ScopeToggle scope={scope} onChange={changeScope} />
      </div>
      <div className="px-3 md:px-6 pb-4 md:pb-6 pt-4 min-h-[400px] md:h-[600px] overflow-y-auto flex flex-col">
        <div className="flex flex-col flex-1 min-h-0">
          <KpiCards income={incomeSummary} expenses={expenseSummary} />

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
              <div className="bg-[var(--surface-light)] rounded-xl overflow-hidden">
              <div className="flex p-1 overflow-x-auto scrollbar-auto-hide">
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
          </div>

          {incomeView === "overview" && (
            <div className="flex-1 min-h-0 overflow-y-auto">
              <LedgerView
                rows={ledgerRows}
                scope={scope}
                limit={visiblePeriods}
                onShowMore={showMore}
                onShowLess={showLess}
              />
            </div>
          )}
          {incomeView === "by_source" && (
            <div className="flex-1 min-h-0 overflow-y-auto">
              {sourceRows.length > 0 ? (
                <CompositionView
                  rows={sourceRows}
                  palette={CHART_COLORS}
                  scope={scope}
                  limit={visiblePeriods}
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
              {categoryRows.length > 0 ? (
                <CompositionView
                  rows={categoryRows}
                  palette={CATEGORY_COLORS}
                  sortSeries
                  scope={scope}
                  limit={visiblePeriods}
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
 * Monthly / yearly scope switch, in the card's title row. It re-folds the
 * series the card already holds, so flipping it costs no request.
 */
function ScopeToggle({ scope, onChange }: { scope: Scope; onChange: (next: Scope) => void }) {
  const { t } = useTranslation();
  return (
    <div data-testid="scope-toggle" className="flex flex-none p-0.5 rounded-lg bg-[var(--surface-light)]">
      {([
        { key: "monthly" as const, label: t("dashboard.scopeMonthly") },
        { key: "yearly" as const, label: t("dashboard.scopeYearly") },
      ]).map(({ key, label }) => (
        <button
          key={key}
          onClick={() => onChange(key)}
          aria-pressed={scope === key}
          className={`px-2.5 py-1 rounded-md text-[11px] md:text-xs font-bold whitespace-nowrap transition-all ${
            scope === key
              ? "bg-[var(--surface)] text-[var(--primary)] shadow-sm"
              : "text-[var(--text-muted)] hover:text-[var(--text-default)]"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

/**
 * The two KPI summary cards above the chart — one for income, one for expenses.
 * Compact and always side-by-side (one row at every width): the headline figure
 * leads (the 3-month average monthly, this year's total yearly), the other two
 * windows sit beneath, and a trend chip compares the headline to its baseline.
 */
function KpiCards({ income, expenses }: { income: KpiSummary; expenses: KpiSummary }) {
  const { t } = useTranslation();
  return (
    <div className="grid grid-cols-2 gap-2 md:gap-3 mb-3">
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
  data: KpiSummary;
  color: string;
}) {
  const Icon = kind === "income" ? TrendingUp : TrendingDown;
  const gradient =
    kind === "income"
      ? "linear-gradient(160deg, rgba(16,185,129,0.14), transparent 62%)"
      : "linear-gradient(160deg, rgba(244,63,94,0.14), transparent 62%)";
  return (
    <div
      data-testid={`kpi-${kind}`}
      className="rounded-xl border border-[var(--surface-light)] p-2.5 md:p-3.5"
      style={{ background: gradient }}
    >
      <div className="flex items-center gap-1.5 mb-2">
        <div
          className="p-1 rounded-md flex-none"
          style={{ background: kind === "income" ? "rgba(16,185,129,0.16)" : "rgba(244,63,94,0.16)", color }}
        >
          <Icon size={13} />
        </div>
        <span className="text-[11px] md:text-xs font-bold text-[var(--text-muted)] truncate">{label}</span>
        <div className="flex-1" />
        <TrendChip value={data.primary} baseline={data.trendBaseline} kind={kind} title={data.trendTitle} />
      </div>
      <div className="text-lg md:text-2xl font-extrabold tabular-nums leading-none">{formatCurrency(data.primary)}</div>
      <div className="text-[10px] text-slate-500 mt-1">{data.primaryLabel}</div>
      {data.stats.length > 0 && (
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-2 pt-2 border-t border-[var(--surface-light)]">
          {data.stats.map((stat) => (
            <div key={stat.label} className="flex items-baseline gap-1.5">
              <span className="text-[10px] text-slate-500 font-semibold">{stat.label}</span>
              <span className="text-[11px] md:text-xs font-bold tabular-nums">{formatCurrency(stat.value)}</span>
            </div>
          ))}
        </div>
      )}
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

/**
 * Totals view — a statement-style ledger, newest period on top. Each row shows
 * the income bar (grows toward the centre), the expense bar (mirrored), and the
 * net for the period. Bars share one scale (widest of any income/|expense|) so
 * magnitudes stay comparable; the exact ₪ sits on every bar so nothing needs a
 * hover. Vertical layout keeps the period labels always visible (no bottom axis).
 */
function LedgerView({
  rows,
  scope,
  limit,
  onShowMore,
  onShowLess,
}: {
  rows: LedgerRow[];
  scope: Scope;
  limit: number;
  onShowMore: () => void;
  onShowLess: () => void;
}) {
  const { t } = useTranslation();
  if (rows.length === 0) return <p className="text-[var(--text-muted)] text-sm">{t("common.noData")}</p>;

  // Median-anchored cap over the FULL history so typical months sit mid-range
  // (with headroom) and widths don't shift when earlier months are revealed;
  // only the *displayed* rows are capped to `limit`.
  const cap = barCap(rows.flatMap((d) => [d.income, Math.abs(d.expenses)]));
  const lastPeriod = rows[rows.length - 1]?.month;
  const visible = rows.slice(-limit).reverse();

  return (
    <div className="min-w-[300px]">
      <div
        className="grid gap-1.5 px-1 pb-2 text-[10px] font-bold uppercase tracking-wide text-[var(--text-muted)]"
        style={{ gridTemplateColumns: `${LEDGER_COLUMNS}` }}
      >
        <div>{scope === "yearly" ? t("dashboard.ledgerYear") : t("dashboard.ledgerMonth")}</div>
        <div className="text-end">{t("dashboard.income")}</div>
        <div>{t("dashboard.expenses")}</div>
        <div className="text-end">{t("dashboard.ledgerNet")}</div>
      </div>
      {visible.map((d) => {
        const net = d.income - Math.abs(d.expenses);
        const isCurrent = d.month === lastPeriod;
        const expenseColor = d.expenses < 0 ? EXPENSE_LIGHT : EXPENSE_COLOR;
        return (
          <div
            key={d.month}
            data-testid="ledger-row"
            data-month={d.month}
            className={`grid gap-1.5 items-center px-1 py-1.5 rounded-lg ${isCurrent ? "bg-[var(--primary)]/10" : ""}`}
            style={{ gridTemplateColumns: `${LEDGER_COLUMNS}` }}
          >
            <div className="text-xs font-bold text-[var(--text-muted)] whitespace-nowrap">
              {formatPeriodLabel(d.month)}
            </div>
            {/* income grows toward the centre; expenses mirror outward */}
            <LedgerBar value={d.income} kind="income" cap={cap} />
            <LedgerBar value={d.expenses} kind="expense" cap={cap} color={expenseColor} />
            <div
              className="text-xs font-extrabold text-end whitespace-nowrap tabular-nums"
              style={{ color: net >= 0 ? INCOME_COLOR : EXPENSE_COLOR }}
            >
              {formatChange(net, { compact: false })}
            </div>
          </div>
        );
      })}
      <PeriodPager
        total={rows.length}
        visible={visible.length}
        scope={scope}
        onShowMore={onShowMore}
        onShowLess={onShowLess}
      />
    </div>
  );
}

/**
 * One ledger bar. Income grows toward the centre, expenses mirror outward. A
 * value above the shared cap is drawn full-width and flagged as an outlier: a
 * hatched strip at the growing tip plus a dashed edge signal "off the scale",
 * while the exact ₪ still shows the real figure. Which physical edge that tip
 * is flips with the document direction, so everything marking it is logical.
 */
function LedgerBar({
  value,
  kind,
  cap,
  color,
}: {
  value: number;
  kind: "income" | "expense";
  cap: number;
  color?: string;
}) {
  const { t, i18n } = useTranslation();
  const abs = Math.abs(value);
  const pct = Math.min(Math.max((abs / cap) * 100, 2), 100);
  const capped = abs > cap;
  const income = kind === "income";
  const barColor = color ?? (income ? INCOME_COLOR : EXPENSE_COLOR);
  const soft = income ? "rgba(16,185,129,0.16)" : "rgba(244,63,94,0.16)";
  const borderRgba = income ? "rgba(16,185,129,0.5)" : "rgba(244,63,94,0.5)";
  // Flexbox anchors the bar on the inline axis, so the *growing* end is the
  // inline-start edge for income and the inline-end edge for expenses in
  // either direction — the tip markers must therefore be logical too. They
  // used to be physical (`left`/`borderLeft*`), which pinned them to the
  // anchored end under RTL: in Hebrew every over-scale bar carried its
  // hatch and its dashed edge on the side that never moves.
  const isRtl = i18n.language === "he";
  // The hatch's diagonal is the one thing with no logical form, so it is
  // mirrored by hand — otherwise the stripes lean against the growth in RTL.
  const tipOnLeft = income !== isRtl;
  return (
    <div className={`flex ${income ? "justify-end" : "justify-start"}`}>
      <div
        data-testid="ledger-bar"
        data-kind={kind}
        data-capped={capped ? "true" : "false"}
        className={`relative h-[22px] rounded-md flex items-center ${income ? "justify-end" : "justify-start"}`}
        title={capped ? t("dashboard.barAboveScale") : undefined}
        // The tip's colour and style are always given, never spread in only
        // when capped. React removes a style property that a re-render stops
        // supplying, and because the browser expands the `border` shorthand
        // into longhands, removing `borderInlineEndColor` does not fall back
        // to the shorthand — it falls back to `currentColor`, the inherited
        // text colour. A bar that lost its cap between renders therefore kept
        // a near-white 1px sliver at its tip. Which bars are capped depends on
        // a median over the visible data, so any filter toggle could strand
        // one. (A logical longhand set after the shorthand wins, same as a
        // physical one: within a declaration block the two cascade in
        // declaration order.)
        style={{
          width: `${pct}%`,
          background: soft,
          borderWidth: 1,
          borderStyle: "solid",
          borderColor: borderRgba,
          [income ? "borderInlineStartColor" : "borderInlineEndColor"]: capped
            ? barColor
            : borderRgba,
          [income ? "borderInlineStartStyle" : "borderInlineEndStyle"]: capped
            ? "dashed"
            : "solid",
        }}
      >
        {capped && (
          <div
            data-testid="ledger-bar-hatch"
            className="absolute inset-y-0 w-4 pointer-events-none"
            style={{
              [income ? "insetInlineStart" : "insetInlineEnd"]: 0,
              [income ? "borderStartStartRadius" : "borderStartEndRadius"]: 5,
              [income ? "borderEndStartRadius" : "borderEndEndRadius"]: 5,
              opacity: 0.6,
              background: `repeating-linear-gradient(${tipOnLeft ? "45deg" : "-45deg"}, ${barColor} 0 1.5px, transparent 1.5px 4.5px)`,
            }}
          />
        )}
        <span
          className="relative text-[11px] font-bold px-2 whitespace-nowrap tabular-nums"
          style={{ color: barColor }}
        >
          {formatCurrency(abs)}
        </span>
      </div>
    </div>
  );
}

/**
 * Breakdown view — one composition row per month, newest on top. Each bar is
 * normalised to full width and split by share, so the *mix* is directly
 * comparable and an outlier month can never dwarf the others. The month total
 * sits on the right with a thin magnitude meter beneath it (relative to the
 * biggest month), so absolute size is still legible.
 *
 * The bars themselves carry no text: a share printed inside a slice only ever
 * fit the handful of widest ones, so the row read as a few arbitrary numbers
 * over a band of anonymous colour. There is deliberately no colour legend
 * either — with 20+ categories it was a wall of swatches nobody could scan.
 * Instead every slice names itself, with both its amount and its share, in a
 * tooltip that follows the cursor and appears instantly (the native `title`
 * attribute made you wait a second per slice, which is unusable for hunting a
 * category).
 */
function CompositionView({
  rows,
  palette,
  sortSeries = false,
  scope,
  limit,
  onShowMore,
  onShowLess,
}: {
  rows: CompositionRow[];
  palette: string[];
  sortSeries?: boolean;
  scope: Scope;
  limit: number;
  onShowMore: () => void;
  onShowLess: () => void;
}) {
  const { t } = useTranslation();
  // Cursor-following tooltip: the only way to name a slice now that the legend
  // is gone, so it has to be instant. Portalled to <body> because the bar clips
  // its children (`overflow-hidden`) and the card may sit in a scroll container.
  const [tip, setTip] = useState<Tip | null>(null);
  const showTip = (e: ReactMouseEvent, name: string, val: number, pct: number, color: string) =>
    setTip({
      x: Math.min(Math.max(e.clientX, 90), window.innerWidth - 90),
      // Above the cursor, unless the row sits so close to the top of the
      // viewport that the panel would be cut off — then flip below it.
      y: e.clientY < 56 ? e.clientY + 20 : e.clientY - 12,
      below: e.clientY < 56,
      text: `${name}: ${formatCurrency(val)} (${Math.round(pct)}%)`,
      color,
    });
  // Stable series order + colour, shared by every row so a category keeps its
  // colour month to month.
  let series = Array.from(new Set(rows.flatMap((d) => Object.keys(d.values))));
  if (sortSeries) series = series.sort();
  const colorOf = (name: string) => palette[series.indexOf(name) % palette.length];

  const totalOf = (v: Record<string, number>) => series.reduce((s, name) => s + (v[name] || 0), 0);
  // Median-anchored meter cap over the FULL history so widths stay stable across
  // "Show earlier months"; totals above it are flagged as outliers.
  const meterCap = barCap(rows.map((d) => totalOf(d.values)));
  const lastPeriod = rows[rows.length - 1]?.month;
  const visible = rows.slice(-limit).reverse();

  return (
    <div className="min-w-[320px]" onMouseLeave={() => setTip(null)}>
      {visible.map((d) => {
        const total = totalOf(d.values);
        const isCurrent = d.month === lastPeriod;
        return (
          <div
            key={d.month}
            data-testid="composition-row"
            data-month={d.month}
            className={`grid gap-3 items-center px-1 py-2 rounded-lg ${isCurrent ? "bg-[var(--primary)]/10" : ""}`}
            style={{ gridTemplateColumns: "56px 1fr 112px" }}
          >
            <div className="text-xs font-bold text-[var(--text-muted)] whitespace-nowrap">
              {formatPeriodLabel(d.month)}
            </div>
            <div className="flex h-6 rounded-md overflow-hidden bg-[var(--background)]">
              {series.map((name) => {
                const val = d.values[name] || 0;
                if (val <= 0) return null;
                const pct = (val / total) * 100;
                const segColor = colorOf(name);
                return (
                  <div
                    key={name}
                    data-testid="composition-segment"
                    aria-label={`${name}: ${formatCurrency(val)} (${Math.round(pct)}%)`}
                    className="h-full"
                    style={{ width: `${pct}%`, background: segColor }}
                    onMouseEnter={(e) => showTip(e, name, val, pct, segColor)}
                    onMouseMove={(e) => showTip(e, name, val, pct, segColor)}
                    onMouseLeave={() => setTip(null)}
                  />
                );
              })}
            </div>
            <div className="text-end">
              <div className="text-xs font-extrabold whitespace-nowrap tabular-nums">{formatCurrency(total)}</div>
              <div
                className="h-[3px] rounded-sm bg-[var(--surface-light)] mt-1 overflow-hidden"
                title={total > meterCap ? t("dashboard.barAboveScale") : undefined}
              >
                <div
                  className="h-full rounded-sm"
                  style={{
                    width: `${Math.min((total / meterCap) * 100, 100)}%`,
                    background:
                      total > meterCap ? OVER_SCALE_HATCH : "var(--text-muted)",
                  }}
                />
              </div>
            </div>
          </div>
        );
      })}
      <PeriodPager
        total={rows.length}
        visible={visible.length}
        scope={scope}
        onShowMore={onShowMore}
        onShowLess={onShowLess}
      />
      <SegmentTooltip tip={tip} />
    </div>
  );
}

/**
 * A slice's hover readout: viewport coordinates, whether the panel hangs below
 * the cursor (top-of-viewport flip), the text, and the slice colour.
 */
type Tip = { x: number; y: number; below: boolean; text: string; color: string };

/**
 * The cursor-following slice tooltip, rendered into <body> so no ancestor's
 * `overflow-hidden` can clip it. Sits above the cursor (below it near the top
 * of the viewport) and is horizontally clamped so it never runs off an edge.
 */
function SegmentTooltip({ tip }: { tip: Tip | null }) {
  if (!tip) return null;
  return createPortal(
    <div
      data-testid="composition-tooltip"
      className="pointer-events-none fixed z-50 flex items-center gap-1.5 whitespace-nowrap rounded-lg border border-white/10 bg-[var(--surface-light)] px-2.5 py-1.5 text-[11px] font-semibold text-white shadow-xl"
      style={{
        left: tip.x,
        top: tip.y,
        transform: `translate(-50%, ${tip.below ? "0" : "-100%"})`,
      }}
    >
      <i className="h-2 w-2 flex-none rounded-sm" style={{ background: tip.color }} />
      {tip.text}
    </div>,
    document.body,
  );
}

/**
 * "Show earlier months/years" / "Show less" control shown under a capped period
 * list. Hidden entirely when everything already fits in the default window.
 */
function PeriodPager({
  total,
  visible,
  scope,
  onShowMore,
  onShowLess,
}: {
  total: number;
  visible: number;
  scope: Scope;
  onShowMore: () => void;
  onShowLess: () => void;
}) {
  const { t } = useTranslation();
  const hasMore = total > visible;
  const canCollapse = visible > DEFAULT_VISIBLE_PERIODS;
  if (!hasMore && !canCollapse) return null;
  return (
    <div className="flex items-center justify-center gap-4 pt-3 pb-1">
      {hasMore && (
        <button
          onClick={onShowMore}
          className="inline-flex items-center gap-1 text-xs font-bold text-[var(--primary)] hover:underline"
        >
          <ChevronDown size={14} />
          {t(scope === "yearly" ? "dashboard.showEarlierYears" : "dashboard.showEarlierMonths", {
            count: total - visible,
          })}
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
