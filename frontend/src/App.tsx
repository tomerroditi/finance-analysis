import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Routes, Route } from "react-router";
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";
import { Layout } from "./components/layout";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { OnboardingGate } from "./components/OnboardingGate";
import { DemoModeProvider } from "./context/DemoModeContext";
import { DialogProvider } from "./context/DialogContext";
import { ServiceWorkerUpdatePrompt } from "./components/ServiceWorkerUpdatePrompt";
import { NetworkStatusToast } from "./components/NetworkStatusToast";
import { RefundsRetaggedToast } from "./components/RefundsRetaggedToast";
import { WriteFailedToast } from "./components/WriteFailedToast";
import { UpdateAvailableToast } from "./components/UpdateAvailableToast";
import {
  PERSIST_BUSTER,
  queryClient,
  queryPersister,
  shouldDehydrateQuery,
} from "./queryClient";
import { ROUTE_CHUNKS } from "./routeChunks";
import { prefetchRoute } from "./services/routePrefetch";
import { readStoredDemoMode } from "./services/demoMode";

const Dashboard = lazy(() =>
  ROUTE_CHUNKS["/"]().then((m) => ({ default: m.Dashboard })),
);
const Transactions = lazy(() =>
  ROUTE_CHUNKS["/transactions"]().then((m) => ({ default: m.Transactions })),
);
const Budget = lazy(() =>
  ROUTE_CHUNKS["/budget"]().then((m) => ({ default: m.Budget })),
);
const Categories = lazy(() =>
  ROUTE_CHUNKS["/categories"]().then((m) => ({ default: m.Categories })),
);
const Investments = lazy(() =>
  ROUTE_CHUNKS["/investments"]().then((m) => ({ default: m.Investments })),
);
const Liabilities = lazy(() =>
  ROUTE_CHUNKS["/liabilities"]().then((m) => ({ default: m.Liabilities })),
);
const Insurances = lazy(() =>
  ROUTE_CHUNKS["/insurances"]().then((m) => ({ default: m.Insurances })),
);
const DataSources = lazy(() =>
  ROUTE_CHUNKS["/data-sources"]().then((m) => ({ default: m.DataSources })),
);
const EarlyRetirement = lazy(() =>
  ROUTE_CHUNKS["/early-retirement"]().then((m) => ({
    default: m.EarlyRetirement,
  })),
);
const DataFlow = lazy(() =>
  ROUTE_CHUNKS["/data-flow"]().then((m) => ({ default: m.DataFlow })),
);
const Onboarding = lazy(() =>
  ROUTE_CHUNKS["/onboarding"]().then((m) => ({ default: m.Onboarding })),
);

/**
 * When this tab started. Anything fetched since is not from the restored
 * snapshot and needs no revalidating.
 */
const BOOTED_AT = Date.now();

// Start the opening route's chunk and reads now, alongside the IndexedDB
// restore, rather than after the restore has settled and the lazy page has
// suspended and revealed — each of which used to sit in front of the first
// request.
prefetchRoute(queryClient, window.location.pathname, {
  isDemoMode: readStoredDemoMode(),
});

/**
 * Treat everything restored from IndexedDB as stale once it is on screen.
 *
 * The snapshot is written through a throttle, so it can predate the last
 * write — a reload moments after retagging a transaction restored the
 * pre-write budget. Restored queries keep their original `dataUpdatedAt`, so
 * anything younger than `staleTime` was trusted as fresh and never refetched,
 * and the old numbers stuck even across reloads. The snapshot still paints
 * instantly; this only makes the server confirm it.
 */
function revalidateRestoredCache() {
  // Runs before the restore releases the app's observers, so this only marks
  // the queries stale; each one refetches as its component mounts. What the
  // boot prefetch already fetched (or is fetching) is newer than the
  // snapshot and is left alone, or the page would ask for it twice.
  void queryClient.invalidateQueries({
    predicate: (query) =>
      query.state.fetchStatus !== "fetching" && query.state.dataUpdatedAt < BOOTED_AT,
  });
}

function App() {
  return (
    <PersistQueryClientProvider
      client={queryClient}
      persistOptions={{
        persister: queryPersister,
        buster: PERSIST_BUSTER,
        maxAge: 1000 * 60 * 60 * 24 * 7,
        dehydrateOptions: { shouldDehydrateQuery },
      }}
      onSuccess={revalidateRestoredCache}
    >
      <ErrorBoundary>
        <DemoModeProvider>
          <DialogProvider>
            <BrowserRouter>
              <Suspense fallback={null}>
                <Routes>
                  <Route path="/onboarding" element={<Onboarding />} />
                  <Route element={<OnboardingGate />}>
                    <Route path="/" element={<Layout />}>
                      <Route index element={<Dashboard />} />
                      <Route path="transactions" element={<Transactions />} />
                      <Route path="budget" element={<Budget />} />
                      <Route path="categories" element={<Categories />} />
                      <Route path="investments" element={<Investments />} />
                      <Route path="liabilities" element={<Liabilities />} />
                      <Route path="insurances" element={<Insurances />} />
                      <Route
                        path="early-retirement"
                        element={<EarlyRetirement />}
                      />
                      <Route
                        path="fire-calculator"
                        element={<Navigate to="/early-retirement" replace />}
                      />
                      <Route path="data-sources" element={<DataSources />} />
                      <Route path="data-flow" element={<DataFlow />} />
                    </Route>
                  </Route>
                </Routes>
              </Suspense>
              <ServiceWorkerUpdatePrompt />
              <NetworkStatusToast />
              <RefundsRetaggedToast />
              <WriteFailedToast />
              <UpdateAvailableToast />
            </BrowserRouter>
          </DialogProvider>
        </DemoModeProvider>
      </ErrorBoundary>
    </PersistQueryClientProvider>
  );
}

export default App;
