import type { Transaction } from "../../types/transaction";

const idOf = (tx: Transaction) => Number(tx.unique_id ?? tx.id ?? 0);

/**
 * The feed's order: newest date first, and within a date a fixed order of
 * the rows themselves.
 *
 * Without the tie-break, rows sharing a date kept the order of the array
 * they arrived in — and a budget pool's array is the union of its rules'
 * lists, which a retag rearranges. The optimistic patch appends a retagged
 * row to its new rule while the server lists it in place, so the row jumped
 * within its day on click and jumped back when the refetch landed.
 *
 * @param a - One row.
 * @param b - The other.
 * @returns A comparator result for `Array.prototype.sort`.
 */
export function compareFeedRows(a: Transaction, b: Transaction): number {
  return (
    new Date(b.date).getTime() - new Date(a.date).getTime() ||
    (a.source ?? "").localeCompare(b.source ?? "") ||
    idOf(b) - idOf(a) ||
    (a.split_id ?? -1) - (b.split_id ?? -1)
  );
}
