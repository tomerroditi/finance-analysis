import React from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronUp } from "lucide-react";

interface BudgetProgressBarProps {
  current: number;
  total: number;
  label?: string;
  subLabel?: string;
  onToggleExpand?: () => void;
  isExpanded?: boolean;
  children?: React.ReactNode;
  actions?: React.ReactNode;
  compact?: boolean;
}

export const BudgetProgressBar: React.FC<BudgetProgressBarProps> = ({
  current,
  total,
  label,
  subLabel,
  onToggleExpand,
  isExpanded = false,
  children,
  actions,
  compact = false,
}) => {
  const { t } = useTranslation();
  // Current is usually negative (expenses), convert to positive for display
  const spent = Math.abs(current);
  // Avoid division by zero
  const percent =
    total > 0 ? Math.min((spent / total) * 100, 100) : spent > 0 ? 100 : 0;

  // Determine color
  let colorClass = "bg-emerald-500";
  if (spent > total && total > 0) {
    colorClass = "bg-rose-500";
  } else if (spent > total * 0.9 && total > 0) {
    colorClass = "bg-amber-500";
  } else if (total === 0 && spent > 0) {
    colorClass = "bg-amber-500"; // Unbudgeted spending
  }

  // Status dot color for compact mode
  const dotColor =
    spent > total && total > 0
      ? "bg-rose-500"
      : spent > total * 0.9 && total > 0
        ? "bg-amber-500"
        : total === 0 && spent > 0
          ? "bg-amber-500"
          : "bg-emerald-500";

  if (compact) {
    return (
      <div className="w-full mb-2 py-2 px-3 md:px-4 border border-[var(--surface-light)] rounded-xl bg-[var(--surface)] shadow-sm hover:shadow-md transition-shadow group">
        <div
          className="flex items-center gap-2 md:gap-3 cursor-pointer flex-wrap"
          onClick={onToggleExpand}
        >
          {/* Status dot + label */}
          <span className={`w-2 h-2 rounded-full shrink-0 ${dotColor}`} />
          {label && (
            <span className="font-semibold text-sm text-[var(--text-default)] whitespace-nowrap truncate max-w-[40vw] md:max-w-none">
              {label}
            </span>
          )}

          {/* Progress bar - fills remaining space */}
          <div className="flex-1 min-w-[60px] bg-[var(--surface-light)] rounded-full h-2 overflow-hidden">
            <div
              className={`h-2 rounded-full ${colorClass} transition-all duration-500 ease-out`}
              style={{ width: `${percent}%` }}
            />
          </div>

          {/* Numbers */}
          <span className="font-bold font-mono text-xs md:text-sm whitespace-nowrap">
            {spent.toFixed(0)}{" "}
            <span className="text-[var(--text-muted)] text-[10px] md:text-xs font-normal">
              / {total.toFixed(0)}
            </span>
          </span>

          {/* Actions - always visible on mobile, hover on desktop */}
          {actions && (
            <div className="opacity-100 md:opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1 shrink-0">
              {actions}
            </div>
          )}

          {/* Expand chevron */}
          {onToggleExpand && (
            <span className="text-[var(--text-muted)] shrink-0">
              {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </span>
          )}
        </div>

        {isExpanded && children}
      </div>
    );
  }

  return (
    <div className="w-full mb-4 p-3 md:p-4 border border-[var(--surface-light)] rounded-xl bg-[var(--surface)] shadow-sm hover:shadow-md transition-shadow group">
      <div className="flex flex-wrap justify-between items-center gap-2 mb-3">
        <div className="flex items-center gap-2 md:gap-3 min-w-0">
          {onToggleExpand && (
            <button
              onClick={onToggleExpand}
              className="p-1 rounded-full hover:bg-[var(--surface-light)] text-[var(--text-muted)] transition-colors shrink-0"
            >
              {isExpanded ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
            </button>
          )}
          <div className="min-w-0">
            {label && (
              <div className="font-semibold text-[var(--text-default)] truncate">
                {label}
              </div>
            )}
            {subLabel && (
              <div className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide truncate">
                {subLabel}
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 md:gap-4 shrink-0">
          {actions && (
            <div className="opacity-100 md:opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1 md:gap-2">
              {actions}
            </div>
          )}
          <div className="text-end">
            <div className="font-bold font-mono text-sm md:text-base">
              {spent.toFixed(2)}{" "}
              <span className="text-[var(--text-muted)] text-xs md:text-sm font-normal">
                / {total.toFixed(2)}
              </span>
            </div>
            {onToggleExpand && (
              <button
                onClick={onToggleExpand}
                className="text-xs font-medium text-[var(--primary)] hover:text-[var(--primary-dark)] mt-1 transition-colors"
              >
                {isExpanded ? t("budget.hideTransactions") : t("budget.viewTransactions")}
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="w-full bg-[var(--surface-light)] rounded-full h-2.5 overflow-hidden">
        <div
          className={`h-2.5 rounded-full ${colorClass} transition-all duration-500 ease-out`}
          style={{ width: `${percent}%` }}
        ></div>
      </div>

      {isExpanded && children}
    </div>
  );
};
