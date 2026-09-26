const ALL_TAGS = "all_tags";

/**
 * A tag list the way the backend stores a goal's category rule: sorted and
 * semicolon-joined, with `null` for "every tag in the category".
 */
export function joinRuleTags(tags?: string[] | null): string | null {
  const cleaned = [...new Set((tags ?? []).map((t) => t.trim()).filter(Boolean))].sort();
  if (cleaned.length === 0 || cleaned.includes(ALL_TAGS)) return null;
  return cleaned.join(";");
}

/** The inverse of {@link joinRuleTags}: `null` (every tag) is an empty list. */
export function splitRuleTags(tags?: string | null): string[] {
  return (tags ?? "")
    .split(";")
    .map((t) => t.trim())
    .filter((t) => t && t !== ALL_TAGS);
}
