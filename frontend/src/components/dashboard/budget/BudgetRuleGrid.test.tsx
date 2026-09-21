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
   * The close column only exists for the tabs whose envelopes can be
   * settled — yearly today. A monthly row must not pay a column's width for
   * an action it has no state for, which is why the callback gates it.
   */
  describe("closing an envelope", () => {
    it("draws no toggle, and no fifth column, without the callback", () => {
      render(<BudgetRuleGrid rules={[makeRule()]} categoryIcons={{}} />);
      expect(screen.queryByRole("button")).not.toBeInTheDocument();
      const row = screen.getByTestId("budget-rule-row");
      expect(row.className).toContain("col-span-4");
      expect(row).not.toHaveAttribute("data-closed");
    });

    it("gives every row a toggle labelled for its own state", () => {
      render(
        <BudgetRuleGrid
          rules={[
            makeRule(),
            makeRule({ id: 2, name: "Insurance", closed: true }),
          ]}
          categoryIcons={{}}
          onToggleClosed={vi.fn()}
        />,
      );

      expect(
        screen.getByTestId("card-rule-closed-toggle-1"),
      ).toHaveAttribute("aria-label", "Close envelope");
      expect(
        screen.getByTestId("card-rule-closed-toggle-2"),
      ).toHaveAttribute("aria-label", "Reopen envelope");
    });

    // Closing is not deleting: the row stays, with its figures, and says so.
    it("dims a closed row and marks it for the tests that read geometry", () => {
      render(
        <BudgetRuleGrid
          rules={[makeRule({ closed: true })]}
          categoryIcons={{ Groceries: "🍔" }}
          onToggleClosed={vi.fn()}
        />,
      );
      const row = screen.getByTestId("budget-rule-row");
      expect(row).toHaveAttribute("data-closed", "true");
      expect(row.className).toContain("opacity-60");
      expect(row.className).toContain("col-span-5");
      // The archive marker takes the category icon's place rather than adding
      // a badge — the row is one line and has no width to spare.
      expect(within(row).getByLabelText("Closed")).toBeInTheDocument();
      expect(within(row).queryByText("🍔")).not.toBeInTheDocument();
      // Its figures are exactly what closing keeps.
      expect(row.textContent).toContain("979");
      expect(row.textContent).toContain("2,000");
    });

    it("hands the clicked rule to the callback", async () => {
      const onToggleClosed = vi.fn();
      render(
        <BudgetRuleGrid
          rules={[makeRule(), makeRule({ id: 2, name: "Insurance" })]}
          categoryIcons={{}}
          onToggleClosed={onToggleClosed}
        />,
      );

      await userEvent.click(screen.getByTestId("card-rule-closed-toggle-2"));
      expect(onToggleClosed).toHaveBeenCalledTimes(1);
      expect(onToggleClosed.mock.calls[0][0]).toMatchObject({
        id: 2,
        name: "Insurance",
      });
    });

    // One mutation serves every row, so gating the toggles on its own
    // `isPending` would lock the whole list for one row's write and its
    // siblings' clicks would land on dead buttons.
    it("disables only the row whose own write is in flight", () => {
      render(
        <BudgetRuleGrid
          rules={[makeRule(), makeRule({ id: 2, name: "Insurance" })]}
          categoryIcons={{}}
          onToggleClosed={vi.fn()}
          isTogglePending={(rule) => rule.id === 2}
        />,
      );
      expect(screen.getByTestId("card-rule-closed-toggle-1")).toBeEnabled();
      expect(screen.getByTestId("card-rule-closed-toggle-2")).toBeDisabled();
    });
  });
});
