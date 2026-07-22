import React, { useState, useMemo } from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import {
  ArrowLeftRight,
  ChevronRight,
  Coins,
  Link2,
  Lock,
  Search,
  Unlink,
  X,
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

type StatusFilter = "all" | "open" | "resolved" | "closed";

const txKey = (source: string, id: number | string) => `${source}_${id}`;
const isOpenStatus = (s: PendingRefund["status"]) =>
  s === "pending" || s === "partial";

/** Click-to-edit note. Shows "+ note" when empty (revealed on row hover). */
const InlineNote: React.FC<{
  value: string | null | undefined;
  onSave: (note: string) => void;
  alwaysShowAdd?: boolean;
}> = ({ value, onSave, alwaysShowAdd = false }) => {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  if (editing) {
    const commit = (save: boolean) => {
      setEditing(false);
      const cleaned = draft.trim();
      if (save && cleaned !== (value ?? "")) onSave(cleaned);
    };
    return (
      <input
        autoFocus
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onClick={(e) => e.stopPropagation()}
        onBlur={() => commit(true)}
        onKeyDown={(e) => {
          e.stopPropagation();
          if (e.key === "Enter") commit(true);
          if (e.key === "Escape") commit(false);
        }}
        placeholder={t("transactions.refunds.notePlaceholder")}
        aria-label={t("transactions.refunds.noteAria")}
        className="w-full max-w-[260px] px-1.5 py-0 text-[11px] italic bg-[var(--background)] border border-amber-500/50 rounded-md focus:outline-none focus:border-amber-400 text-[var(--text-primary)]"
      />
    );
  }

  return (
    <button
      data-testid="inline-note"
      onClick={(e) => {
        e.stopPropagation();
        setDraft(value ?? "");
        setEditing(true);
      }}
      title={t("transactions.refunds.noteAria")}
      className={`truncate max-w-full rounded px-0.5 text-start transition-opacity ${
        value
          ? "italic text-amber-500/80 hover:bg-amber-500/10"
          : `text-[var(--text-muted)] hover:bg-[var(--surface-light)] ${
              alwaysShowAdd
                ? "opacity-60"
                : "opacity-0 group-hover:opacity-60 focus-visible:opacity-60"
            }`
      }`}
      dir="auto"
    >
      {value ? `"${value}"` : t("transactions.refunds.addNote")}
    </button>
  );
};

const RefundsView: React.FC = () => {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const qk = useQueryKeys();
  const confirm = useConfirm();
  const [linkingRefund, setLinkingRefund] = useState<PendingRefund | null>(null);
  const [linkingSource, setLinkingSource] = useState<RefundSource | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [hoveredSourceKey, setHoveredSourceKey] = useState<string | null>(null);
  const [hoveredRequestId, setHoveredRequestId] = useState<number | null>(null);

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
  const notesMutation = useMutation({
    mutationFn: (params: { id: number; notes: string }) =>
      pendingRefundsApi.updateNotes(params.id, params.notes),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: qkPrefix.pendingRefunds }),
  });
  const sourceNoteMutation = useMutation({
    mutationFn: (params: {
      refund_source: string;
      refund_transaction_id: number;
      note: string;
    }) => pendingRefundsApi.setSourceNote(params),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: qkPrefix.pendingRefunds }),
  });

  const summary = useMemo(() => {
    const all = refunds ?? [];
    const open = all.filter((r) => isOpenStatus(r.status));
    return {
      openCount: open.length,
      outstanding: open.reduce(
        (sum, r) => sum + (r.remaining ?? r.expected_amount),
        0,
      ),
      received: all.reduce((sum, r) => sum + (r.total_refunded ?? 0), 0),
      availableInSources: (refundSources ?? []).reduce(
        (sum, s) => sum + (s.available ?? 0),
        0,
      ),
    };
  }, [refunds, refundSources]);

  const counts = useMemo(() => {
    const all = refunds ?? [];
    return {
      all: all.length,
      open: all.filter((r) => isOpenStatus(r.status)).length,
      resolved: all.filter((r) => r.status === "resolved").length,
      closed: all.filter((r) => r.status === "closed").length,
    };
  }, [refunds]);

  const filteredRefunds = useMemo(() => {
    let list = refunds ?? [];
    if (statusFilter === "open") list = list.filter((r) => isOpenStatus(r.status));
    else if (statusFilter !== "all")
      list = list.filter((r) => r.status === statusFilter);

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
    return [...list].sort((a, b) => {
      // Open requests first, then by date desc
      const oa = isOpenStatus(a.status) ? 0 : 1;
      const ob = isOpenStatus(b.status) ? 0 : 1;
      if (oa !== ob) return oa - ob;
      return (b.date ?? "").localeCompare(a.date ?? "");
    });
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
          s.note,
          ...s.allocations.map((a) => a.pending_description),
        ].some((field) => field?.toLowerCase().includes(query)),
      );
    }
    return list;
  }, [refundSources, searchQuery]);

  // Keys of sources funding the hovered request, and ids of requests funded
  // by the hovered source — powers the two-way cross-highlight.
  const highlightedSourceKeys = useMemo(() => {
    if (hoveredRequestId == null) return new Set<string>();
    const r = refunds?.find((x) => x.id === hoveredRequestId);
    return new Set(
      (r?.links ?? []).map((l) =>
        txKey(l.refund_source, l.refund_transaction_id),
      ),
    );
  }, [hoveredRequestId, refunds]);

  const highlightedRequestIds = useMemo(() => {
    if (!hoveredSourceKey) return new Set<number>();
    const src = refundSources?.find(
      (s) => txKey(s.refund_source, s.refund_transaction_id) === hoveredSourceKey,
    );
    return new Set((src?.allocations ?? []).map((a) => a.pending_refund_id));
  }, [hoveredSourceKey, refundSources]);

  if (isLoading) {
    return (
      <div className="p-4 md:p-8 text-center text-[var(--text-muted)]">
        {t("transactions.refunds.loading")}
      </div>
    );
  }

  const toggleExpanded = (id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleUnlink = async (linkId: number) => {
    const ok = await confirm({
      title: t("transactions.refunds.unlink"),
      message: t("transactions.refunds.confirmUnlink"),
      confirmLabel: t("transactions.refunds.unlink"),
      isDestructive: true,
    });
    if (ok) unlinkMutation.mutate(linkId);
  };

  const handleClose = async (id: number) => {
    const ok = await confirm({
      title: t("transactions.refunds.closeRefund"),
      message: t("transactions.refunds.confirmClose"),
      confirmLabel: t("transactions.refunds.closeRefund"),
    });
    if (ok) closeMutation.mutate(id);
  };

  const handleCancel = async (id: number) => {
    const ok = await confirm({
      title: t("common.cancel"),
      message: t("transactions.refunds.confirmCancel"),
      confirmLabel: t("common.confirm"),
      isDestructive: true,
    });
    if (ok) cancelMutation.mutate(id);
  };

  const statusDot: Record<PendingRefund["status"], string> = {
    pending: "bg-amber-400",
    partial: "bg-blue-400",
    resolved: "bg-emerald-400",
    closed: "bg-slate-400",
  };

  const filterChips: { value: StatusFilter; label: string; count: number }[] = [
    { value: "all", label: t("transactions.refunds.filterAll"), count: counts.all },
    { value: "open", label: t("transactions.refunds.filterOpen"), count: counts.open },
    { value: "resolved", label: t("transactions.refunds.status.resolved"), count: counts.resolved },
    { value: "closed", label: t("transactions.refunds.status.closed"), count: counts.closed },
  ];

  const renderRequestRow = (item: PendingRefund) => {
    const refunded = item.total_refunded ?? 0;
    const remaining = item.remaining ?? item.expected_amount;
    const isActive = isOpenStatus(item.status);
    const isExpanded = expanded.has(item.id);
    const pct =
      item.expected_amount > 0
        ? Math.min(100, (refunded / item.expected_amount) * 100)
        : 0;
    const highlighted = highlightedRequestIds.has(item.id);

    return (
      <div
        key={item.id}
        data-testid="refund-row"
        className={`border-b border-[var(--surface-light)]/50 last:border-b-0 ${
          highlighted ? "bg-purple-500/10" : ""
        }`}
        onMouseEnter={() => setHoveredRequestId(item.id)}
        onMouseLeave={() => setHoveredRequestId(null)}
      >
        <div
          role="button"
          tabIndex={0}
          onClick={() => toggleExpanded(item.id)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              toggleExpanded(item.id);
            }
          }}
          className="group grid grid-cols-[12px_10px_minmax(0,1fr)_max-content] sm:grid-cols-[12px_10px_minmax(0,1fr)_150px_90px_max-content] gap-2.5 items-center px-3 py-2 cursor-pointer hover:bg-[var(--surface-light)]/30 transition-colors"
        >
          <ChevronRight
            size={12}
            className={`text-[var(--text-muted)] transition-transform rtl:rotate-180 ${
              isExpanded ? "rotate-90 rtl:rotate-90" : ""
            }`}
          />
          <span
            className={`w-2 h-2 rounded-full justify-self-center ${statusDot[item.status]}`}
            title={t(`transactions.refunds.status.${item.status}`)}
          />
          <div className="min-w-0">
            <div className="text-[13px] font-semibold truncate" dir="auto">
              {item.description || t("transactions.refunds.unknownExpense")}
            </div>
            <div className="text-[11px] text-[var(--text-muted)] flex items-center gap-1.5 min-w-0">
              <span className="shrink-0" dir="ltr">{item.date || t("transactions.refunds.noDate")}</span>
              <span className="shrink-0">·</span>
              <span className="truncate shrink-0 max-w-[140px]" dir="auto">
                {item.provider
                  ? humanizeProvider(item.provider)
                  : humanizeService(item.source_table)}
              </span>
              <span className="shrink-0">·</span>
              <InlineNote
                value={item.notes}
                onSave={(note) => notesMutation.mutate({ id: item.id, notes: note })}
              />
            </div>
          </div>
          <div className="hidden sm:flex flex-col gap-[3px]">
            <div className="flex justify-between gap-1.5 text-[11px] text-[var(--text-muted)]">
              <span className="text-emerald-400 font-semibold">{formatCurrency(refunded)}</span>
              <span>{formatCurrency(item.expected_amount)}</span>
            </div>
            <div className="h-[3px] rounded-full bg-[var(--surface-light)] overflow-hidden">
              <div
                className={`h-full rounded-full ${isActive ? "bg-amber-400" : "bg-emerald-400"}`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
          <div className="text-end text-[12px] font-semibold">
            {item.status === "closed" ? (
              <span className="text-slate-400 font-normal">—</span>
            ) : isActive ? (
              <span className="text-amber-400">{formatCurrency(remaining)}</span>
            ) : (
              <span className="text-emerald-400">✓</span>
            )}
            <small className="block text-[9.5px] font-medium text-[var(--text-muted)] uppercase tracking-wide">
              {item.status === "closed"
                ? t("transactions.refunds.status.closed")
                : isActive
                  ? t("transactions.refunds.left")
                  : t("transactions.refunds.settled")}
            </small>
          </div>
          <div className="flex items-center gap-0.5">
            {isActive && (
              <button
                className="px-2 py-1 rounded-md text-[11px] font-medium text-emerald-400 hover:bg-emerald-500/15 transition-colors"
                onClick={(e) => {
                  e.stopPropagation();
                  setLinkingRefund(item);
                }}
              >
                <span className="flex items-center gap-1">
                  <Link2 size={12} />
                  {t("transactions.refunds.linkShort")}
                </span>
              </button>
            )}
            {isActive && (
              <button
                className="hidden sm:block px-2 py-1 rounded-md text-[11px] font-medium text-blue-400 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 hover:bg-blue-500/15 transition-all"
                onClick={(e) => {
                  e.stopPropagation();
                  handleClose(item.id);
                }}
              >
                <span className="flex items-center gap-1">
                  <Lock size={12} />
                  {t("transactions.refunds.closeShort")}
                </span>
              </button>
            )}
            {item.status !== "closed" && (
              <button
                className="hidden sm:block px-2 py-1 rounded-md text-[11px] font-medium text-red-400 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 hover:bg-red-500/15 transition-all"
                aria-label={t("common.cancel")}
                onClick={(e) => {
                  e.stopPropagation();
                  handleCancel(item.id);
                }}
              >
                <X size={12} />
              </button>
            )}
          </div>
        </div>

        {isExpanded && (
          <div className="px-3 pb-2 ps-10 sm:ps-16">
            {/* Mobile-only progress (hidden column on phones) */}
            <div className="sm:hidden flex items-center gap-2 text-[11px] text-[var(--text-muted)] pb-1.5">
              <span className="text-emerald-400 font-semibold">{formatCurrency(refunded)}</span>
              <span>/</span>
              <span>{formatCurrency(item.expected_amount)}</span>
            </div>
            {!item.links || item.links.length === 0 ? (
              <div className="text-[11.5px] italic text-[var(--text-muted)] py-0.5">
                {t("transactions.refunds.noRefundsLinked")}
              </div>
            ) : (
              item.links.map((link) => {
                const key = txKey(link.refund_source, link.refund_transaction_id);
                const src = refundSources?.find(
                  (s) => txKey(s.refund_source, s.refund_transaction_id) === key,
                );
                const sharedWith = (src?.allocations.length ?? 1) - 1;
                const free = src?.available ?? 0;
                return (
                  <div
                    key={link.id}
                    className="flex items-baseline gap-2 py-[3px] text-[11.5px] text-[var(--text-muted)] flex-wrap"
                  >
                    <span className="text-emerald-400 font-semibold">
                      +{formatCurrency(link.amount)}
                    </span>
                    <span className="truncate max-w-[240px]" dir="auto">
                      {link.description || t("transactions.refunds.refundTransaction")}
                    </span>
                    {link.transaction_amount != null &&
                      link.transaction_amount !== link.amount && (
                        <span className="text-[10.5px]">
                          {t("transactions.refunds.ofTransaction", {
                            amount: formatCurrency(link.transaction_amount),
                          })}
                        </span>
                      )}
                    {sharedWith > 0 && (
                      <span
                        className="text-[9.5px] font-semibold text-purple-400 border border-purple-400/50 rounded-full px-1.5"
                        title={t("transactions.refunds.sharedSourceTooltip", {
                          count: sharedWith,
                        })}
                      >
                        {t("transactions.refunds.sharedSource", { count: sharedWith })}
                      </span>
                    )}
                    {free > 0.005 && (
                      <span className="text-[9.5px] font-semibold text-blue-400">
                        {t("transactions.refunds.freeAmount", {
                          amount: formatCurrency(free),
                        })}
                      </span>
                    )}
                    <span className="shrink-0" dir="ltr">{link.date}</span>
                    <span className="flex-1" />
                    {item.status !== "closed" && (
                      <button
                        className="flex items-center gap-1 text-[10px] text-[var(--text-muted)] hover:text-red-400 transition-colors"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleUnlink(link.id);
                        }}
                      >
                        <Unlink size={11} />
                        {t("transactions.refunds.unlink")}
                      </button>
                    )}
                  </div>
                );
              })
            )}
            {/* Mobile actions (Close/Cancel are hover-only on desktop) */}
            {(isActive || item.status !== "closed") && (
              <div className="sm:hidden flex items-center gap-2 pt-1.5">
                {isActive && (
                  <button
                    className="flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-medium text-blue-400 bg-blue-500/10"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleClose(item.id);
                    }}
                  >
                    <Lock size={12} />
                    {t("transactions.refunds.closeShort")}
                  </button>
                )}
                {item.status !== "closed" && (
                  <button
                    className="flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-medium text-red-400 bg-red-500/10"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleCancel(item.id);
                    }}
                  >
                    <X size={12} />
                    {t("common.cancel")}
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  const renderSource = (src: RefundSource) => {
    const key = txKey(src.refund_source, src.refund_transaction_id);
    const total = src.transaction_amount;
    const available = src.available ?? 0;
    const usedPct =
      total != null && total > 0
        ? Math.min(100, (src.total_allocated / total) * 100)
        : 100;

    return (
      <div
        key={key}
        data-testid="refund-source-item"
        className={`px-3 py-2 border-b border-[var(--surface-light)]/50 last:border-b-0 transition-colors group ${
          highlightedSourceKeys.has(key) ? "bg-purple-500/10" : "hover:bg-purple-500/10"
        }`}
        onMouseEnter={() => setHoveredSourceKey(key)}
        onMouseLeave={() => setHoveredSourceKey(null)}
      >
        <div className="flex justify-between items-baseline gap-2">
          <span className="text-[12px] font-semibold truncate" dir="auto">
            {src.description || t("transactions.refunds.refundTransaction")}
          </span>
          <span className="text-[12px] font-bold text-emerald-400 shrink-0" dir="ltr">
            +{formatCurrency(total ?? src.total_allocated)}
          </span>
        </div>
        <div className="text-[10.5px] text-[var(--text-muted)] mt-px flex items-center gap-1 min-w-0">
          <span className="shrink-0" dir="ltr">{src.date}</span>
          <span className="shrink-0">·</span>
          <span className="truncate" dir="auto">
            {src.provider ? humanizeProvider(src.provider) : humanizeService(src.refund_source)}
            {src.account_name ? ` · ${src.account_name}` : ""}
          </span>
        </div>
        <div className="text-[10.5px] mt-px">
          <InlineNote
            value={src.note}
            onSave={(note) =>
              sourceNoteMutation.mutate({
                refund_source: src.refund_source,
                refund_transaction_id: src.refund_transaction_id,
                note,
              })
            }
          />
        </div>
        <div className="flex h-1 rounded-full overflow-hidden bg-[var(--surface-light)] mt-1.5">
          <span className="bg-emerald-400" style={{ width: `${usedPct}%` }} />
          {available > 0.005 && (
            <span className="bg-blue-400/55" style={{ width: `${100 - usedPct}%` }} />
          )}
        </div>
        <div className="flex flex-wrap gap-1 mt-1.5">
          {src.allocations.map((alloc) => (
            <span
              key={alloc.link_id}
              className="text-[10px] text-[var(--text-muted)] bg-[var(--background)] border border-[var(--surface-light)] rounded-full px-2 py-px max-w-full truncate"
              dir="auto"
            >
              {alloc.pending_description || t("transactions.refunds.unknownExpense")}{" "}
              · <b className="text-[var(--text-primary)] font-semibold" dir="ltr">{formatCurrency(alloc.amount)}</b>
            </span>
          ))}
          {available > 0.005 ? (
            <button
              className="text-[10px] font-bold text-blue-400 border border-dashed border-blue-400/60 rounded-full px-2 py-px hover:bg-blue-500/15 transition-colors"
              onClick={() => setLinkingSource(src)}
            >
              {t("transactions.refunds.freeChipAction", {
                amount: formatCurrency(available),
              })}
            </button>
          ) : (
            <span className="text-[10px] text-[var(--text-muted)] px-1 py-px">
              {t("transactions.refunds.fullyAllocated")}
            </span>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="max-w-[1180px] mx-auto py-4 px-2 sm:px-4">
      {/* ── Toolbar: KPIs + filters + search ── */}
      <div className="flex items-center gap-4 md:gap-5 flex-wrap px-3.5 py-2.5 bg-[var(--surface)] border border-[var(--surface-light)] rounded-xl">
        <div className="flex items-center gap-4 md:gap-5 flex-wrap">
          <div className="flex flex-col">
            <span className="text-base font-bold text-amber-400" dir="ltr">
              {formatCurrency(summary.outstanding)}
            </span>
            <span className="text-[10px] uppercase tracking-wide text-[var(--text-muted)]">
              {t("transactions.refunds.outstanding")} ·{" "}
              {t("transactions.refunds.openCount", { count: summary.openCount })}
            </span>
          </div>
          <div className="w-px h-6 bg-[var(--surface-light)]" />
          <div className="flex flex-col">
            <span className="text-base font-bold text-emerald-400" dir="ltr">
              +{formatCurrency(summary.received)}
            </span>
            <span className="text-[10px] uppercase tracking-wide text-[var(--text-muted)]">
              {t("transactions.refunds.received")}
            </span>
          </div>
          <div className="w-px h-6 bg-[var(--surface-light)]" />
          <div className="flex flex-col">
            <span className="text-base font-bold text-blue-400" dir="ltr">
              {formatCurrency(summary.availableInSources)}
            </span>
            <span className="text-[10px] uppercase tracking-wide text-[var(--text-muted)]">
              {t("transactions.refunds.availableToAllocate")}
            </span>
          </div>
        </div>
        <div className="flex-1" />
        <div className="flex overflow-x-auto scrollbar-auto-hide gap-1">
          {filterChips.map(({ value, label, count }) => (
            <button
              key={value}
              onClick={() => setStatusFilter(value)}
              aria-pressed={statusFilter === value}
              className={`shrink-0 whitespace-nowrap px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors ${
                statusFilter === value
                  ? "bg-[var(--surface-light)] text-[var(--text-primary)]"
                  : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              }`}
            >
              {label} <span className="font-normal opacity-70">{count}</span>
            </button>
          ))}
        </div>
        <div className="relative w-full sm:w-auto">
          <Search
            size={14}
            className="absolute start-2.5 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
          />
          <input
            type="search"
            placeholder={t("transactions.refunds.searchPlaceholder")}
            aria-label={t("transactions.refunds.searchPlaceholder")}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full sm:w-[180px] ps-8 pe-3 py-1.5 bg-[var(--background)] border border-[var(--surface-light)] rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
          />
        </div>
      </div>

      {/* ── Two-pane main ── */}
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_330px] gap-3.5 mt-3.5 items-start">
        {/* Requests */}
        <section
          className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-xl overflow-hidden"
          aria-label={t("transactions.refunds.requestsPanel")}
        >
          <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-[var(--surface-light)] text-[11px] uppercase tracking-wide text-[var(--text-muted)] font-semibold">
            <span>{t("transactions.refunds.requestsPanel")}</span>
            <span className="normal-case font-normal tracking-normal hidden sm:block">
              {t("transactions.refunds.panelHint")}
            </span>
          </div>
          {filteredRefunds.length > 0 ? (
            filteredRefunds.map(renderRequestRow)
          ) : (
            <div className="text-center py-10 px-4 text-[var(--text-muted)]">
              <ArrowLeftRight size={40} className="mx-auto mb-3 opacity-20" />
              {refunds && refunds.length > 0 ? (
                <p className="text-xs">{t("transactions.refunds.noMatches")}</p>
              ) : (
                <>
                  <p className="text-sm">{t("transactions.refunds.noExpectations")}</p>
                  <p className="text-xs mt-1.5">{t("transactions.refunds.markExpenses")}</p>
                </>
              )}
            </div>
          )}
        </section>

        {/* Sources rail */}
        <aside
          className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-xl overflow-hidden lg:sticky lg:top-4"
          aria-label={t("transactions.refunds.sourcesPanel")}
        >
          <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-[var(--surface-light)] text-[11px] uppercase tracking-wide text-[var(--text-muted)] font-semibold">
            <span>{t("transactions.refunds.sourcesPanel")}</span>
            <span className="normal-case font-normal tracking-normal">
              {t("transactions.refunds.sourcesCount", { count: filteredSources.length })}
            </span>
          </div>
          {filteredSources.length > 0 ? (
            <>
              {filteredSources.map(renderSource)}
              <div className="px-3 py-2 text-[10.5px] text-[var(--text-muted)] border-t border-[var(--surface-light)] hidden lg:block">
                {t("transactions.refunds.crossHint")}
              </div>
            </>
          ) : (
            <div className="text-center py-8 px-4 text-[var(--text-muted)]">
              <Coins size={32} className="mx-auto mb-2 opacity-20" />
              <p className="text-xs">{t("transactions.refunds.noSources")}</p>
              <p className="text-[10.5px] mt-1">{t("transactions.refunds.noSourcesHint")}</p>
            </div>
          )}
        </aside>
      </div>

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
