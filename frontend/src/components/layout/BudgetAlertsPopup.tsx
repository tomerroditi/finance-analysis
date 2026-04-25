import { useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { AlertTriangle, X } from "lucide-react";
import { formatCurrency } from "../../utils/numberFormatting";
import { useBudgetAlerts } from "../../hooks/useBudgetAlerts";
import { useBudgetAlertDismissals } from "../../hooks/useBudgetAlertDismissals";

interface BudgetAlertsPopupProps {
  isOpen: boolean;
  onClose: () => void;
}

export function BudgetAlertsPopup({ isOpen, onClose }: BudgetAlertsPopupProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data, isLoading } = useBudgetAlerts();
  const { isDismissed, dismiss, dismissAll } = useBudgetAlertDismissals(
    data?.year,
    data?.month,
  );

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  const visibleAlerts = useMemo(
    () => (data?.alerts ?? []).filter((a) => !isDismissed(a.rule_id)),
    [data?.alerts, isDismissed],
  );

  if (!isOpen) return null;

  const handleOpenBudget = () => {
    onClose();
    navigate("/budget");
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 backdrop-blur-sm animate-in fade-in duration-200 modal-overlay pt-16 sm:pt-24 px-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-[calc(100vw-2rem)] sm:max-w-md bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl shadow-2xl animate-in zoom-in-95 duration-200 max-h-[80vh] flex flex-col">
        <div className="flex items-center justify-between px-4 sm:px-6 py-4 border-b border-[var(--surface-light)]">
          <div className="flex items-center gap-2">
            <AlertTriangle size={18} className="text-amber-400" />
            <h2 className="font-semibold text-[var(--text-default)]">
              {t("budgetAlerts.title")}
            </h2>
          </div>
          <button
            onClick={onClose}
            aria-label={t("common.close")}
            className="p-2 rounded-lg hover:bg-[var(--surface-light)] transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-3">
          {isLoading ? (
            <p className="text-sm text-[var(--text-muted)] text-center py-6">
              {t("budgetAlerts.loading")}
            </p>
          ) : visibleAlerts.length === 0 ? (
            <p className="text-sm text-[var(--text-muted)] text-center py-6">
              {t("budgetAlerts.empty")}
            </p>
          ) : (
            visibleAlerts.map((alert) => {
              const percent = Math.min(alert.percentage * 100, 100);
              const isCritical = alert.severity === "critical";
              const colorClass = isCritical ? "bg-rose-500" : "bg-amber-500";
              const badgeClass = isCritical
                ? "bg-rose-500/15 text-rose-400 border-rose-500/30"
                : "bg-amber-500/15 text-amber-400 border-amber-500/30";
              const severityLabel = isCritical
                ? t("budgetAlerts.severityCritical")
                : t("budgetAlerts.severityWarning");
              return (
                <div
                  key={alert.rule_id}
                  className="rounded-xl border border-[var(--surface-light)] bg-[var(--surface-light)]/30 p-3 sm:p-4"
                >
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <div className="min-w-0">
                      <div className="font-semibold text-sm text-[var(--text-default)] truncate">
                        {alert.name || alert.category}
                      </div>
                      <div className="text-xs text-[var(--text-muted)] truncate">
                        {alert.category}
                      </div>
                    </div>
                    <span
                      className={`shrink-0 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md border ${badgeClass}`}
                    >
                      {severityLabel}
                    </span>
                  </div>

                  <div className="w-full bg-[var(--surface-light)] rounded-full h-2 overflow-hidden mb-2">
                    <div
                      className={`h-2 rounded-full ${colorClass} transition-all duration-500 ease-out`}
                      style={{ width: `${percent}%` }}
                    />
                  </div>

                  <div className="flex items-center justify-between text-xs">
                    <span className="text-[var(--text-muted)]">
                      <span dir="ltr">
                        {formatCurrency(alert.spent)} /{" "}
                        {formatCurrency(alert.amount)}
                      </span>
                    </span>
                    <span className="flex items-center gap-2">
                      <span
                        className={`font-bold font-mono ${
                          isCritical ? "text-rose-400" : "text-amber-400"
                        }`}
                        dir="ltr"
                      >
                        {(alert.percentage * 100).toFixed(0)}%
                      </span>
                      <button
                        onClick={() => dismiss(alert.rule_id)}
                        className="text-[var(--text-muted)] hover:text-[var(--text-default)] underline-offset-2 hover:underline transition-colors"
                      >
                        {t("budgetAlerts.dismiss")}
                      </button>
                    </span>
                  </div>
                </div>
              );
            })
          )}
        </div>

        <div className="px-4 sm:px-6 py-3 border-t border-[var(--surface-light)] flex items-center justify-between gap-2">
          <button
            onClick={() => {
              if (visibleAlerts.length === 0) return;
              dismissAll(visibleAlerts.map((a) => a.rule_id));
            }}
            disabled={visibleAlerts.length === 0}
            className="text-xs font-medium text-[var(--text-muted)] hover:text-[var(--text-default)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {t("budgetAlerts.dismissAll")}
          </button>
          <button
            onClick={handleOpenBudget}
            className="text-xs font-medium px-3 py-1.5 rounded-lg bg-[var(--primary)] text-white hover:opacity-90 transition-opacity"
          >
            {t("budgetAlerts.openBudget")}
          </button>
        </div>
      </div>
    </div>
  );
}
