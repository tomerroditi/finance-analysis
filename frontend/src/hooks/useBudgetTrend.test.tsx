import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { budgetApi } from "../services/api";
import { useBudgetTrend } from "./useBudgetTrend";
import { DemoModeProvider } from "../context/DemoModeContext";

vi.mock("../services/api", () => ({
  budgetApi: { getAnalysis: vi.fn(), getTrend: vi.fn() },
  testingApi: {
    getDemoModeStatus: vi
      .fn()
      .mockResolvedValue({ data: { demo_mode: false, forced: false } }),
  },
}));

const getAnalysis = budgetApi.getAnalysis as Mock;
const getTrend = budgetApi.getTrend as Mock;

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <DemoModeProvider>{children}</DemoModeProvider>
    </QueryClientProvider>
  );
}

/** The hook is always rendered for 2026-06, the last point of every series. */
function renderTrend(months = 1) {
  return renderHook(() => useBudgetTrend(2026, 6, months), {
    wrapper: createWrapper(),
  });
}

/** One `/budget/trend` point, as the backend returns it. */
function trendPoint(
  year: number,
  month: number,
  budget: number,
  actual: number,
  rules: Record<string, number> = {},
  limits: Record<string, number> = {},
) {
  return { year, month, budget, actual, rules, limits };
}

