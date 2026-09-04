import { describe, it, expect } from "vitest";
import { isAllTagsRule } from "./budgetRules";

/**
 * The anchor rule's tag is the backend's `ALL_TAGS` constant, which is the
 * lowercase string `"all_tags"` (backend/constants/budget.py). It reaches the
 * frontend as a one-element array from the rules endpoints and as a raw
 * semicolon string from others, and rows written by older builds carry mixed
 * case (`"All_tags"`), so the match has to be case-insensitive in every shape.
 *
 * Getting this wrong is invisible in a type-check and blanks the whole
 * Project Budgets tab: ProjectBudgetView gates its entire body on finding
 * this rule, so a miss renders no status band, no ledger and no empty state.
 */
describe("isAllTagsRule", () => {
  describe("the shapes the API actually sends", () => {
    it("matches the lowercase constant as a one-element array", () => {
      expect(isAllTagsRule({ tags: ["all_tags"] })).toBe(true);
    });

    it("matches the lowercase constant as a raw string", () => {
      expect(isAllTagsRule({ tags: "all_tags" })).toBe(true);
    });

    it("matches mixed case written by older builds", () => {
      expect(isAllTagsRule({ tags: ["All_tags"] })).toBe(true);
      expect(isAllTagsRule({ tags: "ALL_TAGS" })).toBe(true);
    });
  });

  describe("rules that are not the anchor", () => {
    it("rejects a per-tag envelope", () => {
      expect(isAllTagsRule({ tags: ["Flights"] })).toBe(false);
      expect(isAllTagsRule({ tags: "Flights;Hotels" })).toBe(false);
    });

    it("rejects a rule that merely includes the anchor tag among others", () => {
      expect(isAllTagsRule({ tags: ["Flights", "all_tags"] })).toBe(false);
    });

    it("rejects a missing or empty tag list", () => {
      expect(isAllTagsRule({})).toBe(false);
      expect(isAllTagsRule({ tags: [] })).toBe(false);
      expect(isAllTagsRule({ tags: "" })).toBe(false);
    });
  });
});
