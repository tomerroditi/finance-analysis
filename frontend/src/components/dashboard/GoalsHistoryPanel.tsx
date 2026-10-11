import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronUp } from "lucide-react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  ReferenceLine,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
} from "recharts";
import { savingsGoalsApi } from "../../services/api";
import { FREE_CASH_KEY, historyRows, type HistoryMode } from "./goalHistoryRows";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import {
  STACK_OFFSET,
  stackAxis,
  stackEnds,
  roundedStackShape,
} from "../charts/stackedBarShape";
import { Skeleton } from "../common/Skeleton";
import { ChartTooltip } from "../charts/ChartTooltip";
import { ChartLegend } from "../charts/ChartLegend";
import { formatMonthCompact, formatMonthYear } from "../../utils/dateFormatting";
import {
  AXIS_DEFAULTS,
  CHART_COLORS,
  CHART_TEXT_COLOR,
  formatAxisNumber,
  hexToRgba,
} from "../../utils/chartStyle";

/**
 * Free cash is drawn in neutral ink rather than a palette hue: it is the money
 * *no* goal holds, so borrowing a goal's colour would imply it belongs to one.
 */
const FREE_CASH_COLOR = CHART_TEXT_COLOR;

/** Faint rule for the zero line — present enough to read against, no more. */
const GRID_COLOR = "rgba(148, 163, 184, 0.25)";

/** Trailing windows the panel offers; 0 means the whole timeline. */
const HISTORY_RANGES = [6, 12, 0] as const;

/** Ties the collapse toggle to the panel it reveals. */
const PANEL_ID = "goals-history-panel";

type HistoryRange = (typeof HISTORY_RANGES)[number];

/** Parse a `YYYY-MM` key into a local-time Date (never UTC midnight). */
function monthDate(month: string): Date {
  const [year, index] = month.split("-").map(Number);
  return new Date(year, index - 1, 1);
}

/**
 * The goals read month by month, under the current standings.
 *
 * The rows above answer "where is each goal now"; this answers "how did it get
 * there". Monthly bars stack how much each goal moved that month — money
 * added, income its rule brought in, less what was spent from it — and
 * cumulative bars stack what each goal held at month end. Free cash sits on
 * top in both, as it stood at month end; below the line when more was set
 * aside than there was.
 *
 * Free cash is a standing balance and a month's movement is a flow, so a
 * household with real savings sees a tall free-cash segment over thin goal
 * ones. That is why the legend is clickable: hide a series and the axis
 * refits to what is left, and a double-click narrows to one.
 */
