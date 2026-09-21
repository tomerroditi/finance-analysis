import React from "react";
import { useTranslation } from "react-i18next";
import { formatCompactCurrency } from "../../utils/numberFormatting";
import { cumulative, lastActivePeriod } from "../../utils/budgetTrends";

const GREEN = "#10b981";
const AMBER = "#f59e0b";
const ROSE = "#f43f5e";
const NEUTRAL = "#64748b";
const REFERENCE = "#94a3b8";

interface BaseProps {
  /** Spend per period, oldest first. */
  series: number[];
  /** Short labels for each period (e.g. "Feb"), used for the hover summary. */
  labels: string[];
  /** Budget for a monthly rule, allocation ceiling for a yearly/project one. */
  budget: number;
  width?: number;
  height?: number;
  /**
   * Stretch to the container's width while keeping `height` exactly. The
   * summary band's figure takes whatever width the stats row has left; letting
   * it scale uniformly instead would make it ~66px tall at that width and grow
   * the whole band. Ledger rows keep the fixed intrinsic size so their trend
   * column stays aligned row to row.
   */
  fluid?: boolean;
  className?: string;
}

interface BarsProps extends BaseProps {
  variant: "bars";
  /**
   * The limit each period carried, oldest first, aligned with `series`. A
   * monthly rule is re-created and re-editable every month, so its
   * history was not all measured against today's cap — the reference steps
   * with it instead of running flat, and each bar takes its colour from the
   * limit that was actually in force. A zero (or an entry past the end of
   * the array) means no rule that period, drawn as a gap. Omit it
   * entirely and every period falls back to `budget`.
   */
  budgets?: number[];
}

interface BurnProps extends BaseProps {
  variant: "burn";
  /**
   * Periods the rule spans (12 for a yearly rule). The line stops at the
   * last active period, so the empty tail reads as "time left".
   */
  totalPeriods: number;
  /** Draw the diagonal "you should be here by now" line (yearly only). */
  showPace?: boolean;
  /**
   * Periods already gone by (months elapsed, for a yearly rule). Pace is
   * measured against the calendar, so a caller that knows it passes it;
   * without it the last period with a charge stands in.
   */
  elapsedPeriods?: number;
}

type RuleSparklineProps = BarsProps | BurnProps;

function colorFor(spent: number, budget: number): string {
  if (budget <= 0) return NEUTRAL;
  if (spent > budget) return ROSE;
  if (spent > budget * 0.9) return AMBER;
  return GREEN;
}

/**
 * The dashed budget reference for the bars variant, as one step per period.
 *
 * Each period's segment spans its own bar plus half the gap on either side,
 * so consecutive periods meet exactly and a run of equal limits draws as the
 * single flat line it used to be — a step only appears where the limit
 * actually moved. A period with no rule (limit <= 0) breaks the path
 * into a new subpath, leaving a gap rather than a line along the floor.
 */
function referencePath(
  limits: number[],
  barWidth: number,
  gap: number,
  width: number,
  limitY: (limit: number) => number,
): string {
  const segments: string[] = [];
  let open = false;

  limits.forEach((limit, i) => {
    if (limit <= 0) {
      open = false;
      return;
    }
    const y = limitY(limit);
    const start = Math.max(i * (barWidth + gap) - gap / 2, 0);
    const end = Math.min(i * (barWidth + gap) + barWidth + gap / 2, width);
    // `L` rather than `M` when the previous period ran up to this one: the
    // vertical riser is what makes a change of limit legible as a step.
    segments.push(`${open ? "L" : "M"} ${start},${y} L ${end},${y}`);
    open = true;
  });

  return segments.join(" ");
}

/**
 * Per-rule trend, drawn two ways because the two kinds of rule ask
 * different questions.
 *
 * `bars` — a monthly rule resets every month, so the question is "is this
 * month unusual?". One bar per month against a dashed budget line; the current
 * month is the only one at full opacity. The line steps with `budgets`, each
 * month drawn against the cap it actually carried, because a raised or cut
 * rule would otherwise rewrite its own history: a month that came in on
 * budget must not turn red because the rule was tightened afterwards.
 *
 * `burn` — a yearly or project rule is a fixed pot spent down once, so
 * comparing months is meaningless and the question is "will it hold?".
 * Cumulative spend against the ceiling, optionally with a pace diagonal: a row
 * can sit well under its ceiling and still be spending too fast for the year,
 * which the percentage column cannot express.
 *
 * Both variants take their colour from `colorFor`, the same share-of-ceiling
 * thresholds the ledger row's dot, bar and percentage use. Pace gets its own
 * mark — the diagonal turns amber when the burn line is above it — rather than
 * the status colour: a rule at 85% of its ceiling is on track by every
 * other surface on the page (the year's health count included), and painting
 * only its trend amber made one row answer two questions in one palette.
 */
