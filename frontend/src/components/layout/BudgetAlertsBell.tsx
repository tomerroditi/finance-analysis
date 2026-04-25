import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Bell } from "lucide-react";
import { BudgetAlertsPopup } from "./BudgetAlertsPopup";
import { useBudgetAlerts } from "../../hooks/useBudgetAlerts";
import { useBudgetAlertDismissals } from "../../hooks/useBudgetAlertDismissals";

interface BudgetAlertsBellProps {
  variant?: "sidebar" | "compact";
  expanded?: boolean;
}

export function BudgetAlertsBell({
  variant = "sidebar",
  expanded = true,
}: BudgetAlertsBellProps) {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const { data } = useBudgetAlerts();
  const { isDismissed } = useBudgetAlertDismissals(data?.year, data?.month);

  const visibleCount = useMemo(
    () => (data?.alerts ?? []).filter((a) => !isDismissed(a.rule_id)).length,
    [data?.alerts, isDismissed],
  );

  const baseClasses =
    variant === "compact"
      ? "p-1.5 -ms-1.5 rounded-lg hover:bg-[var(--surface-light)] transition-colors"
      : `relative flex items-center gap-3 px-4 py-3 rounded-lg transition-all w-full text-[var(--text-muted)] hover:bg-[var(--surface-light)] hover:text-white`;

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className={`relative ${baseClasses}`}
        aria-label={t("budgetAlerts.title")}
      >
        <Bell size={variant === "compact" ? 20 : 20} />
        {variant === "sidebar" && expanded && (
          <span className="text-sm font-medium">{t("budgetAlerts.title")}</span>
        )}
        {visibleCount > 0 && (
          <span className="absolute -top-1 -end-1 min-w-[18px] h-[18px] flex items-center justify-center rounded-full bg-rose-500 text-white text-[10px] font-bold px-1">
            {visibleCount > 99 ? "99+" : visibleCount}
          </span>
        )}
      </button>
      <BudgetAlertsPopup isOpen={isOpen} onClose={() => setIsOpen(false)} />
    </>
  );
}
