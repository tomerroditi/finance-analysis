import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import { createPortal } from "react-dom";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { TrendingUp, TrendingDown, ArrowUp, ArrowDown, Minus, ChevronDown, ChevronUp } from "lucide-react";
import { analyticsApi } from "../../services/api";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { useTranslation } from "react-i18next";
import { formatCurrency, formatChange } from "../../utils/numberFormatting";
import { CHART_COLORS, isTouchDevice } from "../../utils/chartStyle";
import {
  allTimeKpi,
  barCap,
  formatPeriodLabel,
  sliceWindow,
  toAllComposition,
  toAllLedger,
  toLedger,
  toYearlyComposition,
  toYearlyLedger,
  yearlyKpi,
  type AllKpi,
  type CompositionRow,
  type LedgerRow,
  type RangeWindow,
  type Scope,
  type YearlyKpi,
} from "./incomeExpensesScope";
import { IncomeExpensesDonut } from "./IncomeExpensesDonut";
import { IncomeExpensesFocus } from "./IncomeExpensesFocus";

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

/** Label for each all-scope window, used by both the chips and the KPI caption. */
const RANGE_LABEL_KEYS: Record<RangeWindow, string> = {
  all: "dashboard.scopeAll",
  year: "dashboard.rangeThisYear",
  last12m: "dashboard.rangeLast12m",
};

/** How many recent periods the ledger / breakdown views show before "Show earlier". */
const DEFAULT_VISIBLE_PERIODS = 12;

/**
 * Ledger grid: period label, income bar, expense bar, net.
 *
 * A bar grows toward the label beside it, so every spare pixel in a label
 * column reads as a gap between the bar's tip and the text it belongs to.
 * Fixed widths could not get that to zero, because they had to hold the
 * widest content any household might ever have: the 56px period column
 * carried 4px of air on every row, and the 88px net column — sized for a
 * seven-figure net almost nobody has — carried about 17px.
 *
 * `max-content` sizes each column to the widest label actually on screen, so
 * that air goes away and a net that really is seven figures still cannot be
 * clipped. It also stops the period column from being a bet on font metrics:
 * 56px was measured against the English labels, and the Hebrew ones ("ספט׳ '26")
 * came within 2px of outgrowing it.
 *
 * The heading row and the data rows hold no track list of their own — they
 * subgrid onto this one — so a column can no longer be resized in one and
 * not the other, which used to slide every heading off the column it names.
 *
 * The trade is that a column is sized by the rows on screen, so revealing
 * earlier periods can widen one and shift the bars. It takes an earlier
 * period whose net is wider than anything currently shown, and it costs a
 * few pixels once; a fixed width pays its slack on every row forever.
 *
 * The net column carries its ₪ in the heading ("Net (₪)") rather than on
 * every row, which is the one thing `max-content` could not shave: the
 * symbol and its NBSP are real glyphs, so twelve rows paid for them twelve
 * times to say what the column says once. The bars keep theirs — they are
 * read individually, and the label sits at a bar's anchored end where it
 * costs no gap.
 */
const LEDGER_COLUMNS = "max-content 1fr 1fr max-content";

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

/**
 * Every series name across a set of breakdown rows, in the order their
 * colours are assigned from. Expense categories are sorted so the warm→cool
 * palette walks them predictably; income sources keep the order they arrive
 * in, which is the backend's own.
 */
function seriesOrder(rows: CompositionRow[], sorted: boolean): string[] {
  const names = Array.from(new Set(rows.flatMap((d) => Object.keys(d.values))));
  return sorted ? names.sort() : names;
}

/** Colour lookup over a fixed series order, cycling the palette. */
function colorLookup(series: string[], palette: string[]): (name: string) => string {
  return (name: string) => {
    const index = series.indexOf(name);
    return palette[(index < 0 ? 0 : index) % palette.length];
  };
}

/**
 * Narrow a monthly series to the all-scope window. The monthly and yearly
 * scopes show every period they hold and let the pager walk back through
 * them, so only the all scope — a single row with nothing to page — needs a
 * window at all.
 */
function windowed<T extends { month: string }>(rows: T[], all: boolean, range: RangeWindow): T[] {
  return all ? sliceWindow(rows, range) : rows;
}

