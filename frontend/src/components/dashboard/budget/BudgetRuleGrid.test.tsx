import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { BudgetRuleGrid } from "./BudgetRuleGrid";
import type { BudgetRule } from "./types";

/**
 * The dashboard's envelope list is one line per rule: name, bar, figures and
 * the remainder with its percentage suffix all live on the same row. The
 * assertions below pin the signal that line carries — nothing the old
 * four-row tile showed may quietly disappear — and the two states where the
 * arithmetic is easy to get wrong: an overspend and a rule with no budget.
 */

function makeRule(overrides: Partial<BudgetRule> = {}): BudgetRule {
  return {
    id: 1,
    name: "Groceries",
    category: "Groceries",
    budget_amount: 2000,
    spent_amount: 979,
    ...overrides,
  };
}

function fill(row: HTMLElement) {
  return row.querySelector<HTMLElement>('[style*="width"]')!;
}

describe("BudgetRuleGrid", () => {
  it("renders one row per rule, each carrying name, figures, remainder and percentage", () => {
    render(
      <BudgetRuleGrid
        rules={[makeRule(), makeRule({ id: 2, name: "Gas", category: "Gas" })]}
        categoryIcons={{ Groceries: "🍔" }}
      />,
    );

    const rows = screen.getAllByTestId("budget-rule-row");
    expect(rows).toHaveLength(2);

    const groceries = rows[0];
    expect(within(groceries).getByText("Groceries")).toBeInTheDocument();
    expect(within(groceries).getByText("🍔")).toBeInTheDocument();
    expect(groceries.textContent).toContain("979");
    expect(groceries.textContent).toContain("2,000");
    expect(groceries.textContent).toContain("1,021");
    expect(groceries.textContent).toContain("49%");
  });

  it("fills the bar proportionally and stays emerald while comfortably under", () => {
    render(
      <BudgetRuleGrid
        rules={[makeRule({ spent_amount: 500 })]}
        categoryIcons={{}}
      />,
    );
    const bar = fill(screen.getByTestId("budget-rule-row"));
    expect(bar.getAttribute("style")).toContain("width: 25%");
    expect(bar.className).toContain("bg-emerald-500");
  });

  it("turns amber from 75% of the envelope", () => {
    render(
      <BudgetRuleGrid
        rules={[makeRule({ spent_amount: 1600 })]}
        categoryIcons={{}}
      />,
    );
    expect(fill(screen.getByTestId("budget-rule-row")).className).toContain(
      "bg-amber-500",
    );
  });

  it("reports an overspend as an over amount, capping the bar at full", () => {
    render(
      <BudgetRuleGrid
        rules={[makeRule({ spent_amount: 2500 })]}
        categoryIcons={{}}
      />,
    );
    const row = screen.getByTestId("budget-rule-row");
    expect(row.textContent).toMatch(/500.*over/);
    expect(row.textContent).toContain("125%");
    const bar = fill(row);
    expect(bar.getAttribute("style")).toContain("width: 100%");
    expect(bar.className).toContain("bg-rose-500");
  });

  // Regression: "Other Expenses" carries a 0 ceiling once every shekel is
  // allocated to explicit rules. Spend against it is entirely unbudgeted, so
  // the row must read fully over rather than as an untouched envelope.
  it("treats spend against a zero budget as fully over", () => {
    render(
      <BudgetRuleGrid
        rules={[makeRule({ budget_amount: 0, spent_amount: 300 })]}
        categoryIcons={{}}
      />,
    );
    const row = screen.getByTestId("budget-rule-row");
    const bar = fill(row);
    expect(bar.className).toContain("bg-rose-500");
    expect(bar.getAttribute("style")).toContain("width: 100%");
    expect(row.textContent).toMatch(/300.*over/);
  });

  it("leaves an untouched zero-budget rule empty rather than full", () => {
    render(
      <BudgetRuleGrid
        rules={[makeRule({ budget_amount: 0, spent_amount: 0 })]}
        categoryIcons={{}}
      />,
    );
    const bar = fill(screen.getByTestId("budget-rule-row"));
    expect(bar.getAttribute("style")).toContain("width: 0%");
    expect(bar.className).toContain("bg-emerald-500");
  });
});
