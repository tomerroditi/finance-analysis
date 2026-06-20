import { describe, it, expect } from "vitest";
import { cardSize, DASHBOARD_CARDS } from "./useDashboardLayout";

describe("cardSize", () => {
  it("returns 'half' for the four compact cards", () => {
    expect(cardSize("budget")).toBe("half");
    expect(cardSize("recent")).toBe("half");
    expect(cardSize("goals")).toBe("half");
    expect(cardSize("recurring")).toBe("half");
  });

  it("returns 'full' for the wide cards", () => {
    expect(cardSize("forecast")).toBe("full");
    expect(cardSize("insights")).toBe("full");
    expect(cardSize("heatmap")).toBe("full");
    expect(cardSize("charts")).toBe("full");
  });

  it("every declared card has a size", () => {
    for (const card of DASHBOARD_CARDS) {
      expect(cardSize(card.id)).toMatch(/^(half|full)$/);
    }
  });
});
