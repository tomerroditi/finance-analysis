import { describe, it, expect } from "vitest";
import { evalCondition } from "./taggingRuleEval";
import type { ConditionNode } from "../services/api";
import type { Transaction } from "../types/transaction";

function tx(description: string): Transaction {
  return { description } as Transaction;
}

function cond(operator: string, value: string): ConditionNode {
  return {
    type: "CONDITION",
    field: "description",
    operator: operator as ConditionNode["operator"],
    value,
  };
}

describe("evalCondition text operators", () => {
  // The backend matches contains/starts_with/ends_with via SQL LIKE, which is
  // case-insensitive for ASCII in SQLite. The preview must mirror that so the
  // "would be auto-tagged" hint agrees with what apply-rules actually does.
  it("contains is case-insensitive (matches backend LIKE)", () => {
    expect(evalCondition(cond("contains", "shufersal"), tx("SHUFERSAL DEAL"))).toBe(true);
    expect(evalCondition(cond("contains", "SHUFERSAL"), tx("shufersal deal"))).toBe(true);
  });

  it("starts_with is case-insensitive", () => {
    expect(evalCondition(cond("starts_with", "uber"), tx("UBER *TRIP"))).toBe(true);
  });

  it("ends_with is case-insensitive", () => {
    expect(evalCondition(cond("ends_with", "flix"), tx("NETFLIX"))).toBe(true);
  });

  // `equals` maps to a case-sensitive `column == value` on the backend.
  it("equals stays case-sensitive", () => {
    expect(evalCondition(cond("equals", "Netflix"), tx("Netflix"))).toBe(true);
    expect(evalCondition(cond("equals", "netflix"), tx("Netflix"))).toBe(false);
  });
});
