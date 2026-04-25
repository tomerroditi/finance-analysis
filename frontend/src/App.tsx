import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Layout } from "./components/layout";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { DemoModeProvider } from "./context/DemoModeContext";
import { DialogProvider } from "./context/DialogContext";
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

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      retry: 1,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
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
          </BrowserRouter>
          </DialogProvider>
        </DemoModeProvider>
      </ErrorBoundary>
    </QueryClientProvider>
  );
}

export default App;
