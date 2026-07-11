import { useQuery } from "@tanstack/react-query";
import { taggingApi, type TaggingRule } from "../services/api";
import { useQueryKeys } from "./useQueryKeys";

/**
 * Shared hook for fetching tagging rules.
 * Replaces 4 duplicate useQuery calls across components.
 */
export function useTaggingRules() {
  const qk = useQueryKeys();
  return useQuery<TaggingRule[]>({
    queryKey: qk.tagging.rules(),
    queryFn: () => taggingApi.getRules().then((res) => res.data as TaggingRule[]),
  });
}