export function GoalsHistoryPanel() {
  const { t } = useTranslation();
  const qk = useQueryKeys();
  const [range, setRange] = useState<HistoryRange>(12);
  // Collapsed by default: the standings above are what the card is opened
  // for, and the history behind them is a second question.
  const [open, setOpen] = useState(false);
  // Series the reader clicked away in the legend, keyed by series key so a
  // renamed goal keeps its state.
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  // Which series a double-click narrowed to, so double-clicking it again is
  // what brings the others back — never a state built up click by click.
  const [isolated, setIsolated] = useState<string | null>(null);
  const [mode, setMode] = useState<HistoryMode>("monthly");

  const { data, isLoading } = useQuery({
    queryKey: qk.savingsGoals.timeline(range),
    queryFn: async () => (await savingsGoalsApi.getTimeline(range)).data,
    // Nothing outside this panel reads the timeline, so a card that is never
    // expanded never pays for it.
    enabled: open,
  });

  // Months where nothing moved still get a row — a gap in a time series reads
  // as "skipped", not "zero".
  const rows = historyRows(data?.months ?? [], mode);

  // Colour follows the goal, not its rank: keyed by id, so reordering never
  // repaints the chart.
  const palette = new Map(
    [...(data?.goals ?? [])]
      .sort((a, b) => a.id - b.id)
      .map((goal, index) => [goal.id, CHART_COLORS[index % CHART_COLORS.length]]),
  );
  // A goal with nothing to draw in this window would be a legend entry with no
  // mark, so only goals that show something get a series.
  const series = (data?.goals ?? []).filter((goal) =>
    rows.some((row) => row[`g${goal.id}`] !== undefined && row[`g${goal.id}`] !== 0),
  );
  // Free cash stacks last, so it caps the column.
  const hasFreeCash = rows.some((row) => row[FREE_CASH_KEY] !== 0);
  const keys = [
    ...series.map((goal) => `g${goal.id}`),
    ...(hasFreeCash ? [FREE_CASH_KEY] : []),
  ];
  // Only what is on screen shapes the chart: the rounded ends follow the
  // visible stack, and so does the zero line.
  const visible = keys.filter((key) => !hidden.has(key));
  const ends = stackEnds(rows, visible, "month");
  const yAxis = stackAxis(rows, visible);
  const hasNegative = rows.some((row) =>
    visible.some((key) => typeof row[key] === "number" && (row[key] as number) < 0),
  );

  /** Hide or show one series; hiding the last one is allowed and says so. */
  const toggleSeries = (key: string) => {
    setHidden((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
    setIsolated(null);
  };

  /** Narrow to one series; double-clicking the same one again undoes it. */
  const isolateSeries = (key: string) => {
    if (isolated === key) {
      setHidden(new Set());
      setIsolated(null);
      return;
    }
    setHidden(new Set(keys.filter((other) => other !== key)));
    setIsolated(key);
  };

  // Compact, and without the series that are zero that month: with a goal
  // per line, the full-size tooltip stood taller than a phone's plot area.
  const tooltip = (
    <ChartTooltip
      compact
      labelFormatter={(m) => formatMonthYear(monthDate(String(m)))}
      filter={(entry) => entry.value !== 0}
    />
  );
  const hasMoreHistory = (data?.total_months ?? 0) > Math.max(...HISTORY_RANGES);

  return (
    <div
      className="mt-4 pt-4 border-t border-[var(--surface-light)]"
      data-testid="goals-history"
    >
      <div
        className={`flex flex-wrap items-center justify-between gap-2 ${open ? "mb-3" : ""}`}
      >
        <button
          type="button"
          onClick={() => setOpen((isOpen) => !isOpen)}
          aria-expanded={open}
          aria-controls={PANEL_ID}
          className="flex items-center gap-1 whitespace-nowrap text-xs md:text-sm font-bold hover:text-[var(--primary)] transition-colors"
        >
          {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          {t("dashboard.goals.historyTitle")}
        </button>
        {open && (
          // The view and the window are one set of controls, so they never
          // split across lines.
          <div className="flex items-center gap-1.5 ms-auto" data-testid="goals-history-controls">
            <div
              className="flex bg-[var(--surface-light)] rounded-lg p-0.5"
              role="group"
              aria-label={t("dashboard.goals.historyModeLabel")}
            >
              {(["monthly", "cumulative"] as const).map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setMode(option)}
                  aria-pressed={mode === option}
                  className={`px-2 py-1 rounded-md text-[10px] md:text-xs font-bold transition-colors ${
                    mode === option
                      ? "bg-[var(--surface)] text-[var(--primary)] shadow-sm"
                      : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                  }`}
                >
                  {t(
                    option === "monthly"
                      ? "dashboard.goals.historyMonthly"
                      : "dashboard.goals.historyCumulative",
                  )}
                </button>
              ))}
            </div>
            <div className="flex bg-[var(--surface-light)] rounded-lg p-0.5">
              {HISTORY_RANGES.map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setRange(option)}
                  // "All time" is only honest while there is more history than
                  // the widest fixed window.
                  disabled={option === 0 && !hasMoreHistory}
                  className={`px-2 py-1 rounded-md text-[10px] md:text-xs font-bold transition-colors disabled:opacity-40 ${
                    range === option
                      ? "bg-[var(--surface)] text-[var(--primary)] shadow-sm"
                      : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                  }`}
                >
                  {option === 0
                    ? t("dashboard.goals.historyAll")
                    : t("dashboard.goals.historyMonths", { count: option })}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {open && (
        <div id={PANEL_ID}>
          {isLoading ? (
            <Skeleton variant="chart" className="h-40" />
          ) : rows.length === 0 || keys.length === 0 ? (
            <p className="text-[10px] md:text-xs text-[var(--text-muted)] py-4 text-center">
              {t("dashboard.goals.historyEmpty")}
            </p>
          ) : (
            <div
              className="rounded-xl border border-[var(--surface-light)] bg-[var(--surface-light)]/20 p-3"
              data-testid="goals-history-chart"
            >
              {/* Taller on a phone: the legend wraps there and would leave the
                  bars, and the tooltip, too little room. */}
              <div className="h-64 md:h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    // Recharts 3 stacks bars in the order they first mounted,
                    // not the order they render in, so a new series order is a
                    // new chart — or free cash ends up under a goal.
                    key={`${mode}:${keys.join(",")}`}
                    data={rows}
                    margin={{ top: 4, bottom: 0, left: 0, right: 4 }}
                    barCategoryGap="22%"
                    stackOffset={STACK_OFFSET}
                  >
                    <defs>
                      {series.map((goal) => (
                        <linearGradient
                          key={goal.id}
                          id={`goal-fill-${goal.id}`}
                          x1="0"
                          y1="0"
                          x2="0"
                          y2="1"
                        >
                          <stop
                            offset="0%"
                            stopColor={hexToRgba(palette.get(goal.id)!, 0.95)}
                          />
                          <stop
                            offset="100%"
                            stopColor={hexToRgba(palette.get(goal.id)!, 0.55)}
                          />
                        </linearGradient>
                      ))}
                      <linearGradient id="goal-fill-free" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={hexToRgba(FREE_CASH_COLOR, 0.55)} />
                        <stop offset="100%" stopColor={hexToRgba(FREE_CASH_COLOR, 0.28)} />
                      </linearGradient>
                    </defs>
                    <XAxis dataKey="month" {...AXIS_DEFAULTS} tickFormatter={formatMonthCompact} />
                    <YAxis
                      {...AXIS_DEFAULTS}
                      tickFormatter={formatAxisNumber}
                      domain={yAxis.domain}
                      ticks={yAxis.ticks}
                      allowDataOverflow
                      width={44}
                    />
                    {/* Only drawn when a bar actually dips under the line —
                        with nothing below it, the axis is the baseline. */}
                    {hasNegative && (
                      <ReferenceLine y={0} stroke={GRID_COLOR} strokeWidth={1} />
                    )}
                    <Tooltip
                      cursor={{ fill: "rgba(148, 163, 184, 0.08)", radius: 6 }}
                      content={tooltip}
                      // Pinned to the top of the plot, so it grows down over
                      // the bars and never over the legend under them.
                      position={{ y: 0 }}
                    />
                    <Legend
                      content={
                        <ChartLegend
                          fontSize={10}
                          hidden={hidden}
                          onToggle={toggleSeries}
                          onIsolate={isolateSeries}
                        />
                      }
                    />
                    {series.map((goal) => (
                      <Bar
                        key={goal.id}
                        dataKey={`g${goal.id}`}
                        name={goal.name}
                        stackId="goals"
                        // The gradient goes on the drawn segment, so the
                        // legend swatch keeps a flat colour it can paint.
                        fill={palette.get(goal.id)}
                        hide={hidden.has(`g${goal.id}`)}
                        maxBarSize={30}
                        shape={roundedStackShape(
                          ends,
                          `g${goal.id}`,
                          "month",
                          `url(#goal-fill-${goal.id})`,
                        )}
                        isAnimationActive={false}
                      />
                    ))}
                    {hasFreeCash && (
                      <Bar
                        dataKey={FREE_CASH_KEY}
                        name={t("dashboard.goals.freeCash")}
                        stackId="goals"
                        fill={FREE_CASH_COLOR}
                        hide={hidden.has(FREE_CASH_KEY)}
                        maxBarSize={30}
                        shape={roundedStackShape(
                          ends,
                          FREE_CASH_KEY,
                          "month",
                          "url(#goal-fill-free)",
                        )}
                        isAnimationActive={false}
                      />
                    )}
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          <p className="mt-2 text-[10px] text-[var(--text-muted)]">
            {t(
              mode === "cumulative"
                ? "dashboard.goals.historyHintCumulative"
                : "dashboard.goals.historyHint",
            )}
          </p>
        </div>
      )}
    </div>
  );
}
