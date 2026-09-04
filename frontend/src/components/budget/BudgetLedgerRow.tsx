import React from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronUp } from "lucide-react";
import { formatCurrency } from "../../utils/numberFormatting";

export interface BudgetLedgerRowProps {
  label: string;
  subLabel?: string;
  /** Raw signed amount: positive = net spend, negative = net refund. */
  current: number;
  total: number;
  isExpanded: boolean;
  onToggleExpand: () => void;
  actions?: React.ReactNode;
  /** Per-rule trend cell (see RuleSparkline). */
  trend?: React.ReactNode;
  children?: React.ReactNode;
}

/**
 * One envelope per line.
 *
 * Replaces the two-line card (title line + full-width 20px bar + padding,
 * ~76px) with a single grid line on desktop, so a month with a dozen
 * envelopes fits on one screen. Below `md:` it keeps two lines — name and
 * percentage, then bar, figures and trend — because eight columns don't fit
 * on a phone.
 *
 * `current` is the signed net for the period: a negative value means refunds
 * exceeded spend. That is not spending, so it is clamped to 0 for the bar and
 * the over-budget test — otherwise a large refund fills the bar and reads as
 * an overspend.
 */
export const BudgetLedgerRow: React.FC<BudgetLedgerRowProps> = ({
  label,
  subLabel,
  current,
  total,
  isExpanded,
  onToggleExpand,
  actions,
  trend,
  children,
}) => {
  const { t } = useTranslation();

  const isNetRefund = current < 0;
  const spent = Math.max(current, 0);
  // No budget means no proportion to draw: a 0-ceiling envelope used to
  // render a full amber bar, which read as "spent out" rather than "no
  // budget set" — and every other cell on the row already shows an em dash.
  const percent = total > 0 ? Math.min((spent / total) * 100, 100) : 0;
  const over = spent > total && total > 0;
  const near = !over && total > 0 && spent > total * 0.9;
  const remaining = total - spent;

  const barColor = over ? "bg-rose-500" : near ? "bg-amber-500" : "bg-emerald-500";
  const pctColor = over
    ? "text-rose-400"
    : near
      ? "text-amber-400"
      : "text-[var(--text-default)]";

  const bar = (
    <span className="relative block h-1.5 w-full rounded-full bg-[var(--surface-light)] overflow-hidden">
      <span
        className={`absolute inset-y-0 start-0 rounded-full ${barColor} transition-all duration-500 ease-out`}
        style={{ width: `${percent}%` }}
      />
    </span>
  );

  const figures = (
    <>
      {formatCurrency(current)}{" "}
      <span className="text-[var(--text-muted)] font-normal">
        / {total > 0 ? formatCurrency(total) : "—"}
      </span>
    </>
  );

  const leftLabel = isNetRefund
    ? t("budget.netRefund", { amount: formatCurrency(Math.abs(current)) })
    : total > 0
      ? over
        ? t("budget.overByAmount", { amount: formatCurrency(Math.abs(remaining)) })
        : t("budget.remainingAmount", { amount: formatCurrency(remaining) })
      : "";

  return (
    <div className="w-full rounded-xl border border-[var(--surface-light)] bg-[var(--surface)] shadow-sm hover:shadow-md transition-shadow group">
      <div className="flex items-center gap-1 px-2 md:px-3">
        <button
          type="button"
          onClick={onToggleExpand}
          aria-expanded={isExpanded}
          className="flex-1 min-w-0 py-2 text-start"
        >
          {/* Desktop: one line, eight columns.
              Every row is its own grid, so the numeric tracks are fixed and
              must fit their widest realistic value — a `whitespace-nowrap`
              figure that outgrows its track doesn't shrink, it spills into
              the next column and knocks that row out of line with the rest
              (the old 112px figures track already spilled at "1,770 ₪ /
              3,000 ₪"). Sized measured: 152px holds "123,456 ₪ / 100,000 ₪"
              and 76px holds "-123,456 ₪". */}
          <span className="hidden md:grid items-center gap-3 grid-cols-[10px_minmax(0,1.3fr)_minmax(0,1fr)_152px_76px_44px_78px]">
            <span
              className={`w-2.5 h-2.5 rounded-full shrink-0 ${total > 0 ? barColor : "bg-[var(--surface-light)]"}`}
            />
            <span className="min-w-0">
              <span
                className="block font-semibold text-sm text-[var(--text-default)] truncate"
                dir="auto"
              >
                {label}
              </span>
              {subLabel && (
                <span
                  className="block text-[10px] uppercase tracking-wide text-[var(--text-muted)] truncate"
                  dir="auto"
                >
                  {subLabel}
                </span>
              )}
            </span>
            {bar}
            <span
              className="text-end font-bold font-mono text-xs whitespace-nowrap"
              dir="ltr"
              data-testid="ledger-figures"
            >
              {figures}
            </span>
            <span
              className={`text-end font-mono text-xs whitespace-nowrap ${over || isNetRefund ? "text-rose-400" : "text-[var(--text-muted)]"}`}
              dir="ltr"
              title={leftLabel}
            >
              {total > 0
                ? over
                  ? `-${formatCurrency(Math.abs(remaining))}`
                  : formatCurrency(remaining)
                : "—"}
            </span>
            <span className={`text-end font-mono text-xs font-bold ${pctColor}`} dir="ltr">
              {total > 0 ? `${Math.round((spent / total) * 100)}%` : "—"}
            </span>
            <span className="flex justify-end">{trend}</span>
          </span>

          {/* Mobile: two lines */}
          <span className="md:hidden flex flex-col gap-1.5">
            <span className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-2 min-w-0">
                <span
                  className={`w-2 h-2 rounded-full shrink-0 ${total > 0 ? barColor : "bg-[var(--surface-light)]"}`}
                />
                <span
                  className="font-semibold text-sm text-[var(--text-default)] truncate"
                  dir="auto"
                >
                  {label}
                </span>
              </span>
              <span className={`font-mono text-xs font-bold shrink-0 ${pctColor}`} dir="ltr">
                {total > 0 ? `${Math.round((spent / total) * 100)}%` : "—"}
              </span>
            </span>
            <span className="flex items-center gap-2">
              {bar}
              <span
                className="font-mono text-[10px] text-[var(--text-muted)] whitespace-nowrap"
                dir="ltr"
                data-testid="ledger-figures"
              >
                {figures}
              </span>
              {trend}
            </span>
            {leftLabel && (
              <span className="text-[10px] text-[var(--text-muted)]" dir="ltr">
                {leftLabel}
              </span>
            )}
          </span>
        </button>

        {actions && (
          <div className="hidden md:flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
            {actions}
          </div>
        )}

        <span className="text-[var(--text-muted)] shrink-0">
          {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </span>
      </div>

      {/* Mobile has no hover, so actions get their own always-visible row. */}
      {actions && (
        <div className="md:hidden flex items-center gap-1 px-2 pb-1.5">{actions}</div>
      )}

      {isExpanded && children}
    </div>
  );
};
