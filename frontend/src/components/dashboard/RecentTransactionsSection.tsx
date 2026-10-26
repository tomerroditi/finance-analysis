import { Fragment, useState, useMemo, useRef, useCallback, useEffect } from "react";
import type { ReactNode } from "react";
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
  Wand2,
  CreditCard,
  Landmark,
  Wallet,
  TrendingUp,
  Shield,
  Layers,
  CheckCircle2,
  CalendarMinus,
  CalendarPlus,
  CalendarClock,
} from "lucide-react";
import {
  transactionsApi,
  pendingRefundsApi,
  budgetMonthOverridesApi,
  type PendingRefund,
  type RefundLink,
  type BudgetMonthOverride,
} from "../../services/api";
import { SplitTransactionModal } from "../modals/SplitTransactionModal";
import { LinkRefundModal } from "../modals/LinkRefundModal";
import { TransactionEditorModal } from "../modals/TransactionEditorModal";
import { SelectDropdown } from "../common/SelectDropdown";
import { RuleQuickAction } from "../transactions/RuleQuickAction";
import { GoalLinkAction } from "../transactions/GoalLinkAction";
import { RecentTransactionDetails } from "./RecentTransactionDetails";
import { useCategoryTagCreate } from "../../hooks/useCategoryTagCreate";
import { useCategories } from "../../hooks/useCategories";
import { useTaggingRules } from "../../hooks/useTaggingRules";
import { isWithoutRule as matchesNoRule } from "../../utils/taggingRuleEval";
import { matchesSource, sourceOptions } from "../../utils/transactionSources";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { patchBudgetForRetag, widenForCascade } from "../budget/budgetOptimistic";
import {
  REFUND_WRITE_PLAN,
  UNCHANGED_BY_ROW_WRITE,
  patchTransactionLists,
  planMonthMove,
  removeFromTransactionLists,
  type MonthMove,
} from "../../writePlans";
import type { Transaction } from "../../types/transaction";
import { Skeleton } from "../common/Skeleton";
import { useTranslation } from "react-i18next";
import { formatShortDate } from "../../utils/dateFormatting";
import { formatCurrency } from "../../utils/numberFormatting";
import { isToday, isYesterday } from "date-fns";
import i18n from "../../i18n";
import { usePendingRows } from "../../hooks/usePendingRows";
import { useConfirm, useNotify } from "../../context/DialogContext";
import { useScrollCap } from "../../hooks/useScrollCap";
import { ForwardArrow } from "../common/ForwardArrow";

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

const SOURCE_ICONS: Record<string, typeof CreditCard> = {
  credit_card_transactions: CreditCard,
  bank_transactions: Landmark,
  cash_transactions: Wallet,
  manual_investment_transactions: TrendingUp,
  insurance_transactions: Shield,
};

/** Key the refund and month-override maps are built with. */
const mapKeyOf = (tx: Transaction) => `${tx.source || "unknown"}_${tx.unique_id || tx.id || ""}`;

const monthIndexLabel = (idx: number) =>
  new Date(Math.floor(idx / 12), idx % 12).toLocaleString(
    i18n.language === "he" ? "he-IL" : "en-US",
    { month: "long", year: "numeric" },
  );

const ACTION_BUTTON_CLASS =
  "flex items-center gap-1 px-1.5 py-1.5 rounded-md text-xs font-medium transition-colors whitespace-nowrap";

interface RecentTransactionsFeedProps {
  transactions: Transaction[] | undefined;
  categoryIcons: Record<string, string> | undefined;
  isLoading: boolean;
  /**
   * Render only the filters and the list, without the dashboard card around
   * them — for lists that live inside another card (the budget rules).
   */
  embedded?: boolean;
  onTransactionUpdated?: () => void;
  /** Refund state per row; without it a row only knows `pending_refund_id`. */
  pendingRefundsMap?: Map<string, PendingRefund>;
  refundLinksMap?: Map<string, RefundLink[]>;
  /** Set on the monthly budget — enables the per-row month move. */
  budgetMonth?: { overrides?: Map<string, BudgetMonthOverride> };
  /** Extra controls for the filters row. */
  filterExtras?: ReactNode;
}

