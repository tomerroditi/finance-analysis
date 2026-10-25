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
import { UpdateAvailableToast } from "./components/UpdateAvailableToast";
import {
  PERSIST_BUSTER,
  queryClient,
  queryPersister,
  shouldDehydrateQuery,
} from "./queryClient";

const Dashboard = lazy(() =>
  import("./pages/Dashboard").then((m) => ({ default: m.Dashboard })),
);
const Transactions = lazy(() =>
  import("./pages/Transactions").then((m) => ({ default: m.Transactions })),
);
const Budget = lazy(() =>
  import("./pages/Budget").then((m) => ({ default: m.Budget })),
);
const Categories = lazy(() =>
  import("./pages/Categories").then((m) => ({ default: m.Categories })),
);
const Investments = lazy(() =>
  import("./pages/Investments").then((m) => ({ default: m.Investments })),
);
const Liabilities = lazy(() =>
  import("./pages/Liabilities").then((m) => ({ default: m.Liabilities })),
);
const Insurances = lazy(() =>
  import("./pages/Insurances").then((m) => ({ default: m.Insurances })),
);
const DataSources = lazy(() =>
  import("./pages/DataSources").then((m) => ({ default: m.DataSources })),
);
const EarlyRetirement = lazy(() =>
  import("./pages/EarlyRetirement").then((m) => ({
    default: m.EarlyRetirement,
  })),
);
const DataFlow = lazy(() =>
  import("./pages/DataFlow").then((m) => ({ default: m.DataFlow })),
);
const Onboarding = lazy(() =>
  import("./pages/Onboarding").then((m) => ({ default: m.Onboarding })),
);

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
  // the queries stale; each one refetches as its component mounts.
  void queryClient.invalidateQueries();
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
              <UpdateAvailableToast />
            </BrowserRouter>
          </DialogProvider>
        </DemoModeProvider>
      </ErrorBoundary>
    </PersistQueryClientProvider>
  );
}

export default App;
