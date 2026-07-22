import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { ArrowLeftRight, ChevronRight, ChevronLeft } from "lucide-react";
import {
  pendingRefundsApi,
  type PendingRefund,
} from "../../services/api";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { useAppStore } from "../../stores/appStore";
import { Skeleton } from "../common/Skeleton";
import { formatCurrency } from "../../utils/numberFormatting";

const isOpenStatus = (s: PendingRefund["status"]) =>
  s === "pending" || s === "partial";

/** Dashboard refunds overview: money owed back, recovery progress, and the
 *  open refund requests that still need attention. */
export function RefundsCard() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const qk = useQueryKeys();
  const setSelectedService = useAppStore((s) => s.setSelectedService);
  const isRtl = i18n.language === "he";

  const { data: refunds, isLoading } = useQuery({
    queryKey: qk.pendingRefunds.all(),
    queryFn: () => pendingRefundsApi.getAll().then((res) => res.data),
  });

  const { data: refundSources } = useQuery({
    queryKey: qk.pendingRefunds.sources(),
    queryFn: () => pendingRefundsApi.getRefundSources().then((res) => res.data),
  });

  const stats = useMemo(() => {
    const all = refunds ?? [];
    const open = all
      .filter((r) => isOpenStatus(r.status))
      .sort((a, b) => (b.date ?? "").localeCompare(a.date ?? ""));
    const outstanding = open.reduce(
      (sum, r) => sum + (r.remaining ?? r.expected_amount),
      0,
    );
    const received = all.reduce((sum, r) => sum + (r.total_refunded ?? 0), 0);
    const available = (refundSources ?? []).reduce(
      (sum, s) => sum + (s.available ?? 0),
      0,
    );
    const total = outstanding + received;
    return {
      open,
      outstanding,
      received,
      available,
      recoveredPct: total > 0 ? Math.min(100, (received / total) * 100) : 0,
    };
  }, [refunds, refundSources]);

  const goToRefunds = () => {
    setSelectedService("refunds");
    navigate("/transactions");
  };

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] p-4 md:p-6">
      <div className="flex items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-amber-500/15 text-amber-400">
            <ArrowLeftRight size={16} />
          </div>
          <p className="text-sm md:text-base font-bold">
            {t("dashboard.refundsCard.title")}
          </p>
        </div>
        <button
          onClick={goToRefunds}
          className="flex items-center gap-0.5 text-xs md:text-sm font-medium text-[var(--primary)] hover:opacity-80 transition-opacity"
        >
          {t("dashboard.refundsCard.viewAll")}
          {isRtl ? <ChevronLeft size={14} /> : <ChevronRight size={14} />}
        </button>
      </div>

      {isLoading ? (
        <Skeleton variant="card" className="h-32" />
      ) : !refunds || refunds.length === 0 ? (
        <p className="text-[var(--text-muted)] text-sm py-6 text-center">
          {t("dashboard.refundsCard.empty")}
        </p>
      ) : (
        <>
          {/* KPI trio */}
          <div className="grid grid-cols-3 gap-2 mb-3">
            <div className="min-w-0">
              <p className="text-base md:text-lg font-bold text-amber-400 truncate">
                {formatCurrency(stats.outstanding)}
              </p>
              <p className="text-[10px] uppercase tracking-wide text-[var(--text-muted)] truncate">
                {t("dashboard.refundsCard.owed")}
              </p>
            </div>
            <div className="min-w-0">
              <p className="text-base md:text-lg font-bold text-emerald-400 truncate">
                {formatCurrency(stats.received)}
              </p>
              <p className="text-[10px] uppercase tracking-wide text-[var(--text-muted)] truncate">
                {t("dashboard.refundsCard.received")}
              </p>
            </div>
            <div className="min-w-0">
              <p className="text-base md:text-lg font-bold text-blue-400 truncate">
                {formatCurrency(stats.available)}
              </p>
              <p className="text-[10px] uppercase tracking-wide text-[var(--text-muted)] truncate">
                {t("dashboard.refundsCard.unallocated")}
              </p>
            </div>
          </div>

          {/* Recovery progress */}
          <div className="mb-4">
            <div className="h-1.5 rounded-full bg-[var(--surface-light)] overflow-hidden">
              <div
                className="h-full rounded-full bg-emerald-400 transition-all"
                style={{ width: `${stats.recoveredPct}%` }}
              />
            </div>
            <p className="text-[10.5px] text-[var(--text-muted)] mt-1">
              {t("dashboard.refundsCard.recoveredOf", {
                received: formatCurrency(stats.received),
                total: formatCurrency(stats.received + stats.outstanding),
              })}
            </p>
          </div>

          {/* Open requests */}
          {stats.open.length === 0 ? (
            <p className="text-[var(--text-muted)] text-xs py-3 text-center">
              {t("dashboard.refundsCard.allSettled")}
            </p>
          ) : (
            <div className="space-y-1">
              <p className="text-[10px] uppercase tracking-wide text-[var(--text-muted)] font-semibold mb-1.5">
                {t("dashboard.refundsCard.openRequests", {
                  count: stats.open.length,
                })}
              </p>
              {stats.open.slice(0, 5).map((item) => {
                const refunded = item.total_refunded ?? 0;
                const pct =
                  item.expected_amount > 0
                    ? Math.min(100, (refunded / item.expected_amount) * 100)
                    : 0;
                return (
                  <button
                    key={item.id}
                    onClick={goToRefunds}
                    className="w-full flex items-center gap-2.5 py-1.5 px-2 -mx-2 rounded-lg hover:bg-[var(--surface-light)]/40 transition-colors text-start"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium truncate" dir="auto">
                        {item.description ||
                          t("transactions.refunds.unknownExpense")}
                      </p>
                      <div className="h-[3px] rounded-full bg-[var(--surface-light)] overflow-hidden mt-1">
                        <div
                          className="h-full rounded-full bg-amber-400"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                    <span
                      className="text-xs shrink-0 whitespace-nowrap"
                      dir="ltr"
                      data-testid="card-refund-remaining"
                    >
                      <span className="font-semibold text-amber-400">
                        {formatCurrency(item.remaining ?? item.expected_amount)}
                      </span>
                      <span className="text-[10.5px] text-[var(--text-muted)]">
                        {" / "}
                        {formatCurrency(item.expected_amount)}
                      </span>
                    </span>
                  </button>
                );
              })}
              {stats.open.length > 5 && (
                <button
                  onClick={goToRefunds}
                  className="w-full text-[11px] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors py-1"
                >
                  {t("dashboard.refundsCard.moreCount", {
                    count: stats.open.length - 5,
                  })}
                </button>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
