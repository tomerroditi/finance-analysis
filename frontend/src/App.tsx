import { BrowserRouter, Routes, Route } from "react-router-dom";
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";
import { Layout } from "./components/layout";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { DemoModeProvider } from "./context/DemoModeContext";
import { DialogProvider } from "./context/DialogContext";
import { ServiceWorkerUpdatePrompt } from "./components/ServiceWorkerUpdatePrompt";
import {
  PERSIST_BUSTER,
  queryClient,
  queryPersister,
  shouldDehydrateQuery,
} from "./queryClient";
import {
  Dashboard,
  Transactions,
  Budget,
  Categories,
  Investments,
  Liabilities,
  Insurances,
  DataSources,
  EarlyRetirement,
  DataFlow,
} from "./pages";

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
    >
      <ErrorBoundary>
        <DemoModeProvider>
          <DialogProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/" element={<Layout />}>
                <Route index element={<Dashboard />} />
                <Route path="transactions" element={<Transactions />} />
                <Route path="budget" element={<Budget />} />
                <Route path="categories" element={<Categories />} />
                <Route path="investments" element={<Investments />} />
                <Route path="liabilities" element={<Liabilities />} />
                <Route path="insurances" element={<Insurances />} />
                <Route path="early-retirement" element={<EarlyRetirement />} />
                <Route path="data-sources" element={<DataSources />} />
                <Route path="data-flow" element={<DataFlow />} />
              </Route>
            </Routes>
            <ServiceWorkerUpdatePrompt />
          </BrowserRouter>
          </DialogProvider>
        </DemoModeProvider>
      </ErrorBoundary>
    </PersistQueryClientProvider>
  );
}

export default App;
