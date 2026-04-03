import { useQuery } from "@tanstack/react-query";
import { taggingApi, type TaggingRule } from "../services/api";

/**
 * Shared hook for fetching tagging rules.
 * Replaces 4 duplicate useQuery calls across components.
 */
export function useTaggingRules() {
  return useQuery<TaggingRule[]>({
    queryKey: ["tagging-rules"],
    queryFn: () => taggingApi.getRules().then((res) => res.data as TaggingRule[]),
  });
}
