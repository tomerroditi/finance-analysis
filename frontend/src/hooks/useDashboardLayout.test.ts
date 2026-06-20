import { describe, it, expect } from "vitest";
import { cardSize, normalize, DASHBOARD_CARDS, isBetaCard } from "./useDashboardLayout";

describe("cardSize", () => {
  it("returns 'half' for the compact cards", () => {
    expect(cardSize("budget")).toBe("half");
    expect(cardSize("recent")).toBe("half");
    expect(cardSize("heatmap")).toBe("half");
  });

  it("returns 'full' for the chart cards", () => {
    expect(cardSize("income_expenses")).toBe("full");
    expect(cardSize("net_worth")).toBe("full");
    expect(cardSize("cash_flow")).toBe("full");
    expect(cardSize("category")).toBe("full");
  });

  it("every declared card has a size", () => {
    for (const card of DASHBOARD_CARDS) {
      expect(cardSize(card.id)).toMatch(/^(half|full)$/);
    }
  });
});

describe("default visibility", () => {
  it("ships income_expenses + net_worth visible and cash_flow + category hidden", () => {
    const { order, hidden } = normalize({});
    expect(order).toContain("income_expenses");
    expect(order).toContain("net_worth");
    expect(hidden).toContain("cash_flow");
    expect(hidden).toContain("category");
  });

  it("default-hidden chart cards are NOT flagged beta", () => {
    expect(isBetaCard("cash_flow")).toBe(false);
    expect(isBetaCard("category")).toBe(false);
  });
});

describe("v2 -> v3 migration of the old 'charts' card", () => {
  it("replaces a VISIBLE charts card with income_expenses + net_worth, hiding the rest", () => {
    const { order, hidden } = normalize({ v: 2, order: ["budget", "charts", "recent"], hidden: [] });
    expect(order).toContain("income_expenses");
    expect(order).toContain("net_worth");
    expect(order).not.toContain("charts");
    expect(hidden).toEqual(expect.arrayContaining(["cash_flow", "category"]));
    expect(order).toContain("budget");
    expect(order).toContain("recent");
  });

  it("keeps all four new cards hidden when charts was hidden", () => {
    const { order, hidden } = normalize({ v: 2, order: ["budget", "recent"], hidden: ["charts"] });
    expect(hidden).toEqual(
      expect.arrayContaining(["income_expenses", "net_worth", "cash_flow", "category"]),
    );
    expect(order).not.toContain("income_expenses");
    expect(order).not.toContain("charts");
  });
});
