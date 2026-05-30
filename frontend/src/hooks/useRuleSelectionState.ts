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
 *                one. `seedKeywords` holds the distinct merchant-prefix keywords
 *                derived from the selection (one per merchant), each a verbatim
 *                substring of its description, which the quick action turns into
 *                an OR of `description contains` conditions. A single transaction
 *                yields one keyword. May be empty when no usable prefix could be
 *                derived (e.g. descriptions that lead with generic words /
 *                numbers) — the editor then opens with no seeded condition.
 * - `view`     — every selected transaction matches the exact same single rule;
 *                offer to open it.
 * - `disabled` — the selection is ambiguous (some match and some don't, or
 *                multiple distinct rules are involved); show a disabled button
 *                with an explanatory tooltip.
 */
export type RuleSelectionState =
  | { kind: "none" }
  | { kind: "add"; seedKeywords: string[] }
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
      // Distinct cleaned keywords across the selection, in first-seen order.
      // Multiple transactions from the same merchant collapse to one keyword;
      // each distinct keyword becomes an OR branch in the new rule.
      const seedKeywords: string[] = [];
      const seen = new Set<string>();
      for (const tx of applicable) {
        const keyword = deriveRuleKeyword(tx.description ?? tx.desc ?? "");
        if (keyword && !seen.has(keyword)) {
          seen.add(keyword);
          seedKeywords.push(keyword);
        }
      }
      return { kind: "add", seedKeywords };
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
