import { useMemo } from "react";
import type { Transaction } from "../types/transaction";
import type { TaggingRule } from "../services/api";
import { useTaggingRules } from "./useTaggingRules";
import { findMatchingRules } from "../utils/taggingRuleEval";

/**
 * Result of evaluating a selection of transactions against the auto-tagging
 * rules, used to drive the "Add Rule" / "View Rule" quick action when marking
 * transactions.
 *
 * - `none`     — no rule-applicable transactions in the selection; hide the button.
 * - `add`      — none of the selected transactions match any rule, and no rule
 *                owns the staged category/tag; offer to create one.
 *                `seedKeywords` holds the distinct transaction descriptions
 *                (verbatim, trimmed, deduped) across the selection, which the
 *                quick action turns into an OR of `description contains`
 *                conditions — one branch per distinct description. A single
 *                transaction yields one condition. May be empty when every
 *                selected transaction has a blank description, in which case the
 *                editor opens with no seeded condition.
 * - `extend`   — nothing matches, but a rule already owns the staged
 *                category/tag. Only one rule per (category, tag) is allowed, so
 *                a second one could not be saved at all: offer to add the
 *                `seedKeywords` to `rule` instead.
 * - `view`     — every selected transaction matches the exact same single rule;
 *                offer to open it.
 * - `disabled` — the selection is ambiguous (some match and some don't, or
 *                multiple distinct rules are involved); show a disabled button
 *                with an explanatory tooltip.
 */
export type RuleSelectionState =
  | { kind: "none" }
  | { kind: "add"; seedKeywords: string[] }
  | { kind: "extend"; rule: TaggingRule; seedKeywords: string[] }
  | { kind: "view"; rule: TaggingRule }
  | { kind: "disabled"; reason: "mixed" | "multiple" };

/**
 * The (category, tag) every transaction in the selection carries, or empty
 * strings when they disagree or any is untagged.
 */
function uniformCategoryTag(transactions: Transaction[]): [string, string] {
  const first = transactions[0];
  if (!first?.category || !first.tag) return ["", ""];
  const agrees = transactions.every(
    (tx) => tx.category === first.category && tx.tag === first.tag,
  );
  return agrees ? [first.category, first.tag] : ["", ""];
}

/** Auto-tagging rules only apply to bank and credit-card transactions. */
function isRuleApplicable(tx: Transaction): boolean {
  const src = (tx.source ?? "").toLowerCase();
  return src.includes("bank") || src.includes("credit_card");
}

export function useRuleSelectionState(
  transactions: Transaction[],
  /**
   * The category/tag the marking UI is about to assign. When either is
   * missing, the selection's own uniform category/tag stands in. Read as
   * primitives below so an inline object literal at the call site cannot bust
   * the memo.
   */
  staged?: { category?: string; tag?: string },
): RuleSelectionState {
  const { data: rules } = useTaggingRules();
  const stagedCategory = staged?.category ?? "";
  const stagedTag = staged?.tag ?? "";

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
      // Seed `contains <description>` verbatim — the description is trivially a
      // substring of itself, so the rule always matches at least the source
      // transaction. Distinct descriptions across the selection are deduped,
      // in first-seen order, and each becomes an OR branch in the new rule.
      const seedKeywords: string[] = [];
      const seen = new Set<string>();
      for (const tx of applicable) {
        const description = (tx.description ?? tx.desc ?? "").trim();
        if (description && !seen.has(description)) {
          seen.add(description);
          seedKeywords.push(description);
        }
      }
      // With nothing staged (the bulk bar opens on empty dropdowns), fall back
      // to the category/tag the selection already carries — but only when every
      // transaction agrees, since a mixed selection names no single rule.
      const [category, tag] =
        stagedCategory && stagedTag
          ? [stagedCategory, stagedTag]
          : uniformCategoryTag(applicable);

      // A rule already owning this exact (category, tag) is the one to grow:
      // the editor filters out tags that a rule already claims, so a second
      // rule for the pair cannot be saved. Lowest id wins if data predating
      // that rule left duplicates — that is the one tagging reaches first.
      const owner =
        category && tag
          ? ruleList
              .filter((r) => r.category === category && r.tag === tag)
              .sort((a, b) => a.id - b.id)[0]
          : undefined;
      if (owner && seedKeywords.length > 0) {
        return { kind: "extend", rule: owner, seedKeywords };
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
  }, [transactions, rules, stagedCategory, stagedTag]);
}
