import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useCategoryTagCreate } from "./useCategoryTagCreate";
import { taggingApi } from "../services/api";
import { makeQueryKeys } from "../services/queryKeys";

const KEY = makeQueryKeys(false).tagging.categories();

function setup(map: Record<string, string[]> = { Food: ["Groceries"] }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  client.setQueryData(KEY, map);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useCategoryTagCreate(), { wrapper });
  return { client, result };
}

describe("useCategoryTagCreate", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(taggingApi, "createCategory").mockResolvedValue(
      {} as Awaited<ReturnType<typeof taggingApi.createCategory>>,
    );
    vi.spyOn(taggingApi, "createTag").mockResolvedValue(
      {} as Awaited<ReturnType<typeof taggingApi.createTag>>,
    );
  });

  it("createCategory stores the title-cased name the backend stores and returns it", async () => {
    const { result } = setup();

    const formatted = await result.current.createCategory("  entertainment ");

    expect(formatted).toBe("Entertainment");
    expect(taggingApi.createCategory).toHaveBeenCalledWith("Entertainment");
  });

  it("createTag title-cases the tag name and returns it", async () => {
    const { result } = setup();

    const formatted = await result.current.createTag("Food", "fast food");

    expect(formatted).toBe("Fast Food");
    expect(taggingApi.createTag).toHaveBeenCalledWith("Food", "Fast Food");
  });

  it("puts the new name in the cached map before the server answers", async () => {
    let answer: () => void = () => {};
    vi.mocked(taggingApi.createTag).mockReturnValue(
      new Promise((resolve) => {
        answer = () => resolve({} as Awaited<ReturnType<typeof taggingApi.createTag>>);
      }),
    );
    const { client, result } = setup();

    const pending = result.current.createTag("Food", "coffee");
    await vi.waitFor(() =>
      expect(client.getQueryData(KEY)).toEqual({ Food: ["Groceries", "Coffee"] }),
    );
    answer();
    await expect(pending).resolves.toBe("Coffee");
  });

  it("resolves without refetching the map itself", async () => {
    const getCategories = vi.spyOn(taggingApi, "getCategories");
    const { client, result } = setup();

    await result.current.createCategory("travel");

    expect(getCategories).not.toHaveBeenCalled();
    expect(client.getQueryData(KEY)).toEqual({ Food: ["Groceries"], Travel: [] });
  });

  it("puts the map back and throws when the server refuses the name", async () => {
    vi.mocked(taggingApi.createCategory).mockRejectedValue(new Error("exists"));
    const { client, result } = setup();

    await expect(result.current.createCategory("food")).rejects.toThrow("exists");

    expect(client.getQueryData(KEY)).toEqual({ Food: ["Groceries"] });
  });
});
