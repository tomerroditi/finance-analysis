import React, { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { AlertTriangle, ChevronDown, ChevronUp, X } from "lucide-react";
import {
  budgetApi,
  type BudgetAlert,
  type BudgetAlertsResponse,
} from "../../services/api";
import { useBudgetAlertDismissals } from "../../hooks/useBudgetAlertDismissals";
import { formatCurrency } from "../../utils/numberFormatting";

interface BudgetAlertsBannerProps {
  year: number;
  month: number;
}

/**
 * In-page budget alerts surfaced at the top of the monthly view. Reuses the
 * dated `/budget/alerts/{year}/{month}` endpoint and the shared per-month
 * dismissal store (same one the sidebar bell/popup use), so dismissing here
 * stays consistent everywhere. Renders nothing when there are no live alerts.
 */
export const BudgetAlertsBanner: React.FC<BudgetAlertsBannerProps> = ({
  year,
  month,
}) => {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(true);
  const { isDismissed, dismiss, dismissAll } = useBudgetAlertDismissals(
    year,
    month,
  );

  const { data } = useQuery<BudgetAlertsResponse>({
    queryKey: ["budgetAlerts", year, month],
    queryFn: () => budgetApi.getMonthAlerts(year, month).then((res) => res.data),
    placeholderData: keepPreviousData,
  });

  const visibleAlerts = useMemo(
    () =>
      (data?.alerts ?? [])
        .filter((a) => !isDismissed(a.rule_id))
        .sort((a, b) => b.percentage - a.percentage),
    [data?.alerts, isDismissed],
  );

  if (visibleAlerts.length === 0) return null;

  const hasCritical = visibleAlerts.some((a) => a.severity === "critical");
  const accent = hasCritical
    ? "border-rose-500/30 bg-rose-500/10"
    : "border-amber-500/30 bg-amber-500/10";
  const iconColor = hasCritical ? "text-rose-400" : "text-amber-400";

  return (
    <div className={`rounded-2xl border ${accent}`}>
      <div className="flex items-center justify-between gap-2 px-4 py-3">
        <button
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center gap-2 min-w-0 text-start"
        >
          <AlertTriangle size={18} className={`${iconColor} shrink-0`} />
          <span className="font-semibold text-sm text-[var(--text-default)]">
            {t("budgetAlerts.summary", { count: visibleAlerts.length })}
          </span>
          <span className="text-[var(--text-muted)] shrink-0">
            {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </span>
        </button>
        <button
          onClick={() => dismissAll(visibleAlerts.map((a) => a.rule_id))}
          className="shrink-0 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--text-default)] transition-colors"
        >
          {t("budgetAlerts.dismissAll")}
        </button>
      </div>

      {expanded && (
        <div className="px-3 pb-3 space-y-2 animate-in fade-in duration-200">
          {visibleAlerts.map((alert: BudgetAlert) => {
            const isCritical = alert.severity === "critical";
            const pctColor = isCritical ? "text-rose-400" : "text-amber-400";
            const dotColor = isCritical ? "bg-rose-500" : "bg-amber-500";
            return (
              <div
                key={alert.rule_id}
                className="flex items-center justify-between gap-3 rounded-xl border border-[var(--surface-light)] bg-[var(--surface)] px-3 py-2"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotColor}`} />
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
                  <span className={`font-bold font-mono text-sm ${pctColor}`} dir="ltr">
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
        </div>
      )}
    </div>
  );
};
