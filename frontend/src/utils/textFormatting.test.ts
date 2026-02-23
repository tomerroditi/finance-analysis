import { describe, it, expect } from "vitest";
import { toTitleCase } from "./textFormatting";

describe("toTitleCase", () => {
  it("capitalizes first letter of each word", () => {
    expect(toTitleCase("hello world")).toBe("Hello World");
  });

  it("lowercases remaining letters", () => {
    expect(toTitleCase("HELLO WORLD")).toBe("Hello World");
  });

  it("preserves initialisms", () => {
    expect(toTitleCase("go to atm")).toBe("Go To ATM");
    expect(toTitleCase("usa trip")).toBe("USA Trip");
    expect(toTitleCase("gpt model")).toBe("GPT Model");
  });

  it("handles hyphenated words", () => {
    expect(toTitleCase("pick-up")).toBe("Pick-Up");
  });

  it("handles hyphenated words with initialisms", () => {
    expect(toTitleCase("p2p-transfer")).toBe("P2P-Transfer");
  });

  it("returns empty/whitespace strings unchanged", () => {
    expect(toTitleCase("")).toBe("");
    expect(toTitleCase("  ")).toBe("  ");
  });

  it("preserves internal whitespace", () => {
    expect(toTitleCase("hello  world")).toBe("Hello  World");
  });

  it("handles single word", () => {
    expect(toTitleCase("food")).toBe("Food");
  });
});
