import { useMemo } from "react";
import type { Transaction } from "../types/transaction";
import type { TaggingRule } from "../services/api";
import { useTaggingRules } from "./useTaggingRules";
import { findMatchingRules } from "../utils/taggingRuleEval";
import { deriveRuleKeyword } from "../utils/ruleKeyword";

/**
 * Result of evaluating a selection of transactions against the auto-tagging
 * rules, used to drive the "Add Rule" / "View Rule" quick action when marking
 * transactions.
 *
 * - `none`     — no rule-applicable transactions in the selection; hide the button.
 * - `add`      — none of the selected transactions match any rule; offer to create
 *                one, seeded from the first transaction's description.
 * - `view`     — every selected transaction matches the exact same single rule;
 *                offer to open it.
 * - `disabled` — the selection is ambiguous (some match and some don't, or
 *                multiple distinct rules are involved); show a disabled button
 *                with an explanatory tooltip.
 */
export type RuleSelectionState =
  | { kind: "none" }
  | { kind: "add"; seedKeyword: string }
  | { kind: "view"; rule: TaggingRule }
  | { kind: "disabled"; reason: "mixed" | "multiple" };

/** Auto-tagging rules only apply to bank and credit-card transactions. */
function isRuleApplicable(tx: Transaction): boolean {
  const src = (tx.source ?? "").toLowerCase();
  return src.includes("bank") || src.includes("credit_card");
}

export function useRuleSelectionState(
  transactions: Transaction[],
): RuleSelectionState {
  const { data: rules } = useTaggingRules();

  return useMemo<RuleSelectionState>(() => {
    const applicable = transactions.filter(isRuleApplicable);
    if (applicable.length === 0) return { kind: "none" };

    const ruleList = rules ?? [];
    const matchedIds = new Set<number>();
    let anyUnmatched = false;
    let anyMultiple = false;

    for (const tx of applicable) {
      const matches = findMatchingRules(ruleList, tx);
      if (matches.length === 0) anyUnmatched = true;
      if (matches.length > 1) anyMultiple = true;
      for (const r of matches) matchedIds.add(r.id);
    }

    if (matchedIds.size === 0) {
      const seed = applicable[0].description ?? applicable[0].desc ?? "";
      return { kind: "add", seedKeyword: deriveRuleKeyword(seed) };
    }

    if (matchedIds.size === 1 && !anyUnmatched && !anyMultiple) {
      const ruleId = [...matchedIds][0];
      const rule = ruleList.find((r) => r.id === ruleId);
      if (rule) return { kind: "view", rule };
    }

    return {
      kind: "disabled",
      reason: matchedIds.size > 1 || anyMultiple ? "multiple" : "mixed",
    };
  }, [transactions, rules]);
}
