import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ClearingHouseReport } from "../../services/api";
import { ClearingHouseSummary, SubscriptionNotice } from "./ClearingHouseSummary";

function report(overrides: Partial<ClearingHouseReport>): ClearingHouseReport {
  return {
    provider: "mislaka",
    account_name: "Me",
    calc_date: "2026-08-31",
    total_savings: 367776,
    forecast_total_balance: 9380396,
    forecast_monthly_pension: 40691,
    forecast_lump_sum: 1292865,
    disability_monthly: 29250,
    survivor_spouse_monthly: 23400,
    survivor_child_monthly: 15600,
    death_lump_sum: 0,
    report_number: 1,
    report_count: 7,
    subscription_expires: "2099-04-11",
    subscription_months_left: 7,
    license_holder: null,
    ...overrides,
  };
}

describe("ClearingHouseSummary", () => {
  it("shows the newest report's forecast, cover and position in the subscription", () => {
    render(
      <ClearingHouseSummary
        reports={[
          report({ calc_date: "2026-07-31", forecast_monthly_pension: 40490 }),
          report({}),
        ]}
      />,
    );

    expect(screen.getByTestId("clearing-house-monthly-pension").textContent).toContain("40,691");
    expect(screen.getByTestId("clearing-house-disability").textContent).toContain("29,250");
    expect(screen.getByText(/report 1 of 7/)).toBeTruthy();
    expect(screen.getByText(/since last report/).textContent).toContain("201");
    expect(screen.getByText(/saved today/).textContent).toContain("367,776");
  });

  it("marks a cover the saver does not hold as none rather than a zero", () => {
    render(<ClearingHouseSummary reports={[report({ death_lump_sum: 0 })]} />);
    expect(screen.getByText("None")).toBeTruthy();
  });

  it("renders nothing without a report", () => {
    const { container } = render(<ClearingHouseSummary reports={[]} />);
    expect(container.innerHTML).toBe("");
  });
});

describe("SubscriptionNotice", () => {
  it("warns when one report is left", () => {
    render(<SubscriptionNotice reports={[report({ subscription_months_left: 1 })]} />);
    expect(screen.getByTestId("clearing-house-subscription-notice").textContent).toContain(
      "1 monthly report left",
    );
  });

  it("stays hidden while the subscription has time left", () => {
    render(<SubscriptionNotice reports={[report({})]} />);
    expect(screen.queryByTestId("clearing-house-subscription-notice")).toBeNull();
  });
});
