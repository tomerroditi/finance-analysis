import { MutationCache, type QueryClient } from "@tanstack/react-query";

/** Trailing-edge debounce before the sweep runs. */
export const INVALIDATE_DEBOUNCE_MS = 200;

/**
 * Build the app-wide "something was written, refresh everything" sweep.
 *
 * Any successful mutation alters server state, so every cached query could
 * now be stale. Sweeping the whole cache beats per-mutation invalidation: a
 * mutation in one feature frequently has knock-on effects (a new transaction
 * shifts budgets, KPIs, sankey, net-worth) and listing every dependent key at
 * every mutation site is fragile. Mounted queries refetch immediately;
 * unmounted ones refetch on next mount and the persister updates the
 * IndexedDB snapshot through its throttle.
 *
 * Trailing-edge debounce: when several mutations land in a burst (bulk
 * tagging, split-then-edit, confirming a run of recurring charges) they
 * coalesce into one sweep rather than one refetch of everything per mutation.
 *
 * Extracted from `queryClient.ts` so a test can drive the real sweep against
 * its own client instead of reimplementing it: `queryClient.ts` builds a
 * module-level singleton wired to IndexedDB, which a component test cannot
 * borrow. Behaviour is unchanged by the extraction.
 *
 * @param client - The query client to sweep.
 * @param delayMs - Debounce window.
 * @returns A `schedule()` to call on every successful mutation.
 */
export function createInvalidationSweep(
  client: QueryClient,
  delayMs: number = INVALIDATE_DEBOUNCE_MS,
): () => void {
  let timer: ReturnType<typeof setTimeout> | undefined;

  return function schedule() {
    if (timer !== undefined) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = undefined;
      client.invalidateQueries();
    }, delayMs);
  };
}

/**
 * Build the app-wide mutation cache: what happens to the query cache around
 * every write, wherever in the app it comes from.
 *
 * Extracted so a test can build the same cache against its own client —
 * `queryClient.ts` owns a module-level singleton wired to IndexedDB that a
 * test cannot borrow.
 *
 * @param getClient - Returns the client this cache belongs to. A function
 *   because the client is constructed *with* this cache, so it does not
 *   exist yet when this is called.
 * @param delayMs - Debounce window for the post-write sweep.
 */
export function createMutationCache(
  getClient: () => QueryClient,
  delayMs: number = INVALIDATE_DEBOUNCE_MS,
): MutationCache {
  let sweep: (() => void) | null = null;
  return new MutationCache({
    onMutate: () => dropReadsOlderThanTheWrite(getClient()),
    // On settled rather than on success: a write that failed still cancelled
    // the reads above, and they have to be re-issued or the screen keeps
    // data nothing will refresh. A failed write sweeping costs one debounced
    // refresh and re-confirms what the server actually holds.
    onSettled: () => {
      sweep ??= createInvalidationSweep(getClient(), delayMs);
      sweep();
    },
  });
}

/**
 * Cancel every read that was already in flight when a write began.
 *
 * Such a read was computed against the state *before* the write, so whatever
 * it returns is already wrong; if it lands after the write it overwrites it.
 * React Query supersedes an older fetch with a newer fetch on the same key,
 * but the features that answer a click immediately do it with
 * `setQueryData`, and a patch is not a fetch — nothing stops the older
 * response from landing on top and restoring what the user just changed.
 *
 * Cancelling here rather than in each call site is the point: it holds for
 * every write in the app, including ones not written yet, instead of relying
 * on each `onMutate` to remember `cancelQueries`. Nothing is lost — the
 * sweep that follows re-issues them against post-write state.
 *
 * A read with no data yet is left alone. It has nothing to overwrite, and
 * cancelling it would restart a page's first load because the user happened
 * to click while it was still coming in.
 *
 * @param client - The client whose in-flight reads to drop.
 */
function dropReadsOlderThanTheWrite(client: QueryClient): void {
  for (const query of client.getQueryCache().findAll({ fetchStatus: "fetching" })) {
    if (query.state.data === undefined) continue;
    void query.cancel({ revert: true });
  }
}
