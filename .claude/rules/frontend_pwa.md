# Frontend PWA / Offline Cache

The dashboard ships as a Progressive Web App: a service worker precaches the
build, persists API GETs to disk, and surfaces lifecycle events through two
toasts. Read this whenever you touch service worker config, add an API
endpoint, change brand assets, or wire a new mutation.

## Layers at a glance

| Layer | File | Job |
|---|---|---|
| Service worker | `frontend/src/sw.ts` | Precaches the static shell, runtime-caches `/api` GETs (NetworkFirst, 4 s timeout), broadcasts `API_NETWORK_FAILED` on every failed fetch |
| QueryClient + persister | `frontend/src/queryClient.ts` | Owns `QueryClient`, persists the React Query cache to IndexedDB via `idb-keyval`, runs the `MutationCache.onSuccess` global invalidator |
| Update prompt | `frontend/src/components/ServiceWorkerUpdatePrompt.tsx` | Translated toast for "offline ready" + "new version available · reload" |
| Failure toast | `frontend/src/components/NetworkStatusToast.tsx` + `hooks/useNetworkFailureToast.ts` | Subscribes to the SW broadcast, debounces, shows a 3.5 s "couldn't reach the server" toast |
| Manifest + icons | `frontend/public/manifest.webmanifest` (generated), `frontend/public/icons/`, `frontend/public/favicon.svg`, `frontend/scripts/generate_pwa_icons.py` | Installable-app metadata + home-screen icons |

`vite-plugin-pwa` runs in `injectManifest` mode — the SW source lives in
`src/sw.ts`, not generated. Don't switch back to `generateSW`: we need
inline plugin functions (`fetchDidFail`) that JSON-config can't express.

## When you add a new GET endpoint

Walk through this checklist before assuming it Just Works:

1. **Is the response sensitive?** If it touches credentials, secrets, or
   anything you'd be uncomfortable sitting in IndexedDB on a stolen
   laptop, route it under `/api/credentials/*`. The SW filter and the
   persister both already exclude that prefix. If you can't put it under
   that prefix, add the new path to **both**:
   - `src/sw.ts` URL filter (the `urlPattern` that registers `NetworkFirst`).
   - `src/queryClient.ts` — either bump the `isCredentialQuery` heuristic
     or add the query-key prefix to `NON_PERSISTABLE_KEY_PREFIXES`.
2. **Is the response real-time / polling?** Anything where "5-minute-old
   data" is dangerous (scraping status, in-flight job progress) belongs in
   the same exclusion list. Polling endpoints should use bare `fetch` or
   add an exclusion in the SW filter.
3. **Is the GET actually a side-effect "preview"?** (e.g.
   `previewRule`, `previewSuggestions`.) These are read-only POSTs that
   the page treats as queries. They're already excluded from
   IndexedDB persistence; if you add another, extend
   `NON_PERSISTABLE_KEY_PREFIXES`.
4. **Default case (idempotent, non-sensitive GET):** do nothing. The SW
   will runtime-cache it under `finance-api-get` and the persister will
   write it to IndexedDB on next throttle tick.

Mirror exclusions in **both** the SW filter and the persister — one without
the other still leaks data.

## When you add a new mutation

`MutationCache.onSuccess` (in `queryClient.ts`) already triggers a
debounced `queryClient.invalidateQueries()` 200 ms after every successful
mutation. So:

- You **don't have to** wire `useMutation`'s `onSuccess` to invalidate
  every dependent query manually. The global hammer covers it.
- You **may still add** a per-mutation `onSuccess` for surgical UX —
  optimistic updates, a one-off `setQueryData`, immediate
  `invalidateQueries({ queryKey: [...] })` ahead of the 200 ms debounce
  window. The two coexist.
- Do **not** call `queryClient.clear()` after a mutation — that
  also wipes the IndexedDB persister and forces every query to refetch
  cold. Use invalidation, not clearing.

Mutations are not intercepted by the SW. POST/PUT/DELETE go straight to
the backend; failures surface through React Query's error state in the
calling page (use the page's own toast/modal pattern, not the global
`NetworkStatusToast`).

## When you change brand assets

The PWA manifest references `theme_color`, `background_color`, and three
icon sizes. They were generated to match `--background` / `--primary` in
`src/index.css`. If you change those CSS variables:

1. Edit `frontend/scripts/generate_pwa_icons.py` (the `BG`, `PRIMARY`,
   `SECONDARY`, `TEXT` tuples).
2. Run `python frontend/scripts/generate_pwa_icons.py` from the
   `frontend/` directory. It rewrites `public/favicon.svg` and the four
   PNGs in `public/icons/`.
3. Update `theme_color` / `background_color` in `vite.config.ts` (under
   `VitePWA({ manifest: ... })`) to match.
4. Update `<meta name="theme-color">` in `frontend/index.html`.

## When you change the cache shape

