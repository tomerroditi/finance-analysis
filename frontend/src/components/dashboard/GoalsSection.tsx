import { useState } from "react";
import {
  useQuery,
  useMutation,
  useQueryClient,
  useIsMutating,
} from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  Target,
  Plus,
  Pencil,
  Trash2,
  Check,
  ChevronUp,
  ChevronDown,
  Loader2,
  Lock,
  Wallet,
} from "lucide-react";
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
import {
  savingsGoalsApi,
  type SavingsGoal,
  type SavingsGoalInput,
  type SavingsGoalFreeCash,
} from "../../services/api";
import {
  FREE_CASH_KEY,
  cumulativeRows,
  lastMonths,
  monthlyRows,
  type HistoryMode,
} from "./goalHistoryRows";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { useScrollCap } from "../../hooks/useScrollCap";
import { GoalAutoLinkField } from "./GoalAutoLinkField";
import { joinRuleTags, splitRuleTags } from "../../utils/goalRuleTags";
import {
  STACK_OFFSET,
  stackAxis,
  stackEnds,
  roundedStackShape,
} from "../charts/stackedBarShape";
import { qkPrefix } from "../../services/queryKeys";
import { useConfirm } from "../../context/DialogContext";
import { Modal } from "../common/Modal";
import { Skeleton } from "../common/Skeleton";
import { ChartTooltip } from "../charts/ChartTooltip";
import { YearlySavingsSection } from "./YearlySavingsSection";
import { ChartLegend } from "../charts/ChartLegend";
import { formatCurrency } from "../../utils/numberFormatting";
import {
  formatMonthCompact,
  formatMonthYear,
} from "../../utils/dateFormatting";
import {
  AXIS_DEFAULTS,
  CHART_COLORS,
  CHART_TEXT_COLOR,
  formatAxisNumber,
  hexToRgba,
} from "../../utils/chartStyle";

/**
 * The free-cash pool is drawn in neutral ink rather than a palette hue: it is
 * the money *no* goal claimed, so borrowing a goal's colour would imply it
 * belongs to one.
 */
const FREE_CASH_COLOR = CHART_TEXT_COLOR;

/** Faint rule for the zero line — present enough to read against, no more. */
const GRID_COLOR = "rgba(148, 163, 184, 0.25)";

/** How tall the waterfall may stand before it scrolls in place (26rem, px). */
const LIST_CAP_PX = 416;

/** A goal row, roughly — the least overflow worth capping for (see the hook). */
const LIST_CAP_SLACK_PX = 120;

/**
 * Every reorder shares this key and scope. The scope makes the server calls
 * run one after another, so rapid clicks cannot land out of order; the key
 * lets the card ask whether any reorder is still in flight.
 */
const REORDER_KEY = ["savings-goals", "reorder"] as const;
/** Every other goal write: each one restates the history the chart draws. */
const GOAL_WRITE_KEY = ["savings-goals", "write"] as const;

/** Figures awaiting the rebuilt ledger pulse faintly rather than vanish. */
const RECALCULATING_CLASS = "animate-pulse opacity-50 transition-opacity";


/**
 * Dashboard savings-goals panel.
 *
 * Goals fill themselves from each month's surplus in priority order, so the
 * list is a waterfall: the top goal is funded first and spills what it cannot
 * take (its target, or its monthly cap) down to the next one. Reordering
 * restates the whole history under the new order: the rows move the moment
 * an arrow is clicked, and their figures show as recalculating until the
 * server's rebuilt ledger arrives.
 *
 * Below the waterfall sits the free-cash pool: the tracked money no goal has
 * earmarked. It is the buffer a month of overspending drains first, and only
 * once it is empty does a deficit reach back into the goals.
 */
