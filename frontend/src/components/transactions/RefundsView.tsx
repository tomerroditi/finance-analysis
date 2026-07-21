import React, { useState, useMemo } from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import {
  ArrowLeftRight,
  CheckCircle2,
  CircleDashed,
  Coins,
  Landmark,
  Link2,
  Calendar,
  CreditCard,
  Receipt,
  Search,
  X,
  Lock,
  Unlink,
  Users,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatCurrency } from "../../utils/numberFormatting";
import {
  pendingRefundsApi,
  type PendingRefund,
  type RefundSource,
} from "../../services/api";
import { humanizeProvider, humanizeService } from "../../utils/textFormatting";
import { LinkRefundModal } from "../modals/LinkRefundModal";
import { useConfirm } from "../../context/DialogContext";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { qkPrefix } from "../../services/queryKeys";

type StatusFilter = "all" | "active" | "resolved" | "closed";
type ViewMode = "expenses" | "sources";

const txKey = (source: string, id: number | string) => `${source}_${id}`;

const RefundsView: React.FC = () => {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const qk = useQueryKeys();
  const confirm = useConfirm();
  const [linkingRefund, setLinkingRefund] = useState<PendingRefund | null>(null);
  const [linkingSource, setLinkingSource] = useState<RefundSource | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [viewMode, setViewMode] = useState<ViewMode>("expenses");

  const { data: refunds, isLoading } = useQuery({
    queryKey: qk.pendingRefunds.all(),
    queryFn: () => pendingRefundsApi.getAll().then((res) => res.data),
  });

  const { data: refundSources } = useQuery({
    queryKey: qk.pendingRefunds.sources(),
    queryFn: () => pendingRefundsApi.getRefundSources().then((res) => res.data),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: qkPrefix.pendingRefunds });
    queryClient.invalidateQueries({ queryKey: qkPrefix.budget });
    queryClient.invalidateQueries({ queryKey: qkPrefix.transactions });
  };

  const closeMutation = useMutation({
    mutationFn: (id: number) => pendingRefundsApi.close(id),
    onSuccess: invalidate,
  });

  const cancelMutation = useMutation({
    mutationFn: (id: number) => pendingRefundsApi.cancel(id),
    onSuccess: invalidate,
  });

  const unlinkMutation = useMutation({
    mutationFn: (linkId: number) => pendingRefundsApi.unlinkRefund(linkId),
    onSuccess: invalidate,
  });

  // How many pending refunds each refund transaction funds — powers the
  // "shared source" badges.
  const sharedCountMap = useMemo(() => {
    const map = new Map<string, number>();
    refundSources?.forEach((src) => {
      map.set(
        txKey(src.refund_source, src.refund_transaction_id),
        src.allocations.length,
      );
    });
    return map;
  }, [refundSources]);

  const summary = useMemo(() => {
    const all = refunds ?? [];
    const active = all.filter(
      (r) => r.status === "pending" || r.status === "partial",
    );
    const outstanding = active.reduce(
      (sum, r) => sum + (r.remaining ?? r.expected_amount),
      0,
    );
    const received = all.reduce((sum, r) => sum + (r.total_refunded ?? 0), 0);
    const availableInSources = (refundSources ?? []).reduce(
      (sum, s) => sum + (s.available ?? 0),
      0,
    );
    return { activeCount: active.length, outstanding, received, availableInSources };
  }, [refunds, refundSources]);

  const filteredRefunds = useMemo(() => {
    let list = refunds ?? [];
    if (statusFilter === "active") {
      list = list.filter((r) => r.status === "pending" || r.status === "partial");
    } else if (statusFilter === "resolved") {
      list = list.filter((r) => r.status === "resolved");
    } else if (statusFilter === "closed") {
      list = list.filter((r) => r.status === "closed");
    }
    const query = searchQuery.trim().toLowerCase();
    if (query) {
      list = list.filter((r) =>
        [
          r.description,
          r.notes,
          r.account_name,
          r.provider,
          r.category,
          r.tag,
          ...(r.links?.map((l) => l.description) ?? []),
        ].some((field) => field?.toLowerCase().includes(query)),
      );
    }
    const sorter = (a: PendingRefund, b: PendingRefund) => {
      const da = a.date ? new Date(a.date).getTime() : 0;
      const db = b.date ? new Date(b.date).getTime() : 0;
      return db - da;
    };
    return {
      active: list
        .filter((r) => r.status !== "resolved" && r.status !== "closed")
        .sort(sorter),
      completed: list
        .filter((r) => r.status === "resolved" || r.status === "closed")
        .sort(sorter),
    };
  }, [refunds, statusFilter, searchQuery]);

  const filteredSources = useMemo(() => {
    let list = refundSources ?? [];
    const query = searchQuery.trim().toLowerCase();
    if (query) {
      list = list.filter((s) =>
        [
          s.description,
          s.account_name,
          s.provider,
          ...s.allocations.map((a) => a.pending_description),
        ].some((field) => field?.toLowerCase().includes(query)),
      );
    }
    return list;
  }, [refundSources, searchQuery]);

  if (isLoading) {
    return (
      <div className="p-4 md:p-8 text-center text-[var(--text-muted)]">
        {t("transactions.refunds.loading")}
      </div>
    );
  }

  const handleUnlink = async (linkId: number) => {
    const ok = await confirm({
      title: t("transactions.refunds.unlink"),
      message: t("transactions.refunds.confirmUnlink"),
      confirmLabel: t("transactions.refunds.unlink"),
      isDestructive: true,
    });
    if (ok) unlinkMutation.mutate(linkId);
  };

  const statusChip = (status: PendingRefund["status"]) => {
    const styles: Record<PendingRefund["status"], string> = {
      pending: "bg-amber-500/10 text-amber-400",
      partial: "bg-blue-500/10 text-blue-400",
      resolved: "bg-emerald-500/10 text-emerald-400",
      closed: "bg-slate-500/10 text-slate-400",
    };
    return (
      <span className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full font-medium ${styles[status]}`}>
        {t(`transactions.refunds.status.${status}`)}
      </span>
    );
  };

  const renderProgressBar = (refunded: number, expected: number) => {
    const pct = expected > 0 ? Math.min(100, (refunded / expected) * 100) : 0;
    return (
      <div className="w-full h-1.5 rounded-full bg-[var(--surface-light)] overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${pct >= 100 ? "bg-emerald-500" : "bg-amber-500"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    );
  };

  const renderRefundCard = (item: PendingRefund) => {
    const refunded = item.total_refunded ?? 0;
    const isActive = item.status === "pending" || item.status === "partial";
    return (
      <div
        key={item.id}
        data-testid="refund-card"
        className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-xl overflow-hidden"
      >
        {/* Header: The Source Expense */}
        <div className="p-4 flex flex-col md:flex-row md:items-start justify-between gap-3 bg-[var(--surface-light)]/30">
          <div className="flex items-start gap-3 min-w-0">
            <div
              className={`p-2 rounded-lg shrink-0 ${
                item.status === "resolved"
                  ? "bg-emerald-500/10 text-emerald-500"
                  : item.status === "closed"
                    ? "bg-slate-500/10 text-slate-400"
                    : "bg-amber-500/10 text-amber-500"
              }`}
            >
              {item.status === "resolved" ? (
                <CheckCircle2 size={20} />
              ) : item.status === "closed" ? (
                <Lock size={20} />
              ) : (
                <CircleDashed size={20} />
              )}
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <span className="font-semibold text-base md:text-lg truncate" dir="auto">
                  {item.description || t("transactions.refunds.unknownExpense")}
                </span>
                {statusChip(item.status)}
              </div>
              <div className="flex items-center gap-3 text-xs md:text-sm text-[var(--text-muted)] flex-wrap">
                <span className="flex items-center gap-1">
                  <Calendar size={13} />
                  {item.date || t("transactions.refunds.noDate")}
                </span>
                <span className="flex items-center gap-1 min-w-0">
                  <CreditCard size={13} className="shrink-0" />
                  <span className="truncate" dir="auto">
                    {item.account_name || t("transactions.refunds.unknownAccount")}
                  </span>
                </span>
                <span className="text-xs px-1.5 py-0.5 rounded bg-[var(--surface-light)]">
                  {item.provider
                    ? humanizeProvider(item.provider)
                    : humanizeService(item.source_table)}
                </span>
              </div>
              {item.notes && (
                <div className="mt-1.5 text-sm italic text-amber-500/80" dir="auto">
                  "{item.notes}"
                </div>
              )}
            </div>
          </div>
          <div className="flex flex-col md:items-end gap-1.5 shrink-0 md:min-w-[220px]">
            <div className="flex md:flex-col items-baseline md:items-end gap-2 md:gap-0">
              <span className="text-xl font-bold font-mono text-[var(--text-primary)]">
                {formatCurrency(item.expected_amount)}
              </span>
              <span className="text-xs text-[var(--text-muted)]">
                {t("transactions.refunds.expectedRefund")}
              </span>
            </div>
            <div className="w-full md:w-[220px]">
              {renderProgressBar(refunded, item.expected_amount)}
              <div className="mt-1 text-xs text-[var(--text-muted)]">
                {t("transactions.refunds.refundedOf", {
                  refunded: formatCurrency(refunded),
                  expected: formatCurrency(item.expected_amount),
                })}
              </div>
            </div>
            {isActive && (
              <div className="flex items-center gap-2 mt-1">
                <button
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors"
                  onClick={() => setLinkingRefund(item)}
                >
                  <Link2 size={14} />
                  {t("budget.linkRefund")}
                </button>
                <button
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-colors"
                  onClick={async () => {
                    const ok = await confirm({
                      title: t("transactions.refunds.closeRefund"),
                      message: t("transactions.refunds.confirmClose"),
                      confirmLabel: t("transactions.refunds.closeRefund"),
                    });
                    if (ok) closeMutation.mutate(item.id);
                  }}
                >
                  <Lock size={14} />
                  {t("transactions.refunds.closeRefund")}
                </button>
                <button
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors"
                  onClick={async () => {
                    const ok = await confirm({
                      title: t("common.cancel"),
                      message: t("transactions.refunds.confirmCancel"),
                      confirmLabel: t("common.confirm"),
                      isDestructive: true,
                    });
                    if (ok) cancelMutation.mutate(item.id);
                  }}
                >
                  <X size={14} />
                  {t("common.cancel")}
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Body: Linked Refunds */}
        <div className="p-4 border-t border-[var(--surface-light)]">
          {!item.links || item.links.length === 0 ? (
            <div className="text-sm text-[var(--text-muted)] italic">
              {t("transactions.refunds.noRefundsLinked")}
            </div>
          ) : (
            <div className="space-y-1.5">
              {item.links.map((link) => {
                const key = txKey(link.refund_source, link.refund_transaction_id);
                const sharedWith = (sharedCountMap.get(key) ?? 1) - 1;
                return (
                  <div
                    key={link.id}
                    className="flex flex-wrap justify-between items-center gap-2 py-1.5 px-3 rounded-lg bg-[var(--surface-light)]/30 group"
                  >
                    <div className="flex items-center gap-2 min-w-0 flex-wrap">
                      <span className="text-emerald-400 font-mono font-medium">
                        +{formatCurrency(link.amount)}
                      </span>
                      {link.transaction_amount != null &&
                        link.transaction_amount !== link.amount && (
                          <span className="text-xs text-[var(--text-muted)]">
                            {t("transactions.refunds.ofTransaction", {
                              amount: formatCurrency(link.transaction_amount),
                            })}
                          </span>
                        )}
                      <span className="text-sm truncate" dir="auto">
                        {link.description || t("transactions.refunds.refundTransaction")}
                      </span>
                      <span className="text-xs text-[var(--text-muted)]">
                        ({link.date})
                      </span>
                      {sharedWith > 0 && (
                        <span
                          className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full bg-purple-500/10 text-purple-400"
                          title={t("transactions.refunds.sharedSourceTooltip", {
                            count: sharedWith,
                          })}
                        >
                          <Users size={11} />
                          {t("transactions.refunds.sharedSource", { count: sharedWith })}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-[var(--text-muted)] opacity-50 group-hover:opacity-100 transition-opacity">
                        {humanizeService(link.refund_source)}
                      </span>
                      {item.status !== "closed" && (
                        <button
                          className="flex items-center gap-1 px-2 py-1 rounded text-xs font-medium hover:bg-red-500/10 text-red-400/70 hover:text-red-400 transition-all"
                          onClick={() => handleUnlink(link.id)}
                        >
                          <Unlink size={14} />
                          {t("transactions.refunds.unlink")}
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    );
  };

  const renderSourceCard = (src: RefundSource) => {
    const total = src.transaction_amount;
    const allocatedPct =
      total != null && total > 0
        ? Math.min(100, (src.total_allocated / total) * 100)
        : 100;
    const available = src.available ?? 0;
    return (
      <div
        key={txKey(src.refund_source, src.refund_transaction_id)}
        data-testid="refund-source-card"
        className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-xl overflow-hidden"
      >
        <div className="p-4 flex flex-col md:flex-row md:items-start justify-between gap-3 bg-[var(--surface-light)]/30">
          <div className="flex items-start gap-3 min-w-0">
            <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-500 shrink-0">
              <Coins size={20} />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <span className="font-semibold text-base md:text-lg truncate" dir="auto">
                  {src.description || t("transactions.refunds.refundTransaction")}
                </span>
                {available > 0 ? (
                  <span className="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full font-medium bg-emerald-500/10 text-emerald-400">
                    {t("transactions.refunds.availableBadge", {
                      amount: formatCurrency(available),
                    })}
                  </span>
                ) : (
                  <span className="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full font-medium bg-slate-500/10 text-slate-400">
                    {t("transactions.refunds.fullyAllocated")}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-3 text-xs md:text-sm text-[var(--text-muted)] flex-wrap">
                <span className="flex items-center gap-1">
                  <Calendar size={13} />
                  {src.date || t("transactions.refunds.noDate")}
                </span>
                {src.account_name && (
                  <span className="flex items-center gap-1 min-w-0">
                    <Landmark size={13} className="shrink-0" />
                    <span className="truncate" dir="auto">{src.account_name}</span>
                  </span>
                )}
                <span className="text-xs px-1.5 py-0.5 rounded bg-[var(--surface-light)]">
                  {src.provider
                    ? humanizeProvider(src.provider)
                    : humanizeService(src.refund_source)}
                </span>
              </div>
            </div>
          </div>
          <div className="flex flex-col md:items-end gap-1.5 shrink-0 md:min-w-[220px]">
            <div className="flex md:flex-col items-baseline md:items-end gap-2 md:gap-0">
              <span className="text-xl font-bold font-mono text-emerald-400">
                {total != null ? `+${formatCurrency(total)}` : formatCurrency(src.total_allocated)}
              </span>
              <span className="text-xs text-[var(--text-muted)]">
                {t("transactions.refunds.transactionAmount")}
              </span>
            </div>
            <div className="w-full md:w-[220px]">
              <div className="w-full h-1.5 rounded-full bg-[var(--surface-light)] overflow-hidden">
                <div
                  className="h-full rounded-full bg-emerald-500 transition-all"
                  style={{ width: `${allocatedPct}%` }}
                />
              </div>
              <div className="mt-1 text-xs text-[var(--text-muted)]">
                {total != null
                  ? t("transactions.refunds.allocatedOf", {
                      allocated: formatCurrency(src.total_allocated),
                      total: formatCurrency(total),
                    })
                  : t("transactions.refunds.allocatedOnly", {
                      allocated: formatCurrency(src.total_allocated),
                    })}
              </div>
            </div>
            {available > 0 && (
              <button
                className="flex items-center gap-1.5 px-3 py-1.5 mt-1 rounded-lg text-xs font-medium bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors"
                onClick={() => setLinkingSource(src)}
              >
                <Link2 size={14} />
                {t("transactions.refunds.linkRemaining")}
              </button>
            )}
          </div>
        </div>

        {/* Allocations */}
        <div className="p-4 border-t border-[var(--surface-light)] space-y-1.5">
          {src.allocations.map((alloc) => (
            <div
              key={alloc.link_id}
              className="flex flex-wrap justify-between items-center gap-2 py-1.5 px-3 rounded-lg bg-[var(--surface-light)]/30"
            >
              <div className="flex items-center gap-2 min-w-0 flex-wrap">
                <Receipt size={14} className="text-amber-400 shrink-0" />
                <span className="text-sm truncate" dir="auto">
                  {alloc.pending_description ||
                    t("transactions.refunds.unknownExpense")}
                </span>
                {statusChip(alloc.pending_status)}
                {alloc.pending_date && (
                  <span className="text-xs text-[var(--text-muted)]">
                    ({alloc.pending_date})
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-mono font-medium text-emerald-400">
                  {formatCurrency(alloc.amount)}
                </span>
                {alloc.pending_status !== "closed" && (
                  <button
                    className="flex items-center gap-1 px-2 py-1 rounded text-xs font-medium hover:bg-red-500/10 text-red-400/70 hover:text-red-400 transition-all"
                    onClick={() => handleUnlink(alloc.link_id)}
                  >
                    <Unlink size={14} />
                    {t("transactions.refunds.unlink")}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  const statusFilters: { value: StatusFilter; label: string }[] = [
    { value: "all", label: t("transactions.refunds.filterAll") },
    { value: "active", label: t("transactions.refunds.active") },
    { value: "resolved", label: t("transactions.refunds.resolved") },
    { value: "closed", label: t("transactions.refunds.closed") },
  ];

  return (
    <div className="max-w-5xl mx-auto py-6 px-4 space-y-6">
      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 md:gap-4">
        <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-xl p-4">
          <div className="text-[10px] sm:text-xs uppercase tracking-wide text-[var(--text-muted)] mb-1">
            {t("transactions.refunds.outstanding")}
          </div>
          <div className="text-xl md:text-2xl font-bold text-amber-400">
            {formatCurrency(summary.outstanding)}
          </div>
          <div className="text-xs text-[var(--text-muted)] mt-0.5">
            {t("transactions.refunds.activeCount", { count: summary.activeCount })}
          </div>
        </div>
        <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-xl p-4">
          <div className="text-[10px] sm:text-xs uppercase tracking-wide text-[var(--text-muted)] mb-1">
            {t("transactions.refunds.received")}
          </div>
          <div className="text-xl md:text-2xl font-bold text-emerald-400">
            {formatCurrency(summary.received)}
          </div>
        </div>
        <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-xl p-4">
          <div className="text-[10px] sm:text-xs uppercase tracking-wide text-[var(--text-muted)] mb-1">
            {t("transactions.refunds.availableToAllocate")}
          </div>
          <div className="text-xl md:text-2xl font-bold text-[var(--text-primary)]">
            {formatCurrency(summary.availableInSources)}
          </div>
          <div className="text-xs text-[var(--text-muted)] mt-0.5">
            {t("transactions.refunds.availableToAllocateHint")}
          </div>
        </div>
      </div>

      {/* Controls */}
      <div className="flex flex-col md:flex-row md:items-center gap-3">
        <div className="relative flex-1">
          <Search
            size={16}
            className="absolute start-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
          />
          <input
            type="text"
            placeholder={t("transactions.refunds.searchPlaceholder")}
            aria-label={t("transactions.refunds.searchPlaceholder")}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full ps-10 pe-4 py-2 bg-[var(--surface)] border border-[var(--surface-light)] rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50 focus:border-emerald-500"
          />
        </div>
        {viewMode === "expenses" && (
          <div className="flex overflow-x-auto scrollbar-auto-hide gap-1">
            {statusFilters.map(({ value, label }) => (
              <button
                key={value}
                onClick={() => setStatusFilter(value)}
                className={`shrink-0 whitespace-nowrap px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  statusFilter === value
                    ? "bg-[var(--accent)] text-white"
                    : "bg-[var(--surface)] border border-[var(--surface-light)] text-[var(--text-muted)] hover:text-white"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        )}
        <div className="flex overflow-x-auto scrollbar-auto-hide gap-1 bg-[var(--surface)] border border-[var(--surface-light)] rounded-lg p-1">
          <button
            onClick={() => setViewMode("expenses")}
            className={`shrink-0 whitespace-nowrap px-3 py-1 rounded-md text-xs font-medium transition-colors ${
              viewMode === "expenses"
                ? "bg-[var(--surface-light)] text-white"
                : "text-[var(--text-muted)] hover:text-white"
            }`}
          >
            {t("transactions.refunds.byExpense")}
          </button>
          <button
            onClick={() => setViewMode("sources")}
            className={`shrink-0 whitespace-nowrap px-3 py-1 rounded-md text-xs font-medium transition-colors ${
              viewMode === "sources"
                ? "bg-[var(--surface-light)] text-white"
                : "text-[var(--text-muted)] hover:text-white"
            }`}
          >
            {t("transactions.refunds.bySource")}
          </button>
        </div>
      </div>

      {viewMode === "expenses" ? (
        <>
          {filteredRefunds.active.length > 0 && (
            <section>
              <h2 className="text-lg font-semibold mb-3 flex items-center gap-2 text-amber-400">
                <CircleDashed size={20} />
                {t("transactions.refunds.active")} ({filteredRefunds.active.length})
              </h2>
              <div className="space-y-4">
                {filteredRefunds.active.map(renderRefundCard)}
              </div>
            </section>
          )}

          {filteredRefunds.completed.length > 0 && (
            <section>
              <h2 className="text-lg font-semibold mb-3 flex items-center gap-2 text-emerald-400">
                <CheckCircle2 size={20} />
                {t("transactions.refunds.resolved")} ({filteredRefunds.completed.length})
              </h2>
              <div className="space-y-4">
                {filteredRefunds.completed.map(renderRefundCard)}
              </div>
            </section>
          )}

          {filteredRefunds.active.length === 0 &&
            filteredRefunds.completed.length === 0 && (
              <div className="text-center py-12 text-[var(--text-muted)]">
                <ArrowLeftRight size={48} className="mx-auto mb-4 opacity-20" />
                {refunds && refunds.length > 0 ? (
                  <p>{t("transactions.refunds.noMatches")}</p>
                ) : (
                  <>
                    <p>{t("transactions.refunds.noExpectations")}</p>
                    <p className="text-sm mt-2">
                      {t("transactions.refunds.markExpenses")}
                    </p>
                  </>
                )}
              </div>
            )}
        </>
      ) : (
        <>
          {filteredSources.length > 0 ? (
            <div className="space-y-4">{filteredSources.map(renderSourceCard)}</div>
          ) : (
            <div className="text-center py-12 text-[var(--text-muted)]">
              <Coins size={48} className="mx-auto mb-4 opacity-20" />
              <p>{t("transactions.refunds.noSources")}</p>
              <p className="text-sm mt-2">{t("transactions.refunds.noSourcesHint")}</p>
            </div>
          )}
        </>
      )}

      {linkingRefund && (
        <LinkRefundModal
          isOpen={!!linkingRefund}
          onClose={() => setLinkingRefund(null)}
          pendingRefund={linkingRefund}
        />
      )}
      {linkingSource && (
        <LinkRefundModal
          isOpen={!!linkingSource}
          onClose={() => setLinkingSource(null)}
          refundTransaction={{
            id: linkingSource.refund_transaction_id,
            source: linkingSource.refund_source,
            amount: linkingSource.transaction_amount ?? linkingSource.total_allocated,
            description: linkingSource.description ?? "",
          }}
        />
      )}
    </div>
  );
};

export default RefundsView;
