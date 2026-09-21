import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

  it("prints one shekel sign per row, on the ceiling", () => {
    // The row is one line and the figures either side of the sign are plainly
    // in the same unit: three signs on a line, thirteen lines to a card, read
    // as noise. The ceiling carries it for the whole row.
    render(<BudgetRuleGrid rules={[makeRule()]} categoryIcons={{}} />);
    const row = screen.getByTestId("budget-rule-row");
    expect(row.textContent!.match(/\u20aa/g)).toHaveLength(1);
    // And the sign sits on the budget, not on the spend or the remainder.
    expect(row.textContent).toMatch(/2,000\s*\u20aa/);
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

  /**
   * Rows expand into an action panel only where a tab supplies actions —
   * yearly today. A row with none stays a plain readout: no focus stop, no
   * pointer cursor promising an interaction it does not have.
   */
  describe("row actions", () => {
    const actionsFor = (rule: BudgetRule) => (
      <button data-testid={`act-${rule.id}`}>close</button>
    );

    it("leaves a row inert, and unexpandable, without a renderer", async () => {
      render(<BudgetRuleGrid rules={[makeRule()]} categoryIcons={{}} />);
      const row = screen.getByTestId("budget-rule-row");
      expect(row).not.toHaveAttribute("role");
      expect(row).not.toHaveAttribute("tabindex");
      expect(row).not.toHaveAttribute("aria-expanded");

      await userEvent.click(row);
      expect(screen.queryByTestId("card-rule-actions-1")).not.toBeInTheDocument();
    });

    /**
     * `role="button"` on a div rather than a real `<button>`: Chromium wraps
     * a button's children in an anonymous box, which `grid-cols-subgrid`
     * cannot reach — the expanded row then sized its own columns and its bar
     * and figures drifted out of line with every collapsed sibling. The
     * geometry half of this is pinned in `dashboard-budget-card.spec.ts`;
     * here we hold the element and its keyboard contract.
     */
    it("opens a row's panel on click and closes it on a second click", async () => {
      render(
        <BudgetRuleGrid
          rules={[makeRule()]}
          categoryIcons={{}}
          renderRowActions={actionsFor}
        />,
      );
      const row = screen.getByTestId("budget-rule-row");
      expect(row.tagName).toBe("DIV");
      expect(row).toHaveAttribute("role", "button");
      expect(row).toHaveAttribute("tabindex", "0");
      expect(row).toHaveAttribute("aria-expanded", "false");
      expect(screen.queryByTestId("card-rule-actions-1")).not.toBeInTheDocument();

      await userEvent.click(row);
      expect(row).toHaveAttribute("aria-expanded", "true");
      expect(screen.getByTestId("card-rule-actions-1")).toBeInTheDocument();
      expect(screen.getByTestId("act-1")).toBeInTheDocument();

      await userEvent.click(row);
      expect(screen.queryByTestId("card-rule-actions-1")).not.toBeInTheDocument();
    });

    // A div carries no native activation, so the handler has to supply one.
    it.each(["{Enter}", " "])(
      "opens the panel from the keyboard with %s",
      async (key) => {
        render(
          <BudgetRuleGrid
            rules={[makeRule()]}
            categoryIcons={{}}
            renderRowActions={actionsFor}
          />,
        );
        screen.getByTestId("budget-rule-row").focus();
        await userEvent.keyboard(key);
        expect(screen.getByTestId("card-rule-actions-1")).toBeInTheDocument();
      },
    );

    // One panel at a time: thirteen rules each holding their actions open
    // turns the card into a wall of buttons with no list left to read.
    it("moves the panel to the row that was clicked", async () => {
      render(
        <BudgetRuleGrid
          rules={[makeRule(), makeRule({ id: 2, name: "Insurance" })]}
          categoryIcons={{}}
          renderRowActions={actionsFor}
        />,
      );
      const rows = screen.getAllByTestId("budget-rule-row");

      await userEvent.click(rows[0]);
      expect(screen.getByTestId("card-rule-actions-1")).toBeInTheDocument();

      await userEvent.click(rows[1]);
      expect(screen.queryByTestId("card-rule-actions-1")).not.toBeInTheDocument();
      expect(screen.getByTestId("card-rule-actions-2")).toBeInTheDocument();
    });

    // A rule can leave the list under its own open panel — deleted from it,
    // or the year cursor moved — and the grid must not hold an id no row can
    // close.
    it("drops the panel when its rule leaves the list", async () => {
      const { rerender } = render(
        <BudgetRuleGrid
          rules={[makeRule(), makeRule({ id: 2, name: "Insurance" })]}
          categoryIcons={{}}
          renderRowActions={actionsFor}
        />,
      );
      await userEvent.click(screen.getAllByTestId("budget-rule-row")[1]);
      expect(screen.getByTestId("card-rule-actions-2")).toBeInTheDocument();

      rerender(
        <BudgetRuleGrid
          rules={[makeRule()]}
          categoryIcons={{}}
          renderRowActions={actionsFor}
        />,
      );
      expect(screen.queryByTestId("card-rule-actions-2")).not.toBeInTheDocument();
      expect(screen.getByTestId("budget-rule-row")).toHaveAttribute(
        "aria-expanded",
        "false",
      );
    });

    // Closing is not deleting: the row stays, with its figures, and says so.
    it("dims a closed row and marks it, with or without actions", () => {
      const { rerender } = render(
        <BudgetRuleGrid
          rules={[makeRule({ closed: true })]}
          categoryIcons={{ Groceries: "🍔" }}
          renderRowActions={actionsFor}
        />,
      );
      let row = screen.getByTestId("budget-rule-row");
      expect(row).toHaveAttribute("data-closed", "true");
      expect(row.className).toContain("opacity-60");
      // The archive marker takes the category icon's place rather than adding
      // a badge — the row is one line and has no width to spare.
      expect(within(row).getByLabelText("Closed")).toBeInTheDocument();
      expect(within(row).queryByText("🍔")).not.toBeInTheDocument();
      // Its figures are exactly what closing keeps.
      expect(row.textContent).toContain("979");
      expect(row.textContent).toContain("2,000");

      // Closed is state, not an action, so it shows on a plain row too.
      rerender(
        <BudgetRuleGrid
          rules={[makeRule({ closed: true })]}
          categoryIcons={{ Groceries: "🍔" }}
        />,
      );
      row = screen.getByTestId("budget-rule-row");
      expect(row).toHaveAttribute("data-closed", "true");
      expect(within(row).getByLabelText("Closed")).toBeInTheDocument();
    });

    it("hands each row its own rule to build actions from", () => {
      const renderRowActions = vi.fn(actionsFor);
      render(
        <BudgetRuleGrid
          rules={[makeRule(), makeRule({ id: 2, name: "Insurance" })]}
          categoryIcons={{}}
          renderRowActions={renderRowActions}
        />,
      );
      expect(renderRowActions.mock.calls.map(([rule]) => rule.name)).toEqual([
        "Groceries",
        "Insurance",
      ]);
    });
  });
});
