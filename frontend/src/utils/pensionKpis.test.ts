import { describe, expect, it } from "vitest";
import type { InsuranceAccount } from "../services/api";
import { computePensionKpis } from "./pensionKpis";

function account(overrides: Partial<InsuranceAccount>): InsuranceAccount {
  return {
    id: 1,
    provider: "mislaka",
    policy_id: "P-1",
    policy_type: "pension",
    pension_type: "makifa",
    account_name: "Fund",
    custom_name: null,
    balance: 0,
    balance_date: null,
    investment_tracks: null,
    commission_deposits_pct: null,
    commission_savings_pct: null,
    insurance_covers: null,
    insurance_costs: null,
    liquidity_date: null,
    details: null,
    ...overrides,
  };
}

const TODAY = new Date(2026, 8, 26);

describe("computePensionKpis", () => {
  it("sums balances and keeps the newest balance date", () => {
    const kpis = computePensionKpis(
      [
        account({ balance: 100_000, balance_date: "2026-07-31" }),
        account({ id: 2, balance: 50_000, balance_date: "2026-08-31" }),
      ],
      [],
      TODAY,
    );
    expect(kpis.totalBalance).toBe(150_000);
    expect(kpis.fundCount).toBe(2);
    expect(kpis.balanceAsOf).toBe("2026-08-31");
  });

  it("counts only the last 12 months of deposits and averages over the months that saw one", () => {
    const kpis = computePensionKpis(
      [account({})],
      [
        { date: "2025-09-30", amount: 9_999 },
        { date: "2025-10-10", amount: 1_000 },
        { date: "2026-08-10", amount: 2_000 },
        { date: "2026-08-12", amount: 1_000 },
        { date: "2026-09-10", amount: -500 },
      ],
      TODAY,
    );
    expect(kpis.recentDeposits).toBe(4_000);
    expect(kpis.monthlyDepositAvg).toBe(2_000);
  });

  it("reports no average when the window has no deposits", () => {
    const kpis = computePensionKpis([account({})], [{ date: "2020-01-01", amount: 1 }], TODAY);
    expect(kpis.recentDeposits).toBe(0);
    expect(kpis.monthlyDepositAvg).toBeNull();
  });

  it("weights the management fee by balance", () => {
    const kpis = computePensionKpis(
      [
        account({ balance: 900_000, commission_savings_pct: 0.1, commission_deposits_pct: 1 }),
        account({ id: 2, balance: 100_000, commission_savings_pct: 1.1, commission_deposits_pct: 3 }),
        account({ id: 3, balance: 500_000 }),
      ],
      [],
      TODAY,
    );
    expect(kpis.feeOnSavingsPct).toBeCloseTo(0.2);
    expect(kpis.feeOnDepositsPct).toBeCloseTo(1.2);
  });

  it("leaves the fee and profit empty when no fund reports them", () => {
    const kpis = computePensionKpis([account({ balance: 10 })], [], TODAY);
    expect(kpis.feeOnSavingsPct).toBeNull();
    expect(kpis.ytdProfit).toBeNull();
  });

  it("sums year-to-date profit and statement costs across funds", () => {
    const kpis = computePensionKpis(
      [
        account({
          details: JSON.stringify({ ytd_profit: 5_000 }),
          insurance_costs: JSON.stringify([
            { title: "Management fee", amount: -300 },
            { title: "Disability risk cost", amount: -700 },
            { title: "Closing balance", amount: 100_000 },
          ]),
        }),
        account({ id: 2, details: JSON.stringify({ ytd_profit: -1_000 }) }),
      ],
      [],
      TODAY,
    );
    expect(kpis.ytdProfit).toBe(4_000);
    expect(kpis.riskCost).toBe(700);
    expect(kpis.managementFee).toBe(300);
    expect(kpis.costsThisYear).toBe(1_000);
  });
});
