import { useState, useMemo, useRef, useCallback, useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Split, RefreshCw, Tag, Wand2, Link2 } from "lucide-react";
import {
  transactionsApi,
  pendingRefundsApi,
  type TaggingRule,
} from "../../services/api";
import { SplitTransactionModal } from "../modals/SplitTransactionModal";
import { LinkRefundModal } from "../modals/LinkRefundModal";
import { SelectDropdown } from "../common/SelectDropdown";
import { useCategoryTagCreate } from "../../hooks/useCategoryTagCreate";
import { useCategories } from "../../hooks/useCategories";
import { useTaggingRules } from "../../hooks/useTaggingRules";
import type { Transaction } from "../../types/transaction";
import { Skeleton } from "../common/Skeleton";
import { useTranslation } from "react-i18next";
import { formatShortDate } from "../../utils/dateFormatting";
import { formatCurrency } from "../../utils/numberFormatting";
import { findMatchingRule } from "../../utils/taggingRuleEval";
import { isToday, isYesterday } from "date-fns";
import i18n from "../../i18n";

function formatTransactionDate(dateStr: string): string {
  const d = new Date(dateStr);
  if (isToday(d)) return i18n.t("common.today");
  if (isYesterday(d)) return i18n.t("common.yesterday");
  return formatShortDate(d);
}

const TRANSACTIONS_PAGE_SIZE = 20;

