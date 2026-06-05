import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { budgetApi } from "../services/api";
import { useBudgetTrend } from "./useBudgetTrend";

vi.mock("../services/api", () => ({
  budgetApi: { getAnalysis: vi.fn() },
}));

const getAnalysis = budgetApi.getAnalysis as Mock;

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

function renderTrend(months = 1) {
  return renderHook(() => useBudgetTrend(2026, 6, months), {
    wrapper: createWrapper(),
  });
}

describe("useBudgetTrend", () => {
  beforeEach(() => {
    getAnalysis.mockReset();
  });

  it("uses the Total Budget row's amount as the budget, not the sum of the per-category rules", async () => {
    // Total Budget cap (10000) is deliberately larger than the sum of the
    // per-category rule amounts (Food 2000 + Transport 1000 = 3000): the
    // headroom is unallocated. The old code summed the category rules and
    // reported 3000; the budget bar must read the 10000 cap instead.
    getAnalysis.mockResolvedValue({
      data: {
        rules: [
          { rule: { name: "Total Budget", amount: 10000 }, current_amount: -5000 },
          { rule: { name: "Food", amount: 2000 }, current_amount: -1500 },
          { rule: { name: "Transport", amount: 1000 }, current_amount: -800 },
          { rule: { name: "Other Expenses", amount: 7000 }, current_amount: -2700 },
        ],
      },
    });

    const { result } = renderTrend();

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const point = result.current.data.at(-1)!;
    expect(point.budget).toBe(10000);
    // Actual is the month's total spend from the Total Budget row (abs 5000),
    // not the sum of the per-category rows (1500 + 800 = 2300), which would
    // drop the "Other Expenses" spend.
    expect(point.actual).toBe(5000);
  });

  it("plots zeros for a month with no budget rules at all", async () => {
    getAnalysis.mockResolvedValue({ data: { rules: [] } });

    const { result } = renderTrend();

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const point = result.current.data.at(-1)!;
    expect(point.budget).toBe(0);
    expect(point.actual).toBe(0);
  });
});
