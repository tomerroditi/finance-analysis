/**
 * Household-level figures for the pension-savings page's KPI strip.
 *
 * Pure so the page stays free of arithmetic and the rules are testable:
 * deposits are windowed (the clearing house only reports a few months, so an
 * "all-time" total is a count of how far back we happened to scrape), and fee
 * rates are weighted by balance (a small fund's high fee must not read as the
 * household's rate).
 */
import type { InsuranceAccount } from "../services/api";
import { classifyStatement } from "./insuranceStatement";
import { parsePolicyDetails } from "./policyDetails";

/** The window the deposits KPI covers. */
export const DEPOSIT_WINDOW_MONTHS = 12;

export interface PensionDeposit {
  date: string;
  amount: number;
}

export interface PensionKpis {
  totalBalance: number;
  fundCount: number;
  /** Newest balance date across the funds (ISO), `null` when none carries one. */
  balanceAsOf: string | null;
  /** Deposits within the last `DEPOSIT_WINDOW_MONTHS` months. */
  recentDeposits: number;
  /** Average over the months in the window that saw a deposit; `null` with none. */
  monthlyDepositAvg: number | null;
  /** Sum of the funds' year-to-date profit; `null` when no fund reports one. */
  ytdProfit: number | null;
  /** Risk-cover cost plus management fee, from the year-to-date statements. */
  costsThisYear: number;
  riskCost: number;
  managementFee: number;
  /** Balance-weighted management fee on savings (%); `null` when no fund reports one. */
  feeOnSavingsPct: number | null;
  /** Balance-weighted management fee on deposits (%); `null` when no fund reports one. */
  feeOnDepositsPct: number | null;
}

function weightedPct(
  accounts: InsuranceAccount[],
  pick: (account: InsuranceAccount) => number | null,
): number | null {
  const rated = accounts.filter((a) => pick(a) != null);
  if (rated.length === 0) return null;
  const weight = rated.reduce((s, a) => s + Math.max(a.balance ?? 0, 0), 0);
  if (weight <= 0) return rated.reduce((s, a) => s + (pick(a) ?? 0), 0) / rated.length;
  return rated.reduce((s, a) => s + (pick(a) ?? 0) * Math.max(a.balance ?? 0, 0), 0) / weight;
}

/** Compute the KPI strip's figures from the funds and their deposit rows. */
export function computePensionKpis(
  accounts: InsuranceAccount[],
  deposits: PensionDeposit[],
  today: Date = new Date(),
): PensionKpis {
  const windowStart = new Date(today.getFullYear(), today.getMonth() - DEPOSIT_WINDOW_MONTHS + 1, 1);
  const cutoff = `${windowStart.getFullYear()}-${String(windowStart.getMonth() + 1).padStart(2, "0")}-01`;
  const inWindow = deposits.filter((d) => d.amount > 0 && d.date >= cutoff);
  const recentDeposits = inWindow.reduce((s, d) => s + d.amount, 0);
  const depositMonths = new Set(inWindow.map((d) => d.date.substring(0, 7))).size;

  const profits = accounts
    .map((a) => parsePolicyDetails(a.details)?.ytd_profit)
    .filter((p): p is number => typeof p === "number");

  let riskCost = 0;
  let managementFee = 0;
  for (const account of accounts) {
    const statement = classifyStatement(account.insurance_costs);
    riskCost += statement.riskCost;
    managementFee += statement.managementFee;
  }

  const balanceDates = accounts.map((a) => a.balance_date).filter((d): d is string => !!d).sort();

  return {
    totalBalance: accounts.reduce((s, a) => s + (a.balance ?? 0), 0),
    fundCount: accounts.length,
    balanceAsOf: balanceDates.length ? balanceDates[balanceDates.length - 1] : null,
    recentDeposits,
    monthlyDepositAvg: depositMonths > 0 ? recentDeposits / depositMonths : null,
    ytdProfit: profits.length ? profits.reduce((s, p) => s + p, 0) : null,
    costsThisYear: riskCost + managementFee,
    riskCost,
    managementFee,
    feeOnSavingsPct: weightedPct(accounts, (a) => a.commission_savings_pct),
    feeOnDepositsPct: weightedPct(accounts, (a) => a.commission_deposits_pct),
  };
}