export function RecentTransactionsFeed({
  transactions,
  categoryIcons,
  isLoading,
}: {
  transactions: Transaction[] | undefined;
  categoryIcons: Record<string, string> | undefined;
  isLoading: boolean;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { createCategory, createTag } = useCategoryTagCreate();
  const [visibleCount, setVisibleCount] = useState(TRANSACTIONS_PAGE_SIZE);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const [editingTxKey, setEditingTxKey] = useState<string | null>(null);
  const [stagedCategory, setStagedCategory] = useState<string>("");
  const [stagedTag, setStagedTag] = useState<string>("");
  const [mobileActionsTxKey, setMobileActionsTxKey] = useState<string | null>(null);
  const [splittingTransaction, setSplittingTransaction] = useState<Transaction | null>(null);
  const [linkingTransaction, setLinkingTransaction] = useState<Transaction | null>(null);

  const txKeyOf = (tx: Transaction) =>
    `${tx.source}_${tx.unique_id ?? tx.id ?? `${tx.date}-${tx.amount}`}`;

  const openEditor = (tx: Transaction) => {
    setStagedCategory(tx.category || "");
    setStagedTag(tx.tag || "");
    setEditingTxKey(txKeyOf(tx));
  };

  const closeEditor = () => {
    setEditingTxKey(null);
    setStagedCategory("");
    setStagedTag("");
  };

  const commitEdit = (tx: Transaction) => {
    const currentTag = tx.tag || "";
    const changed =
      stagedCategory !== (tx.category || "") || stagedTag !== currentTag;
    if (changed) {
      tagMutation.mutate({ tx, category: stagedCategory, tag: stagedTag });
    }
    closeEditor();
  };

  // Categories for inline tag editing
  const { data: categories } = useCategories({ enabled: !!editingTxKey });
  const { data: taggingRules } = useTaggingRules();

  const invalidateAnalytics = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["income-outcome"] });
    queryClient.invalidateQueries({ queryKey: ["analytics-category"] });
    queryClient.invalidateQueries({ queryKey: ["sankey"] });
    queryClient.invalidateQueries({ queryKey: ["net-worth-over-time"] });
    queryClient.invalidateQueries({ queryKey: ["income-by-source"] });
    queryClient.invalidateQueries({ queryKey: ["monthly-expenses"] });
    queryClient.invalidateQueries({ queryKey: ["budget-analysis"] });
  }, [queryClient]);

  // Tag update mutation. We patch every cached transactions list synchronously
  // so the inline editor reflects the new category/tag immediately. Refetches
  // can be delayed or coalesced by React Query's debounced global invalidator
  // when many queries are active, leaving the row visibly stale despite a
  // successful API call. The patch is keyed by (source, unique_id ?? id) which
  // matches the row's React key, so the SelectDropdown re-renders with the new
  // value without waiting for the network round-trip.
  const tagMutation = useMutation({
    mutationFn: ({ tx, category, tag }: { tx: Transaction; category: string; tag: string }) =>
      transactionsApi.updateTag(
        String(tx.unique_id ?? tx.id),
        category,
        tag,
        tx.source || "",
      ),
    onSuccess: (_data, { tx, category, tag }) => {
      const sameRow = (t: Transaction) =>
        t.source === tx.source &&
        (t.unique_id ?? t.id) === (tx.unique_id ?? tx.id);
      const patchList = (old: Transaction[] | undefined) =>
        old?.map((t) => (sameRow(t) ? { ...t, category, tag: tag || undefined } : t)) ?? old;
      queryClient.setQueriesData<Transaction[]>({ queryKey: ["all-transactions"] }, patchList);
      queryClient.setQueriesData<Transaction[]>({ queryKey: ["transactions"] }, patchList);
      queryClient.invalidateQueries({ queryKey: ["categories"] });
      invalidateAnalytics();
    },
  });

  // Mark as pending refund
  const markPendingMutation = useMutation({
    mutationFn: (tx: Transaction) =>
      pendingRefundsApi.create({
        source_type: "transaction",
        source_id: tx.unique_id || "",
        source_table: tx.source || "",
        expected_amount: Math.abs(tx.amount),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["pendingRefunds"] });
      invalidateAnalytics();
    },
  });

  const sorted = useMemo(() => {
    if (!transactions) return [];
    return [...transactions].sort(
      (a, b) => new Date(b.date).getTime() - new Date(a.date).getTime(),
    );
  }, [transactions]);

  const visible = useMemo(() => sorted.slice(0, visibleCount), [sorted, visibleCount]);
  const hasMore = visibleCount < sorted.length;

  // IntersectionObserver to auto-load more when sentinel enters viewport
  const handleObserver = useCallback(
    (entries: IntersectionObserverEntry[]) => {
      const [entry] = entries;
      if (entry.isIntersecting && hasMore) {
        setVisibleCount((prev) => Math.min(prev + TRANSACTIONS_PAGE_SIZE, sorted.length));
      }
    },
    [hasMore, sorted.length],
  );

  useEffect(() => {
    const node = sentinelRef.current;
    if (!node) return;
    const observer = new IntersectionObserver(handleObserver, {
      root: node.closest("[data-scroll-root]"),
      rootMargin: "200px",
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [handleObserver]);

  // Reset visible count when transactions change (e.g. demo mode toggle)

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setVisibleCount(TRANSACTIONS_PAGE_SIZE);
  }, [transactions]);

  // Group by date label
  const grouped = useMemo(() => {
    const groups: { label: string; items: Transaction[] }[] = [];
    let currentLabel = "";
    for (const tx of visible) {
      const label = formatTransactionDate(tx.date);
      if (label !== currentLabel) {
        groups.push({ label, items: [] });
        currentLabel = label;
      }
      groups[groups.length - 1].items.push(tx);
    }
    return groups;
  }, [visible]);

  // Precompute which tagging rule matches each visible transaction
  const ruleMatchMap = useMemo(() => {
    if (!taggingRules || !visible.length) return new Map<string, TaggingRule>();
    const map = new Map<string, TaggingRule>();
    for (const tx of visible) {
      const key = txKeyOf(tx);
      const match = findMatchingRule(taggingRules, tx);
      if (match) map.set(key, match);
    }
    return map;
  }, [taggingRules, visible]);

  if (isLoading) {
    return (
      <div className="bg-[var(--surface)] rounded-2xl p-6 border border-[var(--surface-light)]">
        <Skeleton variant="text" lines={1} className="mb-4" />
        <Skeleton variant="text" lines={5} />
      </div>
    );
  }

  if (sorted.length === 0) return null;

  return (
    <div className="bg-[var(--surface)] rounded-2xl p-4 md:p-6 border border-[var(--surface-light)]">
      <div className="flex items-center justify-between mb-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
          🧾 {t("dashboard.recentTransactions")}
        </p>
        <Link
          to="/transactions"
          className="text-sm font-medium text-[var(--primary)] hover:underline"
        >
          {t("dashboard.viewAll")} &rarr;
        </Link>
      </div>

      <div
        data-scroll-root=""
        className="max-h-[500px] overflow-y-auto space-y-4 scrollbar-auto-hide"
      >
        {grouped.map((group) => (
          <div key={group.label}>
            <p className="text-xs font-semibold text-[var(--text-muted)] mb-2 sticky top-0 bg-[var(--surface)] py-1 z-10">
              {group.label}
            </p>
            <div className="space-y-1">
              {group.items.map((tx) => {
                const icon = tx.category ? categoryIcons?.[tx.category] ?? "" : "";
                const isPositive = tx.amount >= 0;
                const txKey = txKeyOf(tx);
                const isEditing = editingTxKey === txKey;
                const matchedRule = ruleMatchMap.get(txKey);

                return (
                  <div key={txKey}>
                    <div
                      className={`flex items-center gap-2 py-2 px-2 rounded-lg hover:bg-[var(--surface-light)]/40 transition-colors sm:cursor-default cursor-pointer ${mobileActionsTxKey === txKey ? "bg-[var(--surface-light)]/30" : ""}`}
                      onClick={() => {
                        // On mobile (< sm), toggle action card
                        if (window.innerWidth < 640) {
                          setMobileActionsTxKey(mobileActionsTxKey === txKey ? null : txKey);
                        }
                      }}
                    >
                      <span className="text-lg flex-shrink-0 w-7 text-center">{icon || "?"}</span>
                      <div className="flex-1 min-w-0">
                        {/* Description gets its own row with up to 2 lines of
                            ellipsis so longer merchant names aren't cropped at
                            inconsistent lengths on narrow screens. */}
                        <span
                          className="text-sm block break-words line-clamp-2"
                          title={tx.description || ""}
                        >
                          {tx.description || ""}
                        </span>
                        <div className="flex items-center gap-1.5 flex-wrap mt-0.5">
                          <span className="text-[11px] text-[var(--text-muted)]">
                            {tx.category}{tx.tag ? ` / ${tx.tag}` : ""}
                          </span>
                          {matchedRule && (
                            <span
                              className="inline-flex items-center gap-0.5 px-1.5 py-px rounded-full bg-violet-500/15 text-violet-400 text-[10px]"
                              title={`${t("tooltips.matchedRule")}: ${matchedRule.name}`}
                            >
                              <Wand2 size={9} />
                              {matchedRule.name}
                            </span>
                          )}
                        </div>
                      </div>
                      {/* Action buttons — hidden on small mobile, visible on sm+ */}
                      <div className="hidden sm:grid grid-cols-3 flex-shrink-0 w-[96px]">
                        <button
                          className={`w-[32px] h-[32px] flex items-center justify-center rounded-md transition-colors ${isEditing ? "bg-[var(--primary)]/20 text-[var(--primary)]" : "text-[var(--text-muted)]/40 hover:text-white hover:bg-[var(--surface-light)]"}`}
                          title={t("tooltips.editCategoryTag")}
                          onClick={() => (isEditing ? closeEditor() : openEditor(tx))}
                        >
                          <Tag size={13} />
                        </button>
                        <button
                          className="w-[32px] h-[32px] flex items-center justify-center rounded-md text-[var(--text-muted)]/40 hover:text-white hover:bg-[var(--surface-light)] transition-colors"
                          title={t("tooltips.splitTransaction")}
                          onClick={() => setSplittingTransaction(tx)}
                        >
                          <Split size={13} />
                        </button>
                        {tx.amount < 0 ? (
                          tx.pending_refund_id ? (
                            <span className="w-[32px] h-[32px] flex items-center justify-center text-amber-400" title={t("tooltips.pendingRefund")}>
                              <RefreshCw size={13} className="animate-pulse" />
                            </span>
                          ) : (
                            <button
                              className="w-[32px] h-[32px] flex items-center justify-center rounded-md text-amber-400/40 hover:text-amber-400 hover:bg-amber-500/20 transition-colors"
                              title={t("tooltips.markPendingRefund")}
                              onClick={() => markPendingMutation.mutate(tx)}
                              disabled={markPendingMutation.isPending}
                            >
                              <RefreshCw size={13} />
                            </button>
                          )
                        ) : (
                          <button
                            className="w-[32px] h-[32px] flex items-center justify-center rounded-md text-emerald-400/40 hover:text-emerald-400 hover:bg-emerald-500/20 transition-colors"
                            title={t("tooltips.linkAsRefund")}
                            onClick={() => setLinkingTransaction(tx)}
                          >
                            <Link2 size={13} />
                          </button>
                        )}
                      </div>
                      <span
                        className={`text-sm font-semibold flex-shrink-0 tabular-nums text-end w-[80px] ${
                          isPositive ? "text-emerald-400" : "text-rose-400"
                        }`}
                      >
                        {isPositive ? "+" : ""}
                        {formatCurrency(tx.amount)}
                      </span>
                    </div>

                    {/* Mobile action buttons — shown on tap */}
                    {mobileActionsTxKey === txKey && (
                      <div className="sm:hidden flex items-center gap-1.5 mx-2 mb-1 ms-9 p-1.5 rounded-lg bg-[var(--surface-light)]/40 border border-[var(--surface-light)] animate-in fade-in slide-in-from-top-1 duration-150">
                        <button
                          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium transition-colors ${isEditing ? "bg-[var(--primary)]/20 text-[var(--primary)]" : "text-[var(--text-muted)] hover:text-white hover:bg-[var(--surface-light)]"}`}
                          onClick={(e) => { e.stopPropagation(); if (isEditing) closeEditor(); else openEditor(tx); }}
                        >
                          <Tag size={13} className="shrink-0" />
                          {t("common.tag")}
                        </button>
                        <button
                          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium text-[var(--text-muted)] hover:text-white hover:bg-[var(--surface-light)] transition-colors"
                          onClick={(e) => { e.stopPropagation(); setSplittingTransaction(tx); }}
                        >
                          <Split size={13} className="shrink-0" />
                          {t("common.split")}
                        </button>
                        {tx.amount < 0 ? (
                          tx.pending_refund_id ? (
                            <span className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-amber-400">
                              <RefreshCw size={13} className="shrink-0 animate-pulse" />
                              {t("common.pending")}
                            </span>
                          ) : (
                            <button
                              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium text-amber-400/70 hover:text-amber-400 hover:bg-amber-500/20 transition-colors"
                              onClick={(e) => { e.stopPropagation(); markPendingMutation.mutate(tx); }}
                              disabled={markPendingMutation.isPending}
                            >
                              <RefreshCw size={13} className="shrink-0" />
                              {t("common.refund")}
                            </button>
                          )
                        ) : (
                          <button
                            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium text-emerald-400/70 hover:text-emerald-400 hover:bg-emerald-500/20 transition-colors"
                            onClick={(e) => { e.stopPropagation(); setLinkingTransaction(tx); }}
                          >
                            <Link2 size={13} className="shrink-0" />
                            {t("common.link")}
                          </button>
                        )}
                      </div>
                    )}

                    {/* Inline tag editing panel — selections are staged in
                        local state and only committed when the user taps Done.
                        This keeps the row's icon/label stable during editing
                        and avoids firing a mutation per dropdown change. */}
                    {isEditing && categories && (
                      <div className="mx-2 mb-2 ms-11 rounded-lg border border-[var(--surface-light)] bg-[var(--surface-light)]/20 overflow-hidden">
                        <div className="flex items-center gap-3 px-3 py-2">
                          <div className="flex-1 min-w-0">
                            <label className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] mb-1 block">{t("common.category")}</label>
                            <SelectDropdown
                              options={Object.keys(categories).map((c) => ({ label: c, value: c }))}
                              value={stagedCategory}
                              onChange={(cat) => {
                                setStagedCategory(cat);
                                if (stagedTag && !(categories[cat] || []).includes(stagedTag)) {
                                  setStagedTag("");
                                }
                              }}
                              placeholder={t("common.select")}
                              size="sm"
                              onCreateNew={async (name) => { await createCategory(name); }}
                            />
                          </div>
                          <div className="flex-1 min-w-0">
                            <label className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] mb-1 block">{t("common.tag")}</label>
                            <SelectDropdown
                              options={
                                stagedCategory && categories[stagedCategory]
                                  ? categories[stagedCategory].map((tagName: string) => ({ label: tagName, value: tagName }))
                                  : []
                              }
                              value={stagedTag}
                              onChange={setStagedTag}
                              placeholder={t("common.select")}
                              size="sm"
                              onCreateNew={
                                stagedCategory
                                  ? async (name) => { await createTag(stagedCategory, name); }
                                  : undefined
                              }
                            />
                          </div>
                          <button
                            className="self-end mb-0.5 px-2.5 py-1 text-[11px] font-medium rounded-md bg-[var(--primary)] text-white hover:bg-[var(--primary)]/90 transition-colors"
                            onClick={() => commitEdit(tx)}
                          >
                            {t("dashboard.done")}
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}

        {/* Sentinel element for infinite scroll */}
        <div ref={sentinelRef} className="h-1" />

        {hasMore && (
          <div className="flex justify-center py-2">
            <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
              <div className="w-4 h-4 border-2 border-[var(--primary)]/30 border-t-[var(--primary)] rounded-full animate-spin" />
              {t("common.loading")}
            </div>
          </div>
        )}
      </div>

      {/* Split Transaction Modal */}
      {splittingTransaction && (
        <SplitTransactionModal
          transaction={splittingTransaction}
          onClose={() => setSplittingTransaction(null)}
          onSuccess={() => {
            setSplittingTransaction(null);
            queryClient.invalidateQueries({ queryKey: ["transactions"] });
            invalidateAnalytics();
          }}
        />
      )}

      {/* Link Refund Modal (for positive/income transactions) */}
      {linkingTransaction && (
        <LinkRefundModal
          isOpen={!!linkingTransaction}
          onClose={() => setLinkingTransaction(null)}
          refundTransaction={{
            id: linkingTransaction.unique_id || linkingTransaction.id || 0,
            source: linkingTransaction.source || "unknown",
            amount: linkingTransaction.amount,
            description: linkingTransaction.description || "",
          }}
        />
      )}
    </div>
  );
}