/** Mean of one ledger field over a slice of periods (0 when empty). */
function avgOf(rows: LedgerRow[], field: "income" | "expenses"): number {
  if (rows.length === 0) return 0;
  return rows.reduce((total, row) => total + row[field], 0) / rows.length;
}

/** One ledger field as the `{month, value}` series the KPI folds want. */
function seriesOf(rows: LedgerRow[], field: "income" | "expenses") {
  return rows.map((row) => ({ month: row.month, value: row[field] }));
}

/**
 * Income & Expenses dashboard card: monthly / yearly / all-time scope, KPI
 * summaries, refund and project filters, and Totals / Income / Expenses
 * sub-views.
 *
 * The all scope folds the whole window into one period, so a breakdown there
 * is a donut with a collapsible legend rather than a composition bar — which
 * is what the separate "Income by source" card used to be, now reachable for
 * expenses too. Either breakdown can be filtered to a single series (click a
 * slice or a legend row), which is the one reading a stack of composition
 * bars cannot give.
 */
export function IncomeExpensesCard() {
  const { t } = useTranslation();
  const qk = useQueryKeys();
  const [incomeView, setIncomeViewState] = useState<"overview" | "by_source" | "by_category">("overview");
  const [scope, setScope] = useState<Scope>("monthly");
  const [range, setRange] = useState<RangeWindow>("all");
  // The one series the breakdown is narrowed to, or null for the full mix.
  const [focus, setFocus] = useState<string | null>(null);
  // Stable identity: the focused view keys its Escape listener off it, and a
  // fresh function every render would re-subscribe on every render.
  const clearFocus = useCallback(() => setFocus(null), []);
  const [visiblePeriods, setVisiblePeriods] = useState(DEFAULT_VISIBLE_PERIODS);
  const showMore = () => setVisiblePeriods((v) => v + DEFAULT_VISIBLE_PERIODS);
  const showLess = () => setVisiblePeriods(DEFAULT_VISIBLE_PERIODS);
  // A window measured in months means nothing once the rows are years, so a
  // scope switch starts the pager over.
  const changeScope = (next: Scope) => {
    setScope(next);
    setVisiblePeriods(DEFAULT_VISIBLE_PERIODS);
  };
  // A focused series is a name out of the tab's own series, and the two tabs
  // share none, so the filter cannot survive a tab switch.
  const setIncomeView = (next: typeof incomeView) => {
    setIncomeViewState(next);
    setFocus(null);
  };
  // Picked from the all-scope donut, where the focused view would have a
  // single row to draw. Months are what "over time" means here, so the click
  // lands on them.
  const focusOverTime = (name: string) => {
    if (scope === "all") changeScope("monthly");
    setFocus(name);
  };
  const [excludePendingRefunds, setExcludePendingRefunds] = useState(true);
  const [includeProjects, setIncludeProjects] = useState(false);
  // Debt payments are money that left the account, so they count by default;
  // the chip takes the envelope view, where loan principal is a transfer into
  // net worth rather than spending. It governs loan *receipts* on the income
  // side too — dropping the payments while keeping the money the loan paid in
  // would report the household as having saved the whole loan.
  const [includeDebt, setIncludeDebt] = useState(true);

  // Both series come from the same itemized classification, filtered the same
  // way, so every view in this card is one number summed three ways. The card
  // used to read a separate totals endpoint and a separate expense-average
  // endpoint, each with its own definition of "expenses" — which put three
  // different all-time totals on one screen, and left the projects chip
  // filtering a series whose credit-card rows have no category to filter on.
  // See `.claude/rules/kpi_calculations.md` → "The Income & Expenses card".
  const { data: expensesByCategoryOverTime } = useQuery({
    queryKey: qk.analytics.expensesByCategoryOverTime(
      excludePendingRefunds,
      !includeProjects,
      !includeDebt,
    ),
    queryFn: async () =>
      (
        await analyticsApi.getExpensesByCategoryOverTime(
          excludePendingRefunds,
          !includeProjects,
          !includeDebt,
        )
      ).data,
    // Every chip is part of the key, so a toggle is a *different* query with
    // no data of its own. Without this the card empties out and rebuilds
    // itself on every toggle: the "no data" line flashes, and because that
    // unmounts the breakdown, an opened legend closes and a focused series is
    // dropped — the reader loses their place for the length of a refetch.
    placeholderData: keepPreviousData,
  });
  const { data: incomeBySourceData } = useQuery({
    queryKey: qk.analytics.incomeBySourceOverTime(excludePendingRefunds, !includeDebt),
    queryFn: async () =>
      (await analyticsApi.getIncomeBySourceOverTime(excludePendingRefunds, !includeDebt)).data,
    placeholderData: keepPreviousData,
  });

  const yearly = scope === "yearly";
  const all = scope === "all";
  const rawSourceRows: CompositionRow[] = useMemo(
    () => (incomeBySourceData ?? []).map((d) => ({ month: d.month, values: d.sources })),
    [incomeBySourceData],
  );
  const rawCategoryRows: CompositionRow[] = useMemo(
    () => (expensesByCategoryOverTime ?? []).map((d) => ({ month: d.month, values: d.categories })),
    [expensesByCategoryOverTime],
  );
  const rawLedgerRows: LedgerRow[] = useMemo(
    () => toLedger(rawSourceRows, rawCategoryRows),
    [rawSourceRows, rawCategoryRows],
  );
  const ledgerRows: LedgerRow[] = useMemo(() => {
    const rows = windowed(rawLedgerRows, all, range);
    if (all) return toAllLedger(rows);
    return yearly ? toYearlyLedger(rows) : rows;
  }, [yearly, all, range, rawLedgerRows]);
  const sourceRows: CompositionRow[] = useMemo(() => {
    const rows = windowed(rawSourceRows, all, range);
    if (all) return toAllComposition(rows);
    return yearly ? toYearlyComposition(rows) : rows;
  }, [yearly, all, range, rawSourceRows]);
  const categoryRows: CompositionRow[] = useMemo(() => {
    const rows = windowed(rawCategoryRows, all, range);
    if (all) return toAllComposition(rows);
    return yearly ? toYearlyComposition(rows) : rows;
  }, [yearly, all, range, rawCategoryRows]);

  // Series order — and with it every series' colour — is derived from the
  // whole monthly history, never from the rows on screen. Derived per view it
  // would be derived from a *different* set each time: a window that drops a
  // category shifts every alphabetically-later one onto a new colour, so the
  // same category changed hue between the scope toggle's three positions.
  const sourceSeries = useMemo(() => seriesOrder(rawSourceRows, false), [rawSourceRows]);
  const categorySeries = useMemo(() => seriesOrder(rawCategoryRows, true), [rawCategoryRows]);
  const sourceColorOf = useMemo(() => colorLookup(sourceSeries, CHART_COLORS), [sourceSeries]);
  const categoryColorOf = useMemo(() => colorLookup(categorySeries, CATEGORY_COLORS), [categorySeries]);

  // Every KPI folds the very rows the ledger draws, so no scope can disagree
  // with another — or with the tab below it — about a month, a year or a
  // household's whole history.
  const yearlyIncome = useMemo(() => yearlyKpi(seriesOf(rawLedgerRows, "income")), [rawLedgerRows]);
  const yearlyExpenses = useMemo(
    () => yearlyKpi(seriesOf(rawLedgerRows, "expenses")),
    [rawLedgerRows],
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

  // The all-scope KPI is the window's own total. Its secondary figure is the
  // per-month average rather than a second window: the whole point of the
  // scope is that there is only one period, and a total on its own says
  // nothing about the size of the household behind it.
  const allSummary = (kpi: AllKpi): KpiSummary => ({
    primary: kpi.total,
    primaryLabel: t(RANGE_LABEL_KEYS[range]),
    stats: [{ label: t("dashboard.perMonthAvg"), value: kpi.perMonth }],
    // No like-for-like baseline exists for an all-time total — there is no
    // earlier "all time" to compare it against — so the trend chip stays off.
    trendBaseline: 0,
    trendTitle: "",
  });

  const allIncome = useMemo(
    () => allTimeKpi(seriesOf(windowed(rawLedgerRows, all, range), "income")),
    [rawLedgerRows, all, range],
  );
  const allExpenses = useMemo(
    () => allTimeKpi(seriesOf(windowed(rawLedgerRows, all, range), "expenses")),
    [rawLedgerRows, all, range],
  );

  const rollingSummary = (field: "income" | "expenses") =>
    monthlySummary(
      avgOf(rawLedgerRows.slice(-3), field),
      avgOf(rawLedgerRows.slice(-6), field),
      avgOf(rawLedgerRows.slice(-12), field),
    );
  const incomeSummary = all
    ? allSummary(allIncome)
    : yearly
      ? yearlySummary(yearlyIncome)
      : rollingSummary("income");
  const expenseSummary = all
    ? allSummary(allExpenses)
    : yearly
      ? yearlySummary(yearlyExpenses)
      : rollingSummary("expenses");

  // Whichever view is on screen scrolls inside this box, and the box keeps
  // its offset when the view is swapped. Reaching a legend row means
  // scrolling down to it, so filtering from there opened the focused view
  // already scrolled past its own filter chip and column headings — the two
  // things that say what is being looked at.
  const viewportRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    viewportRef.current?.scrollTo({ top: 0 });
  }, [focus, incomeView, scope, range]);

  // The periods the pager walks, whichever tab is open.
  const activeRows =
    incomeView === "overview" ? ledgerRows : incomeView === "by_source" ? sourceRows : categoryRows;

  /**
   * A breakdown tab, in one of its three forms: one series over time when the
   * chart has been filtered to one, a donut over the whole window in the all
   * scope, and a composition row per period otherwise.
   */
  const breakdown = (
    rows: CompositionRow[],
    series: string[],
    colorOf: (name: string) => string,
    seriesHeading: string,
    emptyMessage: string,
  ) => {
    if (rows.length === 0) return <p className="text-[var(--text-muted)] text-sm">{emptyMessage}</p>;
    if (focus) {
      return (
        <IncomeExpensesFocus
          rows={rows}
          series={focus}
          color={colorOf(focus)}
          scope={scope}
          limit={visiblePeriods}
          allLabel={t("dashboard.scopeAll")}
          onClear={clearFocus}
        />
      );
    }
    if (all) {
      return (
        <IncomeExpensesDonut
          values={rows[0].values}
          colorOf={colorOf}
          seriesHeading={seriesHeading}
          onSelect={focusOverTime}
        />
      );
    }
    return (
      <CompositionView
        rows={rows}
        series={series}
        colorOf={colorOf}
        limit={visiblePeriods}
        onSelect={setFocus}
      />
    );
  };

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
              <button
                onClick={() => setIncludeDebt(!includeDebt)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium border transition-colors ${
                  includeDebt
                    ? "bg-amber-500/10 border-amber-500/20 text-amber-400"
                    : "bg-[var(--surface-light)] border-[var(--surface-light)] text-[var(--text-muted)]"
                }`}
                title={t("dashboard.debtChipTitle")}
              >
                {includeDebt ? t("dashboard.debtIncluded") : t("dashboard.debtExcluded")}
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

          {all && <RangeChips range={range} onChange={setRange} />}

          <div ref={viewportRef} className="flex-1 min-h-0 overflow-y-auto">
            {incomeView === "overview" && (
              <LedgerView rows={ledgerRows} scope={scope} limit={visiblePeriods} />
            )}
            {incomeView === "by_source" &&
              breakdown(
                sourceRows,
                sourceSeries,
                sourceColorOf,
                t("dashboard.breakdownSource"),
                `📭 ${t("dashboard.noIncomeSourceData")}`,
              )}
            {incomeView === "by_category" &&
              breakdown(
                categoryRows,
                categorySeries,
                categoryColorOf,
                t("dashboard.breakdownCategory"),
                t("common.noData"),
              )}
            <PeriodPager
              total={activeRows.length}
              visible={Math.min(activeRows.length, visiblePeriods)}
              scope={scope}
              onShowMore={showMore}
              onShowLess={showLess}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Monthly / yearly / all-time scope switch, in the card's title row. It
 * re-folds the series the card already holds, so flipping it costs no request.
 */
function ScopeToggle({ scope, onChange }: { scope: Scope; onChange: (next: Scope) => void }) {
  const { t } = useTranslation();
  return (
    <div data-testid="scope-toggle" className="flex flex-none p-0.5 rounded-lg bg-[var(--surface-light)]">
      {([
        { key: "monthly" as const, label: t("dashboard.scopeMonthly") },
        { key: "yearly" as const, label: t("dashboard.scopeYearly") },
        { key: "all" as const, label: t("dashboard.scopeAll") },
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
 * How much history the all scope folds.
 *
 * The other two scopes answer a shorter span by scrolling to the period that
 * covers it; a single all-time figure has no such row, so the window is the
 * only way to ask it about one. Day-level bounds are deliberately absent:
 * every series the card holds is keyed by month, so a stray day could only
 * ever be rounded to one.
 */
function RangeChips({
  range,
  onChange,
}: {
  range: RangeWindow;
  onChange: (next: RangeWindow) => void;
}) {
  const { t } = useTranslation();
  return (
    <div data-testid="range-chips" className="bg-[var(--surface-light)] rounded-xl overflow-hidden self-start mb-3">
      <div className="flex gap-1 p-1 overflow-x-auto scrollbar-auto-hide">
        {(Object.keys(RANGE_LABEL_KEYS) as RangeWindow[]).map((key) => (
          <button
            key={key}
            onClick={() => onChange(key)}
            aria-pressed={range === key}
            className={`shrink-0 whitespace-nowrap px-2 md:px-3 py-1 rounded-lg text-xs font-bold transition-all ${
              range === key
                ? "bg-[var(--surface)] text-[var(--primary)] shadow-sm"
                : "text-[var(--text-muted)] hover:text-[var(--text-default)]"
            }`}
          >
            {t(RANGE_LABEL_KEYS[key])}
          </button>
        ))}
      </div>
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
        {/* An all-time total has no earlier all-time to measure against, and a
            0% chip beside it would read as "flat" rather than "not asked". */}
        {data.trendBaseline !== 0 && (
          <TrendChip value={data.primary} baseline={data.trendBaseline} kind={kind} title={data.trendTitle} />
        )}
      </div>
      <div
        data-testid="kpi-primary"
        className="text-lg md:text-2xl font-extrabold tabular-nums leading-none"
      >
        {formatCurrency(data.primary)}
      </div>
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
 * net for the period. The exact ₪ sits on every bar so nothing needs a hover,
 * and the vertical layout keeps the period labels always visible (no bottom
 * axis).
 *
 * Each column carries its own scale, so a bar's length is comparable down its
 * column but not across the gutter — an income bar and an expense bar of equal
 * length are not equal money. Comparing the two is what the Net column is for,
 * and it states the difference outright rather than asking anyone to eyeball
 * two lengths.
 */
function LedgerView({
  rows,
  scope,
  limit,
}: {
  rows: LedgerRow[];
  scope: Scope;
  limit: number;
}) {
  const { t } = useTranslation();
  if (rows.length === 0) return <p className="text-[var(--text-muted)] text-sm">{t("common.noData")}</p>;

  // One cap per column, not one pooled over both. Income and expenses are
  // different distributions — a household's income carries the lumpy events
  // (a bonus, a windfall, a fund liquidation) while its expenses cluster —
  // so pooling them let a single 400k income month set the scale a 17k
  // expense month had to live on. Every expense then rendered in the bottom
  // third of its column, and ordinary high-salary months were flagged as
  // over-scale outliers beside the genuine ones.
  //
  // Both are still median-anchored over the FULL history, so typical periods
  // sit mid-range with headroom and widths don't shift when earlier ones are
  // revealed; only the *displayed* rows are capped to `limit`.
  const incomeCap = barCap(rows.map((d) => d.income));
  const expenseCap = barCap(rows.map((d) => Math.abs(d.expenses)));
  const lastPeriod = rows[rows.length - 1]?.month;
  const visible = rows.slice(-limit).reverse();

  return (
    <div className="min-w-[300px]">
      <div className="grid gap-x-1" style={{ gridTemplateColumns: `${LEDGER_COLUMNS}` }}>
        <div className="col-span-4 grid grid-cols-subgrid px-1 pb-2 text-[10px] font-bold uppercase tracking-wide text-[var(--text-muted)]">
          <div>
            {scope === "yearly"
              ? t("dashboard.ledgerYear")
              : scope === "all"
                ? t("dashboard.ledgerPeriod")
                : t("dashboard.ledgerMonth")}
          </div>
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
              className={`col-span-4 grid grid-cols-subgrid items-center px-1 py-1.5 rounded-lg ${isCurrent ? "bg-[var(--primary)]/10" : ""}`}
            >
              <div className="text-xs font-bold text-[var(--text-muted)] whitespace-nowrap">
                {formatPeriodLabel(d.month, t("dashboard.scopeAll"))}
              </div>
              {/* income grows toward the centre; expenses mirror outward */}
              <LedgerBar value={d.income} kind="income" cap={incomeCap} />
              <LedgerBar value={d.expenses} kind="expense" cap={expenseCap} color={expenseColor} />
              {/* The ₪ lives in the column heading — see LEDGER_COLUMNS. */}
              <div
                className="text-xs font-extrabold text-end whitespace-nowrap tabular-nums"
                style={{ color: net >= 0 ? INCOME_COLOR : EXPENSE_COLOR }}
              >
                {formatChange(net, { compact: false, currency: false })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/**
 * One ledger bar. Income grows toward the centre, expenses mirror outward. A
 * value above its column's cap is drawn full-width and flagged as an outlier: a
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
 *
 * A slice is also the control that filters the view down to its own series:
 * the readout that names it is already under the cursor, so the click that
 * follows needs nothing added around the chart. The tooltip says so, since a
 * bar gives no other hint that it can be clicked.
 */
function CompositionView({
  rows,
  series,
  colorOf,
  limit,
  onSelect,
}: {
  rows: CompositionRow[];
  /** Series names in colour order, shared with the donut and focus views. */
  series: string[];
  colorOf: (name: string) => string;
  limit: number;
  /** Filter the tab down to one series. */
  onSelect: (name: string) => void;
}) {
  const { t } = useTranslation();
  // Cursor-following tooltip: the only way to name a slice now that the legend
  // is gone, so it has to be instant. Portalled to <body> because the bar clips
  // its children (`overflow-hidden`) and the card may sit in a scroll container.
  const [tip, setTip] = useState<Tip | null>(null);
  const showTip = (
    e: ReactMouseEvent,
    name: string,
    val: number,
    pct: number,
    color: string,
    pinned = false,
  ) =>
    setTip({
      x: Math.min(Math.max(e.clientX, 90), window.innerWidth - 90),
      // Above the cursor, unless the row sits so close to the top of the
      // viewport that the panel would be cut off — then flip below it.
      y: e.clientY < 56 ? e.clientY + 20 : e.clientY - 12,
      below: e.clientY < 56,
      name,
      text: `${name}: ${formatCurrency(val)} (${Math.round(pct)}%)`,
      color,
      pinned,
    });

  /**
   * Dismiss the readout, unless a tap pinned it.
   *
   * A tap does not only synthesize a click: Chromium sends the whole mouse
   * sequence, and the `mouseleave` that ends it arrives *after* the click
   * that pinned the readout. Clearing unconditionally therefore closed the
   * panel a phone had just opened, in the same gesture — the very failure the
   * pinning exists to prevent.
   */
  const hideTip = () => setTip((cur) => (cur?.pinned ? cur : null));

  /**
   * What a tap does, which is not what a click does.
   *
   * A touch has no hover to precede it: the browser synthesizes the mouse
   * events and the click from the same tap, so filtering on click would mean
   * a phone could never read a slice at all — the readout naming it would be
   * replaced by the filtered view in the same gesture. So a tap *pins* the
   * readout instead, and the filter becomes a button inside it. That is the
   * repo's tap-to-reveal pattern (`frontend_responsive.md`), and it is why
   * the desktop tooltip can stay a plain hover with no controls in it.
   */
  const onSegmentClick = (
    e: ReactMouseEvent,
    name: string,
    val: number,
    pct: number,
    color: string,
  ) => {
    if (isTouchDevice) showTip(e, name, val, pct, color, true);
    else onSelect(name);
  };

  const totalOf = (v: Record<string, number>) => series.reduce((s, name) => s + (v[name] || 0), 0);
  // Median-anchored meter cap over the FULL history so widths stay stable across
  // "Show earlier months"; totals above it are flagged as outliers.
  const meterCap = barCap(rows.map((d) => totalOf(d.values)));
  const lastPeriod = rows[rows.length - 1]?.month;
  const visible = rows.slice(-limit).reverse();

  return (
    <div className="min-w-[320px]" onMouseLeave={hideTip}>
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
              {formatPeriodLabel(d.month, t("dashboard.scopeAll"))}
            </div>
            <div className="flex h-6 rounded-md overflow-hidden bg-[var(--background)]">
              {series.map((name) => {
                const val = d.values[name] || 0;
                if (val <= 0) return null;
                const pct = (val / total) * 100;
                const segColor = colorOf(name);
                return (
                  <button
                    key={name}
                    type="button"
                    data-testid="composition-segment"
                    aria-label={`${name}: ${formatCurrency(val)} (${Math.round(pct)}%)`}
                    className="h-full"
                    style={{ width: `${pct}%`, background: segColor }}
                    onClick={(e) => onSegmentClick(e, name, val, pct, segColor)}
                    onMouseEnter={(e) => showTip(e, name, val, pct, segColor)}
                    onMouseMove={(e) => showTip(e, name, val, pct, segColor)}
                    onMouseLeave={hideTip}
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
      <SegmentTooltip
        tip={tip}
        hint={t(isTouchDevice ? "dashboard.tapToFilter" : "dashboard.clickToFilter")}
        onFilter={() => {
          const name = tip?.name;
          setTip(null);
          if (name) onSelect(name);
        }}
        onDismiss={() => setTip(null)}
      />
    </div>
  );
}

/**
 * A slice's readout: viewport coordinates, whether the panel hangs below the
 * cursor (top-of-viewport flip), the slice's name, its text, its colour, and
 * whether it is pinned — a pinned readout was opened by a tap, stays until
 * dismissed, and carries the filter button a hover readout does not need.
 */
type Tip = {
  x: number;
  y: number;
  below: boolean;
  name: string;
  text: string;
  color: string;
  pinned: boolean;
};

/**
 * The cursor-following slice tooltip, rendered into <body> so no ancestor's
 * `overflow-hidden` can clip it. Sits above the cursor (below it near the top
 * of the viewport) and is horizontally clamped so it never runs off an edge.
 */
function SegmentTooltip({
  tip,
  hint,
  onFilter,
  onDismiss,
}: {
  tip: Tip | null;
  hint: string;
  onFilter: () => void;
  onDismiss: () => void;
}) {
  const { t } = useTranslation();
  if (!tip) return null;
  return createPortal(
    <>
      {/* A pinned readout is dismissed by tapping anywhere off it, so it needs
          something off it to tap. */}
      {tip.pinned && (
        <div
          data-testid="composition-tooltip-backdrop"
          className="fixed inset-0 z-40"
          onClick={onDismiss}
        />
      )}
      <div
        data-testid="composition-tooltip"
        className={`fixed z-50 whitespace-nowrap rounded-lg border border-white/10 bg-[var(--surface-light)] px-2.5 py-1.5 text-[11px] font-semibold text-white shadow-xl ${
          tip.pinned ? "" : "pointer-events-none"
        }`}
        style={{
          left: tip.x,
          top: tip.y,
          transform: `translate(-50%, ${tip.below ? "0" : "-100%"})`,
        }}
      >
        <span className="flex items-center gap-1.5">
          <i className="h-2 w-2 flex-none rounded-sm" style={{ background: tip.color }} />
          {tip.text}
        </span>
        {tip.pinned ? (
          // The filter is a button here because the tap that opened this
          // readout is the only gesture a phone has: spend it on the reading,
          // and let the filter be a second, deliberate one.
          <button
            type="button"
            data-testid="composition-tooltip-filter"
            onClick={onFilter}
            className="mt-1.5 w-full rounded-md bg-[var(--primary)]/15 px-2 py-1 text-[11px] font-bold text-[var(--primary)]"
          >
            {t("dashboard.filterToSeries")}
          </button>
        ) : (
          /* Nothing about a coloured band says it can be clicked, and the
             readout naming it is already under the cursor. */
          <span className="block text-[10px] font-medium text-[var(--text-muted)]">{hint}</span>
        )}
      </div>
    </>,
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
