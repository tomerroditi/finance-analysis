import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test-utils";
import { YearlyBudgetView } from "./YearlyBudgetView";
import {
  budgetApi,
  pendingRefundsApi,
  type PendingRefund,
  type YearlyAnalysis,
} from "../../services/api";
import type { Transaction } from "../../types/transaction";
import type * as ApiModule from "../../services/api";

/**
 * The yearly analysis endpoint reports `current_amount` **spend-positive** —
 * `get_yearly_budget_view` already multiplies the (negative) transaction sum
 * by -1, and `summary.total_spent` is the plain sum of those values. That is
 * the same convention BudgetLedgerRow documents: positive is spend, negative
 * means refunds outran spend for the period.
 *
 * Negating it again in the view made every rule look like a net refund:
 * the bar clamped to 0%, and the remaining column reported the untouched
 * budget in red. These tests pin the sign at the boundary so the row and the
 * status band above it can never disagree again.
 */
vi.mock("../../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof ApiModule>();
  return {
    ...actual,
    budgetApi: {
      ...actual.budgetApi,
      getYearlyAnalysis: vi.fn(),
      setYearlyRuleClosed: vi.fn(),
    },
    pendingRefundsApi: {
      ...actual.pendingRefundsApi,
      getAll: vi.fn(),
    },
  };
});

vi.mock("./BudgetNoticeLine", () => ({ BudgetNoticeLine: () => null }));

const YEAR = new Date().getFullYear();

function entry(
  id: number,
  name: string,
  currentAmount: number,
  closed = false,
  data: Transaction[] = [],
): YearlyAnalysis["rules"][number] {
  return {
    rule: {
      id,
      name,
      amount: 20000,
      category: name,
      tags: ["Flights", "Hotel"],
      year: YEAR,
    },
    current_amount: currentAmount,
    data,
    allow_edit: true,
    allow_delete: true,
    closed,
  };
}

function analysis(
  rules: YearlyAnalysis["rules"],
  overrides: Partial<YearlyAnalysis["summary"]> = {},
): YearlyAnalysis {
  const spent = rules.reduce((sum, r) => sum + r.current_amount, 0);
  return {
    rules,
    summary: {
      total_allocated: 20000 * rules.length,
      total_spent: spent,
      remaining: 20000 * rules.length - spent,
      on_track: rules.length,
      over: 0,
      closed: 0,
      biggest_overspend: null,
      ...overrides,
    },
    alerts: [],
    carried_from: null,
    skipped_conflicts: [],
  };
}

function renderAnalysis(data: YearlyAnalysis) {
  vi.mocked(budgetApi.getYearlyAnalysis).mockResolvedValue({
    data,
  } as Awaited<ReturnType<typeof budgetApi.getYearlyAnalysis>>);
  return renderWithProviders(<YearlyBudgetView tabs={null} />);
}

