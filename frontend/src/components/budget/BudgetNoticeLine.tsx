import React, { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { AlertTriangle, ChevronDown, ChevronUp, X } from "lucide-react";
import {
  budgetApi,
  type BudgetAlert,
  type BudgetAlertsResponse,
  type CategoryConflict,
} from "../../services/api";
import { useBudgetAlertDismissals } from "../../hooks/useBudgetAlertDismissals";
import { useBudgetAlertSettings } from "../../hooks/useBudgetAlertSettings";
import { formatCurrency } from "../../utils/numberFormatting";
import { useQueryKeys } from "../../hooks/useQueryKeys";

interface BudgetNoticeLineProps {
  /** Alerts are per-month; omit on the yearly and project tabs. */
  year?: number;
  month?: number;
  /** Set when this month's rules were auto-filled from an earlier month. */
  copiedFrom?: string | null;
  onDismissCopied?: () => void;
}

/**
 * One line for everything the page wants to warn about.
 *
 * Alerts, the auto-copy notice and category conflicts each used to own a
 * full-width bar with its own dismiss control; stacked on a bad day they
 * pushed the budget itself below the fold. Here they collapse into a row of
 * severity chips that expands to the detail.
 *
 * The severe data-freshness banner is deliberately NOT merged in: it is rare,
 * it means the figures on screen are materially wrong, and it earns the
 * interruption. See BudgetFreshnessBanner.
 */
export const BudgetNoticeLine: React.FC<BudgetNoticeLineProps> = ({
  year,
  month,
  copiedFrom,
  onDismissCopied,
}) => {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const [conflictsDismissed, setConflictsDismissed] = useState(false);
  const { enabled, threshold } = useBudgetAlertSettings();
  const qk = useQueryKeys();
  const { isDismissed, dismiss, dismissAll } = useBudgetAlertDismissals(
    year ?? 0,
    month ?? 0,
  );

  const { data: alertData } = useQuery<BudgetAlertsResponse>({
    queryKey: qk.budget.alertsMonth(year ?? 0, month ?? 0, threshold),
    queryFn: () =>
      budgetApi.getMonthAlerts(year as number, month as number, threshold).then((res) => res.data),
    placeholderData: keepPreviousData,
    enabled: enabled && year !== undefined && month !== undefined,
  });

  const { data: conflicts } = useQuery({
    queryKey: qk.budget.categoryConflicts(),
    queryFn: () =>
      budgetApi.getCategoryConflicts().then((r) => r.data.conflicts as CategoryConflict[]),
  });

  const alerts = useMemo(
    () =>
      (alertData?.alerts ?? [])
        .filter((a) => !isDismissed(a.rule_id))
        .sort((a, b) => b.percentage - a.percentage),
    [alertData?.alerts, isDismissed],
  );

  const activeConflicts = conflictsDismissed ? [] : (conflicts ?? []);
  const conflictNames = activeConflicts.map((c) => c.category).join(", ");

  const showAlerts = enabled && alerts.length > 0;
  if (!showAlerts && !activeConflicts.length && !copiedFrom) return null;

  const hasCritical = alerts.some((a) => a.severity === "critical");
  const accent = hasCritical
    ? "border-rose-500/30 bg-rose-500/10"
    : "border-amber-500/30 bg-amber-500/10";

  const chip = (tone: "bad" | "warn" | "muted") =>
    `text-[10px] sm:text-xs font-medium px-2.5 py-1 rounded-full border ${
      tone === "bad"
        ? "border-rose-500/40 bg-rose-500/10 text-rose-400"
        : tone === "warn"
          ? "border-amber-500/40 bg-amber-500/10 text-amber-400"
          : "border-[var(--surface-light)] text-[var(--text-muted)]"
    }`;

  return (
    <div className={`rounded-2xl border ${accent}`}>
      <div className="flex items-center justify-between gap-2 px-3 py-2">
        <button
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          className="flex items-center gap-2 min-w-0 flex-wrap py-1 text-start"
        >
          <AlertTriangle
            size={16}
            className={`shrink-0 ${hasCritical ? "text-rose-400" : "text-amber-400"}`}
          />
          {showAlerts && (
            <span className={chip(hasCritical ? "bad" : "warn")}>
              {t("budgetAlerts.summary", { count: alerts.length })}
            </span>
          )}
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

        {showAlerts && (
          <button
            onClick={() => dismissAll(alerts.map((a) => a.rule_id))}
            className="shrink-0 py-2 -my-2 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--text-default)] transition-colors"
          >
            {t("budgetAlerts.dismissAll")}
          </button>
        )}
      </div>

      {expanded && (
        <div className="px-3 pb-3 space-y-2 animate-in fade-in duration-200">
          {alerts.map((alert: BudgetAlert) => {
            const isCritical = alert.severity === "critical";
            return (
              <div
                key={alert.rule_id}
                className="flex items-center justify-between gap-3 rounded-xl border border-[var(--surface-light)] bg-[var(--surface)] px-3 py-2"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span
                    className={`w-1.5 h-1.5 rounded-full shrink-0 ${isCritical ? "bg-rose-500" : "bg-amber-500"}`}
                  />
                  <span
                    className="font-semibold text-sm text-[var(--text-default)] truncate"
                    dir="auto"
                  >
                    {alert.name || alert.category}
                  </span>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <span className="text-xs text-[var(--text-muted)]" dir="ltr">
                    {formatCurrency(alert.spent)} / {formatCurrency(alert.amount)}
                  </span>
                  <span
                    className={`font-bold font-mono text-sm ${isCritical ? "text-rose-400" : "text-amber-400"}`}
                    dir="ltr"
                  >
                    {(alert.percentage * 100).toFixed(0)}%
                  </span>
                  <button
                    onClick={() => dismiss(alert.rule_id)}
                    aria-label={t("budgetAlerts.dismiss")}
                    className="p-1.5 rounded-md text-[var(--text-muted)] hover:text-[var(--text-default)] hover:bg-[var(--surface-light)] transition-colors"
                  >
                    <X size={14} />
                  </button>
                </div>
              </div>
            );
          })}

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
