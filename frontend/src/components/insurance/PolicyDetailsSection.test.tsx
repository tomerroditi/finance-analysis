import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PolicyDetailsSection } from "./PolicyDetailsSection";

describe("PolicyDetailsSection", () => {
  it("shows a pension's forecasts, this year's figures, its agent and its loans", () => {
    render(
      <PolicyDetailsSection
        id="d"
        isPension
        details={{
          retirement_age: 67,
          monthly_pension_forecast: 29333,
          monthly_pension_forecast_no_deposits: 5307,
          forecast_yield_pct: 4.38,
          ytd_profit: 12717,
          last_month_management_fee: 80.33,
          representative: {
            name: "Agency Ltd",
            id: "1",
            role: "agent",
            can_act: true,
            appointed: null,
            expires: "2035-12-20",
          },
          loans: [
            {
              amount: 40000,
              balance: 30500,
              interest_pct: 3.2,
              monthly_payment: 722,
              payments_months: 60,
              received: "2025-01-26",
              ends: "2030-01-26",
            },
          ],
        }}
      />,
    );

    expect(screen.getByText("Forecast at age 67")).toBeTruthy();
    expect(screen.getByText("Monthly pension, deposits continue")).toBeTruthy();
    expect(screen.getByText(/29,333/)).toBeTruthy();
    expect(screen.getByText("4.38%")).toBeTruthy();
    expect(screen.getByText("Agency Ltd")).toBeTruthy();
    expect(screen.getAllByTestId("policy-loan-row")).toHaveLength(1);
  });

  it("says so when a Keren Hishtalmut has no agent and no loans", () => {
    render(<PolicyDetailsSection id="d" isPension={false} details={{ balance_forecast: 652576 }} />);

    expect(screen.getByText("Balance, deposits continue")).toBeTruthy();
    expect(screen.getByText("No agent holds power of attorney")).toBeTruthy();
    expect(screen.getByText("No loans")).toBeTruthy();
  });
});
