import { type ReactNode } from "react";
import { render, type RenderOptions } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { DemoModeProvider } from "./context/DemoModeContext";
import { DialogProvider } from "./context/DialogContext";

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

interface WrapperProps {
  children: ReactNode;
}

export function renderWithProviders(
  ui: React.ReactElement,
  options?: Omit<RenderOptions, "wrapper"> & { route?: string },
) {
  const queryClient = createTestQueryClient();
  const { route = "/", ...renderOptions } = options ?? {};

  function Wrapper({ children }: WrapperProps) {
    return (
      <QueryClientProvider client={queryClient}>
        <DemoModeProvider>
          <DialogProvider>
            <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
          </DialogProvider>
        </DemoModeProvider>
      </QueryClientProvider>
    );
  }

  return {
    ...render(ui, { wrapper: Wrapper, ...renderOptions }),
    queryClient,
  };
}

export { createTestQueryClient };
