/** Shape shared by monthly, yearly and project budget rules. */
export interface TaggedBudgetRule {
  tags?: string | string[];
}

/** The backend's `ALL_TAGS` constant (backend/constants/budget.py). */
const ALL_TAGS = "all_tags";

/**
 * True for a project's "everything in this category" anchor rule.
 *
 * The tag list is exactly `["all_tags"]` for that rule — lowercase, matching
 * the backend constant — but it arrives as an array from some endpoints and as
 * a raw semicolon-joined string from others, and rows written by older builds
 * carry mixed case. Mirror the backend's own test
 * (`[t.lower() for t in tags] == [ALL_TAGS]`) rather than matching a literal:
 * ProjectBudgetView gates its whole body on finding this rule, so a missed
 * match renders the tab blank.
 */
export function isAllTagsRule(rule: TaggedBudgetRule): boolean {
  const tags =
    typeof rule.tags === "string" ? rule.tags.split(";") : (rule.tags ?? []);
  return tags.length === 1 && tags[0].trim().toLowerCase() === ALL_TAGS;
}
