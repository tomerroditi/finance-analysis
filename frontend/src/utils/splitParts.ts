import type { Transaction } from "../types/transaction";

/** Whether a row is one part of a split transaction. */
export function isSplitPart(tx: Transaction): boolean {
  return tx.type === "split_child" && tx.parent_unique_id != null;
}

/** "Category / Tag", or the category alone, or null when the parent had neither. */
export function parentTagLabel(tx: Transaction): string | null {
  if (!tx.parent_category) return null;
  return tx.parent_tag ? `${tx.parent_category} / ${tx.parent_tag}` : tx.parent_category;
}

/**
 * Every part of the split a row belongs to, itself included, largest first.
 * `unique_id` is per table, so a part is matched on its source as well.
 */
export function splitSiblings(transactions: Transaction[], tx: Transaction): Transaction[] {
  if (!isSplitPart(tx)) return [];
  return transactions
    .filter(
      (other) =>
        isSplitPart(other) &&
        other.parent_unique_id === tx.parent_unique_id &&
        other.source === tx.source,
    )
    .sort((a, b) => Math.abs(b.amount) - Math.abs(a.amount));
}
