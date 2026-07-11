import { useQueryClient } from "@tanstack/react-query";
import { taggingApi } from "../services/api";
import { toTitleCase } from "../utils/textFormatting";
import { qkPrefix } from "../services/queryKeys";

export function useCategoryTagCreate() {
  const queryClient = useQueryClient();

  const createCategory = async (name: string) => {
    const formatted = toTitleCase(name);
    await taggingApi.createCategory(formatted);
    await queryClient.invalidateQueries({ queryKey: qkPrefix.categories });
    return formatted;
  };

  const createTag = async (category: string, name: string) => {
    const formatted = toTitleCase(name);
    await taggingApi.createTag(category, formatted);
    await queryClient.invalidateQueries({ queryKey: qkPrefix.categories });
    return formatted;
  };

  return { createCategory, createTag };
}
