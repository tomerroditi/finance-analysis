import { describe, it, expect } from "vitest";
import { sortCategoriesMap } from "./useCategories";

describe("sortCategoriesMap", () => {
  it("sorts category keys alphabetically", () => {
    const input = { Transport: [], Food: [], Salary: [] };
    expect(Object.keys(sortCategoriesMap(input))).toEqual([
      "Food",
      "Salary",
      "Transport",
    ]);
  });

  it("sorts each category's tags alphabetically", () => {
    const input = { Food: ["Restaurants", "Groceries", "Coffee"] };
    expect(sortCategoriesMap(input).Food).toEqual([
      "Coffee",
      "Groceries",
      "Restaurants",
    ]);
  });

  it("places a newly appended category in its sorted position, not last", () => {
    // Backend appends new categories to the end; the sort must reposition them.
    const input = { Food: [], Transport: [], Apparel: [] };
    expect(Object.keys(sortCategoriesMap(input))).toEqual([
      "Apparel",
      "Food",
      "Transport",
    ]);
  });

  it("places a newly appended tag in its sorted position, not last", () => {
    const input = { Food: ["Groceries", "Restaurants", "Bakery"] };
    expect(sortCategoriesMap(input).Food).toEqual([
      "Bakery",
      "Groceries",
      "Restaurants",
    ]);
  });

  it("does not mutate the input arrays", () => {
    const tags = ["Restaurants", "Groceries"];
    const input = { Food: tags };
    sortCategoriesMap(input);
    expect(tags).toEqual(["Restaurants", "Groceries"]);
  });

  it("handles an empty map", () => {
    expect(sortCategoriesMap({})).toEqual({});
  });
});
