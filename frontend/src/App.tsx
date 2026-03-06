import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Layout } from "./components/layout";
import { DemoModeProvider } from "./context/DemoModeContext";
import {
  Dashboard,
  Transactions,
  Budget,
  Categories,
  Investments,
  Insurances,
  DataSources,
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
      <DemoModeProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Layout />}>
              <Route index element={<Dashboard />} />
              <Route path="transactions" element={<Transactions />} />
              <Route path="budget" element={<Budget />} />
              <Route path="categories" element={<Categories />} />
              <Route path="investments" element={<Investments />} />
              <Route path="insurances" element={<Insurances />} />
              <Route path="data-sources" element={<DataSources />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </DemoModeProvider>
    </QueryClientProvider>
  );
}

export default App;
