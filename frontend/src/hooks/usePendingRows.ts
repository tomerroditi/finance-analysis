import { useCallback, useState } from "react";

/**
 * Track which rows of a list a shared mutation is currently writing.
 *
 * A list renders one `useMutation` and every row calls it, so `isPending` is
 * true for the *whole list* while any one row is in flight. Gating each row's
 * button on that disables every sibling: on a slow write the list locks for
 * seconds and clicks land on dead buttons, which reads as the action not
 * having registered. Gating on this instead keeps the double-submit guard on
 * the row being written and leaves the others alone.
 *
 * A set rather than the mutation's own `variables`, because more than one row
 * can be in flight at once — `TransactionsTable` unlinks every refund link of
 * a transaction in a loop — and `variables` only ever holds the most recent
 * call, which would re-enable the rows still being written.
 *
 * Wire it to the mutation's lifecycle, not to the click, so a row is released
 * whether the write succeeded or failed:
 *
 * ```tsx
 * const writing = usePendingRows();
 * const mutation = useMutation({
 *   mutationFn: (tx: Transaction) => api.mark(tx),
 *   onMutate: (tx) => { writing.begin(rowKey(tx)); },
 *   onSettled: (_data, _error, tx) => writing.end(rowKey(tx)),
 * });
 * // …
 * <button disabled={writing.isPending(rowKey(tx))} />
 * ```
 *
 * @returns `isPending(key)` for the row's disabled state, plus `begin` /
 *   `end` to call from the mutation's `onMutate` / `onSettled`.
 */
export function usePendingRows<K = string>() {
  const [rows, setRows] = useState<ReadonlySet<K>>(() => new Set<K>());

  const begin = useCallback((key: K) => {
    setRows((current) => new Set(current).add(key));
  }, []);

  const end = useCallback((key: K) => {
    setRows((current) => {
      if (!current.has(key)) return current;
      const next = new Set(current);
      next.delete(key);
      return next;
    });
  }, []);

  const isPending = useCallback((key: K) => rows.has(key), [rows]);

  return { isPending, begin, end };
}
