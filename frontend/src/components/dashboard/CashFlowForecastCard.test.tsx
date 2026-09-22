import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CashFlowForecastSection } from "./CashFlowForecastCard";
import { analyticsApi, testingApi, type CashFlowForecast } from "../../services/api";
import { DemoModeProvider } from "../../context/DemoModeContext";

/**
 * The forecast hero's two captions both explain where its numbers came from,
 * and both are conditional — which is exactly the kind of thing that ships
 * inverted. The income caption names the recurring money the projection is
 * leaning on; the header caption admits when the data stops short of today,
 * so a week-old scrape does not read as a week of spending nothing.
 */

function makeForecast(overrides: Partial<CashFlowForecast> = {}): CashFlowForecast {
  return {
    month: "2026-09",
    days_in_month: 30,
    day_of_month: 23,
    days_remaining: 7,
    observed_through: "2026-09-23",
    actual_income: 12000,
    actual_expenses: 8000,
    expected_income: 30000,
    expected_expenses: 14000,
    projected_net: 16000,
    income_basis: "recurring",
    recurring_income_due: 18000,
    recurring_income_items: [
      {
        label: "TECH COMPANY LTD - SALARY",
        normalized: "tech company ltd salary",
        amount: 18000,
        cadence: "monthly",
        expected_date: "2026-09-25",
      },
    ],
    current_bank_balance: 100000,
    projected_end_balance: 118000,
    safe_to_spend: 18000,
    safe_to_spend_daily: 2571,
    avg_monthly_income: 30000,
    avg_monthly_expenses: 14000,
    committed_remaining: 0,
    daily: [
      { date: "2026-09-01", actual_balance: 100000, projected_balance: null },
    ],
    ...overrides,
  };
}

async function renderCard(forecast: CashFlowForecast) {
  vi.spyOn(analyticsApi, "getCashFlowForecast").mockResolvedValue({
    data: forecast,
  } as Awaited<ReturnType<typeof analyticsApi.getCashFlowForecast>>);
  vi.spyOn(testingApi, "getDemoModeStatus").mockResolvedValue({
    data: { demo_mode: false, forced: false },
  } as Awaited<ReturnType<typeof testingApi.getDemoModeStatus>>);

  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <DemoModeProvider>
        <CashFlowForecastSection />
      </DemoModeProvider>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(screen.getByText("This Month")).toBeInTheDocument());
}

describe("CashFlowForecastSection", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("names the recurring income the projection is leaning on", async () => {
    await renderCard(makeForecast());

    const caption = screen.getByTestId("forecast-income-due");
    expect(caption.textContent).toContain("18,000");
    // The breakdown behind it is the stream list, so a user can see which
    // money the number is waiting on.
    expect(caption.getAttribute("title")).toContain("TECH COMPANY LTD - SALARY");
  });

  it("says nothing about recurring income when none is due", async () => {
    await renderCard(
      makeForecast({
        income_basis: "trend",
        recurring_income_due: 0,
        recurring_income_items: [],
      }),
    );

    expect(screen.queryByTestId("forecast-income-due")).not.toBeInTheDocument();
  });

  it("admits when the data stops short of today", async () => {
    await renderCard(makeForecast({ observed_through: "2026-09-17" }));

    expect(screen.getByTestId("forecast-observed-through")).toBeInTheDocument();
  });

  it("still admits a sync that stopped in an earlier month", async () => {
    // Compared as ISO strings, not day-of-month numbers: 28 > 23 would have
    // read August the 28th as later than September the 23rd and hidden this.
    await renderCard(makeForecast({ observed_through: "2026-08-28" }));

    expect(screen.getByTestId("forecast-observed-through")).toBeInTheDocument();
  });

  it("stays quiet when the data is current", async () => {
    await renderCard(makeForecast({ observed_through: "2026-09-23" }));

    expect(
      screen.queryByTestId("forecast-observed-through"),
    ).not.toBeInTheDocument();
  });

  it("stays quiet when the month has no transactions at all", async () => {
    await renderCard(makeForecast({ observed_through: null }));

    expect(
      screen.queryByTestId("forecast-observed-through"),
    ).not.toBeInTheDocument();
  });
});
