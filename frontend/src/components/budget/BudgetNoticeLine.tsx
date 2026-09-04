import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ChevronDown, ChevronUp, X } from "lucide-react";
import { budgetApi, type CategoryConflict } from "../../services/api";
import { useQueryKeys } from "../../hooks/useQueryKeys";

interface BudgetNoticeLineProps {
  /** Set when this month's rules were auto-filled from an earlier month. */
  copiedFrom?: string | null;
  onDismissCopied?: () => void;
}

/**
 * One line for everything the page wants to warn about.
 *
 * The auto-copy notice and category conflicts each used to own a full-width
 * bar with its own dismiss control; stacked they pushed the budget itself
 * below the fold. Here they collapse into a row of chips that expands to the
 * detail.
 *
 * Over-budget alerts are deliberately NOT here. Every rule row already carries
 * a red dot, its own over-by figure and a >100% percentage, so a banner
 * restating "1 budget needs attention" only pushed those rows further down.
 * The bell in the app shell (BudgetAlertsPopup) remains the cross-page surface
 * for them.
 */
export const BudgetNoticeLine: React.FC<BudgetNoticeLineProps> = ({
  copiedFrom,
  onDismissCopied,
}) => {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const [conflictsDismissed, setConflictsDismissed] = useState(false);
  const qk = useQueryKeys();

  const { data: conflicts } = useQuery({
    queryKey: qk.budget.categoryConflicts(),
    queryFn: () =>
      budgetApi.getCategoryConflicts().then((r) => r.data.conflicts as CategoryConflict[]),
  });

  const activeConflicts = conflictsDismissed ? [] : (conflicts ?? []);
  const conflictNames = activeConflicts.map((c) => c.category).join(", ");

  if (!activeConflicts.length && !copiedFrom) return null;

  const chip = (tone: "warn" | "muted") =>
    `text-[10px] sm:text-xs font-medium px-2.5 py-1 rounded-full border ${
      tone === "warn"
        ? "border-amber-500/40 bg-amber-500/10 text-amber-400"
        : "border-[var(--surface-light)] text-[var(--text-muted)]"
    }`;

  return (
    <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10">
      <div className="flex items-center justify-between gap-2 px-3 py-2">
        <button
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          className="flex items-center gap-2 min-w-0 flex-wrap py-1 text-start"
        >
          <AlertTriangle size={16} className="shrink-0 text-amber-400" />
          {activeConflicts.length > 0 && (
            <span className={chip("warn")} dir="auto">
              {t("budget.categoryConflict.chip", { names: conflictNames })}
            </span>
          )}
          {copiedFrom && (
            <span className={chip("muted")} dir="auto">
              {t("budget.notices.copiedChip", { month: copiedFrom })}
            </span>
          )}
          <span className="text-[var(--text-muted)] shrink-0">
            {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </span>
        </button>
      </div>

      {expanded && (
        <div className="px-3 pb-3 space-y-2 animate-in fade-in duration-200">
          {activeConflicts.length > 0 && (
            <div className="flex items-start gap-2 rounded-xl border border-[var(--surface-light)] bg-[var(--surface)] px-3 py-2 text-sm">
              <span dir="auto">
                {t("budget.categoryConflict.banner", { names: conflictNames })}
              </span>
              <button
                onClick={() => setConflictsDismissed(true)}
                aria-label={t("common.dismiss")}
                className="ms-auto shrink-0 text-[var(--text-muted)] hover:text-[var(--text-default)]"
              >
                <X size={16} />
              </button>
            </div>
          )}

          {copiedFrom && (
            <div className="flex items-start gap-2 rounded-xl border border-[var(--surface-light)] bg-[var(--surface)] px-3 py-2 text-sm">
              <span dir="auto">{t("budget.rulesCopiedFrom", { month: copiedFrom })}</span>
              {onDismissCopied && (
                <button
                  onClick={onDismissCopied}
                  aria-label={t("common.dismiss")}
                  className="ms-auto shrink-0 text-[var(--text-muted)] hover:text-[var(--text-default)]"
                >
                  <X size={16} />
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
