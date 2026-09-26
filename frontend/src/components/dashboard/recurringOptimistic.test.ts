import { describe, it, expect } from "vitest";
import { applyDecisions } from "./recurringOptimistic";
import type { RecurringItem, RecurringSummary } from "../../services/api";

/**
 * The card shows a verdict from this arithmetic before the server confirms
 * it, so anything it gets wrong is visible to the user until the refetch
 * lands. These pin it against what ``RecurringService.get_recurring`` would
 * have answered.
 */

function item(overrides: Partial<RecurringItem> = {}): RecurringItem {
  return {
    label: "NETFLIX.COM",
    normalized: "netflix",
    amount: 45,
    last_amount: 45,
    cadence: "monthly",
    period_days: 30,
    monthly_equivalent: 45,
    occurrences: 6,
    category: "Entertainment",
    first_date: "2026-03-01",
    last_date: "2026-09-01",
    next_expected_date: "2026-10-01",
    status: "active",
    price_change: 0,
    confirmation: "pending",
    confidence: 0.9,
    amount_kind: "fixed",
    ...overrides,
  };
}

function summary(
  items: RecurringItem[],
  overrides: Partial<RecurringSummary> = {},
): RecurringSummary {
  return {
    items,
    total_monthly: 0,
    pending_monthly: 0,
    pending_count: items.length,
    confirmed_count: 0,
    dismissed_count: 0,
    ...overrides,
  };
}

describe("applyDecisions", () => {
  it("moves a confirmed charge's cost out of pending and into the total", () => {
    const before = summary([item(), item({ normalized: "spotify", monthly_equivalent: 20 })], {
      pending_monthly: 65,
    });

    const after = applyDecisions(
      before,
      [{ normalized: "netflix", decision: "confirmed" }],
      false,
    );

    expect(after.total_monthly).toBe(45);
    expect(after.pending_monthly).toBe(20);
    expect(after.confirmed_count).toBe(1);
    expect(after.pending_count).toBe(1);
  });

  it("leaves the summary it was given untouched", () => {
    const before = summary([item()]);

    applyDecisions(before, [{ normalized: "netflix", decision: "confirmed" }], false);

    expect(before.items[0].confirmation).toBe("pending");
    expect(before.total_monthly).toBe(0);
  });

  it("drops a dismissal from a list that does not carry dismissed items", () => {
    const before = summary([item()]);

    const after = applyDecisions(
      before,
      [{ normalized: "netflix", decision: "dismissed" }],
      false,
    );

    expect(after.items).toEqual([]);
    expect(after.dismissed_count).toBe(1);
  });

  it("keeps a dismissal listed when the summary asked for them", () => {
    const before = summary([item()]);

    const after = applyDecisions(
      before,
      [{ normalized: "netflix", decision: "dismissed" }],
      true,
    );

    expect(after.items[0].confirmation).toBe("dismissed");
    expect(after.dismissed_count).toBe(1);
  });

  it("counts a restored dismissal back down", () => {
    const before = summary([item({ confirmation: "dismissed" })], {
      dismissed_count: 1,
      pending_count: 0,
    });

    const after = applyDecisions(
      before,
      [{ normalized: "netflix", decision: "pending" }],
      true,
    );

    expect(after.dismissed_count).toBe(0);
    expect(after.pending_count).toBe(1);
  });

  it("never counts an ended charge into either total", () => {
    const before = summary([item({ status: "ended" })]);

    const after = applyDecisions(
      before,
      [{ normalized: "netflix", decision: "confirmed" }],
      false,
    );

    expect(after.total_monthly).toBe(0);
    expect(after.confirmed_count).toBe(1);
  });

  it("applies a whole batch, as 'confirm all' sends it", () => {
    const before = summary([
      item(),
      item({ normalized: "spotify", monthly_equivalent: 20 }),
      item({ normalized: "gym", monthly_equivalent: 199 }),
    ]);

    const after = applyDecisions(
      before,
      [
        { normalized: "netflix", decision: "confirmed" },
        { normalized: "spotify", decision: "confirmed" },
        { normalized: "gym", decision: "confirmed" },
      ],
      false,
    );

    expect(after.total_monthly).toBe(264);
    expect(after.pending_count).toBe(0);
  });

  it("ignores a verdict for a charge this summary never listed", () => {
    const before = summary([item()]);

    const after = applyDecisions(
      before,
      [{ normalized: "not here", decision: "confirmed" }],
      false,
    );

    expect(after.items).toHaveLength(1);
    expect(after.items[0].confirmation).toBe("pending");
    expect(after.dismissed_count).toBe(0);
  });
});
