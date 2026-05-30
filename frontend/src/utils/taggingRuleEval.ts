import type { TaggingRule, ConditionNode } from "../services/api";
import type { Transaction } from "../types/transaction";

/** Evaluate a single condition leaf against a transaction. */
export function evalCondition(node: ConditionNode, tx: Transaction): boolean {
  const { field, operator, value } = node;
  if (!field || !operator) return false;

  // Service field: compare against source
  if (field === "service") {
    if (operator !== "equals") return false;
    const svc = String(value).toLowerCase().replace(/\s+/g, "_");
    return (tx.source || "").toLowerCase().includes(svc);
  }

  const fieldMap: Record<string, string | number> = {
    description: tx.description ?? tx.desc ?? "",
    amount: tx.amount,
    provider: tx.provider ?? "",
    account_name: tx.account_name ?? "",
  };
  const fv = fieldMap[field];
  if (fv === undefined) return false;

  // Numeric operators
  if (field === "amount") {
    const n = Number(fv);
    if (operator === "gt") return n > Number(value);
    if (operator === "lt") return n < Number(value);
    if (operator === "gte") return n >= Number(value);
    if (operator === "lte") return n <= Number(value);
    if (operator === "equals") return n === Number(value);
    if (operator === "between" && Array.isArray(value))
      return n >= Number(value[0]) && n <= Number(value[1]);
    return false;
  }

  // Text operators. The backend uses SQL LIKE for contains/starts_with/
  // ends_with, which is case-insensitive for ASCII in SQLite, so we lowercase
  // both sides to match. `equals` maps to a case-sensitive `column == value`
  // on the backend, so it stays an exact comparison.
  const sv = String(fv);
  const tv = String(value);
  const svLower = sv.toLowerCase();
  const tvLower = tv.toLowerCase();
  if (operator === "contains") return svLower.includes(tvLower);
  if (operator === "equals") return sv === tv;
  if (operator === "starts_with") return svLower.startsWith(tvLower);
  if (operator === "ends_with") return svLower.endsWith(tvLower);
  return false;
}

/** Recursively evaluate a condition tree against a transaction. */
export function evalConditionTree(node: ConditionNode, tx: Transaction): boolean {
  if (node.type === "CONDITION") return evalCondition(node, tx);
  const subs = node.subconditions ?? [];
  if (subs.length === 0) return true; // empty group matches all
  if (node.type === "AND") return subs.every((s) => evalConditionTree(s, tx));
  if (node.type === "OR") return subs.some((s) => evalConditionTree(s, tx));
  return false;
}

/** Find the first tagging rule whose conditions match a transaction. */
export function findMatchingRule(
  rules: TaggingRule[],
  tx: Transaction,
): TaggingRule | undefined {
  return rules.find((r) => evalConditionTree(r.conditions, tx));
}

/** Find every tagging rule whose conditions match a transaction. */
export function findMatchingRules(
  rules: TaggingRule[],
  tx: Transaction,
): TaggingRule[] {
  return rules.filter((r) => evalConditionTree(r.conditions, tx));
}
