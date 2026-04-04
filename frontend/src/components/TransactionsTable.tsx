import React, { useState, useMemo, useEffect, useRef, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Search,
  X,
  Split,
  Trash2,
  CheckCircle2,
  RefreshCw,
  Link2,
  Plus,
  Filter,
  ChevronUp,
  ChevronDown,
  Settings2,
} from "lucide-react";
import { SplitTransactionModal } from "./modals/SplitTransactionModal";
import { LinkRefundModal } from "./modals/LinkRefundModal";
import {
  transactionsApi,
  taggingApi,
  pendingRefundsApi,
  type PendingRefund,
} from "../services/api";
import { formatDate } from "../utils/dateFormatting";
import { humanizeProvider } from "../utils/textFormatting";
import { useTransactionFilters } from "../hooks/useTransactionFilters";
import { FilterPanel } from "./transactions/FilterPanel";
import { Pagination } from "./transactions/Pagination";
import { BulkActionsBar, type BulkEditData } from "./transactions/BulkActionsBar";
import { useCategoryTagCreate } from "../hooks/useCategoryTagCreate";
import { useCategories } from "../hooks/useCategories";
import { useCashBalances } from "../hooks/useCashBalances";
import { useTranslation } from "react-i18next";
import { formatCurrency } from "../utils/numberFormatting";
import type { Transaction } from "../types/transaction";


export interface TransactionsTableProps {
  transactions: Transaction[];

  // Feature toggles
  showSelection?: boolean;
  showBulkActions?: boolean; // Show floating bulk tagging bar
  showActions?: boolean;
  showDelete?: boolean;
  showFilter?: boolean;

  // Split parents filter (controlled by parent due to API dependency)
  showSplitParentsFilter?: boolean;
  includeSplitParents?: boolean;
  onIncludeSplitParentsChange?: (value: boolean) => void;

  // Pagination config
  rowsPerPage?: number;
  rowsPerPageOptions?: number[] | null;

  // Callbacks
  onTransactionUpdated?: () => void;
  onSelectionChange?: (ids: Set<string>) => void;
  onAddTransaction?: () => void;
  pendingRefundsMap?: Map<string, PendingRefund>;
  refundLinksMap?: Map<string, number>;

  // External filter control
  onlyUntagged?: boolean;

  // Styling
  compact?: boolean;
}

type SortDirection = "asc" | "desc" | null;

interface SortConfig {
  key: string;
  direction: SortDirection;
}

const getTransactionId = (tx: Transaction): string => {
  return `${tx.source || "unknown"}_${tx.unique_id || tx.id || ""}`;
};

const getDescription = (tx: Transaction): string => {
  return tx.description || tx.desc || "";
};

