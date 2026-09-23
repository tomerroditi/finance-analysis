/**
 * Readers for the pension clearing house's per-policy details and reports.
 *
 * `insurance_accounts.details` is a JSON object the clearing-house scraper
 * writes; older (HaPhoenix) rows have none. Every field is optional, so the
 * UI renders whatever a policy carries and nothing else.
 */
import type { ClearingHouseReport } from "../services/api";

export interface PolicyRepresentative {
  name: string | null;
  id: string | null;
  role: string | null;
  can_act: boolean;
  appointed: string | null;
  expires: string | null;
}

export interface PolicyLoan {
  amount: number;
  balance: number;
  interest_pct: number | null;
  monthly_payment: number;
  payments_months: number | null;
  received: string | null;
  ends: string | null;
}

export interface PolicyDetails {
  source_date?: string | null;
  status?: string | null;
  manufacturer?: string | null;
  employer?: string | null;
  join_date?: string | null;
  retirement_age?: number | null;
  balance_forecast?: number | null;
  balance_forecast_no_deposits?: number | null;
  monthly_pension_forecast?: number | null;
  monthly_pension_forecast_no_deposits?: number | null;
  forecast_yield_pct?: number | null;
  ytd_profit?: number | null;
  last_month_management_fee?: number | null;
  representative?: PolicyRepresentative | null;
  loans?: PolicyLoan[];
}

/** Status the portal gives an active policy ("פעיל"); anything else is not. */
const ACTIVE_STATUS = "פעיל";

/** Parse a policy's details JSON; `null` when there are none or it is unreadable. */
export function parsePolicyDetails(json: string | null | undefined): PolicyDetails | null {
  if (!json) return null;
  try {
    const parsed = JSON.parse(json);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as PolicyDetails)
      : null;
  } catch {
    return null;
  }
}

/** Whether the details mark the policy inactive (no status means unknown, not inactive). */
export function isInactive(details: PolicyDetails | null): boolean {
  return !!details?.status && details.status !== ACTIVE_STATUS;
}

/** Days before expiry from which the subscription notice shows. */
export const SUBSCRIPTION_NOTICE_DAYS = 45;

/**
 * Whether the monthly clearing-house subscription is about to stop.
 *
 * True once at most one report is left, or the expiry is within
 * `SUBSCRIPTION_NOTICE_DAYS` (or already past).
 */
export function isSubscriptionEndingSoon(
  report: ClearingHouseReport | undefined,
  today: Date = new Date(),
): boolean {
  if (!report) return false;
  if (report.subscription_months_left != null && report.subscription_months_left <= 1) {
    return true;
  }
  if (!report.subscription_expires) return false;
  const msLeft = new Date(report.subscription_expires).getTime() - today.getTime();
  return msLeft <= SUBSCRIPTION_NOTICE_DAYS * 24 * 60 * 60 * 1000;
}