describe("useBudgetTrend", () => {
  beforeEach(() => {
    getAnalysis.mockReset();
    getTrend.mockReset();
    getAnalysis.mockResolvedValue({ data: { rules: [] } });
    getTrend.mockResolvedValue({ data: [] });
  });

  it("asks the backend once for the whole series", async () => {
    // The series used to be one analysis request per month — twelve for the
    // budget page's sparkline, all re-fired by the global invalidation after
    // every mutation, which is what starved `/budget/overview`.
    getTrend.mockResolvedValue({
      data: [
        trendPoint(2026, 4, 10000, 4000),
        trendPoint(2026, 5, 10000, 4500),
        trendPoint(2026, 6, 10000, 5000),
      ],
    });

    const { result } = renderTrend(3);

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(getTrend).toHaveBeenCalledTimes(1);
    expect(getTrend).toHaveBeenCalledWith(2026, 6, 3, false);
    expect(result.current.data).toHaveLength(3);
  });

  it("uses the Total Budget row's amount as the budget, not the sum of the per-category rules", async () => {
    // Total Budget cap (10000) is deliberately larger than the sum of the
    // per-category rule amounts (Food 2000 + Transport 1000 = 3000): the
    // headroom is unallocated. Summing the category rules would report 3000;
    // the budget bar must read the 10000 cap instead.
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
    getTrend.mockResolvedValue({ data: [trendPoint(2026, 6, 10000, 5000)] });

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
    getTrend.mockResolvedValue({ data: [trendPoint(2026, 6, 0, 0)] });

    const { result } = renderTrend();

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const point = result.current.data.at(-1)!;
    expect(point.budget).toBe(0);
    expect(point.actual).toBe(0);
  });

  it("prefers the analysis figures for the month being viewed", async () => {
    // `/budget/trend` is read-only; `/budget/analysis` auto-fills an empty
    // current or future month by copying the previous month's rules. Without
    // this overlay the first visit to a brand-new month would plot a zero bar
    // for it, and keep plotting one until something else invalidated the
    // trend.
    getTrend.mockResolvedValue({
      data: [trendPoint(2026, 5, 10000, 4500), trendPoint(2026, 6, 0, 0)],
    });
    getAnalysis.mockResolvedValue({
      data: {
        rules: [
          { rule: { name: "Total Budget", amount: 10000 }, current_amount: -5000 },
        ],
      },
    });

    const { result } = renderTrend(2);

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    // The earlier month keeps the trend's own numbers…
    expect(result.current.data[0]).toMatchObject({ budget: 10000, actual: 4500 });
    // …while the viewed month takes the auto-filled ones.
    expect(result.current.data[1]).toMatchObject({ budget: 10000, actual: 5000 });
  });

  it("builds the per-rule series from the same response, keyed by name", async () => {
    // Names, not ids: an auto-filled month creates fresh rows, so the same
    // envelope carries a different id every month.
    getTrend.mockResolvedValue({
      data: [
        trendPoint(2026, 5, 10000, 4500, { Food: 1200, Transport: 300 }),
        trendPoint(2026, 6, 10000, 5000, { Food: 1500 }),
      ],
    });
    // The viewed month is overlaid from the analysis, so its rules have to
    // come from there too — otherwise the two halves of the same bar would
    // disagree about the month.
    getAnalysis.mockResolvedValue({
      data: {
        rules: [
          { rule: { name: "Total Budget", amount: 10000 }, current_amount: -5000 },
          { rule: { name: "Food", amount: 2000 }, current_amount: 1500 },
        ],
      },
    });

    const { result } = renderTrend(2);

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.byRule.Food).toEqual([1200, 1500]);
    // A rule absent from a month plots zero there rather than shifting the
    // series out of alignment with `data`.
    expect(result.current.byRule.Transport).toEqual([300, 0]);
  });

  it("carries the limit each rule held in each month", async () => {
    // A monthly envelope is a fresh, separately editable row per month, so
    // the sparkline cannot draw the whole history against today's cap: a
    // month that came in on budget would turn red once the cap is cut.
    getTrend.mockResolvedValue({
      data: [
        trendPoint(2026, 5, 10000, 4500, { Food: 1900 }, { Food: 2000 }),
        trendPoint(2026, 6, 10000, 5000, { Food: 1500 }, { Food: 1500 }),
      ],
    });
    getAnalysis.mockResolvedValue({
      data: {
        rules: [
          { rule: { name: "Total Budget", amount: 10000 }, current_amount: -5000 },
          { rule: { name: "Food", amount: 1500 }, current_amount: 1500 },
        ],
      },
    });

    const { result } = renderTrend(2);

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.byRuleLimit.Food).toEqual([2000, 1500]);
  });

  it("takes the viewed month's limit from the analysis, not the read-only trend", async () => {
    // `/budget/trend` never auto-fills, so a brand-new month reports nothing
    // for its rules there. Reading the limit from the trend alone would draw
    // the current month as unbudgeted right after its envelopes were copied
    // forward.
    getTrend.mockResolvedValue({
      data: [
        trendPoint(2026, 5, 10000, 4500, { Food: 1900 }, { Food: 2000 }),
        trendPoint(2026, 6, 0, 0),
      ],
    });
    getAnalysis.mockResolvedValue({
      data: {
        rules: [
          { rule: { name: "Total Budget", amount: 10000 }, current_amount: -800 },
          { rule: { name: "Food", amount: 2400 }, current_amount: 800 },
        ],
      },
    });

    const { result } = renderTrend(2);

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.byRuleLimit.Food).toEqual([2000, 2400]);
  });

  it("leaves a zero for a month the rule did not exist in", async () => {
    // Zero reads as "no envelope that month" downstream, which the sparkline
    // draws as a gap rather than a reference line along the floor.
    getTrend.mockResolvedValue({
      data: [
        trendPoint(2026, 5, 10000, 4500, {}, {}),
        trendPoint(2026, 6, 10000, 5000, { Food: 1500 }, { Food: 1500 }),
      ],
    });
    getAnalysis.mockResolvedValue({
      data: {
        rules: [
          { rule: { name: "Total Budget", amount: 10000 }, current_amount: -5000 },
          { rule: { name: "Food", amount: 1500 }, current_amount: 1500 },
        ],
      },
    });

    const { result } = renderTrend(2);

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.byRuleLimit.Food).toEqual([0, 1500]);
  });

  it("reports no data when every month is empty", async () => {
    getTrend.mockResolvedValue({
      data: [trendPoint(2026, 5, 0, 0), trendPoint(2026, 6, 0, 0)],
    });

    const { result } = renderTrend(2);

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.hasData).toBe(false);
  });
});
