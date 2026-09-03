/** Shape shared by monthly, yearly and project budget rules. */
export interface TaggedBudgetRule {
  tags?: string | string[];
}

/**
 * True for a project's "everything in this category" anchor rule.
 *
 * The tag list is `["ALL_TAGS"]` for that rule, but it arrives as a raw
 * string from some endpoints and an array from others, so both are handled.
 */
export function isAllTagsRule(rule: TaggedBudgetRule): boolean {
  return (
    rule.tags?.includes("ALL_TAGS") === true ||
    rule.tags === "ALL_TAGS" ||
    (Array.isArray(rule.tags) && rule.tags[0] === "ALL_TAGS")
  );
}
