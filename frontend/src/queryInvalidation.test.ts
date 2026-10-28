import { describe, it, expect, vi } from "vitest";
import { QueryClient, QueryObserver } from "@tanstack/react-query";
import { WRITE_FAILED_EVENT, createMutationCache } from "./queryInvalidation";

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

  it("drops a read that started while the write was in flight", async () => {
    // The budget's tag write: the row list refetched mid-write, the server
    // answered from before the commit, and that answer outlived the write.
    const client = makeClient();
    let served = "old";
    const key = ["thing"];
    const queryFn = async () => {
      const asOf = served;
      await flush(SWEEP_MS * 4);
      return asOf;
    };
    await client.fetchQuery({ queryKey: key, queryFn });

    let midWrite: Promise<unknown> | undefined;
    await client
      .getMutationCache()
      .build(client, {
        mutationFn: async () => {
          midWrite = client
            .fetchQuery({ queryKey: key, queryFn, staleTime: 0 })
            .catch(() => undefined);
          await flush(SWEEP_MS);
          served = "new";
          return null;
        },
      })
      .execute(undefined);

    const observer = new QueryObserver(client, { queryKey: key, queryFn });
    const unsubscribe = observer.subscribe(() => {});
    await midWrite;
    await vi.waitFor(() => expect(client.getQueryData(key)).toBe("new"), {
      timeout: 2000,
    });
    unsubscribe();
  });

  it("joins the write's own refetch instead of restarting it", async () => {
    // Restarting every refetch the write's `onSuccess` had just started sent
    // each read three times, and the screen waited behind all of them.
    const client = makeClient();
    const key = ["thing"];
    const queryFn = vi.fn(async () => {
      await flush(SWEEP_MS * 4);
      return "fresh";
    });
    await client.fetchQuery({ queryKey: key, queryFn });
    const observer = new QueryObserver(client, { queryKey: key, queryFn });
    const unsubscribe = observer.subscribe(() => {});
    queryFn.mockClear();

    await client
      .getMutationCache()
      .build(client, {
        mutationFn: async () => null,
        onSuccess: () => {
          void client.invalidateQueries({ queryKey: key });
        },
      })
      .execute(undefined);

    await flush(SWEEP_MS * 8);
    expect(queryFn).toHaveBeenCalledTimes(1);
    unsubscribe();
  });

  it("follows a write's plan: what it names first, and nothing it skips", async () => {
    const client = makeClient();
    const order: string[] = [];
    const watch = (key: readonly unknown[], name: string) => {
      const queryFn = async () => {
        order.push(name);
        await flush(SWEEP_MS);
        return name;
      };
      const observer = new QueryObserver(client, { queryKey: key, queryFn });
      return observer.subscribe(() => {});
    };
    const stops = [
      watch(["trend"], "trend"),
      watch(["month", 10], "month"),
      watch(["icons"], "icons"),
    ];
    await vi.waitFor(() => expect(order).toHaveLength(3));
    order.length = 0;

    await client
      .getMutationCache()
      .build(client, {
        mutationFn: async () => null,
        onMutate: () => ({ refresh: { first: [["month"]], skip: [["icons"]] } }),
      })
      .execute(undefined);

    await vi.waitFor(() => expect(order).toEqual(["month", "trend"]), { timeout: 2000 });
    await flush(SWEEP_MS * 4);
    expect(order).toEqual(["month", "trend"]);
    expect(client.getQueryState(["icons"])?.isInvalidated).toBe(false);
    stops.forEach((stop) => stop());
  });

  it("refreshes only what a write says it can reach", async () => {
    const client = makeClient();
    const fetched: string[] = [];
    const watch = (name: string) => {
      const observer = new QueryObserver(client, {
        queryKey: [name],
        queryFn: async () => {
          fetched.push(name);
          return name;
        },
      });
      return observer.subscribe(() => {});
    };
    const stops = [watch("insights"), watch("trend"), watch("budget")];
    await vi.waitFor(() => expect(fetched).toHaveLength(3));
    fetched.length = 0;

    await client
      .getMutationCache()
      .build(client, {
        mutationFn: async () => null,
        onMutate: () => ({ refresh: { only: [["insights"]] } }),
      })
      .execute(undefined);

    await vi.waitFor(() => expect(fetched).toEqual(["insights"]), { timeout: 2000 });
    await flush(SWEEP_MS * 4);
    expect(fetched).toEqual(["insights"]);
    expect(client.getQueryState(["trend"])?.isInvalidated).toBe(false);

    // A write with no limit in the same burst widens it back to everything.
    fetched.length = 0;
    const mutations = client.getMutationCache();
    await Promise.all([
      mutations
        .build(client, { mutationFn: async () => null, onMutate: () => ({ refresh: { only: [] } }) })
        .execute(undefined),
      mutations.build(client, { mutationFn: async () => null }).execute(undefined),
    ]);
    await vi.waitFor(() => expect(new Set(fetched)).toEqual(new Set(["insights", "trend", "budget"])), {
      timeout: 2000,
    });
    stops.forEach((stop) => stop());
  });

  it("re-asks a read it cancelled even when its plan does not reach it", async () => {
    const client = makeClient();
    let served = "old";
    const queryFn = async () => {
      const asOf = served;
      await flush(SWEEP_MS * 2);
      return asOf;
    };
    const observer = new QueryObserver(client, { queryKey: ["trend"], queryFn });
    const unsubscribe = observer.subscribe(() => {});
    await vi.waitFor(() => expect(client.getQueryData(["trend"])).toBe("old"));

    // A refetch is under way when a write that names only another read lands.
    void observer.refetch();
    served = "new";
    await client
      .getMutationCache()
      .build(client, {
        mutationFn: async () => null,
        onMutate: () => ({ refresh: { only: [["insights"]] } }),
      })
      .execute(undefined);

    // The cancelled refetch is issued again rather than left on the old data.
    await vi.waitFor(() => expect(client.getQueryData(["trend"])).toBe("new"), { timeout: 2000 });
    unsubscribe();
  });

  it("refreshes nothing after a write whose plan reaches nothing", async () => {
    const client = makeClient();
    let fetches = 0;
    const observer = new QueryObserver(client, { queryKey: ["any"], queryFn: async () => ++fetches });
    const unsubscribe = observer.subscribe(() => {});
    await vi.waitFor(() => expect(fetches).toBe(1));

    await client
      .getMutationCache()
      .build(client, { mutationFn: async () => null, onMutate: () => ({ refresh: { only: [] } }) })
      .execute(undefined);

    await flush(SWEEP_MS * 6);
    expect(fetches).toBe(1);
    expect(client.getQueryState(["any"])?.isInvalidated).toBe(false);
    unsubscribe();
  });

  it("refreshes everything after a failed write, whatever it planned", async () => {
    const client = makeClient();
    let fetches = 0;
    const observer = new QueryObserver(client, {
      queryKey: ["icons"],
      queryFn: async () => ++fetches,
    });
    const unsubscribe = observer.subscribe(() => {});
    await vi.waitFor(() => expect(fetches).toBe(1));

    await client
      .getMutationCache()
      .build(client, {
        mutationFn: async () => {
          throw new Error("half-landed");
        },
        onMutate: () => ({ refresh: { skip: [["icons"]] } }),
      })
      .execute(undefined)
      .catch(() => undefined);

    await vi.waitFor(() => expect(fetches).toBe(2), { timeout: 2000 });
    unsubscribe();
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

describe("a failed write", () => {
  /**
   * Run one failing write through the app's cache; return what each
   * `write-failed` notice said about it.
   */
  async function failWith(options: {
    onMutateResult?: unknown;
    meta?: Record<string, unknown>;
    onError?: () => void;
  }) {
    const client = makeClient();
    const heard: boolean[] = [];
    const listener = (event: Event) =>
      heard.push((event as CustomEvent<{ reverted: boolean }>).detail.reverted);
    window.addEventListener(WRITE_FAILED_EVENT, listener);
    try {
      await client
        .getMutationCache()
        .build(client, {
          mutationFn: async () => {
            throw new Error("refused");
          },
          onMutate: () => options.onMutateResult,
          onError: options.onError,
          meta: options.meta,
        })
        .execute(undefined)
        .catch(() => undefined);
    } finally {
      window.removeEventListener(WRITE_FAILED_EVENT, listener);
    }
    return heard;
  }

  it("says the change was undone when it had changed the screen", async () => {
    expect(await failWith({ onMutateResult: { restore: () => {} }, onError: () => {} })).toEqual([
      true,
    ]);
  });

  it("says it could not save when it waited and has no error handling of its own", async () => {
    expect(await failWith({ onMutateResult: { refresh: {} } })).toEqual([false]);
    expect(await failWith({})).toEqual([false]);
  });

  it("leaves a waiting write that handles its own error alone", async () => {
    expect(await failWith({ onError: () => {} })).toEqual([]);
  });

  it("is not announced twice for a write that reports its own failure", async () => {
    expect(
      await failWith({ onMutateResult: { restore: () => {} }, meta: { reportsOwnError: true } }),
    ).toEqual([]);
    expect(await failWith({ meta: { reportsOwnError: true } })).toEqual([]);
  });
});
