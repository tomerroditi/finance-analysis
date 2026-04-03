import { useQuery } from "@tanstack/react-query";
import { taggingApi } from "../services/api";

/**
 * Shared hook for fetching the categories map (category → tags[]).
 * Replaces 10+ duplicate useQuery calls across modals and pages.
 */
export function useCategories(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ["categories"],
    queryFn: () => taggingApi.getCategories().then((res) => res.data),
    enabled: options?.enabled,
  });
}
