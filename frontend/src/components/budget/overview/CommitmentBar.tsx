import React from "react";
import { useTranslation } from "react-i18next";
import type { BudgetOverview } from "../../../services/api";
import { formatCurrency } from "../../../utils/numberFormatting";

/**
 * One segment of the bar. ``grow`` is the raw shekel figure — the segments are
 * flex-grown by value, so their widths are the proportions themselves and no
 * percentage arithmetic is needed.
 */
interface Segment {
  key: string;
  grow: number;
  /** Inline style for the block, so a segment can be a fill, a hatch or a track. */
  style: React.CSSProperties;
  label: string;
  amount: number;
  sub?: string;
}

/**
 * Slate for fixed, blue for day-to-day. Slate reads as a recessive neutral on
 * purpose: recurring charges are the part of the month nobody decides, so they
 * must not compete with the spend the user actually controls.
 */
const FIXED_FILL: React.CSSProperties = { background: "#64748b" };
const VARIABLE_FILL: React.CSSProperties = { background: "var(--primary)" };
const OVER_FILL: React.CSSProperties = { background: "#ff2056" };
const TRACK: React.CSSProperties = { background: "var(--surface-light)" };
/**
 * Committed money is drawn rather than filled — it has not been spent yet, and a
 * solid block would claim otherwise. The hatch also carries the distinction
 * without relying on hue.
 */
const COMMITTED_FILL: React.CSSProperties = {
  border: "1px dashed var(--text-muted)",
  background:
    "repeating-linear-gradient(135deg, rgba(148,163,184,0.25) 0 3px, transparent 3px 6px)",
};

function Swatch({ style }: { style: React.CSSProperties }) {
  return (
    <span
      aria-hidden
      className="w-2.5 h-2.5 rounded-[3px] shrink-0 mt-[3px]"
      style={style}
    />
  );
}

interface CommitmentBarProps {
  overview: BudgetOverview;
  /** Bar thickness in pixels. */
  height?: number;
  /** Drop the per-segment sub-line, for the narrow dashboard card. */
  compact?: boolean;
  /**
   * Hide the "free to spend" legend entry. The card states that figure in the
   * chip beside its total, so repeating it there costs a whole legend row for
   * nothing.
   */
  hideFreeInLegend?: boolean;
}

/**
 * Where a month's budget stands, as four parts rather than a clock.
 *
 * The pacing question ("should I have spent this much by the 19th?") has no
 * honest answer, because a month is not spent evenly — rent, school fees and
 * insurances land in the first days. This bar answers the question that does
 * have one: of the budget, how much is already gone on charges that were always
 * going to happen, how much went on day-to-day choices, how much is spoken for
 * before month end, and how much is genuinely left.
 *
 * A settled month has nothing committed and may have overspent, so it draws
 * three parts instead — fixed, day-to-day, and the overspill in rose — with a
 * marker where the budget sat.
 */
export const CommitmentBar: React.FC<CommitmentBarProps> = ({
  overview,
  height = 14,
  compact = false,
  hideFreeInLegend = false,
}) => {
  const { t } = useTranslation();
  const {
    is_current_month: isCurrent,
    fixed_spent: fixed,
    variable_spent: variable,
    committed_remaining: committed,
    free_to_spend: free,
    monthly_budget: budget,
    monthly_spent: spent,
    variable_per_day: perDay,
    days_left: daysLeft,
    days_elapsed: daysElapsed,
    charges_due: chargesDue,
  } = overview;

  const over = Math.max(spent - budget, 0);
  // A closed month is measured against its own limit; the bar has to grow past
  // that limit when it was breached, so the scale is whichever is larger.
  const scale = Math.max(spent, budget, 1);
  const markerPercent = (budget / scale) * 100;

  const segments: Segment[] = [
    {
      key: "fixed",
      grow: Math.max(fixed, 0),
      style: FIXED_FILL,
      label: t("budget.overview.fixedCharged"),
      amount: fixed,
      sub: t("budget.overview.recurringCount", { count: chargesDue.length }),
    },
    {
      key: "variable",
      grow: Math.max(variable, 0),
      style: VARIABLE_FILL,
      label: isCurrent
        ? t("budget.overview.variableSpent")
        : t("budget.overview.dayToDay"),
      amount: variable,
      sub: isCurrent
        ? t("budget.overview.perDayShort", { amount: formatCurrency(perDay) })
        : t("budget.overview.perDayOverMonth", {
            amount: formatCurrency(perDay),
            count: daysElapsed,
          }),
    },
  ];

  if (isCurrent) {
    segments.push({
      key: "committed",
      grow: Math.max(committed, 0),
      style: COMMITTED_FILL,
      label: t("budget.overview.stillCommitted"),
      amount: committed,
      sub: t("budget.overview.chargesDueCount", { count: chargesDue.length }),
    });
    segments.push({
      key: "free",
      grow: Math.max(free, 0),
      style: TRACK,
      label: t("budget.overview.freeToSpend"),
      amount: free,
      sub: t("budget.overview.perDay", {
        amount: formatCurrency(daysLeft > 0 ? free / daysLeft : free),
        count: daysLeft,
      }),
    });
  } else if (over > 0) {
    segments.push({
      key: "over",
      grow: over,
      style: OVER_FILL,
      label: t("budget.overview.overBudgetSegment"),
      amount: over,
      sub: t("budget.overview.budgetMarker", { amount: formatCurrency(budget) }),
    });
  } else {
    segments.push({
      key: "free",
      grow: Math.max(budget - spent, 0),
      style: TRACK,
      label: t("budget.overview.freeToSpend"),
      amount: Math.max(budget - spent, 0),
    });
  }

  const legend = hideFreeInLegend
    ? segments.filter((segment) => segment.key !== "free")
    : segments;

  return (
    <div data-testid="budget-commitment-bar">
      {/* `flex-grow` by shekel value: the widths *are* the proportions, so a
          rounding error can never leave a sliver of track at the end. */}
      <span
        className="relative flex gap-0.5 w-full"
        style={{ height: `${height}px` }}
      >
        {segments.map((segment) => (
          <span
            key={segment.key}
            data-testid={`commitment-segment-${segment.key}`}
            className="h-full rounded"
            style={{ flex: `${segment.grow} 0 0`, ...segment.style }}
          />
        ))}
        {!isCurrent && over > 0 && (
          <span
            aria-hidden
            className="absolute -top-1 -bottom-1 w-0.5 rounded-sm bg-[var(--text)] opacity-80"
            style={{ insetInlineStart: `${markerPercent}%` }}
          />
        )}
      </span>

      <div className="grid grid-cols-[repeat(auto-fit,minmax(158px,1fr))] gap-x-4 gap-y-2.5 mt-2.5">
        {legend.map((segment) => (
          <div key={segment.key} className="flex items-start gap-2 min-w-0">
            <Swatch style={segment.style} />
            <div className="flex flex-col gap-px min-w-0">
              <span className="flex items-baseline gap-1.5">
                <span className="text-xs text-[var(--text-muted)] whitespace-nowrap">
                  {segment.label}
                </span>
                <span dir="ltr" className="text-xs font-bold font-mono whitespace-nowrap">
                  {formatCurrency(segment.amount)}
                </span>
              </span>
              {!compact && segment.sub && (
                <span className="text-[11px] text-[var(--text-muted)]">
                  {segment.sub}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
