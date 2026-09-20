import { useState, useMemo, useRef, useCallback, useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import {
  Split,
  RefreshCw,
  Tag,
  Link2,
  MoreHorizontal,
  Pencil,
  Eraser,
  Info,
  Trash2,
  Filter,
} from "lucide-react";
import { transactionsApi, pendingRefundsApi } from "../../services/api";
import { SplitTransactionModal } from "../modals/SplitTransactionModal";
import { LinkRefundModal } from "../modals/LinkRefundModal";
import { TransactionEditorModal } from "../modals/TransactionEditorModal";
import { SelectDropdown } from "../common/SelectDropdown";
import { RuleQuickAction } from "../transactions/RuleQuickAction";
import { GoalLinkAction } from "../transactions/GoalLinkAction";
import { RecentTransactionDetails } from "./RecentTransactionDetails";
import { useCategoryTagCreate } from "../../hooks/useCategoryTagCreate";
import { useCategories } from "../../hooks/useCategories";
import { qkPrefix } from "../../services/queryKeys";
import type { Transaction } from "../../types/transaction";
import { Skeleton } from "../common/Skeleton";
import { useTranslation } from "react-i18next";
import { formatShortDate } from "../../utils/dateFormatting";
import { formatCurrency } from "../../utils/numberFormatting";
import { isToday, isYesterday } from "date-fns";
import i18n from "../../i18n";
import { usePendingRows } from "../../hooks/usePendingRows";
import { useConfirm, useNotify } from "../../context/DialogContext";

function formatTransactionDate(dateStr: string): string {
  const d = new Date(dateStr);
  if (isToday(d)) return i18n.t("common.today");
  if (isYesterday(d)) return i18n.t("common.yesterday");
  return formatShortDate(d);
}

const TRANSACTIONS_PAGE_SIZE = 20;

/** Same predicate the transactions page's "Only Untagged" filter uses. */
const isUntagged = (tx: Transaction) => !tx.tag || tx.tag === "-";

/** Manual entries are the only rows the backend lets us edit or delete. */
const isManualSource = (tx: Transaction) =>
  !!tx.source &&
  (tx.source.includes("cash") || tx.source.includes("manual_investment"));

const ACTION_BUTTON_CLASS =
  "flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium transition-colors whitespace-nowrap";

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
  const confirm = useConfirm();
  const notify = useNotify();
  const { createCategory, createTag } = useCategoryTagCreate();
  const [visibleCount, setVisibleCount] = useState(TRANSACTIONS_PAGE_SIZE);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const scrollRootRef = useRef<HTMLDivElement>(null);
  const [onlyUntagged, setOnlyUntagged] = useState(false);
  const [editingTxKey, setEditingTxKey] = useState<string | null>(null);
  const [stagedCategory, setStagedCategory] = useState<string>("");
  const [stagedTag, setStagedTag] = useState<string>("");
  const [actionsTxKey, setActionsTxKey] = useState<string | null>(null);
  const [detailsTxKey, setDetailsTxKey] = useState<string | null>(null);
  const [splittingTransaction, setSplittingTransaction] = useState<Transaction | null>(null);
  const [linkingTransaction, setLinkingTransaction] = useState<Transaction | null>(null);
  const [editingTransaction, setEditingTransaction] = useState<Transaction | null>(null);

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

  // Collapsing a row's action bar must take the panels it opened with it —
  // the category/tag editor and the details sheet are separate state, so
  // without this they stayed on screen under a row with no actions bar.
  const collapseRow = (txKey: string) => {
    setActionsTxKey((current) => (current === txKey ? null : current));
    setDetailsTxKey((current) => (current === txKey ? null : current));
    if (editingTxKey === txKey) closeEditor();
  };

  const toggleActions = (tx: Transaction) => {
    const txKey = txKeyOf(tx);
    if (actionsTxKey === txKey) {
      collapseRow(txKey);
      return;
    }
    // The details sheet is only reachable from a row's action bar, so it
    // follows whichever bar is open rather than lingering under a closed one.
    setActionsTxKey(txKey);
    setDetailsTxKey(null);
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

  const invalidateAnalytics = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: qkPrefix.analytics });
    queryClient.invalidateQueries({ queryKey: qkPrefix.budget });
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
        Array.isArray(old)
          ? old.map((t) => (sameRow(t) ? { ...t, category, tag: tag || undefined } : t))
          : old;
      queryClient.setQueriesData<Transaction[]>({ queryKey: qkPrefix.transactionsList }, patchList);
      queryClient.invalidateQueries({ queryKey: qkPrefix.categories });
      invalidateAnalytics();
    },
  });

  // Per row: marking one transaction must not disable the refund button on
  // every other row while the write is out. See `usePendingRows`.
  const markingRefund = usePendingRows();
  const clearingTagging = usePendingRows();

  const clearTaggingMutation = useMutation({
    mutationFn: (tx: Transaction) =>
      transactionsApi.update(String(tx.unique_id ?? tx.id), {
        source: tx.source || "",
        category: "",
        tag: "",
      }),
    onMutate: (tx) => clearingTagging.begin(txKeyOf(tx)),
    onSettled: (_data, _error, tx) => clearingTagging.end(txKeyOf(tx)),
    onSuccess: (_data, tx) => {
      const sameRow = (candidate: Transaction) =>
        candidate.source === tx.source &&
        (candidate.unique_id ?? candidate.id) === (tx.unique_id ?? tx.id);
      queryClient.setQueriesData<Transaction[]>(
        { queryKey: qkPrefix.transactionsList },
        (old) =>
          Array.isArray(old)
            ? old.map((candidate) =>
                sameRow(candidate)
                  ? { ...candidate, category: undefined, tag: undefined }
                  : candidate,
              )
            : old,
      );
      queryClient.invalidateQueries({ queryKey: qkPrefix.categories });
      invalidateAnalytics();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (tx: Transaction) =>
      transactionsApi.delete(String(tx.unique_id ?? tx.id), tx.source || ""),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.transactions });
      invalidateAnalytics();
    },
    onError: () => notify.error(t("transactions.failedDelete")),
  });

  const requestDelete = async (tx: Transaction) => {
    const ok = await confirm({
      title: t("transactions.deleteTransaction"),
      message: t("transactions.deleteConfirmation"),
      confirmLabel: t("common.delete"),
      isDestructive: true,
    });
    if (ok) deleteMutation.mutate(tx);
  };

  // Mark as pending refund
  const markPendingMutation = useMutation({
    mutationFn: (tx: Transaction) =>
      pendingRefundsApi.create({
        source_type: "transaction",
        source_id: tx.unique_id || "",
        source_table: tx.source || "",
        expected_amount: Math.abs(tx.amount),
      }),
    onMutate: (tx) => {
      markingRefund.begin(txKeyOf(tx));
    },
    onSettled: (_data, _error, tx) => markingRefund.end(txKeyOf(tx)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.transactions });
      queryClient.invalidateQueries({ queryKey: qkPrefix.pendingRefunds });
      invalidateAnalytics();
    },
  });

  const sorted = useMemo(() => {
    if (!transactions) return [];
    return [...transactions].sort(
      (a, b) => new Date(b.date).getTime() - new Date(a.date).getTime(),
    );
  }, [transactions]);

  const filtered = useMemo(
    () => (onlyUntagged ? sorted.filter(isUntagged) : sorted),
    [sorted, onlyUntagged],
  );
  const untaggedCount = useMemo(() => sorted.filter(isUntagged).length, [sorted]);

  const visible = useMemo(() => filtered.slice(0, visibleCount), [filtered, visibleCount]);
  const hasMore = visibleCount < filtered.length;

  // IntersectionObserver to auto-load more when sentinel enters viewport
  const handleObserver = useCallback(
    (entries: IntersectionObserverEntry[]) => {
      const [entry] = entries;
      if (entry.isIntersecting && hasMore) {
        setVisibleCount((prev) => Math.min(prev + TRANSACTIONS_PAGE_SIZE, filtered.length));
      }
    },
    [hasMore, filtered.length],
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

  // Reset the page size only when the feed is actually showing a different
  // dataset (demo-mode toggle, a new scrape, a split). Tagging a row rewrites
  // the cached array in place, and resetting on every new array identity threw
  // the reader back to the first 20 rows — losing the scroll position right
  // after the edit they had scrolled down to make.
  const datasetKey =
    sorted.length === 0
      ? "empty"
      : `${sorted.length}|${txKeyOf(sorted[0])}|${txKeyOf(sorted[sorted.length - 1])}`;
  const [lastDatasetKey, setLastDatasetKey] = useState(datasetKey);
  if (lastDatasetKey !== datasetKey) {
    // Adjusting state during render is React's documented way to reset derived
    // state on a prop change — an effect would render the stale page size first.
    setLastDatasetKey(datasetKey);
    setVisibleCount(TRANSACTIONS_PAGE_SIZE);
  }

  const toggleOnlyUntagged = () => {
    setOnlyUntagged((prev) => !prev);
    setVisibleCount(TRANSACTIONS_PAGE_SIZE);
    scrollRootRef.current?.scrollTo({ top: 0 });
  };

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
      <div className="flex items-center justify-between gap-2 mb-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
          {t("dashboard.recentTransactions")}
        </p>
        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={toggleOnlyUntagged}
            aria-pressed={onlyUntagged}
            aria-label={t("transactions.filters.onlyUntagged")}
            title={t("transactions.filters.onlyUntagged")}
            className={`flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-medium transition-colors ${
              onlyUntagged
                ? "bg-[var(--primary)]/20 text-[var(--primary)]"
                : "text-[var(--text-muted)] hover:text-white hover:bg-[var(--surface-light)]"
            }`}
          >
            <Filter size={13} className="shrink-0" />
            <span className="hidden sm:inline">{t("transactions.filters.onlyUntagged")}</span>
            <span className="tabular-nums" dir="ltr">
              ({untaggedCount})
            </span>
          </button>
          <Link
            to="/transactions"
            className="text-sm font-medium text-[var(--primary)] hover:underline whitespace-nowrap"
          >
            {t("dashboard.viewAll")} &rarr;
          </Link>
        </div>
      </div>

      <div
        ref={scrollRootRef}
        data-scroll-root=""
        className="max-h-[500px] overflow-y-auto space-y-4 scrollbar-auto-hide"
      >
        {filtered.length === 0 && (
          <p className="py-6 text-center text-sm text-[var(--text-muted)]">
            {t("dashboard.noUntaggedTransactions")}
          </p>
        )}
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
                const actionsOpen = actionsTxKey === txKey;
                const detailsOpen = detailsTxKey === txKey;
                const hasTagging = !!(tx.category || tx.tag);
                const manual = isManualSource(tx);

                return (
                  <div key={txKey}>
                    <div
                      data-testid="recent-tx-row"
                      className={`flex items-center gap-2 py-1 px-2 rounded-lg hover:bg-[var(--surface-light)]/40 transition-colors sm:cursor-default cursor-pointer ${actionsOpen ? "bg-[var(--surface-light)]/30" : ""}`}
                      onClick={() => {
                        // On mobile (< sm), tapping the row stands in for the
                        // "more actions" button the row has no space for.
                        if (window.innerWidth < 640) toggleActions(tx);
                      }}
                    >
                      <span className="text-lg flex-shrink-0 w-7 text-center">{icon || "?"}</span>
                      {/* Description and category/tag stack instead of
                          sharing one line. Side by side, the label was
                          `flex-shrink-0`, so a long "Category / Tag" pair
                          squeezed the description down to its ellipsis — and
                          even letting both shrink only split a column barely
                          wider than the label itself. */}
                      <div className="flex-1 min-w-0">
                        {!!tx.description && (
                          <p
                            className="text-sm truncate leading-tight"
                            title={tx.description}
                            dir="auto"
                          >
                            {tx.description}
                          </p>
                        )}
                        {!!tx.category && (
                          <p
                            data-testid="recent-tx-meta"
                            className="text-[11px] text-[var(--text-muted)] truncate leading-tight"
                            title={`${tx.category}${tx.tag ? ` / ${tx.tag}` : ""}`}
                            dir="auto"
                          >
                            {tx.category}{tx.tag ? ` / ${tx.tag}` : ""}
                          </p>
                        )}
                      </div>
                      {/* Quick actions — hidden on small mobile, visible on sm+.
                          Everything else lives behind the "more" toggle. */}
                      <div className="hidden sm:grid grid-cols-4 flex-shrink-0 w-[128px]">
                        <button
                          className={`w-[32px] h-[32px] flex items-center justify-center rounded-md transition-colors ${isEditing ? "bg-[var(--primary)]/20 text-[var(--primary)]" : "text-[var(--text-muted)]/40 hover:text-white hover:bg-[var(--surface-light)]"}`}
                          title={t("tooltips.editCategoryTag")}
                          onClick={(e) => { e.stopPropagation(); if (isEditing) closeEditor(); else openEditor(tx); }}
                        >
                          <Tag size={13} />
                        </button>
                        <button
                          className="w-[32px] h-[32px] flex items-center justify-center rounded-md text-[var(--text-muted)]/40 hover:text-white hover:bg-[var(--surface-light)] transition-colors"
                          title={t("tooltips.splitTransaction")}
                          onClick={(e) => { e.stopPropagation(); setSplittingTransaction(tx); }}
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
                              onClick={(e) => { e.stopPropagation(); markPendingMutation.mutate(tx); }}
                              disabled={markingRefund.isPending(txKeyOf(tx))}
                            >
                              <RefreshCw size={13} />
                            </button>
                          )
                        ) : (
                          <button
                            className="w-[32px] h-[32px] flex items-center justify-center rounded-md text-emerald-400/40 hover:text-emerald-400 hover:bg-emerald-500/20 transition-colors"
                            title={t("tooltips.linkAsRefund")}
                            onClick={(e) => { e.stopPropagation(); setLinkingTransaction(tx); }}
                          >
                            <Link2 size={13} />
                          </button>
                        )}
                        <button
                          className={`w-[32px] h-[32px] flex items-center justify-center rounded-md transition-colors ${actionsOpen ? "bg-[var(--surface-light)] text-white" : "text-[var(--text-muted)]/40 hover:text-white hover:bg-[var(--surface-light)]"}`}
                          title={t("tooltips.moreActions")}
                          aria-label={t("tooltips.moreActions")}
                          aria-expanded={actionsOpen}
                          onClick={(e) => { e.stopPropagation(); toggleActions(tx); }}
                        >
                          <MoreHorizontal size={13} />
                        </button>
                      </div>
                      <span
                        className={`text-sm font-semibold flex-shrink-0 tabular-nums text-end w-[80px] ${
                          isPositive ? "text-emerald-400" : "text-rose-400"
                        }`}
                        dir="ltr"
                      >
                        {isPositive ? "+" : ""}
                        {formatCurrency(tx.amount)}
                      </span>
                    </div>

                    {/* Full action bar — the same set the transactions table
                        offers per row, opened by the "more" button (or by
                        tapping the row on mobile). */}
                    {actionsOpen && (
                      <div className="flex flex-wrap items-center gap-1.5 mx-2 mb-1 ms-9 p-1.5 rounded-lg bg-[var(--surface-light)]/40 border border-[var(--surface-light)] animate-in fade-in slide-in-from-top-1 duration-150">
                        <button
                          className={`${ACTION_BUTTON_CLASS} ${isEditing ? "bg-[var(--primary)]/20 text-[var(--primary)]" : "text-[var(--text-muted)] hover:text-white hover:bg-[var(--surface-light)]"}`}
                          onClick={(e) => { e.stopPropagation(); if (isEditing) closeEditor(); else openEditor(tx); }}
                        >
                          <Tag size={13} className="shrink-0" />
                          {t("common.tag")}
                        </button>
                        <button
                          className={`${ACTION_BUTTON_CLASS} text-[var(--text-muted)] hover:text-white hover:bg-[var(--surface-light)] disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-[var(--text-muted)] disabled:cursor-not-allowed`}
                          title={t("transactions.bulk.clearCategoryTag")}
                          aria-label={t("transactions.bulk.clearCategoryTag")}
                          disabled={!hasTagging || clearingTagging.isPending(txKey)}
                          onClick={(e) => { e.stopPropagation(); clearTaggingMutation.mutate(tx); }}
                        >
                          <Eraser size={13} className="shrink-0" />
                          {t("common.clear")}
                        </button>
                        <RuleQuickAction
                          transactions={[tx]}
                          stagedCategory={isEditing ? stagedCategory : tx.category}
                          stagedTag={isEditing ? stagedTag : tx.tag}
                          variant="compact"
                        />
                        <button
                          className={`${ACTION_BUTTON_CLASS} text-[var(--text-muted)] hover:text-white hover:bg-[var(--surface-light)]`}
                          onClick={(e) => { e.stopPropagation(); setSplittingTransaction(tx); }}
                        >
                          <Split size={13} className="shrink-0" />
                          {t("common.split")}
                        </button>
                        <GoalLinkAction transaction={tx} variant="compact" />
                        {tx.amount < 0 ? (
                          tx.pending_refund_id ? (
                            <span className={`${ACTION_BUTTON_CLASS} text-amber-400`}>
                              <RefreshCw size={13} className="shrink-0 animate-pulse" />
                              {t("common.pending")}
                            </span>
                          ) : (
                            <button
                              className={`${ACTION_BUTTON_CLASS} text-amber-400/70 hover:text-amber-400 hover:bg-amber-500/20`}
                              onClick={(e) => { e.stopPropagation(); markPendingMutation.mutate(tx); }}
                              disabled={markingRefund.isPending(txKeyOf(tx))}
                            >
                              <RefreshCw size={13} className="shrink-0" />
                              {t("common.refund")}
                            </button>
                          )
                        ) : (
                          <button
                            className={`${ACTION_BUTTON_CLASS} text-emerald-400/70 hover:text-emerald-400 hover:bg-emerald-500/20`}
                            onClick={(e) => { e.stopPropagation(); setLinkingTransaction(tx); }}
                          >
                            <Link2 size={13} className="shrink-0" />
                            {t("common.link")}
                          </button>
                        )}
                        <button
                          className={`${ACTION_BUTTON_CLASS} ${detailsOpen ? "bg-[var(--primary)]/20 text-[var(--primary)]" : "text-[var(--text-muted)] hover:text-white hover:bg-[var(--surface-light)]"}`}
                          aria-expanded={detailsOpen}
                          onClick={(e) => {
                            e.stopPropagation();
                            setDetailsTxKey(detailsOpen ? null : txKey);
                          }}
                        >
                          <Info size={13} className="shrink-0" />
                          {t("common.details")}
                        </button>
                        {manual && (
                          <>
                            <button
                              className={`${ACTION_BUTTON_CLASS} text-[var(--text-muted)] hover:text-white hover:bg-[var(--surface-light)]`}
                              title={t("tooltips.editTransaction")}
                              onClick={(e) => { e.stopPropagation(); setEditingTransaction(tx); }}
                            >
                              <Pencil size={13} className="shrink-0" />
                              {t("common.edit")}
                            </button>
                            <button
                              className={`${ACTION_BUTTON_CLASS} text-rose-400/70 hover:text-rose-400 hover:bg-rose-500/20`}
                              title={t("tooltips.delete")}
                              disabled={deleteMutation.isPending}
                              onClick={(e) => { e.stopPropagation(); void requestDelete(tx); }}
                            >
                              <Trash2 size={13} className="shrink-0" />
                              {t("common.delete")}
                            </button>
                          </>
                        )}
                      </div>
                    )}

                    {detailsOpen && (
                      <div className="mx-2 mb-2 ms-9 rounded-lg border border-[var(--surface-light)] bg-[var(--surface-light)]/20 overflow-hidden">
                        <RecentTransactionDetails tx={tx} />
                      </div>
                    )}

                    {/* Inline tag editing panel — selections are staged in
                        local state and only committed when the user taps Done.
                        This keeps the row's icon/label stable during editing
                        and avoids firing a mutation per dropdown change. */}
                    {isEditing && categories && (
                      <div
                        data-testid="recent-tx-editor"
                        className="mx-2 mb-2 ms-11 rounded-lg border border-[var(--surface-light)] bg-[var(--surface-light)]/20 overflow-hidden"
                      >
                        <div className="flex flex-col gap-2 px-3 py-2 sm:flex-row sm:items-end sm:gap-3">
                          <div className="min-w-0 sm:flex-1">
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
                              onCreateNew={async (name) => {
                                const formatted = await createCategory(name);
                                setStagedCategory(formatted);
                                setStagedTag("");
                              }}
                            />
                          </div>
                          <div className="min-w-0 sm:flex-1">
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
                                  ? async (name) => {
                                      const formatted = await createTag(stagedCategory, name);
                                      setStagedTag(formatted);
                                    }
                                  : undefined
                              }
                            />
                          </div>
                          <button
                            className="self-end shrink-0 px-2.5 py-1 text-[11px] font-medium rounded-md bg-[var(--primary)] text-white hover:bg-[var(--primary)]/90 transition-colors sm:mb-0.5"
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
            queryClient.invalidateQueries({ queryKey: qkPrefix.transactions });
            invalidateAnalytics();
          }}
        />
      )}

      {/* Manual transaction editor */}
      {editingTransaction && (
        <TransactionEditorModal
          transaction={{
            ...editingTransaction,
            unique_id: String(editingTransaction.unique_id ?? editingTransaction.id ?? ""),
          }}
          onClose={() => setEditingTransaction(null)}
          onSuccess={() => {
            setEditingTransaction(null);
            queryClient.invalidateQueries({ queryKey: qkPrefix.transactions });
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
