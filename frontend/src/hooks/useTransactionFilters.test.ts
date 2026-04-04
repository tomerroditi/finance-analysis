import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useTransactionFilters } from "./useTransactionFilters";
import type { Transaction } from "../types/transaction";

const makeTx = (overrides: Partial<Transaction> = {}): Transaction => ({
  id: 1,
  amount: -100,
  date: "2026-01-15",
  description: "Test transaction",
  category: "Food",
  tag: "Groceries",
  provider: "Leumi",
  account_name: "Main",
  source: "bank_transactions",
  ...overrides,
});

const sampleTransactions: Transaction[] = [
  makeTx({ id: 1, description: "Supermarket", category: "Food", tag: "Groceries", amount: -200, date: "2026-01-10" }),
  makeTx({ id: 2, description: "Bus fare", category: "Transport", tag: "Public Transport", amount: -15, date: "2026-01-12" }),
  makeTx({ id: 3, description: "Salary deposit", category: "Salary", tag: "-", amount: 8000, date: "2026-01-01" }),
  makeTx({ id: 4, description: "Restaurant dinner", category: "Food", tag: "Restaurants", amount: -150, date: "2026-01-20" }),
  makeTx({ id: 5, description: "Fuel", category: "Transport", tag: "Fuel", amount: -300, date: "2026-02-01", provider: "Hapoalim", account_name: "Savings" }),
];