`PERSIST_BUSTER` (in `queryClient.ts`) is a string suffix on every
serialized cache. Bump it whenever:

- An API response shape changes in a backwards-incompatible way (a
  field renamed, a number became an object, a list became an array of
  objects).
- A new `shouldDehydrateQuery` rule retroactively excludes data that
  used to be persisted.

Bumping the buster causes every user's IndexedDB cache to be discarded
on next load — they refetch cold once, then resume. This is preferable
to silently hydrating stale shapes into typed components and crashing.

## When you add new SW lifecycle copy

Translation keys for SW-driven UI live under `pwa.*` in both
`frontend/src/locales/en.json` and `frontend/src/locales/he.json`:

```
pwa.offlineReady            – first install confirmation
pwa.updateAvailableTitle    – new build detected
pwa.updateAvailableMessage  – body copy
pwa.reload                  – button label
pwa.dismiss                 – close button + aria-label
pwa.networkFailedTitle      – fetch failed toast title
pwa.networkFailedMessage    – fetch failed toast body
```

Add new keys to **both** locale files. The Hebrew text is hand-translated;
don't auto-generate.

## Local development

The SW is intentionally **disabled in `npm run dev`**
(`devOptions.enabled: false` in `vite.config.ts`). The dashboard fetches
from the Vite proxy normally; you don't have to fight a stale cache while
iterating.

To exercise PWA features locally:

```bash
cd frontend
npm run build
npm run preview        # serves /sw.js, /manifest.webmanifest, etc.
```

Open Chrome DevTools → Application → Service Workers to inspect, or
DevTools → Application → IndexedDB → `finance-analysis` to see the
persisted React Query cache.

## Build size & precache budget

Workbox refuses to precache assets larger than 2 MiB by default. Plotly
inflates the main bundle past that, so we set
`maximumFileSizeToCacheInBytes: 10 MiB` in `injectManifest`. **Do not
keep raising that limit** — it's there to stop us shipping a 50 MB SW
cache. The right fix is route-level code splitting (lazy-load Plotly off
the dashboard route). The bundle is already on the engineering-debt
list in `docs/next-features.md`.

If you add a heavy dependency that pushes a single chunk past 10 MiB,
the build will fail with a Workbox error. Fix it by code-splitting, not
by bumping the limit.

## CSP and worker-src

`frontend/index.html` ships a strict CSP. The SW currently works because
of:

```
worker-src 'self' blob:
script-src 'self'
```

If you ever need the SW to import a script from a CDN (e.g.
`importScripts('https://...')`), you must extend `script-src` and
`worker-src`. We don't do that today and shouldn't start without a
strong reason — every external import becomes a supply-chain attack
surface inside the SW.

## Anti-patterns (do NOT)

- Do **not** cache mutations. The SW filter is GET-only by design;
  don't extend it to other methods.
- Do **not** add a new endpoint to the SW exclusion list **only**, or
  to the persister exclusion list **only**. Both layers cache; both
  must agree.
- Do **not** call `queryClient.clear()` from a mutation handler. Use
  `invalidateQueries` (or rely on the global invalidator).
- Do **not** put credentials, OTP secrets, or scrape-result raw payloads
  into a query whose key doesn't include the word "credential" or
  "scraping" — the heuristics in `shouldDehydrateQuery` won't catch it.
- Do **not** switch `vite-plugin-pwa` back to `generateSW`. The custom
  `fetchDidFail` plugin in `src/sw.ts` requires `injectManifest`.
- Do **not** ship a new build that changes the API response shape of a
  cached endpoint without bumping `PERSIST_BUSTER`. Old clients will
  hydrate the new code with the old shape.
- Do **not** show `NetworkStatusToast` for mutation failures. Mutations
  go around the SW; surface their errors locally in the page that
  triggered them.

## File map (quick reference)

```
frontend/
├── index.html                                     # CSP, theme-color, icon links
├── public/
│   ├── favicon.svg                                # Generated (regen: scripts/generate_pwa_icons.py)
│   └── icons/                                     # 192, 512, 512-maskable, apple-touch-icon
├── scripts/
│   └── generate_pwa_icons.py                      # Regenerates favicon + icons
├── src/
│   ├── sw.ts                                      # Custom service worker (injectManifest)
│   ├── queryClient.ts                             # QueryClient, persister, mutation invalidator
│   ├── App.tsx                                    # PersistQueryClientProvider mounts here
│   ├── components/
│   │   ├── ServiceWorkerUpdatePrompt.tsx          # Update / offline-ready toast
│   │   └── NetworkStatusToast.tsx                 # Network failure toast
│   ├── hooks/
│   │   └── useNetworkFailureToast.ts              # SW message listener + debounce
│   └── locales/{en,he}.json                       # `pwa.*` keys
├── vite.config.ts                                 # VitePWA({ strategies: "injectManifest", ... })
└── tsconfig.app.json                              # types: ["vite-plugin-pwa/react", ...]
```
