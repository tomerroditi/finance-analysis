import type { QueryClient } from "@tanstack/react-query";

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
