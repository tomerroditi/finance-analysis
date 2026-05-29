import React from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronUp } from "lucide-react";
import { formatCurrency } from "../../utils/numberFormatting";

interface BudgetRuleRowProps {
  label: string;
  subLabel?: string;
  /** Raw signed amount (expenses are negative); displayed as magnitude. */
  current: number;
  total: number;
  isExpanded: boolean;
  onToggleExpand: () => void;
  actions?: React.ReactNode;
  children?: React.ReactNode;
  /** Visually de-emphasize (e.g. the "Other Expenses" pseudo-rule). */
  dimmed?: boolean;
}

/**
 * Two-line budget rule row: name + figures on top, full-width progress bar +
 * status hint below. Replaces the single-line dense `BudgetProgressBar`
 * compact mode for better scannability. Tapping the body toggles the
 * expandable transaction list; edit/delete actions reveal on hover (desktop)
 * or sit on a dedicated row (mobile).
 */
export const BudgetRuleRow: React.FC<BudgetRuleRowProps> = ({
  label,
  subLabel,
  current,
  total,
  isExpanded,
  onToggleExpand,
  actions,
  children,
  dimmed = false,
}) => {
  const { t } = useTranslation();
  const spent = Math.abs(current);
  const percent =
    total > 0 ? Math.min((spent / total) * 100, 100) : spent > 0 ? 100 : 0;
  const over = spent > total && total > 0;
  const near = !over && total > 0 && spent > total * 0.9;
  const unbudgeted = total === 0 && spent > 0;

  const barColor = over
    ? "bg-rose-500"
    : near || unbudgeted
      ? "bg-amber-500"
      : "bg-emerald-500";
  const dotColor = barColor;

  const remaining = total - spent;
  const hint =
    total > 0
      ? over
        ? t("budget.overByAmount", { amount: formatCurrency(Math.abs(remaining)) })
        : t("budget.remainingAmount", { amount: formatCurrency(remaining) })
      : null;

  return (
    <div
      className={`w-full rounded-xl border border-[var(--surface-light)] bg-[var(--surface)] shadow-sm hover:shadow-md transition-shadow group ${
        dimmed ? "opacity-60" : ""
      }`}
    >
      <div
        className="px-3 md:px-4 pt-2.5 pb-2 cursor-pointer"
        onClick={onToggleExpand}
      >
        {/* Line 1: dot + name + figures + actions + chevron */}
        <div className="flex items-center gap-2 md:gap-3">
          <span className={`w-2 h-2 rounded-full shrink-0 ${dotColor}`} />
          <div className="min-w-0 flex-1">
            <div
              className="font-semibold text-sm text-[var(--text-default)] truncate"
              dir="auto"
            >
              {label}
            </div>
            {subLabel && (
              <div
                className="text-[10px] uppercase tracking-wide text-[var(--text-muted)] truncate"
                dir="auto"
              >
                {subLabel}
              </div>
            )}
          </div>

          <span className="font-bold font-mono text-xs md:text-sm whitespace-nowrap shrink-0" dir="ltr">
            {formatCurrency(spent)}{" "}
            <span className="text-[var(--text-muted)] text-[10px] md:text-xs font-normal">
              / {formatCurrency(total)}
            </span>
          </span>

          <span className="text-[var(--text-muted)] shrink-0">
            {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </span>
        </div>

        {/* Line 2: progress bar (equal length) with the remaining/over amount
            written inside, + actions */}
        <div className="flex items-center gap-2 mt-2">
          <div className="relative flex-1 bg-[var(--surface-light)] rounded-full h-5 overflow-hidden">
            <div
              className={`absolute inset-y-0 start-0 rounded-full ${barColor} transition-all duration-500 ease-out`}
              style={{ width: `${percent}%` }}
            />
            {hint && (
              <span
                className="absolute inset-y-0 end-2 flex items-center text-[10px] font-medium whitespace-nowrap text-white"
                dir="ltr"
              >
                {hint}
              </span>
            )}
          </div>
          {actions && (
            <div className="flex items-center gap-1 shrink-0">{actions}</div>
          )}
        </div>
      </div>

      {isExpanded && children}
    </div>
  );
};