describe("useTransactionFilters", () => {
  describe("initial state", () => {
    it("returns all transactions unfiltered", () => {
      const { result } = renderHook(() => useTransactionFilters(sampleTransactions));
      expect(result.current.filteredTransactions).toHaveLength(5);
    });

    it("has zero active filters", () => {
      const { result } = renderHook(() => useTransactionFilters(sampleTransactions));
      expect(result.current.activeFilterCount).toBe(0);
    });

    it("derives unique accounts from transactions", () => {
      const { result } = renderHook(() => useTransactionFilters(sampleTransactions));
      expect(result.current.options.accounts).toContain("Leumi - Main");
      expect(result.current.options.accounts).toContain("Hapoalim - Savings");
    });

    it("derives unique categories", () => {
      const { result } = renderHook(() => useTransactionFilters(sampleTransactions));
      expect(result.current.options.categories).toEqual(
        expect.arrayContaining(["Food", "Transport", "Salary"]),
      );
    });

    it("derives tags from all categories", () => {
      const { result } = renderHook(() => useTransactionFilters(sampleTransactions));
      expect(result.current.options.tags).toEqual(
        expect.arrayContaining(["Groceries", "Restaurants", "Public Transport", "Fuel"]),
      );
    });
  });

  describe("text filter", () => {
    it("filters by description", () => {
      const { result } = renderHook(() => useTransactionFilters(sampleTransactions));
      act(() => result.current.updateFilters({ filterText: "supermarket" }));
      expect(result.current.filteredTransactions).toHaveLength(1);
      expect(result.current.filteredTransactions[0].description).toBe("Supermarket");
    });

    it("filters by category text", () => {
      const { result } = renderHook(() => useTransactionFilters(sampleTransactions));
      act(() => result.current.updateFilters({ filterText: "transport" }));
      expect(result.current.filteredTransactions).toHaveLength(2);
    });

    it("is case-insensitive", () => {
      const { result } = renderHook(() => useTransactionFilters(sampleTransactions));
      act(() => result.current.updateFilters({ filterText: "SALARY" }));
      expect(result.current.filteredTransactions).toHaveLength(1);
    });
  });

  describe("onlyUntagged filter", () => {
    it("filters to transactions with no tag or dash tag", () => {
      const { result } = renderHook(() => useTransactionFilters(sampleTransactions));
      act(() => result.current.updateFilters({ onlyUntagged: true }));
      expect(result.current.filteredTransactions).toHaveLength(1);
      expect(result.current.filteredTransactions[0].tag).toBe("-");
    });

    it("increments active filter count", () => {
      const { result } = renderHook(() => useTransactionFilters(sampleTransactions));
      act(() => result.current.updateFilters({ onlyUntagged: true }));
      expect(result.current.activeFilterCount).toBe(1);
    });
  });

  describe("account filter", () => {
    it("filters by selected accounts", () => {
      const { result } = renderHook(() => useTransactionFilters(sampleTransactions));
      act(() => result.current.updateFilters({ selectedAccounts: ["Hapoalim - Savings"] }));
      expect(result.current.filteredTransactions).toHaveLength(1);
      expect(result.current.filteredTransactions[0].provider).toBe("Hapoalim");
    });
  });

  describe("amount filter", () => {
    it("filters by minimum amount", () => {
      const { result } = renderHook(() => useTransactionFilters(sampleTransactions));
      act(() => result.current.updateFilters({ amountMin: 0 }));
      expect(result.current.filteredTransactions).toHaveLength(1);
      expect(result.current.filteredTransactions[0].amount).toBe(8000);
    });

    it("filters by maximum amount", () => {
      const { result } = renderHook(() => useTransactionFilters(sampleTransactions));
      act(() => result.current.updateFilters({ amountMax: -200 }));
      expect(result.current.filteredTransactions).toHaveLength(2);
    });

    it("filters by range", () => {
      const { result } = renderHook(() => useTransactionFilters(sampleTransactions));
      act(() => result.current.updateFilters({ amountMin: -200, amountMax: -100 }));
      expect(result.current.filteredTransactions).toHaveLength(2);
    });
  });

  describe("date filter", () => {
    it("filters by start date", () => {
      const { result } = renderHook(() => useTransactionFilters(sampleTransactions));
      act(() => result.current.updateFilters({ dateStart: "2026-01-15" }));
      expect(result.current.filteredTransactions).toHaveLength(2);
    });

    it("filters by end date", () => {
      const { result } = renderHook(() => useTransactionFilters(sampleTransactions));
      act(() => result.current.updateFilters({ dateEnd: "2026-01-12" }));
      expect(result.current.filteredTransactions).toHaveLength(3);
    });
  });

  describe("category filter", () => {
    it("filters by selected categories", () => {
      const { result } = renderHook(() => useTransactionFilters(sampleTransactions));
      act(() => result.current.updateFilters({ selectedCategories: ["Food"] }));
      expect(result.current.filteredTransactions).toHaveLength(2);
    });

    it("narrows tag options to selected categories", () => {
      const { result } = renderHook(() => useTransactionFilters(sampleTransactions));
      act(() => result.current.updateFilters({ selectedCategories: ["Food"] }));
      expect(result.current.options.tags).toEqual(
        expect.arrayContaining(["Groceries", "Restaurants"]),
      );
      expect(result.current.options.tags).not.toContain("Fuel");
    });
  });

  describe("tag filter", () => {
    it("filters by selected tags", () => {
      const { result } = renderHook(() => useTransactionFilters(sampleTransactions));
      act(() => result.current.updateFilters({ selectedTags: ["Groceries"] }));
      expect(result.current.filteredTransactions).toHaveLength(1);
    });
  });

  describe("combined filters", () => {
    it("applies multiple filters together", () => {
      const { result } = renderHook(() => useTransactionFilters(sampleTransactions));
      act(() =>
        result.current.updateFilters({
          selectedCategories: ["Food"],
          amountMin: -200,
          amountMax: -100,
        }),
      );
      expect(result.current.filteredTransactions).toHaveLength(2);
    });

    it("counts all active filters", () => {
      const { result } = renderHook(() => useTransactionFilters(sampleTransactions));
      act(() =>
        result.current.updateFilters({
          onlyUntagged: true,
          amountMin: -500,
          selectedAccounts: ["Leumi - Main"],
        }),
      );
      expect(result.current.activeFilterCount).toBe(3);
    });
  });

  describe("resetFilters", () => {
    it("clears all filters", () => {
      const { result } = renderHook(() => useTransactionFilters(sampleTransactions));
      act(() =>
        result.current.updateFilters({
          filterText: "test",
          onlyUntagged: true,
          amountMin: -500,
        }),
      );
      expect(result.current.activeFilterCount).toBeGreaterThan(0);

      act(() => result.current.resetFilters());
      expect(result.current.activeFilterCount).toBe(0);
      expect(result.current.filteredTransactions).toHaveLength(5);
    });
  });

  describe("empty transactions", () => {
    it("handles empty array", () => {
      const { result } = renderHook(() => useTransactionFilters([]));
      expect(result.current.filteredTransactions).toHaveLength(0);
      expect(result.current.options.accounts).toHaveLength(0);
      expect(result.current.options.categories).toHaveLength(0);
      expect(result.current.options.tags).toHaveLength(0);
    });
  });
});
