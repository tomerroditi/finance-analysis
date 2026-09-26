import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { PensionKpis } from "../../utils/pensionKpis";
import { PensionKpiStrip } from "./PensionKpiStrip";

const KPIS: PensionKpis = {
  totalBalance: 377_764,
  fundCount: 3,
  balanceAsOf: "2026-08-31",
  recentDeposits: 36_000,
  monthlyDepositAvg: 3_000,
  ytdProfit: 12_500,
  costsThisYear: 2_950,
  riskCost: 2_130,
  managementFee: 820,
  feeOnSavingsPct: 0.2234,
  feeOnDepositsPct: 1.5,
};

describe("PensionKpiStrip", () => {
  it("shows balance, deposits, profit, costs and the weighted fee", () => {
    render(<PensionKpiStrip kpis={KPIS} />);
    expect(screen.getByTestId("pension-kpi-balance").textContent).toContain("377,764");
    expect(screen.getByTestId("pension-kpi-balance").textContent).toContain("3 funds");
    expect(screen.getByTestId("pension-kpi-deposits").textContent).toContain("3,000");
    expect(screen.getByTestId("pension-kpi-profit").textContent).toContain("12,500");
    expect(screen.getByTestId("pension-kpi-costs").textContent).toContain("2,130");
    expect(screen.getByTestId("pension-kpi-fee").textContent).toContain("0.22%");
    expect(screen.getByTestId("pension-kpi-fee").textContent).toContain("1.50% on deposits");
  });

  it("drops the profit tile when no fund reports one", () => {
    render(<PensionKpiStrip kpis={{ ...KPIS, ytdProfit: null }} />);
    expect(screen.queryByTestId("pension-kpi-profit")).toBeNull();
    expect(screen.getByTestId("pension-kpi-strip").className).toContain("lg:grid-cols-4");
  });
});
