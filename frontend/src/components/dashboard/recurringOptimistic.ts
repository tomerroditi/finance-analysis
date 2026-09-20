import type {
  RecurringDecisionInput,
  RecurringSummary,
} from "../../services/api";

/**
 * Re-derive a recurring summary as if a batch of verdicts had been stored.
 *
 * A verdict is a cheap write, but it invalidates every derived read the
 * dashboard holds — the budget Overview, the forecast, the insight cards —
 * so the round trip that proves it landed is long enough for the card to look
 * broken, with the item still sitting in "needs review" after the click. The
 * card applies the same arithmetic the backend would locally and shows the
 * result immediately; the refetch that follows either agrees or corrects it.
 *
 * Totals count only *live* (non-ended) charges, matching
 * ``RecurringService.get_recurring``, and dismissed items are dropped from a
 * summary that was fetched without them.
 *
 * @param summary - The cached summary to re-derive.
 * @param decisions - The verdicts being stored.
 * @param includeDismissed - Whether this summary lists dismissed candidates.
 * @returns A new summary; the input is left untouched.
 */
export function applyDecisions(
  summary: RecurringSummary,
  decisions: RecurringDecisionInput[],
  includeDismissed: boolean,
): RecurringSummary {
  const verdicts = new Map(decisions.map((d) => [d.normalized, d.decision]));

  // Dismissals are counted across *every* candidate, including the ones a
  // summary without `include_dismissed` never listed — so the count moves by
  // the delta this batch causes rather than being recounted from `items`.
  let dismissedDelta = 0;
  const items = summary.items.map((item) => {
    const decision = verdicts.get(item.normalized);
    if (!decision || decision === item.confirmation) return item;
    dismissedDelta +=
      (decision === "dismissed" ? 1 : 0) -
      (item.confirmation === "dismissed" ? 1 : 0);
    return { ...item, confirmation: decision };
  });

  const visible = includeDismissed
    ? items
    : items.filter((item) => item.confirmation !== "dismissed");
  const live = visible.filter((item) => item.status !== "ended");
  const sumOf = (confirmation: string) =>
    Math.round(
      live
        .filter((item) => item.confirmation === confirmation)
        .reduce((total, item) => total + item.monthly_equivalent, 0) * 100,
    ) / 100;

  return {
    items: visible,
    total_monthly: sumOf("confirmed"),
    pending_monthly: sumOf("pending"),
    pending_count: visible.filter((i) => i.confirmation === "pending").length,
    confirmed_count: visible.filter((i) => i.confirmation === "confirmed")
      .length,
    dismissed_count: Math.max(0, summary.dismissed_count + dismissedDelta),
  };
}
