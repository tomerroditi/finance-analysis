/// <reference lib="webworker" />
/// <reference types="vite/client" />

import { precacheAndRoute, cleanupOutdatedCaches, createHandlerBoundToURL } from "workbox-precaching";
import { NavigationRoute, registerRoute } from "workbox-routing";
import { NetworkFirst } from "workbox-strategies";
import { ExpirationPlugin } from "workbox-expiration";
import { CacheableResponsePlugin } from "workbox-cacheable-response";
import type { WorkboxPlugin } from "workbox-core/types";

declare const self: ServiceWorkerGlobalScope;

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});

precacheAndRoute(self.__WB_MANIFEST);
cleanupOutdatedCaches();

const navigationRoute = new NavigationRoute(
  createHandlerBoundToURL("/index.html"),
  { denylist: [/^\/api\//, /^\/docs/, /^\/openapi/] },
);
registerRoute(navigationRoute);

/**
 * Tell every open client that an API GET we tried to serve from the
 * network failed. The page-side hook decides whether to show a toast,
 * debouncing across parallel failures.
 */
const broadcastNetworkFailure: WorkboxPlugin = {
  fetchDidFail: async ({ originalRequest }) => {
    const clients = await self.clients.matchAll({ type: "window" });
    for (const client of clients) {
      client.postMessage({
        type: "API_NETWORK_FAILED",
        url: originalRequest.url,
      });
    }
  },
};

/**
 * Cacheable API GETs.
 *
 * Excluded from the cache:
 *  - `/api/scraping/*`     — real-time scraper state and triggers, must
 *                            never be served stale.
 *  - `/api/credentials/*`  — never persist any response that touches
 *                            financial-institution credentials, even
 *                            metadata that lists which accounts exist.
 *  - `/api/backups`        — backup management: must reflect server truth.
 */
registerRoute(
  ({ url, request }) =>
    request.method === "GET" &&
    url.pathname.startsWith("/api/") &&
    !url.pathname.startsWith("/api/scraping/") &&
    !url.pathname.startsWith("/api/credentials") &&
    !url.pathname.startsWith("/api/backups"),
  new NetworkFirst({
    cacheName: "finance-api-get",
    networkTimeoutSeconds: 4,
    plugins: [
      broadcastNetworkFailure,
      new ExpirationPlugin({
        maxEntries: 200,
        maxAgeSeconds: 60 * 60 * 24 * 7, // 7 days
      }),
      new CacheableResponsePlugin({ statuses: [0, 200] }),
    ],
  }),
  "GET",
);
