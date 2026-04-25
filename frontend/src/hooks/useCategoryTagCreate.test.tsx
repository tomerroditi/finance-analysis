import { describe, it, expect } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useCategoryTagCreate } from "./useCategoryTagCreate";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe("useCategoryTagCreate", () => {
  it("createCategory title-cases the name and returns it", async () => {
    const { result } = renderHook(() => useCategoryTagCreate(), {
      wrapper: createWrapper(),
    });

    const formatted = await result.current.createCategory("entertainment");
    expect(formatted).toBe("Entertainment");
  });

  it("createTag title-cases the tag name and returns it", async () => {
    const { result } = renderHook(() => useCategoryTagCreate(), {
      wrapper: createWrapper(),
    });

    const formatted = await result.current.createTag("Food", "fast food");
    expect(formatted).toBe("Fast Food");
  });

  it("createCategory invalidates the categories query", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    // Pre-populate cache
    queryClient.setQueryData(["categories"], { old: "data" });

    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useCategoryTagCreate(), { wrapper });

    await result.current.createCategory("new category");

    // After invalidation, the cached data should be refetched (stale)
    await waitFor(() => {
      const state = queryClient.getQueryState(["categories"]);
      expect(state?.isInvalidated).toBe(true);
    });
  });
});
