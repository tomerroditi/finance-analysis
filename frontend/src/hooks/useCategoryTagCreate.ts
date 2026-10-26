import { useMutation, useQueryClient } from "@tanstack/react-query";
import { taggingApi } from "../services/api";
import { toTitleCase } from "../utils/textFormatting";
import { qkPrefix } from "../services/queryKeys";
import type { RefreshPlan } from "../queryInvalidation";

type CategoriesMap = Record<string, string[]>;

/**
 * What a new category or tag can change: the categories map, its usage, and
 * — for a category — the project picker, which lists unclaimed categories.
 * Nothing else reads a category no transaction carries yet.
 */
export const CATEGORY_CREATE_PLAN: RefreshPlan = {
  only: [qkPrefix.categories, ["category-usage"], ["budget", "available-projects"]],
};

/** The name the backend stores (`_clean_name`: stripped, then title-cased). */
const normalise = (name: string) => toTitleCase(name.trim());

/**
 * Inline "create category / tag" for the pickers in every tagging modal.
 *
 * The new name lands in the cached categories map before the request is
 * sent, so the picker can select it at once; the call resolves when the
 * server has stored it (a rejected name throws, and the map is put back).
 * The refetch that follows runs behind it, along `CATEGORY_CREATE_PLAN` —
 * this used to await it, so every inline create waited a round trip *and* a
 * refetch of the whole map before the modal could go on.
 */
export function useCategoryTagCreate() {
  const queryClient = useQueryClient();

  // Every cached map under the prefix — in practice the current mode's only,
  // since switching Demo Mode resets the cache. Keyed by prefix so the hook
  // needs no Demo Mode context of its own.
  const patch = async (change: (map: CategoriesMap) => CategoriesMap) => {
    await queryClient.cancelQueries({ queryKey: qkPrefix.categories });
    const before = queryClient.getQueriesData<CategoriesMap>({ queryKey: qkPrefix.categories });
    for (const [key, map] of before) {
      if (map) queryClient.setQueryData<CategoriesMap>(key, change(map));
    }
    return () => {
      for (const [key, map] of before) queryClient.setQueryData(key, map);
    };
  };

  const mutation = useMutation({
    mutationFn: async ({ category, tag }: { category: string; tag?: string }) => {
      if (tag === undefined) await taggingApi.createCategory(category);
      else await taggingApi.createTag(category, tag);
    },
    onMutate: async ({ category, tag }) => ({
      refresh: CATEGORY_CREATE_PLAN,
      restore: await patch((map) =>
        tag === undefined
          ? { ...map, [category]: map[category] ?? [] }
          : { ...map, [category]: [...(map[category] ?? []).filter((existing) => existing !== tag), tag] },
      ),
    }),
    onError: (_error, _variables, context) => context?.restore(),
  });

  const createCategory = async (name: string) => {
    const formatted = normalise(name);
    await mutation.mutateAsync({ category: formatted });
    return formatted;
  };

  const createTag = async (category: string, name: string) => {
    const formatted = normalise(name);
    await mutation.mutateAsync({ category, tag: formatted });
    return formatted;
  };

  return { createCategory, createTag };
}
