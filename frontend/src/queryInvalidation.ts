import {
  MutationCache,
  hashKey,
  matchQuery,
  type InvalidateQueryFilters,
  type Query,
  type QueryClient,
  type QueryKey,
} from "@tanstack/react-query";

/** Trailing-edge debounce before the sweep runs. */
export const INVALIDATE_DEBOUNCE_MS = 200;

/**
 * Build the app-wide "something was written, refresh everything" sweep.
 *
 * Any successful mutation alters server state, so every cached query could
 * now be stale. Sweeping the whole cache beats per-mutation invalidation: a
 * mutation in one feature frequently has knock-on effects (a new transaction
 * shifts budgets, KPIs, net-worth) and listing every dependent key at
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
): (plan?: RefreshPlan) => void {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let first: QueryKey[] = [];
  // What every write in the burst agrees it cannot have changed: a read is
  // left alone only if no write in the batch could have touched it.
  let skip: QueryKey[] | null = null;
  // The union of what the burst's writes say is all they reach; `null` once
  // any write in it names no limit, which means everything.
  let only: QueryKey[] | null | undefined;

  return function schedule(plan: RefreshPlan = {}) {
    first = [...first, ...(plan.first ?? [])];
    const planSkip = plan.skip ?? [];
    skip =
      skip === null
        ? [...planSkip]
        : skip.filter((key) => planSkip.some((other) => hashKey(other) === hashKey(key)));
    only = plan.only === undefined || only === null ? null : [...(only ?? []), ...plan.only];
    if (timer !== undefined) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = undefined;
      const batch = { first, skip: skip ?? [], only: only ?? null };
      first = [];
      skip = null;
      only = undefined;
      if (batch.only !== null && batch.only.length === 0 && batch.first.length === 0) return;
      const limit = batch.only;
      const rest: InvalidateQueryFilters =
        limit === null
          ? {}
          : { predicate: (query) => limit.some((queryKey) => matchQuery({ queryKey }, query)) };
      void refreshInOrder(client, batch.first, rest, batch.skip);
    }, delayMs);
  };
}

/**
 * Refetch what is on screen under `first`, and only then everything else.
 *
 * A write invalidates the whole cache, and the browser runs six requests at
 * a time: with ~25 refetches fired together, the one read the user is waiting
 * for — the month they just retagged in — queued behind the trend, the
 * alerts and every dashboard card, and arrived seconds after the backend
 * could have answered it. Ordering the refetch puts that read first.
 *
 * Every refetch joins one already under way rather than restarting it. Every
 * read still in flight here began after the write committed (the mutation
 * cache drops older ones); restarting it abandons the response mid-way while
 * its request keeps a connection busy.
 *
 * @param client - The query client to refresh.
 * @param first - Keys whose mounted queries refetch before anything else.
 * @param rest - Filters for the second pass; everything when omitted.
 * @param skip - Keys the second pass leaves alone — reads the write cannot
 *   have changed, which are neither refetched nor marked stale.
 */
export async function refreshInOrder(
  client: QueryClient,
  first: readonly QueryKey[],
  rest: InvalidateQueryFilters = {},
  skip: readonly QueryKey[] = [],
): Promise<void> {
  await Promise.allSettled(
    first.map((queryKey) =>
      client.refetchQueries({ queryKey, type: "active" }, { cancelRefetch: false }),
    ),
  );
  const under = (keys: readonly QueryKey[], query: Query) =>
    keys.some((queryKey) => matchQuery({ queryKey }, query));
  await client.invalidateQueries(
    {
      ...rest,
      predicate: (query) =>
        // What the first pass just fetched is current; refetching it again
        // would only re-send the request the user already waited for.
        !(query.isActive() && under(first, query)) &&
        !under(skip, query) &&
        (rest.predicate?.(query) ?? true),
    },
    { cancelRefetch: false },
  );
}

/**
 * How a write wants the cache refreshed after it, returned from its
 * `onMutate` as `{ refresh: RefreshPlan }`.
 *
 * Without one, a write refreshes everything at once — the safe default. A
 * write that knows its reach names the reads its screen waits on (`first`,
 * fetched the moment it succeeds), the reads it cannot have changed
 * (`skip`, left alone) or, when shorter, the only reads it can change
 * (`only`). A failed write ignores its plan and refreshes everything: it may
 * have half-landed.
 */
export interface RefreshPlan {
  first?: readonly QueryKey[];
  skip?: readonly QueryKey[];
  /**
   * Everything the write can reach, when that is a short list: only these
   * (and `first`) are refreshed. `[]` refreshes nothing beyond `first` — for
   * a write that changes no other read, or a call that writes nothing at all
   * (better kept out of `useMutation` altogether). Omitted means anything
   * not in `skip`.
   */
  only?: readonly QueryKey[];
}

const planOf = (onMutateResult: unknown): RefreshPlan => {
  if (typeof onMutateResult !== "object" || onMutateResult === null) return {};
  return (onMutateResult as { refresh?: RefreshPlan }).refresh ?? {};
};

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
  let sweep: ((plan?: RefreshPlan) => void) | null = null;
  return new MutationCache({
    onMutate: () => dropReadsOlderThanTheWrite(getClient()),
    // Again on success, before the mutation's own `onSuccess` runs: a read
    // that started while the write was in flight may have been answered
    // before the commit. Dropping it here is what lets every later refetch
    // trust that whatever is in flight already reflects the write.
    //
    // The reads the write's screen waits on (its plan's `first`) start here
    // too, ahead of the mutation's own `onSuccess` and the sweep, so they
    // take a connection before anything else can. Not returned: the cache
    // awaits this callback, and the write's own `onSuccess` must not wait.
    onSuccess: (_data, _variables, onMutateResult) => {
      const client = getClient();
      dropReadsOlderThanTheWrite(client);
      for (const queryKey of planOf(onMutateResult).first ?? []) {
        void client.refetchQueries({ queryKey, type: "active" }, { cancelRefetch: false });
      }
    },
    // On settled rather than on success: a write that failed still cancelled
    // the reads above, and they have to be re-issued or the screen keeps
    // data nothing will refresh. A failed write sweeping costs one debounced
    // refresh and re-confirms what the server actually holds. Read after the
    // write's own `onSuccess`, which may widen the plan once the reply shows
    // the write reached further than expected.
    onSettled: (_data, error, _variables, onMutateResult) => {
      sweep ??= createInvalidationSweep(getClient(), delayMs);
      sweep(error ? {} : planOf(onMutateResult));
    },
  });
}

/**
 * Cancel every read that was in flight when a write began or committed.
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
