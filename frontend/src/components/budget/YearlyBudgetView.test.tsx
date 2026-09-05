import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "../../test-utils";
import { YearlyBudgetView } from "./YearlyBudgetView";
import { budgetApi, type YearlyAnalysis } from "../../services/api";
import type * as ApiModule from "../../services/api";

/**
 * The yearly analysis endpoint reports `current_amount` **spend-positive** —
 * `get_yearly_budget_view` already multiplies the (negative) transaction sum
 * by -1, and `summary.total_spent` is the plain sum of those values. That is
 * the same convention BudgetLedgerRow documents: positive is spend, negative
 * means refunds outran spend for the period.
 *
 * Negating it again in the view made every envelope look like a net refund:
 * the bar clamped to 0%, and the remaining column reported the untouched
 * budget in red. These tests pin the sign at the boundary so the row and the
 * status band above it can never disagree again.
 */
vi.mock("../../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof ApiModule>();
  return {
    ...actual,
    budgetApi: { ...actual.budgetApi, getYearlyAnalysis: vi.fn() },
  };
});

vi.mock("./BudgetNoticeLine", () => ({ BudgetNoticeLine: () => null }));

const YEAR = new Date().getFullYear();

function analysis(currentAmount: number): YearlyAnalysis {
  return {
    rules: [
      {
        rule: {
          id: 1,
          name: "Vacations",
          amount: 20000,
          category: "Vacations",
          tags: ["Flights", "Hotel"],
          year: YEAR,
        },
        current_amount: currentAmount,
        data: [],
        allow_edit: true,
        allow_delete: true,
      },
    ],
    summary: {
      total_allocated: 20000,
      total_spent: currentAmount,
      remaining: 20000 - currentAmount,
      on_track: 1,
      over: 0,
      biggest_overspend: null,
    },
    alerts: [],
    carried_from: null,
    skipped_conflicts: [],
  };
}

function renderView(currentAmount: number) {
  vi.mocked(budgetApi.getYearlyAnalysis).mockResolvedValue({
    data: analysis(currentAmount),
  } as Awaited<ReturnType<typeof budgetApi.getYearlyAnalysis>>);
  return renderWithProviders(<YearlyBudgetView tabs={null} />);
}

/**
 * The row renders a desktop grid and a mobile stack, and jsdom applies no CSS
 * so both are in the tree. Assert against the desktop one (first in DOM
 * order); both are fed from the same props.
 */
async function ledgerFigures() {
  const figures = await screen.findAllByTestId("ledger-figures");
  return figures[0];
}

async function ledgerRow() {
  return (await ledgerFigures()).closest("div.w-full") as HTMLElement;
}

describe("YearlyBudgetView", () => {
  beforeEach(() => vi.clearAllMocks());

  describe("spend-positive current_amount", () => {
    it("renders the API's spend as spend, not as a net refund", async () => {
      renderView(5086.25);
      const row = await ledgerRow();

      expect((await ledgerFigures()).textContent).toContain("5,086");
      expect(row.textContent).not.toContain("-5,086");
      expect(row.textContent).not.toMatch(/net refund/i);
    });

    it("fills the progress bar to the share of the envelope spent", async () => {
      renderView(5000);
      const row = await ledgerRow();

      const fill = row.querySelector<HTMLElement>('[style*="width"]');
      expect(fill?.style.width).toBe("25%");
      expect(row.textContent).toContain("25%");
    });

    it("agrees with the status band totalling the same figures", async () => {
      renderView(5000);
      await ledgerFigures();

      // The band sums `summary.total_spent` straight from the API; the row
      // must read the same number rather than its mirror image.
      const band = screen.getByTestId("budget-status-band");
      expect(band.textContent).toContain("5,000");
    });
  });

  describe("genuine net refund", () => {
    it("still renders a negative period as a refund", async () => {
      renderView(-250);
      const row = await ledgerRow();

      expect(row.textContent).toMatch(/net refund/i);
      expect(row.querySelector<HTMLElement>('[style*="width"]')?.style.width).toBe(
        "0%",
      );
    });
  });
});
