import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Check, Eye, EyeOff, Repeat, RotateCcw, X } from "lucide-react";
import {
  analyticsApi,
  type RecurringDecisionInput,
  type RecurringItem,
} from "../../services/api";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { qkPrefix } from "../../services/queryKeys";
import { Skeleton } from "../common/Skeleton";
import { formatCurrency } from "../../utils/numberFormatting";
import { formatDate } from "../../utils/dateFormatting";

const STATUS_STYLES: Record<RecurringItem["status"], string> = {
  active: "bg-[var(--surface-light)] text-[var(--text-muted)]",
  new: "bg-blue-500/15 text-blue-300",
  price_changed: "bg-amber-500/15 text-amber-300",
  ended: "bg-rose-500/15 text-rose-300",
};

/**
 * Dashboard subscriptions / recurring-charges panel from ``/analytics/recurring``.
 *
 * Detection is a heuristic, so nothing it finds is treated as a real
 * commitment until the user says so: candidates land in a "needs review"
 * block at the top and only move into the list — and into the monthly total,
 * the budget Overview's committed spend and the forecast — once confirmed.
 */
export function RecurringSection() {
  const { t } = useTranslation();
  const qk = useQueryKeys();
  const queryClient = useQueryClient();
  const [showDismissed, setShowDismissed] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: qk.analytics.recurring(showDismissed),
    queryFn: async () => {
      const res = await analyticsApi.getRecurring(showDismissed);
      return res.data;
    },
  });

  const decide = useMutation({
    mutationFn: (decisions: RecurringDecisionInput[]) =>
      analyticsApi.setRecurringDecisions(decisions),
    // A verdict moves money between "committed" and "free to spend", so the
    // budget Overview and every analytics figure built on recurring charges
    // have to be refetched alongside this panel.
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.analytics });
      queryClient.invalidateQueries({ queryKey: qkPrefix.budget });
    },
  });

  const items = data?.items ?? [];
  const pending = items.filter((item) => item.confirmation === "pending");
  const confirmed = items.filter((item) => item.confirmation === "confirmed");
  const dismissed = items.filter((item) => item.confirmation === "dismissed");
  const isEmpty = items.length === 0;

  const decideOne = (item: RecurringItem, decision: RecurringDecisionInput["decision"]) =>
    decide.mutate([{ normalized: item.normalized, decision }]);

  const decideAll = (
    group: RecurringItem[],
    decision: RecurringDecisionInput["decision"],
  ) =>
    decide.mutate(
      group.map((item) => ({ normalized: item.normalized, decision })),
    );

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] p-4 md:p-6">
      <div className="flex items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-[var(--primary)]/15 text-[var(--primary)]">
            <Repeat size={16} />
          </div>
          <p className="text-sm md:text-base font-bold">{t("dashboard.recurring.title")}</p>
        </div>
        {!!data && confirmed.length > 0 && (
          <div className="text-end">
            <p className="text-[10px] md:text-xs text-[var(--text-muted)]">{t("dashboard.recurring.totalMonthly")}</p>
            <p dir="ltr" className="text-sm md:text-base font-bold text-start">{formatCurrency(data.total_monthly)}</p>
          </div>
        )}
      </div>

      {isLoading ? (
        <Skeleton variant="card" className="h-40" />
      ) : isEmpty ? (
        <p className="text-[var(--text-muted)] text-sm py-6 text-center">{t("dashboard.recurring.empty")}</p>
      ) : (
        <div className="space-y-4">
          {pending.length > 0 && (
            <section
              aria-label={t("dashboard.recurring.review.title")}
              className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-2.5"
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <div className="min-w-0">
                  <p className="text-xs md:text-sm font-bold text-amber-300">
                    {t("dashboard.recurring.review.title")}
                  </p>
                  <p className="text-[10px] md:text-xs text-[var(--text-muted)]">
                    {t("dashboard.recurring.review.subtitle", {
                      count: pending.length,
                      amount: formatCurrency(data?.pending_monthly ?? 0),
                    })}
                  </p>
                </div>
                <button
                  type="button"
                  disabled={decide.isPending}
                  onClick={() => decideAll(pending, "confirmed")}
                  className="shrink-0 text-[10px] md:text-xs px-2 py-1 rounded-lg bg-[var(--primary)]/15 text-[var(--primary)] hover:bg-[var(--primary)]/25 disabled:opacity-50 transition-colors"
                >
                  {t("dashboard.recurring.review.confirmAll")}
                </button>
              </div>

              {/* Capped so a long backlog of candidates cannot push the
                  confirmed charges out of the card's own scroll view. */}
              <div className="space-y-1.5 max-h-[220px] overflow-y-auto pe-1">
                {pending.map((item) => (
                  <div
                    key={item.normalized}
                    data-testid="recurring-pending-item"
                    className="flex items-center gap-2 py-2 px-2.5 rounded-lg bg-[var(--surface)]"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-xs md:text-sm font-medium truncate" dir="auto" title={item.label}>
                        {item.label}
                      </p>
                      <p className="text-[9px] md:text-[10px] text-[var(--text-muted)]">
                        {t("dashboard.recurring.review.evidence", {
                          cadence: t(`dashboard.recurring.cadence.${item.cadence}`),
                          count: item.occurrences,
                          amount: formatCurrency(item.amount),
                        })}
                      </p>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        type="button"
                        disabled={decide.isPending}
                        aria-label={t("dashboard.recurring.review.confirm", { label: item.label })}
                        title={t("dashboard.recurring.review.confirm", { label: item.label })}
                        onClick={() => decideOne(item, "confirmed")}
                        className="p-2 rounded-lg bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25 disabled:opacity-50 transition-colors"
                      >
                        <Check size={16} />
                      </button>
                      <button
                        type="button"
                        disabled={decide.isPending}
                        aria-label={t("dashboard.recurring.review.dismiss", { label: item.label })}
                        title={t("dashboard.recurring.review.dismiss", { label: item.label })}
                        onClick={() => decideOne(item, "dismissed")}
                        className="p-2 rounded-lg bg-rose-500/15 text-rose-300 hover:bg-rose-500/25 disabled:opacity-50 transition-colors"
                      >
                        <X size={16} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {confirmed.length === 0 && pending.length > 0 ? (
            <p className="text-[var(--text-muted)] text-xs py-2 text-center">
              {t("dashboard.recurring.noneConfirmed")}
            </p>
          ) : (
            <div className="space-y-1.5 max-h-[360px] overflow-y-auto pe-1">
              {confirmed.map((item) => (
                <div
                  key={item.normalized}
                  data-testid="recurring-confirmed-item"
                  className={`group flex items-center gap-2 py-2 px-2.5 rounded-lg hover:bg-[var(--surface-light)]/40 transition-colors ${
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
                  <button
                    type="button"
                    disabled={decide.isPending}
                    aria-label={t("dashboard.recurring.review.unconfirm", { label: item.label })}
                    title={t("dashboard.recurring.review.unconfirm", { label: item.label })}
                    onClick={() => decideOne(item, "pending")}
                    className="shrink-0 p-2 rounded-lg text-[var(--text-muted)] hover:bg-[var(--surface-light)] md:opacity-0 md:group-hover:opacity-100 md:focus:opacity-100 disabled:opacity-50 transition-opacity"
                  >
                    <RotateCcw size={16} />
                  </button>
                </div>
              ))}
            </div>
          )}

          {showDismissed && dismissed.length > 0 && (
            <div className="space-y-1.5 border-t border-[var(--surface-light)] pt-2">
              {dismissed.map((item) => (
                <div
                  key={item.normalized}
                  data-testid="recurring-dismissed-item"
                  className="flex items-center gap-2 py-2 px-2.5 rounded-lg opacity-60"
                >
                  <p className="text-xs md:text-sm font-medium truncate flex-1" dir="auto" title={item.label}>
                    {item.label}
                  </p>
                  <button
                    type="button"
                    disabled={decide.isPending}
                    onClick={() => decideOne(item, "pending")}
                    className="shrink-0 text-[10px] md:text-xs px-2 py-1 rounded-lg bg-[var(--surface-light)] hover:bg-[var(--surface-light)]/70 disabled:opacity-50 transition-colors"
                  >
                    {t("dashboard.recurring.review.restore")}
                  </button>
                </div>
              ))}
            </div>
          )}

          {(showDismissed || (data?.dismissed_count ?? 0) > 0) && (
            <button
              type="button"
              onClick={() => setShowDismissed((shown) => !shown)}
              className="flex items-center gap-1.5 text-[10px] md:text-xs text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
            >
              {showDismissed ? <EyeOff size={12} /> : <Eye size={12} />}
              {showDismissed
                ? t("dashboard.recurring.review.hideDismissed")
                : t("dashboard.recurring.review.showDismissed", {
                    count: data?.dismissed_count ?? 0,
                  })}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
