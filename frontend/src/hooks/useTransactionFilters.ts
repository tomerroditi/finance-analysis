import { useState, useMemo, useCallback } from "react";
import type { Transaction } from "../types/transaction";

export interface TransactionFilterState {
  filterText: string;
  onlyUntagged: boolean;
  selectedAccounts: string[];
  amountMin: number | null;
  amountMax: number | null;
  dateStart: string | null;
  dateEnd: string | null;
  selectedCategories: string[];
  selectedTags: string[];
}

export interface FilterOptions {
  accounts: string[];
  categories: string[];
  tags: string[];
}

const DEFAULT_FILTERS: TransactionFilterState = {
  filterText: "",
  onlyUntagged: false,
  selectedAccounts: [],
  amountMin: null,
  amountMax: null,
  dateStart: null,
  dateEnd: null,
  selectedCategories: [],
  selectedTags: [],
};

const getDescription = (tx: Transaction): string => {
  return tx.description || tx.desc || "";
};

const buildAccountLabel = (tx: Transaction): string => {
  const provider = tx.provider || (tx.source?.includes("cash") ? "Cash" : "Manual");
  const account = tx.account_name || "";
  return `${provider} - ${account}`;
};

export function useTransactionFilters(transactions: Transaction[]) {
  const [filters, setFilters] = useState<TransactionFilterState>(DEFAULT_FILTERS);

  const options = useMemo<FilterOptions>(() => {
    const accountSet = new Set<string>();
    const categorySet = new Set<string>();
    const tagsByCategory = new Map<string, Set<string>>();

    for (const tx of transactions) {
      accountSet.add(buildAccountLabel(tx));

      if (tx.category && tx.category !== "-") {
        categorySet.add(tx.category);
      }
      if (tx.tag && tx.tag !== "-") {
        const cat = tx.category || "";
        if (!tagsByCategory.has(cat)) tagsByCategory.set(cat, new Set());
        tagsByCategory.get(cat)!.add(tx.tag);
      }
    }

    let tags: string[];
    if (filters.selectedCategories.length > 0) {
      const tagSet = new Set<string>();
      for (const cat of filters.selectedCategories) {
        tagsByCategory.get(cat)?.forEach((t) => tagSet.add(t));
      }
      tags = Array.from(tagSet).sort();
    } else {
      const allTagSet = new Set<string>();
      tagsByCategory.forEach((tagSet) => tagSet.forEach((t) => allTagSet.add(t)));
      tags = Array.from(allTagSet).sort();
    }

    return {
      accounts: Array.from(accountSet).sort(),
      categories: Array.from(categorySet).sort(),
      tags,
    };
  }, [transactions, filters.selectedCategories]);

  const activeFilterCount = useMemo(() => {
    let count = 0;
    if (filters.onlyUntagged) count++;
    if (filters.selectedAccounts.length > 0) count++;
    if (filters.amountMin !== null) count++;
    if (filters.amountMax !== null) count++;
    if (filters.dateStart !== null) count++;
    if (filters.dateEnd !== null) count++;
    if (filters.selectedCategories.length > 0) count++;
    if (filters.selectedTags.length > 0) count++;
    return count;
  }, [filters]);

  const filteredTransactions = useMemo(() => {
    let result = transactions;

    if (filters.onlyUntagged) {
      result = result.filter((tx) => !tx.tag || tx.tag === "-");
    }

    if (filters.filterText.trim()) {
      const lower = filters.filterText.toLowerCase();
      result = result.filter(
        (tx) =>
          getDescription(tx).toLowerCase().includes(lower) ||
          (tx.category ?? "").toLowerCase().includes(lower) ||
          (tx.tag ?? "").toLowerCase().includes(lower) ||
          (tx.provider ?? "").toLowerCase().includes(lower) ||
          (tx.account_name ?? "").toLowerCase().includes(lower),
      );
    }

    if (filters.selectedAccounts.length > 0) {
      result = result.filter((tx) =>
        filters.selectedAccounts.includes(buildAccountLabel(tx)),
      );
    }

    if (filters.amountMin !== null) {
      result = result.filter((tx) => tx.amount >= filters.amountMin!);
    }
    if (filters.amountMax !== null) {
      result = result.filter((tx) => tx.amount <= filters.amountMax!);
    }

    if (filters.dateStart) {
      result = result.filter((tx) => tx.date >= filters.dateStart!);
    }
    if (filters.dateEnd) {
      result = result.filter((tx) => tx.date <= filters.dateEnd!);
    }

    if (filters.selectedCategories.length > 0) {
      result = result.filter((tx) =>
        filters.selectedCategories.includes(tx.category || ""),
      );
    }

    if (filters.selectedTags.length > 0) {
      result = result.filter((tx) =>
        filters.selectedTags.includes(tx.tag || ""),
      );
    }

    return result;
  }, [transactions, filters]);

  const updateFilters = useCallback(
    (updates: Partial<TransactionFilterState>) => {
      setFilters((prev) => {
        const next = { ...prev, ...updates };
        // Clear selected tags that are no longer valid when categories change
        if (updates.selectedCategories !== undefined && next.selectedTags.length > 0) {
          const validCategories = updates.selectedCategories;
          if (validCategories.length > 0) {
            // We'll let the tags stay - they get filtered in the options derivation
            // and the user can see they have stale selections
          }
        }
        return next;
      });
    },
    [],
  );

  const resetFilters = useCallback(() => {
    setFilters(DEFAULT_FILTERS);
  }, []);

  return {
    filters,
    options,
    activeFilterCount,
    filteredTransactions,
    updateFilters,
    resetFilters,
  };
}
