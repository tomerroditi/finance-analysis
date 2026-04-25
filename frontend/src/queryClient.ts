import { MutationCache, QueryClient, type Query } from "@tanstack/react-query";
import { createAsyncStoragePersister } from "@tanstack/query-async-storage-persister";
import { createStore, get, set, del } from "idb-keyval";

/**
 * Query keys whose data must never be persisted to disk.
 *
 * Match by the first segment of the key array. We intentionally exclude
 * anything tied to active scraping or one-off previews — restoring a stale
 * scrape "in-progress" value across reloads would mislead the UI.
 */
const NON_PERSISTABLE_KEY_PREFIXES = new Set<string>([
  "scrapingStatus",
  "scraping-status",
  "rule-preview",
  "rule-conflicts",
  "retirement-preview",
  "suggestion-preview",
]);

/**
 * Anything credential-related is force-excluded regardless of the exact
 * key shape — even though only metadata like "you have a Bank Hapoalim
 * account" hits the cache (real secrets live in the OS keyring), that
 * metadata is still PII we don't want sitting in IndexedDB on a shared
 * or stolen device.
 */
function isCredentialQuery(key: readonly unknown[]): boolean {
  return key.some(
    (segment) =>
      typeof segment === "string" && segment.toLowerCase().includes("credential"),
  );
}

const DB_NAME = "finance-analysis";
const STORE_NAME = "react-query";
const CACHE_KEY = "tq-cache-v1";

const idbStore = createStore(DB_NAME, STORE_NAME);

/**
 * Any successful mutation alters server state, so every cached query
 * could now be stale. We invalidate the entire cache rather than relying
 * on per-mutation `onSuccess` invalidation: a mutation in one feature
 * frequently has knock-on effects (a new transaction shifts budgets,
 * KPIs, sankey, net-worth, etc.) and listing every dependent key on
 * every mutation site is fragile. Mounted queries refetch immediately;
 * unmounted ones refetch on next mount and the persister updates the
 * IndexedDB snapshot through its throttle.
 *
 * Trailing-edge debounce: when several mutations land in a burst (bulk
 * tagging, split-then-edit, etc.) we coalesce them into a single sweep
 * 200 ms after the last one settles instead of refetching every query
 * once per mutation.
 */
const INVALIDATE_DEBOUNCE_MS = 200;
let invalidateTimer: ReturnType<typeof setTimeout> | undefined;

const scheduleInvalidateAll = () => {
  if (invalidateTimer !== undefined) clearTimeout(invalidateTimer);
  invalidateTimer = setTimeout(() => {
    invalidateTimer = undefined;
    queryClient.invalidateQueries();
  }, INVALIDATE_DEBOUNCE_MS);
};

const mutationCache = new MutationCache({
  onSuccess: () => {
    scheduleInvalidateAll();
  },
});

export const queryClient = new QueryClient({
  mutationCache,
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5,
      // Keep cached data around long enough for a "load instantly from
      // disk while we refetch" experience after a cold start.
      gcTime: 1000 * 60 * 60 * 24 * 7, // 7 days
      retry: 1,
    },
  },
});

export const queryPersister = createAsyncStoragePersister({
  storage: {
    getItem: (key) => get<string>(key, idbStore).then((v) => v ?? null),
    setItem: (key, value) => set(key, value, idbStore),
    removeItem: (key) => del(key, idbStore),
  },
  key: CACHE_KEY,
  throttleTime: 1000,
});

export function shouldDehydrateQuery(query: Query): boolean {
  if (query.state.status !== "success") return false;
  const head = query.queryKey[0];
  if (typeof head !== "string") return false;
  if (NON_PERSISTABLE_KEY_PREFIXES.has(head)) return false;
  if (isCredentialQuery(query.queryKey)) return false;
  return true;
}

/**
 * Bumped whenever the on-disk cache shape changes (e.g. an API response
 * type was renamed). A mismatch causes the persister to discard the saved
 * cache instead of hydrating stale data into incompatible components.
 */
export const PERSIST_BUSTER = "v1";
