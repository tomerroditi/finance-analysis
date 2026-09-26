import { describe, it, expect } from "vitest";
import { budgetLink, parseBudgetEntry } from "./budgetNavigation";

/**
 * These two halves have to agree: the dashboard budget card writes the link
 * and the Budget page reads it back. A mismatch is silent — the page just
 * opens on the Overview for today's month, which is exactly the bug the
 * query string exists to fix.
 */
describe("budgetLink", () => {
  it("names the tab it should open", () => {
    expect(budgetLink("yearly")).toBe("/budget?tab=yearly");
  });

  it("carries the month cursor the card was showing", () => {
    expect(budgetLink("monthly", { year: 2026, month: 3 })).toBe(
      "/budget?tab=monthly&year=2026&month=3",
    );
  });

  it("escapes a project name with spaces", () => {
    expect(budgetLink("projects", { project: "Cyprus Vacation" })).toContain(
      "project=Cyprus+Vacation",
    );
  });

  it("leaves out a project that is not selected yet", () => {
    expect(budgetLink("projects", { project: null })).toBe("/budget?tab=projects");
  });
});

describe("parseBudgetEntry", () => {
  const parse = (search: string) => parseBudgetEntry(new URLSearchParams(search));

  it("round-trips every link the card can build", () => {
    expect(parse(budgetLink("monthly", { year: 2026, month: 3 }).split("?")[1])).toEqual({
      tab: "monthly",
      year: 2026,
      month: 3,
    });
    expect(parse(budgetLink("projects", { project: "Cyprus Vacation" }).split("?")[1])).toEqual({
      tab: "projects",
      year: undefined,
      month: undefined,
      project: "Cyprus Vacation",
    });
  });

  it("falls back to the overview when no tab is named", () => {
    expect(parse("").tab).toBe("overview");
  });

  it("ignores a tab that is not one of the four", () => {
    expect(parse("tab=groceries").tab).toBe("overview");
  });

  it("drops an out-of-range or non-numeric period", () => {
    expect(parse("tab=monthly&year=2026&month=13").month).toBeUndefined();
    expect(parse("tab=monthly&month=abc").month).toBeUndefined();
    expect(parse("tab=monthly&year=12").year).toBeUndefined();
  });

  it("drops a blank project name so the view picks its own", () => {
    expect(parse("tab=projects&project=%20%20").project).toBeUndefined();
  });
});
