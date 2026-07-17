import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Repeat } from "lucide-react";
import { analyticsApi, type RecurringItem } from "../../services/api";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { Skeleton } from "../common/Skeleton";
import { formatCurrency } from "../../utils/numberFormatting";
import { formatDate } from "../../utils/dateFormatting";

const STATUS_STYLES: Record<RecurringItem["status"], string> = {
  active: "bg-[var(--surface-light)] text-[var(--text-muted)]",
  new: "bg-blue-500/15 text-blue-300",
  price_changed: "bg-amber-500/15 text-amber-300",
  ended: "bg-rose-500/15 text-rose-300",
};

/** Dashboard subscriptions / recurring-charges panel from ``/analytics/recurring``. */
export function RecurringSection() {
  const { t } = useTranslation();
  const qk = useQueryKeys();

  const { data, isLoading } = useQuery({
    queryKey: qk.analytics.recurring(),
    queryFn: async () => {
      const res = await analyticsApi.getRecurring();
      return res.data;
    },
  });

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] p-4 md:p-6">
      <div className="flex items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-[var(--primary)]/15 text-[var(--primary)]">
            <Repeat size={16} />
          </div>
          <p className="text-sm md:text-base font-bold">{t("dashboard.recurring.title")}</p>
        </div>
        {!!data && data.items.length > 0 && (
          <div className="text-end">
            <p className="text-[10px] md:text-xs text-[var(--text-muted)]">{t("dashboard.recurring.totalMonthly")}</p>
            <p dir="ltr" className="text-sm md:text-base font-bold text-start">{formatCurrency(data.total_monthly)}</p>
          </div>
        )}
      </div>

      {isLoading ? (
        <Skeleton variant="card" className="h-40" />
      ) : !data || data.items.length === 0 ? (
        <p className="text-[var(--text-muted)] text-sm py-6 text-center">{t("dashboard.recurring.empty")}</p>
      ) : (
        <div className="space-y-1.5 max-h-[360px] overflow-y-auto pe-1">
          {data.items.map((item) => (
            <div
              key={item.normalized}
              className={`flex items-center gap-2 py-2 px-2.5 rounded-lg hover:bg-[var(--surface-light)]/40 transition-colors ${
                item.status === "ended" ? "opacity-60" : ""
              }`}
            >
              <div className="min-w-0 flex-1">
                <p className="text-xs md:text-sm font-medium truncate" dir="auto" title={item.label}>{item.label}</p>
                <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                  <span className="text-[9px] md:text-[10px] px-1.5 py-0.5 rounded bg-[var(--surface-light)] text-[var(--text-muted)]">
                    {t(`dashboard.recurring.cadence.${item.cadence}`)}
                  </span>
                  {item.status !== "active" && (
                    <span className={`text-[9px] md:text-[10px] px-1.5 py-0.5 rounded ${STATUS_STYLES[item.status]}`}>
                      {t(`dashboard.recurring.status.${item.status}`)}
                    </span>
                  )}
                  {item.status !== "ended" && (
                    <span className="text-[9px] md:text-[10px] text-[var(--text-muted)]">
                      {t("dashboard.recurring.next", { date: formatDate(item.next_expected_date) })}
                    </span>
                  )}
                </div>
              </div>
              <div className="text-end shrink-0">
                <p dir="ltr" className="text-xs md:text-sm font-bold tabular-nums">{formatCurrency(item.amount)}</p>
                <p className="text-[9px] md:text-[10px] text-[var(--text-muted)]">
                  {t("dashboard.recurring.perMonth", { amount: formatCurrency(item.monthly_equivalent) })}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
