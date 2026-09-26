import { describe, expect, it } from "vitest";
import type { ClearingHouseReport } from "../services/api";
import { isInactive, isSubscriptionEndingSoon, parsePolicyDetails } from "./policyDetails";

function report(overrides: Partial<ClearingHouseReport>): ClearingHouseReport {
  return {
    provider: "mislaka",
    account_name: "Me",
    calc_date: "2026-08-31",
    total_savings: null,
    forecast_total_balance: null,
    forecast_monthly_pension: null,
    forecast_lump_sum: null,
    disability_monthly: null,
    survivor_spouse_monthly: null,
    survivor_child_monthly: null,
    death_lump_sum: null,
    report_number: null,
    report_count: null,
    subscription_expires: null,
    subscription_months_left: null,
    license_holder: null,
    ...overrides,
  };
}

describe("parsePolicyDetails", () => {
  it("reads a details object", () => {
    expect(parsePolicyDetails('{"ytd_profit": 120}')?.ytd_profit).toBe(120);
  });

  it("returns null for missing, broken or non-object JSON", () => {
    expect(parsePolicyDetails(null)).toBeNull();
    expect(parsePolicyDetails("{not json")).toBeNull();
    expect(parsePolicyDetails("[1, 2]")).toBeNull();
  });
});

describe("isInactive", () => {
  it("is only true for a status other than the portal's active one", () => {
    expect(isInactive({ status: "לא פעיל" })).toBe(true);
    expect(isInactive({ status: "פעיל" })).toBe(false);
    expect(isInactive({})).toBe(false);
    expect(isInactive(null)).toBe(false);
  });
});

describe("isSubscriptionEndingSoon", () => {
  const today = new Date("2026-09-24");

  it("warns once at most one report is left", () => {
    expect(isSubscriptionEndingSoon(report({ subscription_months_left: 1 }), today)).toBe(true);
  });

  it("warns when the expiry is within the notice window", () => {
    const soon = report({ subscription_months_left: 3, subscription_expires: "2026-10-20" });
    expect(isSubscriptionEndingSoon(soon, today)).toBe(true);
  });

  it("stays quiet with months left and a distant expiry, or no subscription data", () => {
    const later = report({ subscription_months_left: 7, subscription_expires: "2027-04-11" });
    expect(isSubscriptionEndingSoon(later, today)).toBe(false);
    expect(isSubscriptionEndingSoon(report({}), today)).toBe(false);
    expect(isSubscriptionEndingSoon(undefined, today)).toBe(false);
  });
});
