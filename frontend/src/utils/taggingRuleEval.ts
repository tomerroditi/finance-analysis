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

/** Auto-tagging rules only apply to bank and credit-card transactions. */
export function isRuleApplicable(tx: Transaction): boolean {
  const src = (tx.source ?? "").toLowerCase();
  return src.includes("bank") || src.includes("credit_card");
}

/** Find the first tagging rule whose conditions match a transaction. */
export function findMatchingRule(
  rules: TaggingRule[],
  tx: Transaction,
): TaggingRule | undefined {
  return rules.find((r) => evalConditionTree(r.conditions, tx));
}

/**
 * A rule-applicable transaction that no rule matches — a candidate for a new
 * rule. Cash and manual rows never qualify: no rule can ever reach them.
 */
export function isWithoutRule(rules: TaggingRule[], tx: Transaction): boolean {
  return isRuleApplicable(tx) && !findMatchingRule(rules, tx);
}

/** Find every tagging rule whose conditions match a transaction. */
export function findMatchingRules(
  rules: TaggingRule[],
  tx: Transaction,
): TaggingRule[] {
  return rules.filter((r) => evalConditionTree(r.conditions, tx));
}

/** Every `description` leaf in a condition tree, however deeply nested. */
function descriptionLeaves(node: ConditionNode): ConditionNode[] {
  if (node.type === "CONDITION") return node.field === "description" ? [node] : [];
  return (node.subconditions ?? []).flatMap(descriptionLeaves);
}

/**
 * The `description` leaves that match on their own: the root itself, or a
 * direct branch of an `OR` root. A leaf inside an `AND` only matches together
 * with its siblings (an amount range, an account), so it does not count.
 */
function standaloneDescriptionLeaves(node: ConditionNode): ConditionNode[] {
  if (node.type === "CONDITION") return node.field === "description" ? [node] : [];
  if (node.type !== "OR") return [];
  return (node.subconditions ?? []).filter(
    (sub) => sub.type === "CONDITION" && sub.field === "description",
  );
}

/**
 * Add one `description contains <value>` branch per value to a rule's existing
 * conditions, at the start of the list.
 *
 * This is how a transaction joins the rule that already owns its category/tag
 * instead of spawning a second rule for the same pair — the editor allows only
 * one rule per (category, tag), so a second one is not even savable.
 *
 * An `OR` root takes the new branches directly; anything else (an `AND` group,
 * or a bare condition) is wrapped in an `OR` so the rule goes on matching
 * everything it matched before. The new branches lead the list (order inside
 * an `OR` changes nothing it matches) so the editor shows the change first.
 * A value is skipped only when a standalone description branch already
 * matches it; when nothing is left to add the tree is returned untouched.
 *
 * A value that a description condition *nested under other conditions*
 * already matches (`description contains X AND amount < -100`) still gets its
 * branch — without it the transaction stays outside the rule — and is
 * reported in `gated`, so the editor can say why the rule needed one.
 *
 * @returns The grown tree, the branch nodes that were added to it (the editor
 *   marks exactly those objects as the change), and the values whose
 *   description the rule already tests behind other conditions.
 */
export function appendDescriptionConditions(
  conditions: ConditionNode,
  values: string[],
): { conditions: ConditionNode; added: ConditionNode[]; gated: string[] } {
  const standalone = standaloneDescriptionLeaves(conditions);
  const nested = descriptionLeaves(conditions).filter((leaf) => !standalone.includes(leaf));
  const matchedBy = (leaves: ConditionNode[], value: string) =>
    leaves.some((leaf) => evalCondition(leaf, { description: value } as Transaction));

  const seen = new Set<string>();
  const added: ConditionNode[] = [];
  const gated: string[] = [];
  for (const value of values) {
    const key = value.toLowerCase();
    if (!value || seen.has(key) || matchedBy(standalone, value)) continue;
    seen.add(key);
    added.push({
      type: "CONDITION",
      field: "description",
      operator: "contains",
      value,
    });
    if (matchedBy(nested, value)) gated.push(value);
  }
  if (added.length === 0) return { conditions, added, gated };

  if (conditions.type === "OR") {
    return {
      conditions: {
        ...conditions,
        subconditions: [...added, ...(conditions.subconditions ?? [])],
      },
      added,
      gated,
    };
  }
  return { conditions: { type: "OR", subconditions: [...added, conditions] }, added, gated };
}