export function RecentTransactionsFeed({
  transactions,
  categoryIcons,
  isLoading,
  embedded = false,
  onTransactionUpdated,
  pendingRefundsMap,
  refundLinksMap,
  budgetMonth,
  filterExtras,
}: RecentTransactionsFeedProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const qk = useQueryKeys();
  const confirm = useConfirm();
  const notify = useNotify();
  const { createCategory, createTag } = useCategoryTagCreate();
  const [visibleCount, setVisibleCount] = useState(TRANSACTIONS_PAGE_SIZE);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const [onlyUntagged, setOnlyUntagged] = useState(false);
  const [onlyWithoutRule, setOnlyWithoutRule] = useState(false);
  const [sourceFilter, setSourceFilter] = useState("");
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

  // Every write below goes through the app's mutation cache, which refreshes
  // after it following the plan its `onMutate` returns — none of them
  // invalidates anything itself, and the host's `onTransactionUpdated` is a
  // notification, not a refetch.

  /**
   * Show a category/tag write on the row and in every cached budget month
   * before the request goes out: this feed is the budget pools' tagging path
   * as well as the dashboard's. The retag plan refreshes the touched months
   * first and nothing a retag cannot change.
   */
  const patchRetag = useCallback(
    (tx: Transaction, category: string, tag: string) => {
      const edit = { source: tx.source || "", unique_id: tx.unique_id ?? tx.id ?? "", category, tag };
      const budget = patchBudgetForRetag(queryClient, [edit]);
      const restoreLists = patchTransactionLists(queryClient, [edit]);
      return {
        refresh: budget.refresh,
        restore: () => {
          budget.restore();
          restoreLists();
        },
      };
    },
    [queryClient],
  );

  const tagMutation = useMutation({
    mutationFn: ({ tx, category, tag }: { tx: Transaction; category: string; tag: string }) =>
      transactionsApi.updateTag(
        String(tx.unique_id ?? tx.id),
        category,
        tag,
        tx.source || "",
      ),
    onMutate: ({ tx, category, tag }) => patchRetag(tx, category, tag),
    onError: (_error, _vars, context) => context?.restore(),
    onSuccess: (res, _vars, context) => {
      widenForCascade(context?.refresh, res.data.refunds_retagged);
      onTransactionUpdated?.();
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
    onMutate: (tx) => {
      clearingTagging.begin(txKeyOf(tx));
      return patchRetag(tx, "", "");
    },
    onSettled: (_data, _error, tx) => clearingTagging.end(txKeyOf(tx)),
    onError: (_error, _tx, context) => context?.restore(),
    onSuccess: (res, _tx, context) => {
      widenForCascade(context?.refresh, res.data.refunds_retagged);
      onTransactionUpdated?.();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (tx: Transaction) =>
      transactionsApi.delete(String(tx.unique_id ?? tx.id), tx.source || ""),
    onMutate: (tx) => ({
      restore: removeFromTransactionLists(queryClient, [tx]),
      refresh: { skip: UNCHANGED_BY_ROW_WRITE },
    }),
    onError: (_error, _tx, context) => {
      context?.restore();
      notify.error(t("transactions.failedDelete"));
    },
    onSuccess: () => onTransactionUpdated?.(),
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
      return { refresh: REFUND_WRITE_PLAN };
    },
    onSettled: (_data, _error, tx) => markingRefund.end(txKeyOf(tx)),
    onSuccess: () => onTransactionUpdated?.(),
  });

  const cancellingRefund = usePendingRows<number>();
  const unlinkingRefund = usePendingRows<number>();

  const cancelPendingMutation = useMutation({
    mutationFn: (pendingId: number) => pendingRefundsApi.cancel(pendingId),
    onMutate: (pendingId) => {
      cancellingRefund.begin(pendingId);
      return { refresh: REFUND_WRITE_PLAN };
    },
    onSettled: (_data, _error, pendingId) => cancellingRefund.end(pendingId),
    onSuccess: () => onTransactionUpdated?.(),
  });

  const unlinkRefundMutation = useMutation({
    mutationFn: (linkId: number) => pendingRefundsApi.unlinkRefund(linkId),
    onMutate: (linkId) => {
      unlinkingRefund.begin(linkId);
      return { refresh: REFUND_WRITE_PLAN };
    },
    onSettled: (_data, _error, linkId) => unlinkingRefund.end(linkId),
    onSuccess: () => onTransactionUpdated?.(),
  });

  // Moves a row one month prior/next for monthly-budget bucketing only (the
  // backend caps the move at ±1 and drops the override at the real month).
  // The badge moves at once; see `planMonthMove` for what is refreshed.
  const monthOverrideMutation = useMutation({
    mutationFn: ({ tx, year, month }: MonthMove) =>
      budgetMonthOverridesApi.set({
        source_type: "transaction",
        source_id: tx.unique_id || "",
        source_table: tx.source || "unknown",
        override_year: year,
        override_month: month,
      }),
    onMutate: (move) => planMonthMove(queryClient, qk.budget.monthOverrides(), move),
    onError: (_error, _move, context) => context?.restore(),
    onSuccess: () => onTransactionUpdated?.(),
  });

  const requestCancelRefund = async (pending: PendingRefund) => {
    const prompt =
      pending.status === "resolved"
        ? { title: t("tooltips.refundResolved"), message: t("transactions.confirmRemoveResolvedRefund") }
        : pending.status === "partial"
          ? { title: t("transactions.refunds.partiallyRefunded"), message: t("transactions.confirmRemovePartialRefund") }
          : { title: t("tooltips.cancelPendingRefund"), message: t("transactions.confirmRemoveRefundRequest") };
    const ok = await confirm({ ...prompt, confirmLabel: t("common.remove"), isDestructive: true });
    if (ok) cancelPendingMutation.mutate(pending.id);
  };

  const requestUnlink = async (links: RefundLink[]) => {
    const ok = await confirm({
      title: t("transactions.refunds.unlink"),
      message:
        links.length > 1
          ? t("transactions.confirmUnlinkRefundMulti", { count: links.length })
          : t("transactions.confirmUnlinkRefund"),
      confirmLabel: t("transactions.refunds.unlink"),
      isDestructive: true,
    });
    if (ok) links.forEach((link) => unlinkRefundMutation.mutate(link.id));
  };

  const sorted = useMemo(() => {
    if (!transactions) return [];
    return [...transactions].sort(
      (a, b) => new Date(b.date).getTime() - new Date(a.date).getTime(),
    );
  }, [transactions]);

  // Undefined until the rules load: treating an empty list as "no rules"
  // would briefly flag every row.
  const { data: taggingRules } = useTaggingRules();
  const isWithoutRule = useMemo(
    () =>
      taggingRules
        ? (tx: Transaction) => matchesNoRule(taggingRules, tx)
        : undefined,
    [taggingRules],
  );

  const sources = useMemo(
    () =>
      sourceOptions(sorted).map((option) => {
        const Icon = option.source ? SOURCE_ICONS[option.source] ?? Layers : Layers;
        return { ...option, icon: <Icon size={13} /> };
      }),
    [sorted],
  );
  // A selection whose last transaction left the feed falls back to every source.
  const activeSource = sources.some((option) => option.value === sourceFilter)
    ? sourceFilter
    : "";
  const fromSource = useMemo(
    () => (activeSource ? sorted.filter((tx) => matchesSource(tx, activeSource)) : sorted),
    [sorted, activeSource],
  );

  const filtered = useMemo(
    () =>
      fromSource.filter(
        (tx) =>
          (!onlyUntagged || isUntagged(tx)) &&
          (!onlyWithoutRule || !isWithoutRule || isWithoutRule(tx)),
      ),
    [fromSource, onlyUntagged, onlyWithoutRule, isWithoutRule],
  );
  const untaggedCount = useMemo(() => fromSource.filter(isUntagged).length, [fromSource]);
  const withoutRuleCount = useMemo(
    () => (isWithoutRule ? fromSource.filter(isWithoutRule).length : undefined),
    [fromSource, isWithoutRule],
  );

  const visible = useMemo(() => filtered.slice(0, visibleCount), [filtered, visibleCount]);
  const hasMore = visibleCount < filtered.length;
  // The feed caps itself only once the cap hides a row (see `useScrollCap`):
  // a couple of transactions must not turn the card into a scroll region that
  // swallows the drag meant for the page.
  const [feedRef, feedCapped] = useScrollCap(500, visible.length);

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

  const resetFeedPosition = () => {
    setVisibleCount(TRANSACTIONS_PAGE_SIZE);
    feedRef.current?.scrollTo({ top: 0 });
  };

  const toggleOnlyUntagged = () => {
    setOnlyUntagged((prev) => !prev);
    resetFeedPosition();
  };

  const toggleOnlyWithoutRule = () => {
    setOnlyWithoutRule((prev) => !prev);
    resetFeedPosition();
  };

  const changeSource = (next: string) => {
    setSourceFilter(next);
    resetFeedPosition();
  };

  const emptyFilterMessage =
    activeSource || (onlyUntagged && onlyWithoutRule)
      ? t("dashboard.noFilteredTransactions")
      : onlyWithoutRule
        ? t("dashboard.noTransactionsWithoutRule")
        : t("dashboard.noUntaggedTransactions");

  const filterButtonClass = (active: boolean) =>
    `flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
      active
        ? "bg-[var(--primary)]/20 text-[var(--primary)]"
        : "text-[var(--text-muted)] hover:text-white hover:bg-[var(--surface-light)]"
    }`;

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
      <div className={embedded ? "" : "bg-[var(--surface)] rounded-2xl p-6 border border-[var(--surface-light)]"}>
        <Skeleton variant="text" lines={1} className="mb-4" />
        <Skeleton variant="text" lines={5} />
      </div>
    );
  }

  if (sorted.length === 0) {
    if (!embedded) return null;
    return (
      <p className="py-4 text-center text-sm text-[var(--text-muted)]">
        {t("transactions.noTransactionsFound")}
      </p>
    );
  }

  return (
    <div className={embedded ? "" : "bg-[var(--surface)] rounded-2xl p-4 md:p-6 border border-[var(--surface-light)]"}>
      {/* Title and "View All" share the top row; the filters get a row of
          their own beneath, starting from the reading edge. The card's width
          follows the dashboard grid, not the viewport, so a desktop column is
          too narrow for all three controls beside the title. */}
      <div className={embedded ? "mb-3" : "mb-4 space-y-2"}>
        {!embedded && (
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
            {t("dashboard.recentTransactions")}
          </p>
          <Link
            to="/transactions"
            className="text-sm font-medium text-[var(--primary)] hover:underline whitespace-nowrap shrink-0"
          >
            {t("dashboard.viewAll")} <ForwardArrow />
          </Link>
        </div>
        )}
        {/* -ms-2 cancels the chips' px-2, so an inactive chip's icon lines up
            with the title above it. */}
        <div data-testid="recent-tx-filters" className="flex flex-wrap items-center gap-2 -ms-2">
          <button
            type="button"
            onClick={toggleOnlyUntagged}
            aria-pressed={onlyUntagged}
            aria-label={t("transactions.filters.onlyUntagged")}
            title={t("transactions.filters.onlyUntagged")}
            className={filterButtonClass(onlyUntagged)}
          >
            <Filter size={13} className="shrink-0" />
            <span className="hidden sm:inline">{t("transactions.filters.onlyUntagged")}</span>
            <span className="tabular-nums" dir="ltr">
              ({untaggedCount})
            </span>
          </button>
          <button
            type="button"
            onClick={toggleOnlyWithoutRule}
            disabled={!isWithoutRule}
            aria-pressed={onlyWithoutRule}
            aria-label={t("transactions.filters.withoutRule")}
            title={t("transactions.filters.withoutRuleHint")}
            className={filterButtonClass(onlyWithoutRule)}
          >
            <Wand2 size={13} className="shrink-0" />
            <span className="hidden sm:inline">{t("transactions.filters.withoutRule")}</span>
            {withoutRuleCount !== undefined && (
              <span className="tabular-nums" dir="ltr">
                ({withoutRuleCount})
              </span>
            )}
          </button>
          {sources.length > 2 && (
            <div data-testid="recent-tx-source" className="min-w-0 max-w-[14rem]">
              <SelectDropdown
                size="sm"
                value={activeSource}
                onChange={changeSource}
                options={sources}
                triggerClassName={`whitespace-nowrap !text-xs font-medium ${
                  activeSource ? "!border-[var(--primary)] text-[var(--primary)]" : ""
                }`}
              />
            </div>
          )}
          {filterExtras}
        </div>
      </div>

      <div
        ref={feedRef}
        data-scroll-root=""
        className={`scrollbar-auto-hide ${
          feedCapped ? "max-h-[500px] overflow-y-auto" : ""
        }`}
      >
        {filtered.length === 0 && (
          <p className="py-6 text-center text-sm text-[var(--text-muted)]">
            {emptyFilterMessage}
          </p>
        )}
        {/* Date headers are direct children of the scroll root, not of a
            per-group wrapper. A sticky element only stays pinned while its
            containing block is on screen: wrapped, each header unpinned the
            moment its own group ended and the next had not reached the top
            yet, leaving a sliver of the outgoing group's last row above the
            pinned date. Sharing the scroll root keeps a date pinned at all
            times — but they then all pin at 0 and stack, so the incoming one
            slides up *over* the outgoing one instead of pushing it, and for
            the ~30px that takes, a clipped band of the previous date showed
            above the current one. Same thin line, made of a date.

            The upward box-shadow closes that. Three numbers are equal on
            purpose: the header is 28px tall (pt-1 + a 16px line + pb-2), the
            shadow reaches 28px above it (26px offset + 2px spread), and the
            gap between groups is 28px (mt-7). Pinned, the shadow is clipped by
            the scroll port and hides the outgoing header for the whole
            overlap, so the date swaps in one frame; unpinned, it fills exactly
            the gap and stops at the previous row's edge, surface over surface.
            The offset/spread split is what makes the shadow *overlap* the
            header's own background rather than abut it — abutting edges snap
            to device pixels independently and left a one-pixel seam of the
            covered date showing through. `stickyDateHeader.test.ts` pins all
            three numbers together. */}
        {grouped.map((group, groupIndex) => (
          <Fragment key={group.label}>
            <p
              data-testid="recent-tx-date"
              className={`text-xs font-semibold text-[var(--text-muted)] sticky top-0 z-10 bg-[var(--surface)] pt-1 pb-2 shadow-[0_-26px_0_2px_var(--surface)] ${
                groupIndex > 0 ? "mt-7" : ""
              }`}
            >
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
                const mapKey = mapKeyOf(tx);
                const pending = pendingRefundsMap?.get(mapKey);
                const isRefundPending = !!pending || !!tx.pending_refund_id;
                const links = refundLinksMap?.get(mapKey) ?? [];
                const unlinkedAmount = tx.amount - links.reduce((sum, link) => sum + link.amount, 0);
                let monthMove: { origIdx: number; curIdx: number; moved: boolean } | null = null;
                if (budgetMonth) {
                  const d = new Date(tx.date);
                  const origIdx = d.getFullYear() * 12 + d.getMonth();
                  const override = budgetMonth.overrides?.get(mapKey);
                  const curIdx = override
                    ? override.override_year * 12 + (override.override_month - 1)
                    : origIdx;
                  monthMove = { origIdx, curIdx, moved: !!override };
                }
                const moveTo = (idx: number) =>
                  monthOverrideMutation.mutate({
                    tx,
                    fromYear: Math.floor((monthMove?.curIdx ?? idx) / 12),
                    fromMonth: ((monthMove?.curIdx ?? idx) % 12) + 1,
                    year: Math.floor(idx / 12),
                    month: (idx % 12) + 1,
                  });

                return (
                  <div key={txKey} data-tx-key={mapKey}>
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
                          isRefundPending ? (
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
                        ) : links.length > 0 ? (
                          <button
                            className="w-[32px] h-[32px] flex items-center justify-center rounded-md text-purple-400 hover:bg-purple-500/20 transition-colors"
                            title={`${t("tooltips.linkedToPending")} (${formatCurrency(tx.amount - unlinkedAmount)})`}
                            disabled={links.some((link) => unlinkingRefund.isPending(link.id))}
                            onClick={(e) => { e.stopPropagation(); void requestUnlink(links); }}
                          >
                            <Link2 size={13} />
                          </button>
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
                      {/* Every row of a monthly-budget list keeps this slot,
                          moved or not, so the badge never shifts one row's
                          action and amount columns out of line. */}
                      {monthMove && (
                        <span
                          data-testid="recent-tx-month-slot"
                          className="flex-shrink-0 w-[14px] text-amber-400"
                        >
                          {monthMove.moved && (
                            <span
                              data-testid="recent-tx-month-moved"
                              title={t("budget.monthMove.movedBadge", {
                                from: monthIndexLabel(monthMove.origIdx),
                                to: monthIndexLabel(monthMove.curIdx),
                              })}
                            >
                              <CalendarClock size={13} />
                            </span>
                          )}
                        </span>
                      )}
                      <div className="flex-shrink-0 w-[80px] text-end">
                        <span
                          className={`block text-sm font-semibold tabular-nums ${
                            isPositive ? "text-emerald-400" : "text-rose-400"
                          }`}
                          dir="ltr"
                        >
                          {isPositive ? "+" : ""}
                          {formatCurrency(tx.amount)}
                        </span>
                        {/* A pool counts a refunded purchase net of its
                            refund but lists it gross; say what it counts for. */}
                        {tx.net_amount != null && (
                          <span
                            data-testid="tx-net-amount"
                            className="block text-[10px] leading-tight text-[var(--text-muted)]"
                            dir="auto"
                          >
                            {tx.amount > 0
                              ? t("transactions.table.refundNetted")
                              : t("transactions.table.afterRefunds", {
                                  amount: formatCurrency(tx.net_amount),
                                })}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Full action bar — the same set the transactions table
                        offers per row, opened by the "more" button (or by
                        tapping the row on mobile). */}
                    {actionsOpen && (
                      <div
                        data-testid="recent-tx-actions"
                        className="flex flex-wrap items-center gap-1 mx-2 mb-1 p-1.5 rounded-lg bg-[var(--surface-light)]/40 border border-[var(--surface-light)] animate-in fade-in slide-in-from-top-1 duration-150"
                      >
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
                          pending ? (
                            <button
                              className={`${ACTION_BUTTON_CLASS} ${
                                pending.status === "resolved"
                                  ? "bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30"
                                  : pending.status === "partial"
                                    ? "bg-blue-500/20 text-blue-400 hover:bg-blue-500/30"
                                    : "bg-amber-500/20 text-amber-400 hover:bg-amber-500/30"
                              }`}
                              title={
                                pending.status === "resolved"
                                  ? t("tooltips.refundResolved")
                                  : pending.status === "partial"
                                    ? `${t("transactions.refunds.partiallyRefunded")} (${formatCurrency(pending.total_refunded || 0)} / ${formatCurrency(pending.expected_amount)}) - ${t("transactions.refunds.clickToCancel")}`
                                    : t("tooltips.cancelPendingRefund")
                              }
                              disabled={cancellingRefund.isPending(pending.id)}
                              onClick={(e) => { e.stopPropagation(); void requestCancelRefund(pending); }}
                            >
                              {pending.status === "resolved" ? (
                                <CheckCircle2 size={13} className="shrink-0" />
                              ) : (
                                <RefreshCw size={13} className={`shrink-0 ${pending.status === "partial" ? "" : "animate-pulse"}`} />
                              )}
                              {t(`transactions.refunds.status.${pending.status === "resolved" || pending.status === "partial" ? pending.status : "pending"}`)}
                            </button>
                          ) : tx.pending_refund_id ? (
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
                          <>
                            {links.length > 0 && (
                              <button
                                className={`${ACTION_BUTTON_CLASS} bg-purple-500/20 text-purple-400 hover:bg-purple-500/30`}
                                title={`${t("tooltips.linkedToPending")} (${formatCurrency(tx.amount - unlinkedAmount)})`}
                                disabled={links.some((link) => unlinkingRefund.isPending(link.id))}
                                onClick={(e) => { e.stopPropagation(); void requestUnlink(links); }}
                              >
                                <Link2 size={13} className="shrink-0" />
                                {t("transactions.refunds.unlink")}
                              </button>
                            )}
                            {(links.length === 0 || unlinkedAmount > 0.005) && (
                              <button
                                className={`${ACTION_BUTTON_CLASS} text-emerald-400/70 hover:text-emerald-400 hover:bg-emerald-500/20`}
                                title={
                                  links.length > 0
                                    ? `${t("tooltips.linkAsRefund")} (${formatCurrency(unlinkedAmount)})`
                                    : undefined
                                }
                                onClick={(e) => { e.stopPropagation(); setLinkingTransaction(tx); }}
                              >
                                <Link2 size={13} className="shrink-0" />
                                {t("common.link")}
                              </button>
                            )}
                          </>
                        )}
                        {monthMove && (
                          <>
                            <button
                              className={`${ACTION_BUTTON_CLASS} text-[var(--text-muted)] hover:text-white hover:bg-[var(--surface-light)] disabled:opacity-40 disabled:cursor-not-allowed`}
                              title={t("budget.monthMove.toPrevMonth")}
                              disabled={monthMove.curIdx < monthMove.origIdx || monthOverrideMutation.isPending}
                              onClick={(e) => { e.stopPropagation(); moveTo(monthMove.curIdx - 1); }}
                            >
                              <CalendarMinus size={13} className="shrink-0" />
                              {t("budget.monthMove.prevShort")}
                            </button>
                            <button
                              className={`${ACTION_BUTTON_CLASS} text-[var(--text-muted)] hover:text-white hover:bg-[var(--surface-light)] disabled:opacity-40 disabled:cursor-not-allowed`}
                              title={t("budget.monthMove.toNextMonth")}
                              disabled={monthMove.curIdx > monthMove.origIdx || monthOverrideMutation.isPending}
                              onClick={(e) => { e.stopPropagation(); moveTo(monthMove.curIdx + 1); }}
                            >
                              <CalendarPlus size={13} className="shrink-0" />
                              {t("budget.monthMove.nextShort")}
                            </button>
                          </>
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
                      <div className="mx-2 mb-2 rounded-lg border border-[var(--surface-light)] bg-[var(--surface-light)]/20 overflow-hidden">
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
          </Fragment>
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
            onTransactionUpdated?.();
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
            onTransactionUpdated?.();
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
            category: linkingTransaction.category ?? null,
            tag: linkingTransaction.tag ?? null,
            splitId: linkingTransaction.split_id ?? null,
          }}
        />
      )}
    </div>
  );
}
