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
}

interface BurnProps extends BaseProps {
  variant: "burn";
  /**
   * Periods the envelope spans (12 for a yearly rule). The line stops at the
   * last active period, so the empty tail reads as "time left".
   */
  totalPeriods: number;
  /** Draw the diagonal "you should be here by now" line (yearly only). */
  showPace?: boolean;
}

type RuleSparklineProps = BarsProps | BurnProps;

function colorFor(spent: number, budget: number): string {
  if (budget <= 0) return NEUTRAL;
  if (spent > budget) return ROSE;
  if (spent > budget * 0.9) return AMBER;
  return GREEN;
}

/**
 * Per-rule trend, drawn two ways because the two kinds of envelope ask
 * different questions.
 *
 * `bars` — a monthly envelope resets every month, so the question is "is this
 * month unusual?". One bar per month against a dashed budget line; the current
 * month is the only one at full opacity.
 *
 * `burn` — a yearly or project envelope is a fixed pot spent down once, so
 * comparing months is meaningless and the question is "will it hold?".
 * Cumulative spend against the ceiling, optionally with a pace diagonal: a row
 * can sit well under its ceiling and still be spending too fast for the year,
 * which the percentage column cannot express.
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

  // One entry per period plus the reference, so the mark is never the only
  // channel. This deliberately does NOT use the app's [data-tooltip] pattern:
  // that renders an absolutely-positioned, `white-space: nowrap` ::after, and
  // a summary this long inflates the document's scrollWidth — which is exactly
  // the horizontal-scroll-on-mobile regression budget.spec.ts guards against.
  // An in-SVG <title> has no layout box at all.
  const summary = [
    ...labels.map((label, i) => `${label} ${formatCompactCurrency(totals[i] ?? 0)}`),
    `${isBars ? t("budget.trend.budget") : t("budget.yearly.allocated")} ${formatCompactCurrency(budget)}`,
  ].join(" · ");

  let body: React.ReactNode;

  if (isBars) {
    const gap = 2;
    const barWidth = (width - gap * (series.length - 1)) / series.length;
    const max = Math.max(...series, budget) * 1.12 || 1;
    const radius = Math.min(2, barWidth / 2);
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
              fill={colorFor(value, budget)}
              opacity={i === series.length - 1 ? 1 : 0.45}
            />
          );
        })}
        {budget > 0 && (
          <line
            x1={0}
            y1={height - (budget / max) * height}
            x2={width}
            y2={height - (budget / max) * height}
            stroke={REFERENCE}
            strokeWidth={1}
            strokeDasharray="3 3"
            opacity={0.75}
          />
        )}
      </>
    );
  } else {
    const { totalPeriods, showPace = false } = props;
    const span = Math.max(totalPeriods, 2);
    const max = Math.max(budget, ...totals) * 1.1 || 1;
    const x = (i: number) => (i / (span - 1)) * width;
    const y = (value: number) => height - (value / max) * height;
    const expected = showPace ? budget * ((last + 1) / span) : budget;
    const stroke =
      finalValue > budget ? ROSE : finalValue > expected ? AMBER : GREEN;
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
            stroke={REFERENCE}
            strokeWidth={1}
            strokeDasharray="2 3"
            opacity={0.45}
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
