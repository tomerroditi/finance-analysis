/**
 * Classification of a pension provider's year-to-date movement statement.
 *
 * The scraper stores the provider's whole statement in the (misleadingly
 * named) `insurance_costs` column: opening and closing balance, deposits and
 * gains sit alongside the deductions. Summing it blindly — which the UI used
 * to do — yields a number several times any real cost. This module is the
 * single reader of that blob.
 */

/** One row of a provider's movement statement. */
export interface StatementRow {
  title: string;
  amount: number;
}

/** Deduction buckets extracted from a statement. */
export interface StatementBreakdown {
  /** Annual cost of the risk covers (disability, death). Never negative. */
  riskCost: number;
  /** Annual management fee in shekels. Never negative. */
  managementFee: number;
  /** Actuarial balance — signed, because it is legitimately ± per policy. */
  actuarial: number;
  /**
   * Σ|amount| of the *negative* rows that matched no bucket. Never negative.
   *
   * Ignoring an unknown row is the right call for the totals, but it makes the
   * opposite failure silent: rename `עלות הביטוח לסיכוני נכות` to
   * `עלות ביטוח לסיכוני נכות` and the risk cost drops to 0 with nothing to
   * show for it. This is the detector — a deduction we saw and did not
   * understand. Positive rows stay out: those are balances, deposits and
   * gains, and they are ignored on purpose.
   */
  unclassified: number;
}

const RISK_KEYS = ["עלות הביטוח", "risk cost"];
const FEE_KEYS = ["דמי ניהול", "management fee"];
const ACTUARIAL_KEYS = ["איזון אקטוארי", "actuarial"];

function titleMatches(title: string, keys: string[]): boolean {
  const lower = title.toLowerCase();
  return keys.some((key) => lower.includes(key.toLowerCase()));
}

function parseRows(json: string | null): StatementRow[] {
  if (!json) return [];
  try {
    const parsed = JSON.parse(json);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

/**
 * Bucket a statement's rows into risk cost, management fee and actuarial
 * balance.
 *
 * Rows that match no bucket are **ignored** by the cost buckets, never counted
 * as cost — so a provider adding a statement row cannot silently re-inflate the
 * figure. Cost buckets take only negative amounts: a positive-signed cost row
 * is a provider-format change, not a cost.
 *
 * An unmatched *deduction* is still tallied into `unclassified`, so a renamed
 * row shows up as money we could not account for instead of vanishing into a
 * confident ₪0.
 */
export function classifyStatement(json: string | null): StatementBreakdown {
  const breakdown: StatementBreakdown = {
    riskCost: 0,
    managementFee: 0,
    actuarial: 0,
    unclassified: 0,
  };

  for (const row of parseRows(json)) {
    const title = row?.title;
    const amount = row?.amount;
    if (typeof title !== "string" || typeof amount !== "number" || !Number.isFinite(amount)) {
      continue;
    }
    // Checked before the sign guard — the actuarial balance is often positive.
    if (titleMatches(title, ACTUARIAL_KEYS)) {
      breakdown.actuarial += amount;
      continue;
    }
    if (amount >= 0) continue;
    if (titleMatches(title, RISK_KEYS)) {
      breakdown.riskCost += Math.abs(amount);
    } else if (titleMatches(title, FEE_KEYS)) {
      breakdown.managementFee += Math.abs(amount);
    } else {
      breakdown.unclassified += Math.abs(amount);
    }
  }

  return breakdown;
}
