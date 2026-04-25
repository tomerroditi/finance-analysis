import { QueryClient, type Query } from "@tanstack/react-query";
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

const DB_NAME = "finance-analysis";
const STORE_NAME = "react-query";
const CACHE_KEY = "tq-cache-v1";

const idbStore = createStore(DB_NAME, STORE_NAME);

export const queryClient = new QueryClient({
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
  return !NON_PERSISTABLE_KEY_PREFIXES.has(head);
}

/**
 * Bumped whenever the on-disk cache shape changes (e.g. an API response
 * type was renamed). A mismatch causes the persister to discard the saved
 * cache instead of hydrating stale data into incompatible components.
 */
export const PERSIST_BUSTER = "v1";
