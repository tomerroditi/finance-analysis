/**
 * Each route's lazy page chunk, by path.
 *
 * `App.tsx` builds its `lazy()` pages from these loaders and the route
 * prefetch calls the same ones, so warming a route also fetches its code —
 * one map, so the two can never point at different modules. A dynamic
 * `import()` is cached by the module graph: calling a loader again costs
 * nothing.
 */
export const ROUTE_CHUNKS = {
  "/": () => import("./pages/Dashboard"),
  "/transactions": () => import("./pages/Transactions"),
  "/budget": () => import("./pages/Budget"),
  "/categories": () => import("./pages/Categories"),
  "/investments": () => import("./pages/Investments"),
  "/liabilities": () => import("./pages/Liabilities"),
  "/insurances": () => import("./pages/Insurances"),
  "/data-sources": () => import("./pages/DataSources"),
  "/early-retirement": () => import("./pages/EarlyRetirement"),
  "/data-flow": () => import("./pages/DataFlow"),
  "/onboarding": () => import("./pages/Onboarding"),
} as const;

/**
 * Start loading a route's page chunk, if it has one. Failures are left to the
 * navigation itself, which retries and reports them.
 *
 * @param path - The route's path.
 */
export function loadRouteChunk(path: string): void {
  const load = (ROUTE_CHUNKS as Record<string, (() => Promise<unknown>) | undefined>)[path];
  load?.().catch(() => undefined);
}
