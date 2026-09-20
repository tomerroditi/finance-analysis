import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";
import type { TaggingRule } from "../services/api";
import type { Transaction } from "../types/transaction";

const rules = vi.hoisted(() => ({ current: [] as TaggingRule[] }));

vi.mock("./useTaggingRules", () => ({
  useTaggingRules: () => ({ data: rules.current }),
}));

const { useRuleSelectionState } = await import("./useRuleSelectionState");

const makeTx = (overrides: Partial<Transaction> = {}): Transaction => ({
  unique_id: "1",
  amount: -100,
  date: "2026-01-15",
  description: "GOZ GOZ",
  source: "credit_card_transactions",
  ...overrides,
});

const makeRule = (overrides: Partial<TaggingRule> = {}): TaggingRule => ({
  id: 1,
  name: "Food - Restaurants",
  category: "Food",
  tag: "Restaurants",
  conditions: {
    type: "OR",
    subconditions: [
      { type: "CONDITION", field: "description", operator: "contains", value: "LOTIE" },
    ],
  },
  ...overrides,
});

describe("useRuleSelectionState", () => {
  beforeEach(() => {
    rules.current = [];
  });

  it("hides itself when nothing in the selection is rule-applicable", () => {
    const { result } = renderHook(() =>
      useRuleSelectionState([makeTx({ source: "cash_transactions" })]),
    );
    expect(result.current.kind).toBe("none");
  });

  it("offers to create a rule when the staged category/tag is unclaimed", () => {
    rules.current = [makeRule()];
    const { result } = renderHook(() =>
      useRuleSelectionState([makeTx()], { category: "Food", tag: "Coffee" }),
    );
    expect(result.current).toEqual({ kind: "add", seedKeywords: ["GOZ GOZ"] });
  });

  // The editor allows only one rule per (category, tag), so a second rule for
  // a claimed pair could not be saved — grow the owner instead.
  it("offers to extend the rule that already owns the staged category/tag", () => {
    const owner = makeRule();
    rules.current = [owner];
    const { result } = renderHook(() =>
      useRuleSelectionState([makeTx()], { category: "Food", tag: "Restaurants" }),
    );
    expect(result.current).toEqual({
      kind: "extend",
      rule: owner,
      seedKeywords: ["GOZ GOZ"],
    });
  });

  it("picks the lowest-id owner when duplicates exist", () => {
    const later = makeRule({ id: 7 });
    const first = makeRule({ id: 3 });
    rules.current = [later, first];
    const { result } = renderHook(() =>
      useRuleSelectionState([makeTx()], { category: "Food", tag: "Restaurants" }),
    );
    expect(result.current).toMatchObject({ kind: "extend", rule: first });
  });

  it("falls back to creating a rule when every description is blank", () => {
    rules.current = [makeRule()];
    const { result } = renderHook(() =>
      useRuleSelectionState([makeTx({ description: "  " })], {
        category: "Food",
        tag: "Restaurants",
      }),
    );
    expect(result.current).toEqual({ kind: "add", seedKeywords: [] });
  });

  // A transaction the rule already catches needs no new condition at all.
  it("offers to view the rule when the selection already matches one", () => {
    const owner = makeRule();
    rules.current = [owner];
    const { result } = renderHook(() =>
      useRuleSelectionState([makeTx({ description: "LOTIE TLV" })], {
        category: "Food",
        tag: "Restaurants",
      }),
    );
    expect(result.current).toEqual({ kind: "view", rule: owner });
  });

  it("stays disabled when only part of the selection matches a rule", () => {
    rules.current = [makeRule()];
    const { result } = renderHook(() =>
      useRuleSelectionState(
        [makeTx({ description: "LOTIE TLV" }), makeTx({ unique_id: "2" })],
        { category: "Food", tag: "Restaurants" },
      ),
    );
    expect(result.current).toEqual({ kind: "disabled", reason: "mixed" });
  });

  // The bulk actions bar opens with empty category/tag dropdowns, so without
  // this the already-tagged selection would offer to create a duplicate rule.
  it("falls back to the selection's own category/tag when nothing is staged", () => {
    const owner = makeRule();
    rules.current = [owner];
    const { result } = renderHook(() =>
      useRuleSelectionState([makeTx({ category: "Food", tag: "Restaurants" })]),
    );
    expect(result.current).toMatchObject({ kind: "extend", rule: owner });
  });

  it("does not fall back when the selection's category/tag disagree", () => {
    rules.current = [makeRule()];
    const { result } = renderHook(() =>
      useRuleSelectionState([
        makeTx({ category: "Food", tag: "Restaurants" }),
        makeTx({ unique_id: "2", description: "PAZ 12", category: "Food", tag: "Coffee" }),
      ]),
    );
    expect(result.current.kind).toBe("add");
  });

  // Call sites pass the staged category/tag as an inline object literal, so a
  // fresh identity every render must not recompute the state.
  it("ignores the staged object's identity when memoizing", () => {
    rules.current = [makeRule()];
    const transactions = [makeTx()];
    const { result, rerender } = renderHook(() =>
      useRuleSelectionState(transactions, { category: "Food", tag: "Restaurants" }),
    );
    const first = result.current;
    rerender();
    expect(result.current).toBe(first);
  });
});
