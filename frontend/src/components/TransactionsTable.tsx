import React, { useState, useMemo, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Search,
  X,
  Edit2,
  Split,
  Trash2,
  CheckCircle2,
  RefreshCw,
  Link2,
  Plus,
  Filter,
  ChevronUp,
  ChevronDown,
} from "lucide-react";
import { TransactionEditorModal } from "./modals/TransactionEditorModal";
import { SplitTransactionModal } from "./modals/SplitTransactionModal";
import { LinkRefundModal } from "./modals/LinkRefundModal";
import {
  transactionsApi,
  taggingApi,
  pendingRefundsApi,
  cashBalancesApi,
} from "../services/api";
import { formatDate } from "../utils/dateFormatting";
import { useTransactionFilters } from "../hooks/useTransactionFilters";
import { FilterPanel } from "./transactions/FilterPanel";
import { SelectDropdown } from "./common/SelectDropdown";

export interface Transaction {
  id?: any;
  unique_id?: any;
  source?: string;
  desc?: string;
  description?: string;
  amount: number;
  date: string;
  category?: string;
  tag?: string;
  provider?: string;
  account_name?: string;
  pending_refund_id?: number; // ID if this transaction has a pending refund
}

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
  pendingRefundsMap?: Map<string, any>;
  refundLinksMap?: Map<string, number>;

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
  compact = false,
}) => {
  const queryClient = useQueryClient();
  // State
  const [currentPage, setCurrentPage] = useState(1);
  const [rowsPerPage, setRowsPerPage] = useState(initialRowsPerPage);
  const [sortConfig, setSortConfig] = useState<SortConfig>({
    key: "date",
    direction: "desc",
  });
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
  const [editingTransaction, setEditingTransaction] =
    useState<Transaction | null>(null);
  const [splittingTransaction, setSplittingTransaction] =
    useState<Transaction | null>(null);
  const [linkingTransaction, setLinkingTransaction] =
    useState<Transaction | null>(null);
  const [deletingTransaction, setDeletingTransaction] =
    useState<Transaction | null>(null);

  // Bulk actions state
  const [bulkMode, setBulkMode] = useState<"tag" | "account" | null>(null);
  const [bulkTagData, setBulkTagData] = useState({ category: "", tag: "" });
  const [bulkCashData, setBulkCashData] = useState({
    description: "",
    account_name: "",
    date: "",
  });

  // Fetch categories for bulk tagging
  const { data: categories } = useQuery({
    queryKey: ["categories"],
    queryFn: () => taggingApi.getCategories().then((res) => res.data),
    enabled: showBulkActions,
  });

  // Fetch cash balances for bulk account dropdown
  const { data: cashBalances = [] } = useQuery({
    queryKey: ["cash-balances"],
    queryFn: () => cashBalancesApi.getAll().then((res) => res.data),
    enabled: showBulkActions,
  });

  // Bulk tag mutation
  const bulkTagMutation = useMutation({
    mutationFn: (data: any) => transactionsApi.bulkTag(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["cash-balances"] });
      setSelectedIds(new Set());
      setBulkMode(null);
      setBulkTagData({ category: "", tag: "" });
      setBulkCashData({ description: "", account_name: "", date: "" });
      onTransactionUpdated?.();
    },
  });

  // Pending refund mutation
  const markPendingMutation = useMutation({
    mutationFn: (tx: Transaction) =>
      pendingRefundsApi.create({
        source_type: "transaction",
        source_id: tx.unique_id,
        source_table: tx.source || "unknown",
        expected_amount: Math.abs(tx.amount),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["budgetAnalysis"] });
      queryClient.invalidateQueries({ queryKey: ["pendingRefunds"] });
      onTransactionUpdated?.();
    },
  });

  const cancelPendingMutation = useMutation({
    mutationFn: (pendingId: number) => pendingRefundsApi.cancel(pendingId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["budgetAnalysis"] });
      queryClient.invalidateQueries({ queryKey: ["pendingRefunds"] });
      onTransactionUpdated?.();
    },
  });

  const unlinkRefundMutation = useMutation({
    mutationFn: (linkId: number) => pendingRefundsApi.unlinkRefund(linkId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["budgetAnalysis"] });
      queryClient.invalidateQueries({ queryKey: ["pendingRefunds"] });
      onTransactionUpdated?.();
    },
  });

  // Reset page when transactions or filter changes
  useEffect(() => {
    setCurrentPage(1);
  }, [transactions, filters]);

  // Sync selection with parent
  useEffect(() => {
    onSelectionChange?.(selectedIds);
  }, [selectedIds, onSelectionChange]);

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
          aVal = (a as any)[sortConfig.key] ?? "";
          bVal = (b as any)[sortConfig.key] ?? "";
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

  const handleDelete = (tx: Transaction) => {
    setDeletingTransaction(tx);
  };

  const confirmDelete = async () => {
    if (!deletingTransaction) return;
    try {
      await transactionsApi.delete(deletingTransaction.unique_id, deletingTransaction.source || "");
      onTransactionUpdated?.();
    } catch (err) {
      alert("Failed to delete transaction.");
    } finally {
      setDeletingTransaction(null);
    }
  };

  const handleModalSuccess = () => {
    setEditingTransaction(null);
    setSplittingTransaction(null);
    onTransactionUpdated?.();
  };

  // Bulk tagging handlers
  const handleBulkTag = () => {
    const selectedTxs = transactions.filter((tx) =>
      selectedIds.has(getTransactionId(tx)),
    );
    const bySource = selectedTxs.reduce((acc: any, tx) => {
      const source = tx.source || "unknown";
      if (!acc[source]) acc[source] = [];
      acc[source].push(tx.unique_id || tx.id);
      return acc;
    }, {});

    Object.entries(bySource).forEach(([source, ids]: [any, any]) => {
      const isCashSource = (source as string).includes("cash");

      if (bulkMode === "tag") {
        bulkTagMutation.mutate({
          transaction_ids: ids,
          source,
          category: bulkTagData.category || undefined,
          tag: bulkTagData.tag || undefined,
        });
      } else if (bulkMode === "account" && isCashSource) {
        bulkTagMutation.mutate({
          transaction_ids: ids,
          source,
          account_name: bulkCashData.account_name || undefined,
        });
      }
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
        await transactionsApi.delete(tx.unique_id, tx.source || "");
      }
      setSelectedIds(new Set());
      onTransactionUpdated?.();
    } catch (err) {
      alert("Partial failure during bulk deletion.");
    }
  };

  // Sort icon component
  const SortIcon = ({ columnKey }: { columnKey: string }) => {
    if (sortConfig.key !== columnKey || !sortConfig.direction) {
      return (
        <ArrowUpDown
          size={14}
          className="ml-1 opacity-20 group-hover:opacity-50"
        />
      );
    }
    return sortConfig.direction === "asc" ? (
      <ArrowUp size={14} className="ml-1 text-[var(--primary)]" />
    ) : (
      <ArrowDown size={14} className="ml-1 text-[var(--primary)]" />
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
        ? "text-right"
        : align === "center"
          ? "text-center"
          : "text-left"
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
  const columnCount = 5 + (showSelection ? 1 : 0) + (showActions ? 1 : 0);


  return (
    <>

      {/* Filter Bar */}
      {showFilter && (
        <div className="mb-3 space-y-3">
          {/* Controls row — single line */}
          <div className="flex items-center gap-3">
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
              Filters
              {activeFilterCount > 0 && (
                <span className="ml-0.5 px-1.5 py-0.5 text-[10px] font-bold rounded-full bg-[var(--primary)] text-white leading-none">
                  {activeFilterCount}
                </span>
              )}
              {filtersOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            </button>
            <div className="relative flex-1 min-w-0">
              <Search
                size={14}
                className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
              />
              <input
                type="text"
                value={filters.filterText}
                onChange={(e) => updateFilters({ filterText: e.target.value })}
                placeholder="Search transactions..."
                className="w-full pl-8 pr-8 py-1.5 text-sm bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-lg focus:outline-none focus:ring-1 focus:ring-[var(--primary)] focus:border-[var(--primary)] text-[var(--text-default)] placeholder:text-[var(--text-muted)]"
              />
              {filters.filterText && (
                <button
                  onClick={() => updateFilters({ filterText: "" })}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 text-[var(--text-muted)] hover:text-[var(--text-default)] transition-colors"
                >
                  <X size={14} />
                </button>
              )}
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 bg-[var(--surface-light)]/20 rounded-lg border border-[var(--surface-light)]">
              <label
                className="text-xs font-medium text-[var(--text-muted)] cursor-pointer select-none whitespace-nowrap"
                htmlFor="table-untagged-only"
              >
                Only Untagged
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
                  Show Split Parents
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
                <span>Add Transaction</span>
              </button>
            )}
            {(filters.filterText || activeFilterCount > 0) && (
              <span className="text-xs text-[var(--text-muted)] whitespace-nowrap">
                {filteredTransactions.length} of {transactions.length}{" "}
                transactions
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
        <table className="w-full text-sm text-left">
          <thead className="bg-[var(--surface-light)] text-[var(--text-muted)] font-medium">
            <tr>
              {showSelection && (
                <th
                  className={`px-4 ${compact ? "py-2" : "py-3"} text-center`}
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
              <SortableHeader label="Date" sortKey="date" width="120px" />
              <SortableHeader label="Account" sortKey="account" width="180px" />
              <SortableHeader label="Description" sortKey="desc" />
              <SortableHeader
                label="Category"
                sortKey="category"
                width="180px"
              />
              <SortableHeader
                label="Amount"
                sortKey="amount"
                align="right"
                width="120px"
              />
              {showActions && (
                <th
                  className={`px-4 ${compact ? "py-2" : "py-3"} text-center text-sm font-medium text-[var(--text-muted)]`}
                  style={{ width: "100px" }}
                >
                  Actions
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
                  className={`hover:bg-[var(--surface-light)]/50 transition-colors ${isSelected ? "bg-[var(--primary)]/5" : ""}`}
                >
                  {showSelection && (
                    <td
                      className={`px-4 ${compact ? "py-2" : "py-3"} text-center`}
                    >
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleSelection(id)}
                        className="rounded border-slate-700 bg-slate-800 text-blue-500 focus:ring-blue-500 cursor-pointer"
                      />
                    </td>
                  )}
                  <td
                    className={`px-4 ${compact ? "py-2" : "py-3"} whitespace-nowrap text-[var(--text-muted)]`}
                  >
                    {formatDate(tx.date)}
                  </td>
                  <td
                    className={`px-4 ${compact ? "py-2" : "py-3"} truncate max-w-[150px]`}
                    title={`${tx.provider || "Manual"} - ${tx.account_name}`}
                  >
                    <div className="flex flex-col">
                      <span className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-tight leading-none mb-1">
                        {tx.provider ||
                          (tx.source?.includes("cash") ? "Cash" : "Manual")}
                      </span>
                      <span className="truncate font-medium text-[var(--text-default)]">
                        {tx.account_name}
                      </span>
                    </div>
                  </td>
                  <td
                    className={`px-4 ${compact ? "py-2" : "py-3"} text-[var(--text-default)] font-medium truncate max-w-[200px]`}
                    title={getDescription(tx)}
                  >
                    {getDescription(tx)}
                  </td>
                  <td
                    className={`px-4 ${compact ? "py-2" : "py-3"} text-[var(--text-muted)]`}
                  >
                    <span className="px-2 py-0.5 rounded-full bg-[var(--surface-light)] text-xs text-[var(--text-muted)] border border-[var(--surface-light)]">
                      {tx.category || "-"} / {tx.tag || "-"}
                    </span>
                  </td>
                  <td
                    className={`px-4 ${compact ? "py-2" : "py-3"} text-right font-bold whitespace-nowrap ${tx.amount > 0 ? "text-emerald-500" : "text-red-500"}`}
                  >
                    {new Intl.NumberFormat("he-IL", {
                      style: "currency",
                      currency: "ILS",
                    }).format(tx.amount)}
                  </td>
                  {showActions && (
                    <td className={`px-4 ${compact ? "py-2" : "py-3"}`}>
                      <div className="flex items-center justify-center gap-1">
                        <button
                          className="p-1.5 rounded-md hover:bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white transition-colors"
                          title="Edit"
                          onClick={() => setEditingTransaction(tx)}
                        >
                          <Edit2 size={14} />
                        </button>
                        <button
                          className="p-1.5 rounded-md hover:bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white transition-colors"
                          title="Split"
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
                                    title="Refund Resolved (Click to remove/unlink)"
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
                                    title={`Partially Refunded (${new Intl.NumberFormat("he-IL", { style: "currency", currency: "ILS" }).format(pending.total_refunded || 0)} / ${new Intl.NumberFormat("he-IL", { style: "currency", currency: "ILS" }).format(pending.expected_amount)}) - Click to Cancel`}
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
                                    <RefreshCw
                                      size={14}
                                      className="animate-spin-slow"
                                    />
                                    {/* Using RefreshCw for partial but maybe PieChart is better if imported? 
                                        Let's stick to RefreshCw but blue distinct color, or PieChart if imported. 
                                        PieChart is not imported. Let's use Link2 or RefreshCw. RefreshCw implies ongoing.
                                    */}
                                    <RefreshCw size={14} />
                                  </button>
                                );
                              }
                              return (
                                <button
                                  className="p-1.5 rounded-md bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 transition-colors"
                                  title="Cancel Pending Refund Request"
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
                                title="Mark as Pending Refund"
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
                                  title="Linked to Pending Refund. Click to Unlink."
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
                                title="Link as Refund"
                                onClick={() => setLinkingTransaction(tx)}
                              >
                                <Link2 size={14} />
                              </button>
                            );
                          })()}
                        {showDelete && isManual && (
                          <button
                            className="p-1.5 rounded-md hover:bg-red-500/10 text-red-400/70 hover:text-red-400 transition-colors"
                            title="Delete"
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
                    ? "No matching transactions."
                    : "No transactions found."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 0 && (
        <div
          className={`flex items-center justify-between ${compact ? "mt-3 px-2" : "mt-4 px-4 py-3 bg-[var(--surface-light)]/30 border-t border-[var(--surface-light)]"}`}
        >
          <div className="flex items-center gap-4">
            <span className="text-sm text-[var(--text-muted)] whitespace-nowrap">
              {sortedTransactions.length > 0 ? (
                <>
                  Showing{" "}
                  <span className="text-white font-medium">{startRow}</span> to{" "}
                  <span className="text-white font-medium">{endRow}</span> of{" "}
                  <span className="text-white font-medium">
                    {sortedTransactions.length}
                  </span>
                </>
              ) : (
                "No results"
              )}
            </span>
            {rowsPerPageOptions && (
              <div className="flex items-center gap-2">
                <span className="text-sm text-[var(--text-muted)] whitespace-nowrap">
                  Rows:
                </span>
                <select
                  value={rowsPerPage}
                  onChange={(e) => {
                    setRowsPerPage(Number(e.target.value));
                    setCurrentPage(1);
                  }}
                  className="bg-[var(--surface)] border border-[var(--surface-light)] rounded px-2 py-1 text-sm outline-none"
                >
                  {rowsPerPageOptions.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setCurrentPage(1)}
              disabled={currentPage === 1}
              className="p-1 rounded hover:bg-[var(--surface-light)] text-[var(--text-muted)] disabled:opacity-30 transition-colors"
            >
              <ChevronsLeft size={compact ? 16 : 20} />
            </button>
            <button
              onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
              disabled={currentPage === 1}
              className="p-1 rounded hover:bg-[var(--surface-light)] text-[var(--text-muted)] disabled:opacity-30 transition-colors"
            >
              <ChevronLeft size={compact ? 16 : 20} />
            </button>
            <span className={`px-4 text-sm whitespace-nowrap`}>
              Page <span className="text-white font-medium">{currentPage}</span>{" "}
              of{" "}
              <span className="text-white font-medium">{totalPages || 1}</span>
            </span>
            <button
              onClick={() =>
                setCurrentPage((prev) => Math.min(totalPages, prev + 1))
              }
              disabled={currentPage === totalPages || totalPages === 0}
              className="p-1 rounded hover:bg-[var(--surface-light)] text-[var(--text-muted)] disabled:opacity-30 transition-colors"
            >
              <ChevronRight size={compact ? 16 : 20} />
            </button>
            <button
              onClick={() => setCurrentPage(totalPages)}
              disabled={currentPage === totalPages || totalPages === 0}
              className="p-1 rounded hover:bg-[var(--surface-light)] text-[var(--text-muted)] disabled:opacity-30 transition-colors"
            >
              <ChevronsRight size={compact ? 16 : 20} />
            </button>
          </div>
        </div>
      )}

      {/* Bulk Action Floating Bar */}
      {showBulkActions && selectedIds.size > 0 && (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 bg-[var(--surface)] border border-[var(--primary)]/50 rounded-2xl shadow-2xl px-6 py-4 flex items-center gap-6 animate-in fade-in slide-in-from-bottom-4 duration-300 z-40">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-[var(--primary)] flex items-center justify-center text-sm font-bold shadow-lg shadow-[var(--primary)]/20">
              {selectedIds.size}
            </div>
            <span className="text-sm font-medium">Selected</span>
          </div>
          <div className="w-px h-8 bg-[var(--surface-light)]" />
          <div className="flex items-center gap-3">
            {bulkMode === "tag" ? (
              <div className="flex items-center gap-2">
                <div className="w-40">
                <SelectDropdown
                  options={categories ? Object.keys(categories).map((cat) => ({ label: cat, value: cat })) : []}
                  value={bulkTagData.category}
                  onChange={(val) =>
                    setBulkTagData({
                      ...bulkTagData,
                      category: val,
                      tag: "",
                    })
                  }
                  placeholder="Category"
                  size="sm"
                />
                </div>
                <div className="w-40">
                <SelectDropdown
                  options={bulkTagData.category && categories?.[bulkTagData.category] ? categories[bulkTagData.category].map((tag: string) => ({ label: tag, value: tag })) : []}
                  value={bulkTagData.tag}
                  onChange={(val) =>
                    setBulkTagData({ ...bulkTagData, tag: val })
                  }
                  placeholder="Tag"
                  size="sm"
                />
                </div>
                <button
                  className="p-1.5 rounded-lg bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 disabled:opacity-50"
                  onClick={handleBulkTag}
                  disabled={bulkTagMutation.isPending}
                >
                  <CheckCircle2 size={20} />
                </button>
                <button
                  className="p-1.5 rounded-lg hover:bg-[var(--surface-light)] text-[var(--text-muted)]"
                  onClick={() => {
                    setBulkMode(null);
                    setBulkTagData({ category: "", tag: "" });
                  }}
                >
                  <X size={20} />
                </button>
              </div>
            ) : bulkMode === "account" ? (
              <div className="flex items-center gap-2">
                <div className="w-40">
                <SelectDropdown
                  options={cashBalances.map((b: any) => ({ label: b.account_name, value: b.account_name }))}
                  value={bulkCashData.account_name}
                  onChange={(val) =>
                    setBulkCashData({
                      ...bulkCashData,
                      account_name: val,
                    })
                  }
                  placeholder="Account"
                  size="sm"
                />
                </div>
                <button
                  className="p-1.5 rounded-lg bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 disabled:opacity-50"
                  onClick={handleBulkTag}
                  disabled={bulkTagMutation.isPending}
                >
                  <CheckCircle2 size={20} />
                </button>
                <button
                  className="p-1.5 rounded-lg hover:bg-[var(--surface-light)] text-[var(--text-muted)]"
                  onClick={() => {
                    setBulkMode(null);
                    setBulkCashData({ description: "", account_name: "", date: "" });
                  }}
                >
                  <X size={20} />
                </button>
              </div>
            ) : (
              <>
                <button
                  className="px-4 py-2 rounded-lg bg-[var(--surface-light)] hover:bg-[var(--surface-base)] text-sm font-medium transition-all"
                  onClick={() => setBulkMode("tag")}
                >
                  Tag Selection
                </button>
                {allSelectedAreCash && (
                  <button
                    className="px-4 py-2 rounded-lg bg-[var(--surface-light)] hover:bg-[var(--surface-base)] text-sm font-medium transition-all"
                    onClick={() => setBulkMode("account")}
                  >
                    Edit Account
                  </button>
                )}
                {showDelete && (
                  <button
                    className="px-4 py-2 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 text-sm font-medium transition-all"
                    onClick={handleBulkDelete}
                  >
                    Delete
                  </button>
                )}
                <button
                  className="px-4 py-2 rounded-lg hover:bg-[var(--surface-light)] text-sm font-medium transition-all"
                  onClick={() => setSelectedIds(new Set())}
                >
                  Cancel
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {/* Modals */}
      {editingTransaction && (
        <TransactionEditorModal
          transaction={editingTransaction}
          onClose={() => setEditingTransaction(null)}
          onSuccess={handleModalSuccess}
        />
      )}
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
            id: linkingTransaction.unique_id,
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
              Delete Transaction
            </h3>
            <p className="text-[var(--text-muted)] mb-6">
              Are you sure you want to delete this manual transaction?
              <br />
              <span className="text-[var(--text-default)] font-medium">
                {getDescription(deletingTransaction) || "No description"}
              </span>
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setDeletingTransaction(null)}
                className="px-4 py-2 rounded-lg bg-[var(--surface-light)] hover:bg-[var(--surface-base)] text-[var(--text-default)] text-sm font-medium transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                className="px-4 py-2 rounded-lg bg-red-500 hover:bg-red-600 text-white text-sm font-medium transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
