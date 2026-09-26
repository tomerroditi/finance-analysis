import { describe, it, expect, vi } from "vitest";
import { QueryClient, QueryObserver } from "@tanstack/react-query";
import { createMutationCache } from "./queryInvalidation";

/**
 * A write must not be undone by a read that predates it.
 *
 * Several features answer a click from the cache instead of waiting for the
 * round trip — the recurring card's verdicts, the dashboard's inline tag
 * editor, an investment snapshot row, the retirement plan. They all do the
 * same thing: `setQueryData` the new state, then let the app-wide sweep
 * refresh everything.
 *
 * The hazard is a fetch that was already in flight when the write happened.
 * React Query supersedes an older fetch with a newer *fetch* on the same key,
 * but a manual patch is not a fetch, so nothing stops the older response from
 * landing on top of it and restoring the value the user just changed. The
 * user sees the change stick, then silently revert.
 *
 * These drive the real mutation cache from `queryInvalidation.ts` — the same
 * wiring `queryClient.ts` installs — because the guard belongs there, not in
 * each of the call sites that would otherwise have to remember it.
 */

const SWEEP_MS = 10;
const flush = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** A client wired exactly as the app wires it. */
function makeClient() {
  // Same shape as `queryClient.ts`: the cache reads the client back through a
  // getter, because the client is constructed with the cache.
  const mutationCache = createMutationCache(() => client, SWEEP_MS);
  const client: QueryClient = new QueryClient({
    mutationCache,
    defaultOptions: {
      queries: { retry: false, staleTime: 5 * 60_000 },
      mutations: { retry: false },
    },
  });
  return client;
}

describe("the app-wide mutation cache", () => {
  it("does not let a read that started before a write land on top of it", async () => {
    const client = makeClient();
    // The server still answers "old" — this read was computed before the write.
    let served = "old";
    const key = ["thing"];
    const queryFn = vi.fn(async () => {
      const asOf = served;
      await flush(SWEEP_MS * 4);
      return asOf;
    });

    // Seed, then start a refetch and leave it in flight.
    await client.fetchQuery({ queryKey: key, queryFn });
    expect(client.getQueryData(key)).toBe("old");
    const inFlight = client.fetchQuery({
      queryKey: key,
      queryFn,
      staleTime: 0,
    });

    // The write lands while that read is still out, and patches the cache the
    // way every optimistic call site in the app does.
    await client
      .getMutationCache()
      .build(client, {
        mutationFn: async () => {
          served = "new";
          return "new";
        },
        onSuccess: () => client.setQueryData(key, "new"),
      })
      .execute(undefined);

    expect(client.getQueryData(key)).toBe("new");

    // The stale read resolves. It must not restore "old".
    await inFlight.catch(() => undefined);
    await flush(SWEEP_MS);
    expect(client.getQueryData(key)).toBe("new");
  });

  it("still refreshes what it cancelled, so nothing is left stale", async () => {
    const client = makeClient();
    let served = "old";
    const key = ["thing"];
    const queryFn = async () => {
      const asOf = served;
      await flush(SWEEP_MS * 2);
      return asOf;
    };

    await client.fetchQuery({ queryKey: key, queryFn });
    // An observer, so the sweep's invalidation actually refetches: a query
    // nothing is watching is only marked stale.
    const observer = new QueryObserver(client, { queryKey: key, queryFn });
    const unsubscribe = observer.subscribe(() => {});

    await client
      .getMutationCache()
      .build(client, {
        mutationFn: async () => {
          served = "fresh-from-server";
          return null;
        },
      })
      .execute(undefined);

    // The sweep runs, refetches, and picks up what the write changed.
    await vi.waitFor(
      () => expect(client.getQueryData(key)).toBe("fresh-from-server"),
      { timeout: 2000 },
    );
    unsubscribe();
  });

  it("cancels before the write patches, never after", async () => {
    // Ordering that matters: the cancel reverts a query to the state it held
    // when its fetch began. If it ran after a write's own `onMutate`, that
    // revert would wipe the optimistic patch the user is looking at — the
    // guard would cause the exact bug it exists to prevent. React Query
    // awaits the cache's `onMutate` before the mutation's; this pins it.
    const client = makeClient();
    const key = ["thing"];
    const queryFn = async () => {
      await flush(SWEEP_MS * 4);
      return "from-server";
    };

    await client.fetchQuery({ queryKey: key, queryFn });
    const inFlight = client.fetchQuery({ queryKey: key, queryFn, staleTime: 0 });

    await client
      .getMutationCache()
      .build(client, {
        mutationFn: async () => null,
        // Patches up front, the way the recurring card and the insights
        // strip do, rather than on success.
        onMutate: () => {
          client.setQueryData(key, "optimistic");
        },
      })
      .execute(undefined);

    expect(client.getQueryData(key)).toBe("optimistic");
    await inFlight.catch(() => undefined);
    await flush(SWEEP_MS);
    expect(client.getQueryData(key)).toBe("optimistic");
  });

  it("leaves a first load alone — it has nothing to overwrite", async () => {
    const client = makeClient();
    const key = ["first-load"];
    let resolved = false;
    const pending = client.fetchQuery({
      queryKey: key,
      queryFn: async () => {
        await flush(SWEEP_MS * 3);
        resolved = true;
        return "loaded";
      },
    });

    await client
      .getMutationCache()
      .build(client, { mutationFn: async () => null })
      .execute(undefined);

    // Cancelling a load that has no data yet would just restart the page's
    // boot for no reason, so it must be allowed to finish.
    await pending;
    expect(resolved).toBe(true);
    expect(client.getQueryData(key)).toBe("loaded");
  });
});