function renderView(currentAmount: number) {
  return renderAnalysis(analysis([entry(1, "Vacations", currentAmount)]));
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
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(pendingRefundsApi.getAll).mockResolvedValue({
      data: [] as PendingRefund[],
    } as Awaited<ReturnType<typeof pendingRefundsApi.getAll>>);
  });

  describe("spend-positive current_amount", () => {
    it("renders the API's spend as spend, not as a net refund", async () => {
      renderView(5086.25);
      const row = await ledgerRow();

      expect((await ledgerFigures()).textContent).toContain("5,086");
      expect(row.textContent).not.toContain("-5,086");
      expect(row.textContent).not.toMatch(/net refund/i);
    });

    it("fills the progress bar to the share of the rule spent", async () => {
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

  describe("closed rules", () => {
    it("marks a closed rule and offers to reopen it", async () => {
      renderAnalysis(
        analysis([entry(1, "Car insurance", 5000, true)], {
          on_track: 0,
          closed: 1,
        }),
      );

      expect(await screen.findAllByTestId("yearly-closed-badge")).not.toHaveLength(
        0,
      );
      expect(
        screen.getAllByRole("button", { name: /reopen rule/i }).length,
      ).toBeGreaterThan(0);
      // The count sits beside the health figures rather than inflating them.
      expect(screen.getAllByTestId("yearly-closed-count")[0].textContent).toBe("1");
    });

    it("keeps a closed rule's figures — closing is not a delete", async () => {
      renderAnalysis(
        analysis([entry(1, "Car insurance", 5000, true)], { closed: 1 }),
      );

      expect((await ledgerFigures()).textContent).toContain("5,000");
      expect((await ledgerFigures()).textContent).toContain("20,000");
    });

    it("lists open rules before closed ones", async () => {
      renderAnalysis(
        analysis(
          [entry(1, "Car insurance", 5000, true), entry(2, "Vacations", 900)],
          { on_track: 1, closed: 1 },
        ),
      );

      const rows = await screen.findAllByTestId("ledger-sublabel");
      // Desktop and mobile layouts are both in the tree; the desktop grid
      // comes first, so the first two sublabels are the two rows in order.
      expect(rows[0].textContent).toContain("Vacations");
      expect(rows[1].textContent).toContain("Car insurance");
    });

    it("reopens without asking for confirmation", async () => {
      vi.mocked(budgetApi.setYearlyRuleClosed).mockResolvedValue(
        {} as Awaited<ReturnType<typeof budgetApi.setYearlyRuleClosed>>,
      );
      renderAnalysis(
        analysis([entry(7, "Car insurance", 5000, true)], { closed: 1 }),
      );

      // Both the desktop and the mobile action rows render under jsdom, so
      // the toggle appears twice; either one drives the same handler.
      const reopen = await screen.findAllByTestId("yearly-close-toggle-7");
      await userEvent.click(reopen[0]);

      await waitFor(() =>
        expect(budgetApi.setYearlyRuleClosed).toHaveBeenCalledWith(7, false),
      );
    });

    it("asks before closing an open rule", async () => {
      vi.mocked(budgetApi.setYearlyRuleClosed).mockResolvedValue(
        {} as Awaited<ReturnType<typeof budgetApi.setYearlyRuleClosed>>,
      );
      renderAnalysis(analysis([entry(7, "Vacations", 5000)]));

      const toggles = await screen.findAllByTestId("yearly-close-toggle-7");
      await userEvent.click(toggles[0]);

      const dialog = await screen.findByRole("alertdialog");
      expect(dialog.textContent).toContain("Vacations");
      expect(budgetApi.setYearlyRuleClosed).not.toHaveBeenCalled();

      await userEvent.click(
        within(dialog).getByRole("button", { name: /close rule/i }),
      );
      await waitFor(() =>
        expect(budgetApi.setYearlyRuleClosed).toHaveBeenCalledWith(7, true),
      );
    });
  });

  describe("related transactions", () => {
    const TRANSACTIONS: Transaction[] = [
      {
        unique_id: "11",
        source: "bank",
        description: "El Al tickets",
        amount: -3200,
        date: `${YEAR}-03-14`,
        category: "Vacations",
        tag: "Flights",
      },
      {
        unique_id: "12",
        source: "credit_card",
        description: "Hotel Firenze",
        amount: -1886.25,
        date: `${YEAR}-07-02`,
        category: "Vacations",
        tag: "Hotel",
      },
    ];

    /** The row's own disclosure button — the one carrying `aria-expanded`. */
    async function expandFirstRow() {
      const toggles = await screen.findAllByRole("button", { expanded: false });
      await userEvent.click(toggles[0]);
    }

    it("hides the rule's transactions until the row is expanded", async () => {
      renderAnalysis(
        analysis([entry(1, "Vacations", 5086.25, false, TRANSACTIONS)]),
      );
      await ledgerFigures();

      expect(screen.queryByText(/el al tickets/i)).toBeNull();
    });

    it("lists the year's transactions behind the rule once expanded", async () => {
      renderAnalysis(
        analysis([entry(1, "Vacations", 5086.25, false, TRANSACTIONS)]),
      );
      await ledgerFigures();
      await expandFirstRow();

      expect(await screen.findByText(/el al tickets/i)).toBeTruthy();
      expect(screen.getByText(/hotel firenze/i)).toBeTruthy();
    });

    it("lists a closed rule's transactions too — closing keeps the history", async () => {
      renderAnalysis(
        analysis([entry(1, "Car insurance", 5086.25, true, TRANSACTIONS)], {
          on_track: 0,
          closed: 1,
        }),
      );
      await ledgerFigures();
      await expandFirstRow();

      expect(await screen.findByText(/el al tickets/i)).toBeTruthy();
      expect(screen.getAllByTestId("yearly-closed-notice")[0]).toBeTruthy();
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