export function GoalsSection() {
  const { t } = useTranslation();
  const qk = useQueryKeys();
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const [editing, setEditing] = useState<SavingsGoal | "new" | null>(null);

  const recalculating = useIsMutating({ mutationKey: REORDER_KEY }) > 0;

  const { data, isLoading } = useQuery({
    queryKey: qk.savingsGoals.all(),
    queryFn: async () => {
      const res = await savingsGoalsApi.getAll();
      return res.data;
    },
    // Held while reorders are queued. A refetch in between — an earlier
    // reorder's invalidation, or the app-wide sweep after it — answers with
    // an order the user has already moved past and snaps the rows back. A
    // disabled query keeps its data and ignores invalidation, then refetches
    // once when the last reorder has landed.
    enabled: !recalculating,
  });

  const { data: pool } = useQuery({
    queryKey: qk.savingsGoals.freeCash(),
    queryFn: async () => {
      const res = await savingsGoalsApi.getFreeCash();
      return res.data;
    },
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: qkPrefix.savingsGoals });

  const deleteMutation = useMutation({
    mutationKey: GOAL_WRITE_KEY,
    mutationFn: (id: number) => savingsGoalsApi.delete(id),
    onSuccess: invalidate,
  });

  const reorderMutation = useMutation({
    mutationKey: REORDER_KEY,
    scope: { id: REORDER_KEY.join(":") },
    mutationFn: (goalIds: number[]) => savingsGoalsApi.reorder(goalIds),
    // Runs at click time even while an earlier reorder is still queued, so
    // the rows move immediately and each click builds on the last one.
    onMutate: async (goalIds: number[]) => {
      const key = qk.savingsGoals.all();
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<SavingsGoal[]>(key);
      if (previous) {
        const byId = new Map(previous.map((g) => [g.id, g]));
        queryClient.setQueryData<SavingsGoal[]>(
          key,
          goalIds.flatMap((id, priority) => {
            const goal = byId.get(id);
            return goal ? [{ ...goal, priority }] : [];
          }),
        );
      }
      return { previous };
    },
    // Only the last reorder in the queue may write: an earlier one's answer
    // is for an order the user has already moved past.
    onSuccess: (res) => {
      if (queryClient.isMutating({ mutationKey: REORDER_KEY }) <= 1) {
        queryClient.setQueryData(qk.savingsGoals.all(), res.data);
      }
    },
    onError: (_err, _ids, context) => {
      if (context?.previous && queryClient.isMutating({ mutationKey: REORDER_KEY }) <= 1) {
        queryClient.setQueryData(qk.savingsGoals.all(), context.previous);
      }
    },
    // Awaited, so "recalculating" lasts until the free-cash pool and the
    // history have caught up with the rebuilt ledger too.
    onSettled: () => invalidate(),
  });

  const goals = data ?? [];

  // Measured rather than counted: rows differ in height (a goal with a monthly
  // figure, a spending line or a clawback note runs taller than a plain
  // one), and what matters is how much a cap would actually hide. `data`, not
  // `goals`: the query's array is stable between renders, while the `?? []`
  // fallback is a fresh one every time.
  const [listRef, capped] = useScrollCap(LIST_CAP_PX, data, LIST_CAP_SLACK_PX);

  /** Swap a goal with its neighbour and persist the new waterfall order. */
  const move = (index: number, direction: -1 | 1) => {
    const next = index + direction;
    if (next < 0 || next >= goals.length) return;
    const ids = goals.map((g) => g.id);
    [ids[index], ids[next]] = [ids[next], ids[index]];
    reorderMutation.mutate(ids);
  };

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] p-4 md:p-6">
      <div className="flex items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-[var(--primary)]/15 text-[var(--primary)]">
            <Target size={16} />
          </div>
          <p className="text-sm md:text-base font-bold">{t("dashboard.goals.title")}</p>
        </div>
        <div className="flex items-center gap-3">
          {recalculating && (
            <span
              role="status"
              className="flex items-center gap-1 text-xs md:text-sm text-[var(--text-muted)]"
            >
              <Loader2 size={14} className="animate-spin" />
              {t("dashboard.goals.recalculating")}
            </span>
          )}
          <button
            onClick={() => setEditing("new")}
            className="flex items-center gap-1 text-xs md:text-sm font-medium text-[var(--primary)] hover:opacity-80 transition-opacity"
          >
            <Plus size={15} />
            {t("dashboard.goals.add")}
          </button>
        </div>
      </div>

      <YearlySavingsSection />

      {isLoading ? (
        <Skeleton variant="card" className="h-32" />
      ) : goals.length === 0 ? (
        <p className="text-[var(--text-muted)] text-sm py-6 text-center">{t("dashboard.goals.empty")}</p>
      ) : (
        /* The waterfall scrolls in place past a few goals. A dozen of them
           would otherwise carry the free-cash row and the history panel down
           the page — off the screen entirely on mobile, where the dashboard
           grid leaves card heights uncapped, and behind the card's own
           scrollbar at >=lg, where the 39rem cap scrolls the header away with
           them. The list is what grows without bound, so it is what is capped,
           and only once a cap would hide something worth scrolling to: until
           then it is a plain block, so a finger dragged across it scrolls the
           page like the rest of the card. The cap is sized to sit under the
           card cap with the history collapsed, so the two scrollers don't both
           appear at rest. */
        <div
          ref={listRef}
          className={`space-y-3 ${capped ? "max-h-[26rem] overflow-y-auto pe-1" : ""}`}
          data-testid="goals-list"
        >
          {goals.map((goal, index) => (
            <GoalRow
              key={goal.id}
              goal={goal}
              rank={index + 1}
              recalculating={recalculating}
              canMoveUp={index > 0}
              canMoveDown={index < goals.length - 1}
              onMoveUp={() => move(index, -1)}
              onMoveDown={() => move(index, 1)}
              onEdit={() => setEditing(goal)}
              onDelete={async () => {
                const ok = await confirm({
                  title: t("common.deleteTitle"),
                  message: t("dashboard.goals.confirmDelete", { name: goal.name }),
                  confirmLabel: t("common.delete"),
                  isDestructive: true,
                });
                if (ok) deleteMutation.mutate(goal.id);
              }}
            />
          ))}
        </div>
      )}

      {!!pool?.has_goals && <FreeCashRow pool={pool} recalculating={recalculating} />}

      {goals.length > 0 && <AllocationHistory goals={goals} />}

      {editing !== null && (
        <GoalEditorModal
          goal={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}

/**
 * The unearmarked remainder of the tracked money, shown under the waterfall.
 *
 * It is deliberately not a goal: nothing fills it and nothing spends it on
 * purpose. It exists so a deficit month has somewhere to land before the
 * engine starts taking money back out of the goals themselves.
 */
function FreeCashRow({
  pool,
  recalculating,
}: {
  pool: SavingsGoalFreeCash;
  recalculating: boolean;
}) {
  const { t } = useTranslation();

  return (
    <div
      className="mt-3 border border-dashed border-[var(--surface-light)] rounded-xl p-3"
      data-testid="goals-free-cash"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className="p-1.5 rounded-lg bg-[var(--surface-light)] text-[var(--text-muted)]">
            <Wallet size={14} />
          </div>
          <div className="min-w-0">
            <p className="text-xs md:text-sm font-medium truncate">
              {t("dashboard.goals.freeCash")}
            </p>
            <p className="text-[10px] md:text-xs text-[var(--text-muted)]">
              {t("dashboard.goals.freeCashHint")}
            </p>
          </div>
        </div>
        <span
          className={`text-sm md:text-base font-bold shrink-0 ${pool.free_cash < -0.5 ? "text-red-400" : ""} ${recalculating ? RECALCULATING_CLASS : ""}`}
          dir="ltr"
        >
          {formatCurrency(pool.free_cash)}
        </span>
      </div>
      {pool.clawed_back_this_month > 0 && (
        <p className="mt-1.5 text-[10px] md:text-xs text-amber-400">
          {t("dashboard.goals.poolDrained", {
            amount: formatCurrency(pool.clawed_back_this_month),
          })}
        </p>
      )}
    </div>
  );
}

/** Trailing windows the history panel offers; 0 means the whole timeline. */
const HISTORY_RANGES = [6, 12, 0] as const;

/** Ties the collapse toggle to the panel it reveals. */
const PANEL_ID = "goals-history-panel";

type HistoryRange = (typeof HISTORY_RANGES)[number];

/**
 * The waterfall read month by month, under the current standings.
 *
 * The rows above answer "where is each goal now"; this answers "how did it get
 * there" — which months fed a goal, which month a deficit took money back out
 * of one (a negative segment, below the axis), and how much was left
 * unearmarked each time.
 *
 * Each bar stacks what the goals took that month, in priority order, with
 * the free-cash pool on top — the money that is tracked and liquid but which
 * no goal has claimed. A segment below the line is money a deficit month took
 * back out of a goal.
 *
 * The pool is a standing balance and the allocations are monthly flows, so a
 * household with real savings will show a tall pool over thin goal segments.
 * That is the point of the legend being clickable: hide the pool and the
 * remaining series rescale to their own size, and a double-click narrows to
 * one goal.
 */
function AllocationHistory({ goals }: { goals: SavingsGoal[] }) {
  const { t } = useTranslation();
  const qk = useQueryKeys();
  const [range, setRange] = useState<HistoryRange>(12);
  // Collapsed by default: the standings above answer "where is each goal now",
  // which is what the card is opened for — the ledger behind them is a second
  // question, and two charts' worth of it pushed the rows off a dashboard
  // screen before anyone asked.
  const [open, setOpen] = useState(false);
  // Series the reader has clicked away in the legend. Keyed by series key, so
  // a goal renamed between fetches keeps its state and a goal that leaves the
  // window simply stops mattering.
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  // Which series a double-click narrowed to, so that double-clicking it again
  // is what brings the others back. Inferring "already alone" from `hidden`
  // instead would make a double-click undo a state the reader had built up
  // click by click, rather than the isolation they just asked for.
  const [isolated, setIsolated] = useState<string | null>(null);

  // Monthly reads what each month moved; cumulative reads what each goal had
  // received by then. Running totals only add up from the first month, so the
  // cumulative view always fetches the whole history and trims to the window
  // itself.
  const [mode, setMode] = useState<HistoryMode>("monthly");
  const fetched = mode === "cumulative" ? 0 : range;
  const { data, isLoading, isFetching } = useQuery({
    queryKey: qk.savingsGoals.timeline(fetched),
    queryFn: async () => (await savingsGoalsApi.getTimeline(fetched)).data,
    // Nothing outside this panel reads the timeline, so a card that is never
    // expanded never pays for the window.
    enabled: open,
  });

  // A goal write restates the whole history server-side, and the chart only
  // refetches once it lands: until then it would draw the old history beside
  // goal rows that already show the new one. It says so instead, as the rows
  // do during a reorder.
  const writing =
    useIsMutating({ mutationKey: GOAL_WRITE_KEY }) +
      useIsMutating({ mutationKey: REORDER_KEY }) >
    0;
  const recalculating = writing || (isFetching && !isLoading);

  // One row per month with a column per goal, which is the shape a stacked
  // chart wants. Months where nothing moved still get a row — the backend
  // sends them, and a gap in a time series reads as "skipped", not "zero".
  const months = data?.months ?? [];
  const rows =
    mode === "cumulative"
      ? lastMonths(cumulativeRows(months, goals), range)
      : monthlyRows(months);

  // Colour follows the goal, not its rank: keyed by id (stable) rather than
  // by priority, so reordering the waterfall never repaints the chart.
  const palette = new Map(
    [...(data?.goals ?? [])]
      .sort((a, b) => a.id - b.id)
      .map((goal, index) => [goal.id, CHART_COLORS[index % CHART_COLORS.length]]),
  );
  // A goal that took nothing in this window would be a legend entry with no
  // mark, so only the ones that actually moved get a series.
  const series = (data?.goals ?? []).filter((goal) =>
    rows.some((row) => row[`g${goal.id}`] !== undefined && row[`g${goal.id}`] !== 0),
  );
  // Free cash stacks last, so it caps the column: the goals take their share
  // from the bottom in priority order and what is left sits on top. A window
  // where every month's surplus was fully claimed drops it, on the same terms
  // as a goal that took nothing.
  const hasFreeCash = rows.some((row) => row[FREE_CASH_KEY] !== 0);
  const keys = [
    ...series.map((goal) => `g${goal.id}`),
    ...(hasFreeCash ? [FREE_CASH_KEY] : []),
  ];
  // Which segment sits at each end of a month's stack, so only the outer
  // corners are rounded and the column reads as one shape rather than a
  // string of beads.
  // Only what is on screen shapes the chart: the rounded corners follow the
  // visible stack, and so does the zero line.
  const visible = keys.filter((key) => !hidden.has(key));
  const ends = stackEnds(rows, visible, "month");
  const yAxis = stackAxis(rows, visible);
  // A segment under the line is money a deficit month took back out of a goal.
  const hasDeficit = rows.some((row) =>
    visible.some((key) => typeof row[key] === "number" && (row[key] as number) < 0),
  );

  /**
   * Hide or show one series.
   *
   * Hiding the last one is allowed: an empty plot under a legend of dimmed
   * entries says what happened and where to undo it, which a click that
   * silently does nothing does not.
   */
  const toggleSeries = (key: string) => {
    setHidden((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
    // Whatever the chart shows now, the reader built it by hand.
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

  // Compact, and without the series that moved nothing that month: with a
  // goal per row, the full-size tooltip stood taller than a phone's plot
  // area and ran over the legend.
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
          // split across lines: on a narrow screen they drop under the title
          // together, side by side.
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
                  onClick={() => setRange(option)}
                  // "All time" is only honest while there is more history than
                  // the widest fixed window; below that it shows the same months
                  // twice.
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
          ) : rows.length === 0 ? (
            <p className="text-[10px] md:text-xs text-[var(--text-muted)] py-4 text-center">
              {t("dashboard.goals.historyEmpty")}
            </p>
          ) : (
            <div
              className={`rounded-xl border border-[var(--surface-light)] bg-[var(--surface-light)]/20 p-3 ${recalculating ? RECALCULATING_CLASS : ""}`}
              data-testid="goals-history-chart"
              aria-busy={recalculating}
            >
              {keys.length === 0 ? (
                // Goals exist, but no month in this window moved a shekel into
                // one or left any surplus behind. There is nothing to stack, so
                // an empty axis is left out.
                <p className="text-[10px] md:text-xs text-[var(--text-muted)] py-2 text-center">
                  {t("dashboard.goals.historyEmpty")}
                </p>
              ) : (
                // Taller on a phone: the legend wraps to three lines there and
                // would leave the bars, and the tooltip, too little room.
                <div className="h-64 md:h-56">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      // Recharts 3 stacks bars in the order they first mounted,
                      // not the order they render in: a reordered goal, a new
                      // one, or a series a wider window brings in kept its old
                      // place — free cash ended up under a goal, and the rounded
                      // ends landed mid-column. A new series order is a new
                      // chart.
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
                        <linearGradient
                          id="goal-fill-free"
                          x1="0"
                          y1="0"
                          x2="0"
                          y2="1"
                        >
                          <stop
                            offset="0%"
                            stopColor={hexToRgba(FREE_CASH_COLOR, 0.55)}
                          />
                          <stop
                            offset="100%"
                            stopColor={hexToRgba(FREE_CASH_COLOR, 0.28)}
                          />
                        </linearGradient>
                      </defs>
                      {/* The months were labelled by the pool panel that used
                          to sit below; with one chart left, this axis carries
                          them. */}
                      <XAxis
                        dataKey="month"
                        {...AXIS_DEFAULTS}
                        tickFormatter={formatMonthCompact}
                      />
                      <YAxis
                        {...AXIS_DEFAULTS}
                        tickFormatter={formatAxisNumber}
                        domain={yAxis.domain}
                        ticks={yAxis.ticks}
                        allowDataOverflow
                        width={44}
                      />
                      {/* Only drawn when a deficit actually pulled a bar under the
                          line — with nothing below it, the axis is the baseline. */}
                      {hasDeficit && (
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
                          stackId="allocations"
                          // The gradient goes on the drawn segment, not on the
                          // series, so the legend swatch keeps a flat colour it
                          // can actually paint — a `url(#…)` fill renders as
                          // nothing in a CSS background.
                          fill={palette.get(goal.id)}
                          // A hidden series leaves the stack entirely, so the
                          // y-axis refits to what is left.
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
                          stackId="allocations"
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
              )}

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

/** Parse a `YYYY-MM` key into a local-time Date (never UTC midnight). */
function monthDate(month: string): Date {
  const [year, index] = month.split("-").map(Number);
  return new Date(year, index - 1, 1);
}

function GoalRow({
  goal,
  rank,
  recalculating,
  canMoveUp,
  canMoveDown,
  onMoveUp,
  onMoveDown,
  onEdit,
  onDelete,
}: {
  goal: SavingsGoal;
  rank: number;
  recalculating: boolean;
  canMoveUp: boolean;
  canMoveDown: boolean;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation();
  // A negative month is a clawback, which the row does not itemize.
  const showThisMonth = goal.this_month_allocation > 0;
  const barColor = goal.is_closed
    ? "from-[var(--text-muted)] to-[var(--text-muted)]"
    : goal.is_achieved
      ? "from-emerald-500 to-emerald-400"
      : "from-[var(--primary)] to-blue-400";

  return (
    <div className="group border border-[var(--surface-light)] rounded-xl p-3 hover:bg-[var(--surface-light)]/30 transition-colors">
      {/* The name owns its own line. It used to share one with the funded /
          target pair and five buttons, which on a phone left it about eight
          characters wide — "New car fund" rendered as "New …", and the row
          named nothing at all. */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-1.5 min-w-0 flex-1">
          <span
            className="text-[10px] font-bold text-[var(--text-muted)] tabular-nums shrink-0"
            title={t("dashboard.goals.priorityHint")}
            dir="ltr"
          >
            #{rank}
          </span>
          {!!goal.is_closed && <Lock size={13} className="text-[var(--text-muted)] shrink-0" />}
          {!goal.is_closed && !!goal.is_achieved && (
            <Check size={14} className="text-emerald-400 shrink-0" />
          )}
          <p className="font-semibold text-sm truncate" dir="auto" title={goal.name}>{goal.name}</p>
        </div>
        <div className="flex items-center gap-0.5 shrink-0">
          <button
            onClick={onMoveUp}
            disabled={!canMoveUp}
            aria-label={t("dashboard.goals.moveUp")}
            className="p-1 rounded-lg text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-light)] disabled:opacity-30 disabled:hover:bg-transparent transition-colors"
          >
            <ChevronUp size={14} />
          </button>
          <button
            onClick={onMoveDown}
            disabled={!canMoveDown}
            aria-label={t("dashboard.goals.moveDown")}
            className="p-1 rounded-lg text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-light)] disabled:opacity-30 disabled:hover:bg-transparent transition-colors"
          >
            <ChevronDown size={14} />
          </button>
          <button onClick={onEdit} aria-label={t("common.edit")} className="p-1.5 rounded-lg text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-light)] transition-colors">
            <Pencil size={14} />
          </button>
          <button onClick={onDelete} aria-label={t("common.delete")} className="p-1.5 rounded-lg text-[var(--text-muted)] hover:text-rose-400 hover:bg-[var(--surface-light)] transition-colors">
            <Trash2 size={14} />
          </button>
        </div>
      </div>
      <div
        className={recalculating ? RECALCULATING_CLASS : undefined}
        aria-busy={recalculating || undefined}
        data-testid="goal-figures"
      >
        <div className="flex items-baseline justify-between gap-2 mb-1.5">
          <span dir="ltr" className="text-sm md:text-base font-bold tabular-nums">
            {formatCurrency(goal.funded)}
            <span className="text-[var(--text-muted)] text-xs md:text-sm font-normal">
              {" / "}
              {formatCurrency(goal.target_amount)}
            </span>
          </span>
          <span dir="ltr" className="text-[10px] md:text-xs text-[var(--text-muted)] tabular-nums shrink-0">
            {goal.progress_pct}%
          </span>
        </div>
        <div className="w-full bg-[var(--surface-light)] rounded-full h-2 overflow-hidden">
          <div className={`h-2 rounded-full bg-gradient-to-r ${barColor} transition-all duration-500`} style={{ width: `${Math.max(0, goal.progress_pct)}%` }} />
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1.5 text-[10px] md:text-xs text-[var(--text-muted)]">
          <GoalStatusLine goal={goal} />
        </div>
        {(showThisMonth || goal.utilized > 0 || showsShekels(goal.owed)) && (
          <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1.5 text-[10px] md:text-xs text-[var(--text-muted)]">
            {showThisMonth && (
              <span>
                {t("dashboard.goals.thisMonth", {
                  amount: formatCurrency(goal.this_month_allocation),
                })}
              </span>
            )}
            {goal.utilized > 0 && (
              <span>
                {t("dashboard.goals.utilized", {
                  spent: formatCurrency(goal.utilized),
                  available: formatCurrency(goal.available),
                })}
              </span>
            )}
            {showsShekels(goal.owed) && (
              <span>
                {t("dashboard.goals.owed", { amount: formatCurrency(goal.owed) })}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/** Whether an amount survives rounding to whole shekels — "0 ₪ owed" is noise. */
function showsShekels(amount: number): boolean {
  return amount >= 0.5;
}

/** The status line: closed, achieved, past due, on-schedule, or plain remainder. */
function GoalStatusLine({ goal }: { goal: SavingsGoal }) {
  const { t } = useTranslation();

  if (goal.is_closed) {
    return <span className="font-medium">{t("dashboard.goals.closed")}</span>;
  }
  if (goal.is_achieved) {
    return <span className="text-emerald-400 font-medium">{t("dashboard.goals.achieved")}</span>;
  }
  if (goal.is_past_due) {
    return (
      <span className="text-amber-400">
        {t("dashboard.goals.pastDue", { amount: formatCurrency(goal.remaining) })}
      </span>
    );
  }
  if (goal.monthly_needed != null && goal.months_remaining === 0) {
    return <span>{t("dashboard.goals.dueThisMonth", { amount: formatCurrency(goal.monthly_needed) })}</span>;
  }
  if (goal.monthly_needed != null && goal.months_remaining != null) {
    return (
      <span>
        {t("dashboard.goals.monthlyNeeded", {
          amount: formatCurrency(goal.monthly_needed),
          count: goal.months_remaining,
        })}
      </span>
    );
  }
  return <span>{t("dashboard.goals.remaining", { amount: formatCurrency(goal.remaining) })}</span>;
}

/** `YYYY-MM` for the current month — the start a goal gets when none is set. */
function currentMonthKey(): string {
  const today = new Date();
  return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;
}

/** "January 2026" for a `YYYY-MM` key, parsed in local time. */
function monthKeyLabel(month: string): string {
  return formatMonthYear(new Date(`${month.slice(0, 7)}-01T00:00:00`));
}

function GoalEditorModal({ goal, onClose }: { goal: SavingsGoal | null; onClose: () => void }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [name, setName] = useState(goal?.name ?? "");
  const [targetAmount, setTargetAmount] = useState(goal ? String(goal.target_amount) : "");
  const [openingBalance, setOpeningBalance] = useState(goal ? String(goal.opening_balance) : "0");
  const [monthlyCap, setMonthlyCap] = useState(goal?.monthly_cap != null ? String(goal.monthly_cap) : "");
  const [startMonth, setStartMonth] = useState(goal?.start_month ?? "");
  const [targetDate, setTargetDate] = useState(goal?.target_date ?? "");
  const [spendRule, setSpendRule] = useState({
    category: goal?.utilization_category ?? "",
    tags: splitRuleTags(goal?.utilization_tags),
  });
  const [saveRule, setSaveRule] = useState({
    category: goal?.contribution_category ?? "",
    tags: splitRuleTags(goal?.contribution_tags),
  });

  const effectiveStart = startMonth || currentMonthKey();
  const startLabel = monthKeyLabel(effectiveStart);

  // Saving restates the goal's history; the editor says so before an opening
  // balance moves, since that changes every month since the start.
  const openingChanged = (Number(openingBalance) || 0) !== (goal?.opening_balance ?? 0);

  const save = useMutation({
    mutationKey: GOAL_WRITE_KEY,
    mutationFn: async (payload: SavingsGoalInput) => {
      return goal
        ? await savingsGoalsApi.update(goal.id, payload)
        : await savingsGoalsApi.create(payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.savingsGoals });
      onClose();
    },
  });

  const canSave = name.trim().length > 0 && Number(targetAmount) > 0;

  const handleSubmit = () => {
    if (!canSave) return;
    save.mutate({
      name: name.trim(),
      target_amount: Number(targetAmount),
      opening_balance: Number(openingBalance) || 0,
      // An empty cap field means uncapped, so the goal can fill in one month.
      monthly_cap:
        saveRule.category || monthlyCap.trim() === "" ? null : Number(monthlyCap),
      start_month: startMonth || null,
      target_date: targetDate || null,
      utilization_category: spendRule.category || null,
      utilization_tags: joinRuleTags(spendRule.category ? spendRule.tags : null),
      contribution_category: saveRule.category || null,
      contribution_tags: joinRuleTags(saveRule.category ? saveRule.tags : null),
    });
  };

  const field =
    "w-full bg-[var(--surface-light)] border border-[var(--surface-light)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[var(--primary)]";
  const label = "block text-xs font-medium text-[var(--text-muted)] mb-1";

  return (
    <Modal
      isOpen
      onClose={onClose}
      title={goal ? t("dashboard.goals.editTitle") : t("dashboard.goals.addTitle")}
      titleIcon={<Target size={18} />}
      maxWidth="md"
    >
      <div className="space-y-4 p-4 md:p-6">
        <div>
          <label className={label} htmlFor="goal-name">{t("dashboard.goals.nameLabel")}</label>
          <input
            id="goal-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t("dashboard.goals.namePlaceholder")}
            className={field}
            dir="auto"
          />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className={label} htmlFor="goal-target">{t("dashboard.goals.targetLabel")}</label>
            <input
              id="goal-target"
              type="number" inputMode="decimal" value={targetAmount}
              onChange={(e) => setTargetAmount(e.target.value)}
              className={field}
              dir="ltr"
            />
          </div>
          <div>
            <label className={label} htmlFor="goal-opening">{t("dashboard.goals.openingLabel")}</label>
            <input
              id="goal-opening"
              type="number" inputMode="decimal" value={openingBalance}
              onChange={(e) => setOpeningBalance(e.target.value)}
              className={field}
              dir="ltr"
            />
            <p className="text-[10px] text-[var(--text-muted)] mt-1">
              {t("dashboard.goals.openingHint")}
            </p>
            {!!goal && openingChanged && (
              <p className="text-[10px] text-amber-400 mt-1">
                {t("dashboard.goals.openingRestateHint", { month: startLabel })}
              </p>
            )}
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {/* A cap limits what a goal takes from surplus; a goal filled by
              its own income (a saved-into rule) takes none. */}
          {!saveRule.category && (
          <div>
            <label className={label} htmlFor="goal-cap">{t("dashboard.goals.capLabel")}</label>
            <input
              id="goal-cap"
              type="number" inputMode="decimal" value={monthlyCap}
              onChange={(e) => setMonthlyCap(e.target.value)}
              placeholder={t("dashboard.goals.capPlaceholder")}
              className={field}
              dir="ltr"
            />
            <p className="text-[10px] text-[var(--text-muted)] mt-1">
              {t("dashboard.goals.capHint")}
            </p>
          </div>
          )}
          <div>
            <label className={label} htmlFor="goal-start">{t("dashboard.goals.startMonthLabel")}</label>
            <input
              id="goal-start"
              // The same calendar as the target date. Goals count whole
              // months, so whichever day is picked, the goal starts with the
              // month it falls in — shown back as that month's first day.
              type="date"
              value={startMonth ? `${startMonth.slice(0, 7)}-01` : ""}
              onChange={(e) => setStartMonth(e.target.value.slice(0, 7))}
              className={field}
              dir="ltr"
            />
            <p className="text-[10px] text-[var(--text-muted)] mt-1">
              {t("dashboard.goals.startMonthHint")}
            </p>
          </div>
        </div>
        <div>
          <label className={label} htmlFor="goal-date">{t("dashboard.goals.dateLabel")}</label>
          <input
            id="goal-date"
            type="date" value={targetDate ?? ""}
            onChange={(e) => setTargetDate(e.target.value)}
            className={field}
            dir="ltr"
          />
        </div>
        <fieldset className="space-y-3 border-t border-[var(--surface-light)] pt-3">
          <legend className="text-xs font-semibold text-[var(--text-muted)] pe-2">
            {t("dashboard.goals.autoLinkTitle")}
          </legend>
          <GoalAutoLinkField
            testId="goal-auto-link-spend"
            label={t("dashboard.goals.autoLinkSpendLabel")}
            hint={t("dashboard.goals.autoLinkSpendHint")}
            category={spendRule.category}
            tags={spendRule.tags}
            onChange={(category, tags) => setSpendRule({ category, tags })}
          />
          <GoalAutoLinkField
            testId="goal-auto-link-save"
            label={t("dashboard.goals.autoLinkSaveLabel")}
            hint={t("dashboard.goals.autoLinkSaveHint")}
            category={saveRule.category}
            tags={saveRule.tags}
            onChange={(category, tags) => setSaveRule({ category, tags })}
          />
        </fieldset>
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm font-medium text-[var(--text-muted)] hover:bg-[var(--surface-light)] transition-colors">
            {t("common.cancel")}
          </button>
          <button
            onClick={handleSubmit}
            disabled={!canSave || save.isPending}
            className="px-4 py-2 rounded-lg text-sm font-bold bg-[var(--primary)] text-white disabled:opacity-50 hover:opacity-90 transition-opacity"
          >
            {t("common.save")}
          </button>
        </div>
      </div>
    </Modal>
  );
}
