import type { BudgetLongEnvelope } from "../../../services/api";

/**
 * Pure helpers for yearly and project envelopes.
 *
 * Kept out of the component file so they can be imported without dragging a
 * component along, and so the arithmetic can be tested directly.
 */

/** Bar colour by how full the envelope is. Matches BudgetLedgerRow's thresholds. */
export function envelopeColor(percent: number): string {
  if (percent > 100) return "bg-rose-500";
  if (percent > 90) return "bg-amber-500";
  return "bg-emerald-500";
}

/** Text colour for the same thresholds. */
export function envelopeTextColor(percent: number): string {
  if (percent > 100) return "text-rose-400";
  if (percent > 90) return "text-amber-400";
  return "text-[var(--text-default)]";
}

/**
 * Share of an envelope consumed.
 *
 * Spend is clamped at zero first: refunds can push an envelope's net negative,
 * and a negative fill would read as a bar running backwards. An envelope with no
 * budget at all is either untouched (0%) or entirely unbudgeted spend (100%) —
 * the same rule the monthly ledger applies to a zero-budget rule.
 */
export function percentOf(envelope: BudgetLongEnvelope): number {
  if (envelope.budget <= 0) return envelope.spent > 0 ? 100 : 0;
  return Math.round((Math.max(envelope.spent, 0) / envelope.budget) * 100);
}

/** Envelopes ranked by how full they are, so the ones in trouble come first. */
export function rankEnvelopes(
  envelopes: BudgetLongEnvelope[],
): BudgetLongEnvelope[] {
  return [...envelopes].sort((a, b) => percentOf(b) - percentOf(a));
}