export const RuleSparkline: React.FC<RuleSparklineProps> = (props) => {
  const { t } = useTranslation();
  const {
    series,
    labels,
    budget,
    width = 74,
    height = 22,
    fluid = false,
    className = "",
  } = props;

  if (!series.length || series.every((v) => v === 0)) {
    return (
      <span
        className={`inline-block text-[var(--text-muted)] text-[10px] ${className}`}
        aria-hidden="true"
      >
        —
      </span>
    );
  }

  const isBars = props.variant === "bars";
  const totals = isBars ? series : cumulative(series);
  const last = isBars ? series.length - 1 : lastActivePeriod(series);
  const finalValue = totals[isBars ? series.length - 1 : last];

  let body: React.ReactNode;
  // Set by the burn branch; the summary is assembled below so the pace
  // warning reaches a reader who never sees the amber diagonal.
  let aheadOfPace = false;
  // Set by the bars branch, for the same reason: a reader who never sees the
  // stepped line still needs to know which month was measured against what.
  let barLimits: number[] = [];

  if (isBars) {
    const gap = 2;
    const barWidth = (width - gap * (series.length - 1)) / series.length;
    // Per-period limits, defaulting to the single `budget` so a caller that
    // has no history of its caps keeps the flat line it had before.
    const limits = series.map((_, i) => props.budgets?.[i] ?? budget);
    barLimits = limits;
    const max = Math.max(...series, ...limits) * 1.12 || 1;
    const radius = Math.min(2, barWidth / 2);
    const limitY = (limit: number) => height - (limit / max) * height;
    body = (
      <>
        {series.map((value, i) => {
          const barHeight = Math.max((value / max) * height, value > 0 ? 1.5 : 0);
          return (
            <rect
              key={labels[i] ?? i}
              x={i * (barWidth + gap)}
              y={height - barHeight}
              width={barWidth}
              height={barHeight}
              rx={radius}
              fill={colorFor(value, limits[i])}
              opacity={i === series.length - 1 ? 1 : 0.45}
            />
          );
        })}
        {limits.some((limit) => limit > 0) && (
          <path
            d={referencePath(limits, barWidth, gap, width, limitY)}
            fill="none"
            stroke={REFERENCE}
            strokeWidth={1}
            strokeDasharray="3 3"
            opacity={0.75}
            data-testid="budget-reference"
          />
        )}
      </>
    );
  } else {
    const { totalPeriods, showPace = false, elapsedPeriods } = props;
    const span = Math.max(totalPeriods, 2);
    const max = Math.max(budget, ...totals) * 1.1 || 1;
    const x = (i: number) => (i / (span - 1)) * width;
    const y = (value: number) => height - (value / max) * height;
    // Pace belongs to the calendar, not to the last charge: a rule whose
    // last spend was in May is not "on May's pace" once September is here, and
    // judging it by a clock that stopped with its own spending flagged rows
    // that had in fact fallen further behind pace with every quiet month.
    const elapsed = Math.min(Math.max(elapsedPeriods ?? last + 1, 1), span);
    const expected = budget * (elapsed / span);
    aheadOfPace = showPace && budget > 0 && finalValue > expected;
    const stroke = colorFor(finalValue, budget);
    const points = totals
      .slice(0, last + 1)
      .map((value, i) => `${x(i)},${y(value)}`)
      .join(" ");
    const ceilingY = y(budget);
    body = (
      <>
        <polygon
          points={`0,${height} ${points} ${x(last)},${height}`}
          fill={stroke}
          opacity={0.16}
        />
        <line
          x1={0}
          y1={ceilingY}
          x2={width}
          y2={ceilingY}
          stroke={REFERENCE}
          strokeWidth={1}
          strokeDasharray="3 3"
          opacity={0.75}
        />
        {showPace && (
          <line
            x1={0}
            y1={height}
            x2={width}
            y2={ceilingY}
            stroke={aheadOfPace ? AMBER : REFERENCE}
            strokeWidth={1}
            strokeDasharray="2 3"
            opacity={aheadOfPace ? 0.9 : 0.45}
            data-testid="pace-line"
          />
        )}
        <polyline
          points={points}
          fill="none"
          stroke={stroke}
          strokeWidth={1.6}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        <circle
          cx={x(last)}
          cy={y(finalValue)}
          r={2.6}
          fill={stroke}
          stroke="var(--surface)"
          strokeWidth={1.5}
        />
      </>
    );
  }

  // One entry per period plus the reference, so the mark is never the only
  // channel. This deliberately does NOT use the app's [data-tooltip] pattern:
  // that renders an absolutely-positioned, `white-space: nowrap` ::after, and
  // a summary this long inflates the document's scrollWidth — which is exactly
  // the horizontal-scroll-on-mobile regression budget.spec.ts guards against.
  // An in-SVG <title> has no layout box at all.
  // A stepped reference is invisible to a screen reader, so each period
  // carries its own limit in the summary as soon as they stop agreeing.
  const limitsVary = barLimits.some((limit) => limit !== barLimits[0]);
  const summary = [
    ...labels.map((label, i) => {
      const value = formatCompactCurrency(totals[i] ?? 0);
      return limitsVary
        ? `${label} ${value} / ${formatCompactCurrency(barLimits[i] ?? 0)}`
        : `${label} ${value}`;
    }),
    `${isBars ? t("budget.trend.budget") : t("budget.yearly.allocated")} ${formatCompactCurrency(isBars ? (barLimits[barLimits.length - 1] ?? budget) : budget)}`,
    ...(aheadOfPace ? [t("budget.trend.aheadOfPace")] : []),
  ].join(" · ");

  return (
    <span
      className={`${fluid ? "block w-full" : "inline-block"} leading-none ${className}`}
      data-testid="rule-sparkline"
    >
      <svg
        {...(fluid
          ? {
              viewBox: `0 0 ${width} ${height}`,
              preserveAspectRatio: "none",
              className: "w-full",
              height,
            }
          : { width, height })}
        role="img"
        aria-label={summary}
      >
        <title>{summary}</title>
        {body}
      </svg>
    </span>
  );
};