export const TransactionsTable: React.FC<TransactionsTableProps> = ({
  transactions,
  showSelection = false,
  showBulkActions = false,
  showActions = false,
  showDelete = false,
  showFilter = false,
  showSplitParentsFilter = false,
  includeSplitParents = false,
  onIncludeSplitParentsChange,
  rowsPerPage: initialRowsPerPage = 10,
  rowsPerPageOptions = null,
  onTransactionUpdated,
  onSelectionChange,
  onAddTransaction,
  pendingRefundsMap,
  refundLinksMap,
  onlyUntagged: onlyUntaggedProp,
  compact = false,
}) => {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { createCategory, createTag } = useCategoryTagCreate();
  // State
  const [currentPage, setCurrentPage] = useState(1);
  const [rowsPerPage, setRowsPerPage] = useState(initialRowsPerPage);
  const [sortConfig, setSortConfig] = useState<SortConfig>({
    key: "date",
    direction: "desc",
  });

  // Column visibility
  const [visibleColumns, setVisibleColumns] = useState<Set<string>>(
    () => new Set(["date", "account", "description", "category", "amount"])
  );
  const [columnDropdownOpen, setColumnDropdownOpen] = useState(false);
  const columnDropdownRef = useRef<HTMLDivElement>(null);

  // Category icons
  const { data: categoryIcons } = useQuery({
    queryKey: ["category-icons"],
    queryFn: () => taggingApi.getIcons().then((res) => res.data),
  });

  // Close column dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        columnDropdownRef.current &&
        !columnDropdownRef.current.contains(event.target as Node)
      ) {
        setColumnDropdownOpen(false);
      }
    };
    if (columnDropdownOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [columnDropdownOpen]);

  const toggleColumn = (column: string) => {
    setVisibleColumns((prev) => {
      const next = new Set(prev);
      if (next.has(column)) {
        next.delete(column);
      } else {
        next.add(column);
      }
      return next;
    });
  };
  const {
    filters,
    options: filterOptions,
    activeFilterCount,
    filteredTransactions,
    updateFilters,
    resetFilters,
  } = useTransactionFilters(transactions);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [filtersOpen, setFiltersOpen] = useState(false);

  // Modal state
  const [splittingTransaction, setSplittingTransaction] =
    useState<Transaction | null>(null);
  const [linkingTransaction, setLinkingTransaction] =
    useState<Transaction | null>(null);
  const [deletingTransaction, setDeletingTransaction] =
    useState<Transaction | null>(null);

  // Bulk actions state
  const [bulkEditData, setBulkEditData] = useState<BulkEditData>({
    date: "",
    description: "",
    amount: "",
    account_name: "",
    category: "",
    tag: "",
  });
  const [amountType, setAmountType] = useState<"expense" | "income">("expense");

  const { data: categories } = useCategories({ enabled: showBulkActions });
  const { data: cashBalances = [] } = useCashBalances({ enabled: showBulkActions });

  const invalidateAnalytics = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["income-outcome"] });
    queryClient.invalidateQueries({ queryKey: ["analytics-category"] });
    queryClient.invalidateQueries({ queryKey: ["sankey"] });
    queryClient.invalidateQueries({ queryKey: ["net-worth-over-time"] });
    queryClient.invalidateQueries({ queryKey: ["income-by-source"] });
    queryClient.invalidateQueries({ queryKey: ["monthly-expenses"] });
    queryClient.invalidateQueries({ queryKey: ["budget-analysis"] });
  }, [queryClient]);

  // Bulk tag mutation
  const bulkTagMutation = useMutation({
    mutationFn: (data: Parameters<typeof transactionsApi.bulkTag>[0]) => transactionsApi.bulkTag(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["cash-balances"] });
      invalidateAnalytics();
      setSelectedIds(new Set());
      setBulkEditData({ date: "", description: "", amount: "", account_name: "", category: "", tag: "" });
      onTransactionUpdated?.();
    },
  });

  // Pending refund mutation
  const markPendingMutation = useMutation({
    mutationFn: (tx: Transaction) =>
      pendingRefundsApi.create({
        source_type: "transaction",
        source_id: tx.unique_id || "",
        source_table: tx.source || "unknown",
        expected_amount: Math.abs(tx.amount),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["pendingRefunds"] });
      invalidateAnalytics();
      onTransactionUpdated?.();
    },
  });

  const cancelPendingMutation = useMutation({
    mutationFn: (pendingId: number) => pendingRefundsApi.cancel(pendingId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["pendingRefunds"] });
      invalidateAnalytics();
      onTransactionUpdated?.();
    },
  });

  const unlinkRefundMutation = useMutation({
    mutationFn: (linkId: number) => pendingRefundsApi.unlinkRefund(linkId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["pendingRefunds"] });
      invalidateAnalytics();
      onTransactionUpdated?.();
    },
  });

  // Reset page when transactions or filter changes
  useEffect(() => {
    setCurrentPage(1);
  }, [transactions, filters]);

  // Sync external onlyUntagged prop with internal filter
  useEffect(() => {
    if (onlyUntaggedProp !== undefined) {
      updateFilters({ onlyUntagged: onlyUntaggedProp });
    }
  }, [onlyUntaggedProp, updateFilters]);

  // Sync selection with parent
  useEffect(() => {
    onSelectionChange?.(selectedIds);
  }, [selectedIds, onSelectionChange]);

  // Reset bulk edit data when selection clears
  useEffect(() => {
    if (selectedIds.size === 0) {
      setBulkEditData({ date: "", description: "", amount: "", account_name: "", category: "", tag: "" });
      setAmountType("expense");
    }
  }, [selectedIds]);

  // Sort transactions
  const sortedTransactions = useMemo(() => {
    if (!sortConfig.key || !sortConfig.direction) return filteredTransactions;

    return [...filteredTransactions].sort((a, b) => {
      let aVal: string | number;
      let bVal: string | number;

      switch (sortConfig.key) {
        case "date":
          aVal = new Date(a.date).getTime();
          bVal = new Date(b.date).getTime();
          break;
        case "account":
        case "account_name":
          aVal = `${a.provider || ""} ${a.account_name || ""}`.toLowerCase();
          bVal = `${b.provider || ""} ${b.account_name || ""}`.toLowerCase();
          break;
        case "desc":
        case "description":
          aVal = getDescription(a).toLowerCase();
          bVal = getDescription(b).toLowerCase();
          break;
        case "category":
          aVal = `${a.category || ""} ${a.tag || ""}`.toLowerCase();
          bVal = `${b.category || ""} ${b.tag || ""}`.toLowerCase();
          break;
        case "amount":
          aVal = Math.abs(a.amount);
          bVal = Math.abs(b.amount);
          break;
        default:
          aVal = ((a as unknown as Record<string, unknown>)[sortConfig.key] ?? "") as string | number;
          bVal = ((b as unknown as Record<string, unknown>)[sortConfig.key] ?? "") as string | number;
      }

      if (aVal === bVal) return 0;
      if (aVal === null || aVal === undefined) return 1;
      if (bVal === null || bVal === undefined) return -1;

      const comparison = aVal < bVal ? -1 : 1;
      return sortConfig.direction === "asc" ? comparison : -comparison;
    });
  }, [filteredTransactions, sortConfig]);

  // Pagination
  const totalPages = Math.ceil(sortedTransactions.length / rowsPerPage);
  const paginatedTransactions = useMemo(() => {
    const startIndex = (currentPage - 1) * rowsPerPage;
    return sortedTransactions.slice(startIndex, startIndex + rowsPerPage);
  }, [sortedTransactions, currentPage, rowsPerPage]);

  const startRow = (currentPage - 1) * rowsPerPage + 1;
  const endRow = Math.min(currentPage * rowsPerPage, sortedTransactions.length);

  // Handlers
  const handleSort = (key: string) => {
    let direction: SortDirection = "asc";
    if (sortConfig.key === key) {
      if (sortConfig.direction === "asc") direction = "desc";
      else if (sortConfig.direction === "desc") direction = null;
    }
    setSortConfig({ key, direction });
  };

  const toggleSelection = (id: string) => {
    const newSelection = new Set(selectedIds);
    if (newSelection.has(id)) {
      newSelection.delete(id);
    } else {
      newSelection.add(id);
    }
    setSelectedIds(newSelection);
  };

  const toggleSelectAll = () => {
    if (selectedIds.size > 0) {
      setSelectedIds(new Set());
    } else {
      const allIds = paginatedTransactions.map((tx) => getTransactionId(tx));
      setSelectedIds(new Set(allIds));
    }
  };

  const isAllSelected = useMemo(() => {
    if (paginatedTransactions.length === 0) return false;
    return paginatedTransactions.every((tx) =>
      selectedIds.has(getTransactionId(tx)),
    );
  }, [paginatedTransactions, selectedIds]);

  const allSelectedAreCash = useMemo(() => {
    if (selectedIds.size === 0) return false;
    return transactions
      .filter((tx) => selectedIds.has(getTransactionId(tx)))
      .every((tx) => tx.source?.includes("cash"));
  }, [transactions, selectedIds]);

  const allSelectedAreManual = useMemo(() => {
    if (selectedIds.size === 0) return false;
    return transactions
      .filter((tx) => selectedIds.has(getTransactionId(tx)))
      .every((tx) => tx.source?.includes("cash") || tx.source?.includes("manual_investment"));
  }, [transactions, selectedIds]);

  const handleDelete = (tx: Transaction) => {
    setDeletingTransaction(tx);
  };

  const confirmDelete = async () => {
    if (!deletingTransaction) return;
    try {
      await transactionsApi.delete(deletingTransaction.unique_id || "", deletingTransaction.source || "");
      onTransactionUpdated?.();
    } catch {
      alert("Failed to delete transaction.");
    } finally {
      setDeletingTransaction(null);
    }
  };

  const handleModalSuccess = () => {
    setSplittingTransaction(null);
    onTransactionUpdated?.();
  };

  // Bulk edit handler
  const handleBulkApply = () => {
    const selectedTxs = transactions.filter((tx) =>
      selectedIds.has(getTransactionId(tx)),
    );
    const bySource = selectedTxs.reduce(
      (acc: Record<string, (string | number)[]>, tx) => {
        const source = tx.source || "unknown";
        if (!acc[source]) acc[source] = [];
        acc[source].push(tx.unique_id || tx.id || 0);
        return acc;
      },
      {},
    );

    Object.entries(bySource).forEach(([source, ids]) => {
      const isManualSource =
        source.includes("cash") || source.includes("manual_investment");
      const payload: Parameters<typeof transactionsApi.bulkTag>[0] = {
        transaction_ids: ids,
        source,
      };
      if (bulkEditData.category) payload.category = bulkEditData.category;
      if (bulkEditData.tag) payload.tag = bulkEditData.tag;
      if (isManualSource) {
        if (bulkEditData.date) payload.date = bulkEditData.date;
        if (bulkEditData.description) payload.description = bulkEditData.description;
        if (bulkEditData.amount) {
          const absAmount = Math.abs(parseFloat(bulkEditData.amount));
          payload.amount = amountType === "expense" ? -absAmount : absAmount;
        }
        if (bulkEditData.account_name) payload.account_name = bulkEditData.account_name;
      }
      bulkTagMutation.mutate(payload);
    });
  };

  const handleBulkDelete = async () => {
    if (
      !window.confirm(
        `Delete ${selectedIds.size} transactions? Only manual entries will be removed.`,
      )
    )
      return;
    const selectedTxs = transactions.filter((tx) =>
      selectedIds.has(getTransactionId(tx)),
    );
    const manualTxs = selectedTxs.filter(
      (tx) =>
        tx.source?.includes("cash") || tx.source?.includes("manual_investment"),
    );

    try {
      for (const tx of manualTxs) {
        await transactionsApi.delete(tx.unique_id || "", tx.source || "");
      }
      setSelectedIds(new Set());
      onTransactionUpdated?.();
    } catch {
      alert("Partial failure during bulk deletion.");
    }
  };

  // Sort icon component
  const SortIcon = ({ columnKey }: { columnKey: string }) => {
    if (sortConfig.key !== columnKey || !sortConfig.direction) {
      return (
        <ArrowUpDown
          size={14}
          className="ms-1 opacity-20 group-hover:opacity-50"
        />
      );
    }
    return sortConfig.direction === "asc" ? (
      <ArrowUp size={14} className="ms-1 text-[var(--primary)]" />
    ) : (
      <ArrowDown size={14} className="ms-1 text-[var(--primary)]" />
    );
  };

  // Header component
  const SortableHeader = ({
    label,
    sortKey,
    align = "left",
    width,
  }: {
    label: string;
    sortKey: string;
    align?: "left" | "right" | "center";
    width?: string;
  }) => (
    <th
      onClick={() => handleSort(sortKey)}
      style={{ width }}
      className={`px-4 ${compact ? "py-2" : "py-3"} text-sm font-medium text-[var(--text-muted)] cursor-pointer group hover:text-white transition-colors ${align === "right"
        ? "text-end"
        : align === "center"
          ? "text-center"
          : "text-start"
        }`}
    >
      <div
        className={`flex items-center ${align === "right" ? "justify-end" : align === "center" ? "justify-center" : "justify-start"}`}
      >
        <span className="truncate">{label}</span>
        <SortIcon columnKey={sortKey} />
      </div>
    </th>
  );

  // Calculate column count for empty state
  const columnCount = visibleColumns.size + (showSelection ? 1 : 0) + (showActions ? 1 : 0);


  return (
    <>

      {/* Filter Bar */}
      {showFilter && (
        <div className="mb-3 space-y-3">
          {/* Controls row — single line */}
          <div className="flex flex-wrap items-center gap-2 md:gap-3">
            <button
              type="button"
              onClick={() => setFiltersOpen(!filtersOpen)}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors shrink-0 ${
                filtersOpen || activeFilterCount > 0
                  ? "bg-[var(--primary)]/10 border-[var(--primary)]/30 text-[var(--primary)]"
                  : "bg-[var(--surface-base)] border-[var(--surface-light)] text-[var(--text-muted)] hover:border-[var(--primary)]/50"
              }`}
            >
              <Filter size={14} />
              {t("transactions.filters.title")}
              {activeFilterCount > 0 && (
                <span className="ms-0.5 px-1.5 py-0.5 text-[10px] font-bold rounded-full bg-[var(--primary)] text-white leading-none">
                  {activeFilterCount}
                </span>
              )}
              {filtersOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            </button>
            <div className="relative flex-1 min-w-[120px]">
              <Search
                size={14}
                className="absolute start-2.5 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
              />
              <input
                type="text"
                value={filters.filterText}
                onChange={(e) => updateFilters({ filterText: e.target.value })}
                placeholder={t("transactions.filters.search")}
                aria-label={t("transactions.filters.search")}
                className="w-full ps-8 pe-8 py-1.5 text-sm bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-lg focus:outline-none focus:ring-1 focus:ring-[var(--primary)] focus:border-[var(--primary)] text-[var(--text-default)] placeholder:text-[var(--text-muted)]"
              />
              {filters.filterText && (
                <button
                  onClick={() => updateFilters({ filterText: "" })}
                  aria-label={t("common.close")}
                  className="absolute end-2 top-1/2 -translate-y-1/2 p-0.5 text-[var(--text-muted)] hover:text-[var(--text-default)] transition-colors"
                >
                  <X size={14} />
                </button>
              )}
            </div>
            <div className="relative" ref={columnDropdownRef}>
              <button
                type="button"
                onClick={() => setColumnDropdownOpen(!columnDropdownOpen)}
                className={`flex items-center gap-1 px-2 py-1.5 text-xs rounded-lg border transition-colors shrink-0 ${
                  columnDropdownOpen
                    ? "bg-[var(--primary)]/10 border-[var(--primary)]/30 text-[var(--primary)]"
                    : "bg-[var(--surface-base)] border-[var(--surface-light)] text-[var(--text-muted)] hover:border-[var(--primary)]/50"
                }`}
                title={t("tooltips.toggleColumns")}
              >
                <Settings2 size={14} />
              </button>
              {columnDropdownOpen && (
                <div className="absolute top-full end-0 mt-1 bg-[var(--surface)] border border-[var(--surface-light)] rounded-lg shadow-xl z-30 py-1 min-w-[160px]">
                  {[
                    { key: "date", label: t("transactions.table.date") },
                    { key: "description", label: t("transactions.table.description") },
                    { key: "category", label: t("transactions.table.category") },
                    { key: "amount", label: t("transactions.table.amount") },
                    { key: "account", label: t("transactions.table.account") },
                  ].map(({ key, label }) => (
                    <label
                      key={key}
                      className="flex items-center gap-2 px-3 py-1.5 text-xs text-[var(--text-default)] hover:bg-[var(--surface-light)] cursor-pointer select-none"
                    >
                      <input
                        type="checkbox"
                        checked={visibleColumns.has(key)}
                        onChange={() => toggleColumn(key)}
                        className="w-3 h-3 rounded border-slate-700 bg-slate-800 text-blue-500 focus:ring-blue-500 cursor-pointer"
                      />
                      {label}
                    </label>
                  ))}
                </div>
              )}
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 bg-[var(--surface-light)]/20 rounded-lg border border-[var(--surface-light)]">
              <label
                className="text-xs font-medium text-[var(--text-muted)] cursor-pointer select-none whitespace-nowrap"
                htmlFor="table-untagged-only"
              >
                {t("transactions.filters.onlyUntagged")}
              </label>
              <input
                id="table-untagged-only"
                type="checkbox"
                checked={filters.onlyUntagged}
                onChange={(e) => updateFilters({ onlyUntagged: e.target.checked })}
                className="w-3 h-3 rounded border-slate-700 bg-slate-800 text-blue-500 focus:ring-blue-500 cursor-pointer"
              />
            </div>
            {showSplitParentsFilter && (
              <div className="flex items-center gap-2 px-3 py-1.5 bg-[var(--surface-light)]/20 rounded-lg border border-[var(--surface-light)]">
                <label
                  className="text-xs font-medium text-[var(--text-muted)] cursor-pointer select-none whitespace-nowrap"
                  htmlFor="table-split-parents"
                >
                  {t("transactions.filters.showSplitParents")}
                </label>
                <input
                  id="table-split-parents"
                  type="checkbox"
                  checked={includeSplitParents}
                  onChange={(e) => onIncludeSplitParentsChange?.(e.target.checked)}
                  className="w-3 h-3 rounded border-slate-700 bg-slate-800 text-blue-500 focus:ring-blue-500 cursor-pointer"
                />
              </div>
            )}
            {onAddTransaction && (
              <button
                onClick={onAddTransaction}
                className="flex items-center gap-2 px-3 py-1.5 bg-[var(--primary)] text-white rounded-lg hover:bg-[var(--primary-hover)] transition-colors text-xs font-medium shrink-0"
              >
                <Plus size={14} />
                <span>{t("transactions.addTransaction")}</span>
              </button>
            )}
            {(filters.filterText || activeFilterCount > 0) && (
              <span className="text-xs text-[var(--text-muted)] whitespace-nowrap">
                {filteredTransactions.length} {t("transactions.pagination.of")} {transactions.length}{" "}
                {t("transactions.title").toLowerCase()}
              </span>
            )}
          </div>
          {filtersOpen && (
            <FilterPanel
              filters={filters}
              options={filterOptions}
              onFilterChange={updateFilters}
              onReset={resetFilters}
              activeFilterCount={activeFilterCount}
              compact={compact}
            />
          )}
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-[var(--surface-light)]">
        <table className="w-full text-sm text-start">
          <thead className="bg-[var(--surface-light)] text-[var(--text-muted)] font-medium">
            <tr>
              {showSelection && (
                <th
                  className={`px-4 ${compact ? "py-2" : "py-3"} text-center hidden md:table-cell`}
                  style={{ width: "50px" }}
                >
                  <input
                    type="checkbox"
                    checked={isAllSelected}
                    onChange={toggleSelectAll}
                    className="rounded border-slate-700 bg-slate-800 text-blue-500 focus:ring-blue-500 cursor-pointer"
                  />
                </th>
              )}
              {visibleColumns.has("date") && (
                <SortableHeader label={t("transactions.table.date")} sortKey="date" width="120px" />
              )}
              {visibleColumns.has("description") && (
                <SortableHeader label={t("transactions.table.description")} sortKey="desc" />
              )}
              {visibleColumns.has("category") && (
                <SortableHeader
                  label={t("transactions.table.category")}
                  sortKey="category"
                  width="180px"
                />
              )}
              {visibleColumns.has("amount") && (
                <SortableHeader
                  label={t("transactions.table.amount")}
                  sortKey="amount"
                  align="right"
                  width="120px"
                />
              )}
              {visibleColumns.has("account") && (
                <SortableHeader label={t("transactions.table.account")} sortKey="account" width="180px" />
              )}
              {showActions && (
                <th
                  className={`px-4 ${compact ? "py-2" : "py-3"} text-center text-sm font-medium text-[var(--text-muted)]`}
                  style={{ width: "100px" }}
                >
                  {t("common.actions")}
                </th>
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--surface-light)] bg-[var(--surface-base)]">
            {paginatedTransactions.map((tx, idx) => {
              const id = getTransactionId(tx);
              const isSelected = selectedIds.has(id);
              const isManual =
                tx.source?.includes("cash") ||
                tx.source?.includes("manual_investment");

              return (
                <tr
                  key={id || idx}
                  className={`hover:bg-[var(--surface-light)]/50 transition-colors ${isSelected ? "bg-[var(--primary)]/5" : ""} ${showSelection ? "cursor-pointer" : ""}`}
                  onClick={(e) => {
                    if (!showSelection) return;
                    const target = e.target as HTMLElement;
                    if (target.closest("input, button, a, select")) return;
                    toggleSelection(id);
                  }}
                >
                  {showSelection && (
                    <td
                      className={`px-4 ${compact ? "py-2" : "py-3"} text-center hidden md:table-cell`}
                    >
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleSelection(id)}
                        className="rounded border-slate-700 bg-slate-800 text-blue-500 focus:ring-blue-500 cursor-pointer"
                      />
                    </td>
                  )}
                  {visibleColumns.has("date") && (
                    <td
                      className={`px-4 ${compact ? "py-2" : "py-3"} whitespace-nowrap text-[var(--text-muted)]`}
                    >
                      {formatDate(tx.date)}
                    </td>
                  )}
                  {visibleColumns.has("description") && (
                    <td
                      className={`px-4 ${compact ? "py-2" : "py-3"} text-[var(--text-default)] font-medium truncate max-w-[200px]`}
                      title={getDescription(tx)}
                    >
                      {getDescription(tx)}
                    </td>
                  )}
                  {visibleColumns.has("category") && (
                    <td
                      className={`px-4 ${compact ? "py-2" : "py-3"} text-[var(--text-muted)]`}
                    >
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[var(--surface-light)] text-xs whitespace-nowrap">
                        {categoryIcons?.[tx.category as string] && <span>{categoryIcons[tx.category as string]}</span>}
                        <span>{tx.category || "-"}</span>
                        {tx.tag && <span className="text-[var(--text-muted)]">/ {tx.tag}</span>}
                      </span>
                    </td>
                  )}
                  {visibleColumns.has("amount") && (
                    <td
                      className={`px-4 ${compact ? "py-2" : "py-3"} text-end font-bold whitespace-nowrap ${tx.amount > 0 ? "text-emerald-500" : "text-red-500"}`}
                    >
                      {new Intl.NumberFormat("he-IL", {
                        style: "currency",
                        currency: "ILS",
                      }).format(tx.amount)}
                    </td>
                  )}
                  {visibleColumns.has("account") && (
                    <td
                      className={`px-4 ${compact ? "py-2" : "py-3"} truncate max-w-[150px]`}
                      title={`${tx.provider ? humanizeProvider(tx.provider) : "Manual"} - ${tx.account_name}${tx.source === "credit_card_transactions" && tx.account_number ? ` (${tx.account_number.slice(-4)})` : ""}`}
                    >
                      <div className="flex flex-col">
                        <span className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-tight leading-none mb-1">
                          {tx.provider
                            ? humanizeProvider(tx.provider)
                            : tx.source?.includes("cash") ? "Cash" : "Manual"}
                        </span>
                        <span className="truncate font-medium text-[var(--text-default)]">
                          {tx.account_name}
                          {tx.source === "credit_card_transactions" && tx.account_number && (
                            <span className="text-[var(--text-muted)] ms-1">
                              ({tx.account_number.slice(-4)})
                            </span>
                          )}
                        </span>
                      </div>
                    </td>
                  )}
                  {showActions && (
                    <td className={`px-4 ${compact ? "py-2" : "py-3"}`}>
                      <div className="flex items-center justify-center gap-1">
                        <button
                          className="p-1.5 rounded-md hover:bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white transition-colors"
                          title={t("tooltips.splitTransaction")}
                          onClick={() => setSplittingTransaction(tx)}
                        >
                          <Split size={14} />
                        </button>
                        {/* Pending refund actions */}
                        {tx.amount < 0 &&
                          (() => {
                            const pending = pendingRefundsMap?.get(
                              getTransactionId(tx),
                            );

                            if (pending) {
                              if (pending.status === "resolved") {
                                return (
                                  <button
                                    className="p-1.5 rounded-md bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 transition-colors"
                                    title={t("tooltips.refundResolved")}
                                    onClick={() => {
                                      if (
                                        window.confirm(
                                          "This refund is marked as resolved. Do you want to remove this record?",
                                        )
                                      ) {
                                        cancelPendingMutation.mutate(
                                          pending.id,
                                        );
                                      }
                                    }}
                                    disabled={cancelPendingMutation.isPending}
                                  >
                                    <CheckCircle2 size={14} />
                                  </button>
                                );
                              }
                              if (pending.status === "partial") {
                                return (
                                  <button
                                    className="p-1.5 rounded-md bg-blue-500/20 text-blue-400 hover:bg-blue-500/30 transition-colors"
                                    title={`${t("tooltips.partiallyRefunded")} (${formatCurrency(pending.total_refunded || 0)} / ${formatCurrency(pending.expected_amount)}) - ${t("tooltips.clickToCancel")}`}
                                    onClick={() => {
                                      if (
                                        window.confirm(
                                          "Remove this partial refund request? Linked refunds will be unlinked.",
                                        )
                                      ) {
                                        cancelPendingMutation.mutate(
                                          pending.id,
                                        );
                                      }
                                    }}
                                    disabled={cancelPendingMutation.isPending}
                                  >
                                    <RefreshCw size={14} />
                                  </button>
                                );
                              }
                              return (
                                <button
                                  className="p-1.5 rounded-md bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 transition-colors"
                                  title={t("tooltips.cancelPendingRefund")}
                                  onClick={() => {
                                    if (
                                      window.confirm(
                                        "Remove this request? If it is linked to refunds, those links will be broken.",
                                      )
                                    ) {
                                      cancelPendingMutation.mutate(pending.id);
                                    }
                                  }}
                                  disabled={cancelPendingMutation.isPending}
                                >
                                  <RefreshCw
                                    size={14}
                                    className="animate-pulse"
                                  />
                                </button>
                              );
                            }
                            return (
                              <button
                                className="p-1.5 rounded-md hover:bg-amber-500/10 text-amber-400/70 hover:text-amber-400 transition-colors"
                                title={t("tooltips.markAsRefund")}
                                onClick={() => markPendingMutation.mutate(tx)}
                                disabled={markPendingMutation.isPending}
                              >
                                <RefreshCw size={14} />
                              </button>
                            );
                          })()}
                        {tx.amount > 0 &&
                          (() => {
                            // Check if this transaction is linked as a refund
                            const linkId = refundLinksMap?.get(
                              getTransactionId(tx),
                            );

                            if (linkId) {
                              return (
                                <button
                                  className="p-1.5 rounded-md bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 transition-colors"
                                  title={t("tooltips.linkedToPending")}
                                  onClick={() => {
                                    if (
                                      window.confirm(
                                        "Unlink this refund from the pending request?",
                                      )
                                    ) {
                                      unlinkRefundMutation.mutate(linkId);
                                    }
                                  }}
                                  disabled={unlinkRefundMutation.isPending}
                                >
                                  <Link2 size={14} />
                                </button>
                              );
                            }

                            return (
                              <button
                                className="p-1.5 rounded-md hover:bg-emerald-500/10 text-emerald-400/70 hover:text-emerald-400 transition-colors"
                                title={t("tooltips.linkAsRefund")}
                                onClick={() => setLinkingTransaction(tx)}
                              >
                                <Link2 size={14} />
                              </button>
                            );
                          })()}
                        {showDelete && isManual && (
                          <button
                            className="p-1.5 rounded-md hover:bg-red-500/10 text-red-400/70 hover:text-red-400 transition-colors"
                            title={t("tooltips.delete")}
                            onClick={() => handleDelete(tx)}
                          >
                            <Trash2 size={14} />
                          </button>
                        )}
                      </div>
                    </td>
                  )}
                </tr>
              );
            })}
            {sortedTransactions.length === 0 && (
              <tr>
                <td
                  colSpan={columnCount}
                  className={`px-4 ${compact ? "py-4" : "py-8"} text-center text-[var(--text-muted)]`}
                >
                  {filters.filterText || activeFilterCount > 0
                    ? t("transactions.noMatchingTransactions")
                    : t("transactions.noTransactionsFound")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <Pagination
        currentPage={currentPage}
        totalPages={totalPages}
        totalItems={sortedTransactions.length}
        startRow={startRow}
        endRow={endRow}
        rowsPerPage={rowsPerPage}
        rowsPerPageOptions={rowsPerPageOptions}
        onPageChange={setCurrentPage}
        onRowsPerPageChange={setRowsPerPage}
        compact={compact}
      />

      {/* Bulk Action Floating Bar */}
      {showBulkActions && selectedIds.size > 0 && (
        <BulkActionsBar
          selectedCount={selectedIds.size}
          bulkEditData={bulkEditData}
          onBulkEditDataChange={setBulkEditData}
          amountType={amountType}
          onAmountTypeChange={setAmountType}
          allSelectedAreManual={allSelectedAreManual}
          allSelectedAreCash={allSelectedAreCash}
          categories={categories}
          cashBalances={cashBalances}
          onApply={handleBulkApply}
          onBulkDelete={handleBulkDelete}
          onClearSelection={() => setSelectedIds(new Set())}
          onCreateCategory={createCategory}
          onCreateTag={createTag}
          isApplying={bulkTagMutation.isPending}
          showDelete={showDelete}
        />
      )}

      {/* Modals */}
      {splittingTransaction && (
        <SplitTransactionModal
          transaction={splittingTransaction}
          onClose={() => setSplittingTransaction(null)}
          onSuccess={handleModalSuccess}
        />
      )}
      {linkingTransaction && (
        <LinkRefundModal
          isOpen={!!linkingTransaction}
          onClose={() => setLinkingTransaction(null)}
          refundTransaction={{
            id: linkingTransaction.unique_id || linkingTransaction.id || 0,
            source: linkingTransaction.source || "unknown",
            amount: linkingTransaction.amount,
            description:
              linkingTransaction.description || linkingTransaction.desc || "",
          }}
        />
      )}

      {/* Delete Confirmation Modal */}
      {deletingTransaction && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setDeletingTransaction(null)}
          />
          <div className="relative bg-[var(--surface)] border border-[var(--surface-light)] rounded-xl p-6 shadow-2xl max-w-md w-full mx-4">
            <h3 className="text-lg font-semibold text-white mb-2">
              {t("transactions.deleteTransaction")}
            </h3>
            <p className="text-[var(--text-muted)] mb-6">
              {t("transactions.deleteConfirmation")}
              <br />
              <span className="text-[var(--text-default)] font-medium">
                {getDescription(deletingTransaction) || t("transactions.noDescription")}
              </span>
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setDeletingTransaction(null)}
                className="px-4 py-2 rounded-lg bg-[var(--surface-light)] hover:bg-[var(--surface-base)] text-[var(--text-default)] text-sm font-medium transition-colors"
              >
                {t("common.cancel")}
              </button>
              <button
                onClick={confirmDelete}
                className="px-4 py-2 rounded-lg bg-red-500 hover:bg-red-600 text-white text-sm font-medium transition-colors"
              >
                {t("common.delete")}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
