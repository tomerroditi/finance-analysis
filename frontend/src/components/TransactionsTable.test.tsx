import { describe, it, expect, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../test-utils";
import { TransactionsTable } from "./TransactionsTable";
import type { Transaction } from "../types/transaction";
import { server } from "../mocks/server";

const makeTx = (overrides: Partial<Transaction> = {}): Transaction => ({
  id: 1,
  unique_id: "1",
  amount: -100,
  date: "2026-01-15",
  description: "Test transaction",
  category: "Food",
  tag: "Groceries",
  provider: "Leumi",
  account_name: "Main",
  source: "bank_transactions",
  ...overrides,
});

const sampleTransactions: Transaction[] = [
  makeTx({ id: 1, unique_id: "1", description: "Supermarket", amount: -200, date: "2026-01-10" }),
  makeTx({ id: 2, unique_id: "2", description: "Bus fare", category: "Transport", tag: "Public Transport", amount: -15, date: "2026-01-12" }),
  makeTx({ id: 3, unique_id: "3", description: "Salary deposit", category: "Salary", tag: "-", amount: 8000, date: "2026-01-01" }),
  makeTx({ id: 4, unique_id: "4", description: "Restaurant dinner", category: "Food", tag: "Restaurants", amount: -150, date: "2026-01-20" }),
  makeTx({ id: 5, unique_id: "5", description: "Fuel", category: "Transport", tag: "Fuel", amount: -300, date: "2026-02-01" }),
];

function renderTable(overrides: Partial<Parameters<typeof TransactionsTable>[0]> = {}) {
  return renderWithProviders(
    <TransactionsTable transactions={sampleTransactions} {...overrides} />,
  );
}

describe("TransactionsTable", () => {
  describe("rendering", () => {
    it("renders all transactions", () => {
      renderTable();
      expect(screen.getByText("Supermarket")).toBeInTheDocument();
      expect(screen.getByText("Bus fare")).toBeInTheDocument();
      expect(screen.getByText("Salary deposit")).toBeInTheDocument();
      expect(screen.getByText("Restaurant dinner")).toBeInTheDocument();
      expect(screen.getByText("Fuel")).toBeInTheDocument();
    });

    it("shows empty state when no transactions", () => {
      renderWithProviders(<TransactionsTable transactions={[]} />);
      expect(screen.getByText("No transactions found.")).toBeInTheDocument();
    });

    it("displays formatted amounts", () => {
      renderTable({ transactions: [makeTx({ amount: -1234.56 })] });
      // The amount should appear formatted (the exact format depends on implementation)
      expect(screen.getByText(/1,234/)).toBeInTheDocument();
    });
  });

  describe("sorting", () => {
    it("defaults to sorting by date descending", () => {
      renderTable();
      const rows = screen.getAllByRole("row");
      // First data row (after header) should be the most recent date
      // 2026-02-01 (Fuel) is the most recent
      const firstDataRow = rows[1];
      expect(within(firstDataRow).getByText("Fuel")).toBeInTheDocument();
    });

    it("sorts by a different column on click", async () => {
      const user = userEvent.setup();
      renderTable();
      // Click Amount header to sort by amount ascending.
      const amountHeader = screen.getByRole("columnheader", { name: /Amount/ });
      await user.click(amountHeader);
      // Amount sorting compares ABSOLUTE values (expenses and income mixed),
      // so ascending is: -15 (Bus fare), -150, -200, -300, 8000.
      // (Before SortableHeader was hoisted to module scope this click was
      // silently eaten by a header remount and the assertion passed on the
      // default date-desc order by coincidence.)
      const rows = screen.getAllByRole("row");
      const firstDataRow = rows[1];
      expect(within(firstDataRow).getByText("Bus fare")).toBeInTheDocument();
    });
  });

  describe("pagination", () => {
    it("paginates with custom rowsPerPage", () => {
      renderTable({ rowsPerPage: 2 });
      // Only 2 rows should be visible (plus header)
      const dataRows = screen.getAllByRole("row").slice(1);
      expect(dataRows).toHaveLength(2);
    });

    it("shows pagination info", () => {
      renderTable({ rowsPerPage: 2 });
      expect(screen.getByText(/Showing/)).toBeInTheDocument();
      expect(screen.getByText(/Page/)).toBeInTheDocument();
    });

    it("navigates to next page", async () => {
      const user = userEvent.setup();
      renderTable({ rowsPerPage: 2 });

      // Initially showing first 2 rows (Fuel and Restaurant dinner — desc by date)
      expect(screen.getByText("Fuel")).toBeInTheDocument();
      expect(screen.getByText("Restaurant dinner")).toBeInTheDocument();
      expect(screen.queryByText("Supermarket")).not.toBeInTheDocument();

      // Find all pagination buttons — they're in a div with gap-1
      // Order: first-page, prev-page, next-page, last-page
      const allButtons = screen.getAllByRole("button");
      // The next-page button is the one that's not disabled and comes after the page text
      // Find by SVG content — the ChevronRight button
      const nextBtn = allButtons.find(
        (btn) => btn.querySelector(".lucide-chevron-right") !== null,
      );
      expect(nextBtn).toBeDefined();
      await user.click(nextBtn!);

      // Page 2 should show different transactions
      expect(screen.queryByText("Fuel")).not.toBeInTheDocument();
    });
  });

  describe("selection", () => {
    it("shows checkboxes when showSelection is true", () => {
      renderTable({ showSelection: true });
      const checkboxes = screen.getAllByRole("checkbox");
      // Header checkbox + one per row
      expect(checkboxes.length).toBeGreaterThan(0);
    });

    it("does not show checkboxes when showSelection is false", () => {
      renderTable({ showSelection: false });
      expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
    });

    it("calls onSelectionChange when a row is selected", async () => {
      const user = userEvent.setup();
      const onSelectionChange = vi.fn();
      renderTable({ showSelection: true, onSelectionChange });

      const checkboxes = screen.getAllByRole("checkbox");
      // Click the first data row checkbox (skip header)
      await user.click(checkboxes[1]);

      expect(onSelectionChange).toHaveBeenCalled();
      const lastCall = onSelectionChange.mock.calls[onSelectionChange.mock.calls.length - 1];
      expect(lastCall[0].size).toBe(1);
    });

    it("select all toggles all visible rows", async () => {
      const user = userEvent.setup();
      const onSelectionChange = vi.fn();
      renderTable({ showSelection: true, onSelectionChange });

      const checkboxes = screen.getAllByRole("checkbox");
      // First checkbox is select-all
      await user.click(checkboxes[0]);

      const lastCall = onSelectionChange.mock.calls[onSelectionChange.mock.calls.length - 1];
      expect(lastCall[0].size).toBe(5);
    });
  });

  describe("filter toggle", () => {
    it("shows filter button when showFilter is true", () => {
      renderTable({ showFilter: true });
      expect(screen.getByText("Filters")).toBeInTheDocument();
    });

    it("does not show filter button when showFilter is false", () => {
      renderTable({ showFilter: false });
      expect(screen.queryByText("Filters")).not.toBeInTheDocument();
    });
  });

  describe("add transaction button", () => {
    it("shows add button when onAddTransaction is provided with showFilter", () => {
      renderTable({ showFilter: true, onAddTransaction: vi.fn() });
      expect(screen.getByText("Add Transaction")).toBeInTheDocument();
    });
  });

  describe("clear category/tag", () => {
    it("renders the eraser button enabled when a row has a category", () => {
      const tx = makeTx({ category: "Food", tag: "Groceries" });
      renderWithProviders(
        <TransactionsTable transactions={[tx]} showActions />,
      );
      expect(
        screen.getByRole("button", { name: "Clear category and tag" }),
      ).toBeEnabled();
    });

    it("renders the eraser button disabled when a row has neither category nor tag", () => {
      const tx = makeTx({ category: undefined, tag: undefined });
      renderWithProviders(
        <TransactionsTable transactions={[tx]} showActions />,
      );
      // The button stays in the DOM (kept for action-column alignment) but is
      // disabled since there is nothing to clear.
      expect(
        screen.getByRole("button", { name: "Clear category and tag" }),
      ).toBeDisabled();
    });

    it("calls PUT /api/transactions/:id with empty strings on per-row click", async () => {
      const capturedBody = vi.fn();
      server.use(
        http.put("/api/transactions/:id", async ({ request }) => {
          const body = await request.json();
          capturedBody(body);
          return HttpResponse.json({ status: "ok" });
        }),
      );

      const tx = makeTx({
        unique_id: "42",
        source: "bank_transactions",
        category: "Food",
        tag: "Groceries",
      });
      renderWithProviders(
        <TransactionsTable transactions={[tx]} showActions />,
      );

      await userEvent.click(
        screen.getByRole("button", { name: "Clear category and tag" }),
      );

      await waitFor(() => expect(capturedBody).toHaveBeenCalledOnce());
      expect(capturedBody).toHaveBeenCalledWith({
        source: "bank_transactions",
        category: "",
        tag: "",
      });
    });
  });
});
