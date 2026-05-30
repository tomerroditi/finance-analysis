import { useState } from "react";
import { createPortal } from "react-dom";
import { Wand2, Eye } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { Transaction } from "../../types/transaction";
import type { ConditionNode, TaggingRule } from "../../services/api";
import { useRuleSelectionState } from "../../hooks/useRuleSelectionState";
import { RuleEditorModal } from "./RuleEditorModal";

interface RuleQuickActionProps {
    /** The transactions currently being marked (single or bulk selection). */
    transactions: Transaction[];
    /** Category staged in the marking UI, used to prefill a new rule. */
    stagedCategory?: string;
    /** Tag staged in the marking UI, used to prefill a new rule. */
    stagedTag?: string;
    /**
     * `bar` — compact icon+label button for the floating bulk actions bar.
     * `inline` — slightly larger button for the single-transaction edit modal.
     */
    variant?: "bar" | "inline";
}

/**
 * "Add Rule" / "View Rule" quick action surfaced while marking transactions.
 *
 * Renders nothing when the selection contains no rule-applicable (bank /
 * credit-card) transactions. Otherwise it inspects how the selection relates to
 * existing auto-tagging rules (see {@link useRuleSelectionState}) and shows:
 * an "Add Rule" button (none match), a "View Rule" button (all share one rule),
 * or a disabled "Add Rule" button (ambiguous selection).
 */
export function RuleQuickAction({
    transactions,
    stagedCategory,
    stagedTag,
    variant = "bar",
}: RuleQuickActionProps) {
    const { t } = useTranslation();
    const state = useRuleSelectionState(transactions);
    const [open, setOpen] = useState(false);

    if (state.kind === "none") return null;

    const iconSize = variant === "bar" ? 18 : 16;
    const baseBtn =
        variant === "bar"
            ? "px-2.5 py-1.5 rounded-lg flex items-center gap-1.5 text-sm font-semibold transition-all whitespace-nowrap"
            : "px-3 py-2 rounded-xl flex items-center justify-center gap-2 text-sm font-semibold transition-all whitespace-nowrap";

    let button;
    let editingRule: TaggingRule | null = null;
    let prefill: { category?: string; tag?: string; conditions?: ConditionNode } | undefined;

    if (state.kind === "view") {
        editingRule = state.rule;
        button = (
            <button
                type="button"
                onClick={() => setOpen(true)}
                className={`${baseBtn} bg-violet-500/15 text-violet-400 hover:bg-violet-500/25`}
                title={t("transactions.ruleAction.viewTooltip")}
            >
                <Eye size={iconSize} /> {t("transactions.ruleAction.view")}
            </button>
        );
    } else if (state.kind === "add") {
        // One `contains <description>` OR branch per distinct selected
        // description. When every selection has a blank description we seed no
        // condition at all (leaving `conditions` undefined) so the editor opens
        // with its default empty builder rather than a `contains ""` rule that
        // would match everything.
        const conditions: ConditionNode | undefined =
            state.seedKeywords.length > 0
                ? {
                      type: "OR",
                      subconditions: state.seedKeywords.map((value) => ({
                          type: "CONDITION" as const,
                          field: "description",
                          operator: "contains" as const,
                          value,
                      })),
                  }
                : undefined;
        prefill = {
            category: stagedCategory || undefined,
            tag: stagedTag || undefined,
            conditions,
        };
        button = (
            <button
                type="button"
                onClick={() => setOpen(true)}
                className={`${baseBtn} bg-[var(--primary)]/15 text-[var(--primary)] hover:bg-[var(--primary)]/25`}
                title={t("transactions.ruleAction.addTooltip")}
            >
                <Wand2 size={iconSize} /> {t("transactions.ruleAction.add")}
            </button>
        );
    } else {
        button = (
            <button
                type="button"
                disabled
                className={`${baseBtn} bg-[var(--surface-light)]/40 text-[var(--text-muted)] opacity-60 cursor-not-allowed`}
                title={t(
                    state.reason === "multiple"
                        ? "transactions.ruleAction.multipleTooltip"
                        : "transactions.ruleAction.mixedTooltip",
                )}
            >
                <Wand2 size={iconSize} /> {t("transactions.ruleAction.add")}
            </button>
        );
    }

    return (
        <>
            {button}
            {/* Portal to <body>: the bulk actions bar uses backdrop-blur
                (a backdrop-filter), which would otherwise make it the
                containing block for the editor's `fixed inset-0` and shrink
                the full-screen modal down to the bar's footprint. */}
            {open &&
                createPortal(
                    <RuleEditorModal
                        isOpen
                        onClose={() => setOpen(false)}
                        editingRule={editingRule}
                        prefill={prefill}
                    />,
                    document.body,
                )}
        </>
    );
}
