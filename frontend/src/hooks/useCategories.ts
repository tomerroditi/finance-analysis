import { useQuery } from "@tanstack/react-query";
import { taggingApi } from "../services/api";
import { useQueryKeys } from "./useQueryKeys";

type CategoriesMap = Record<string, string[]>;

/**
 * Sort the categories map alphabetically: category keys and each category's
 * tag list. Keeps every category/tag dropdown, filter, and list in a stable,
 * predictable order — including newly created categories/tags, which the
 * backend appends and would otherwise show up at the bottom of the list.
 */
export function sortCategoriesMap(data: CategoriesMap): CategoriesMap {
  const sorted: CategoriesMap = {};
  for (const category of Object.keys(data).sort((a, b) => a.localeCompare(b))) {
    sorted[category] = [...data[category]].sort((a, b) => a.localeCompare(b));
  }
  return sorted;
}

/**
 * Shared hook for fetching the categories map (category → tags[]).
 * Replaces 10+ duplicate useQuery calls across modals and pages.
 *
 * The map is returned alphabetically sorted (keys and tag lists) via
 * `sortCategoriesMap`, so all consumers render options in a consistent order.
 */
export function useCategories(options?: { enabled?: boolean }) {
  const qk = useQueryKeys();
  return useQuery({
    queryKey: qk.tagging.categories(),
    queryFn: () => taggingApi.getCategories().then((res) => res.data),
    enabled: options?.enabled,
    select: sortCategoriesMap,
  });
}
