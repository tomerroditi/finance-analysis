import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GoalsSection } from "./GoalsSection";
import {
  savingsGoalsApi,
  taggingApi,
  testingApi,
  type SavingsGoal,
  type SavingsGoalEntry,
  type SavingsGoalFreeCash,
  type SavingsGoalTimeline,
  type YearlySavings,
} from "../../services/api";
import { DemoModeProvider } from "../../context/DemoModeContext";
import type { ConfirmOptions } from "../../context/DialogContext";

/**
 * GoalsSection lists goals the user funds by hand: each row adds and takes out
 * money as dated entries, offers this month's suggested funding, and lists its
 * entries with an undo. Under the goals, free cash goes red when more is set
 * aside than there is, with a confirmed "Cover it" plan.
 *
 * The `is_closed` / `is_achieved` flags arrive from SQLite as 0/1 integers, so
 * the row markup must guard them with `!!` — a bare `{0 && <Icon/>}` renders
 * the literal string "0" beside the goal name.
 */

const { confirmMock, notifyError } = vi.hoisted(() => ({
  confirmMock: vi.fn(async (_options: ConfirmOptions) => true),
  notifyError: vi.fn(),
}));

vi.mock("../../context/DialogContext", () => ({
  useConfirm: () => confirmMock,
  useNotify: () => ({ error: notifyError, info: vi.fn() }),
}));

function makeGoal(overrides: Partial<SavingsGoal> = {}): SavingsGoal {
  return {
    id: 1,
    name: "Vacation",
    target_amount: 10000,
    priority: 0,
    monthly_amount: null,
    start_month: "2026-01",
    target_date: null,
    contribution_category: null,
    contribution_tags: null,
    utilization_category: null,
    utilization_tags: null,
    status: "active",
    closed_month: null,
    notes: null,
    added: 2500,
    income: 0,
    spent: 0,
    saved: 2500,
    balance: 2500,
    available: 2500,
    owed: 0,
    remaining: 7500,
    progress_pct: 25,
    is_achieved: false,
    is_closed: false,
    months_remaining: null,
    monthly_needed: null,
    is_past_due: false,
    added_this_month: 0,
    suggested_this_month: 0,
    entries: [],
    ...overrides,
  };
}

function makeEntry(overrides: Partial<SavingsGoalEntry> = {}): SavingsGoalEntry {
  return {
    id: 100,
    goal_id: 1,
    date: "2026-09-01",
    amount: 500,
    source: "manual",
    note: null,
    ...overrides,
  };
}

/** A resolved axios-shaped answer carrying the whole goal list. */
function listAnswer(goals: SavingsGoal[] = []) {
  return { data: goals } as Awaited<ReturnType<typeof savingsGoalsApi.addEntry>>;
}

async function renderGoals(
  goals: SavingsGoal[],
  pool: Partial<SavingsGoalFreeCash> = {},
  timeline: Partial<SavingsGoalTimeline> = {},
) {
  vi.spyOn(savingsGoalsApi, "getAll").mockResolvedValue({
    data: goals,
  } as Awaited<ReturnType<typeof savingsGoalsApi.getAll>>);

  // The history panel fetches as soon as it is expanded, so the timeline is
  // stubbed here rather than per test — an unmocked call would hit the network.
  vi.spyOn(savingsGoalsApi, "getTimeline").mockResolvedValue({
    data: {
      has_goals: true,
      total_months: 0,
      months: [],
      goals: [],
      ...timeline,
    },
  } as Awaited<ReturnType<typeof savingsGoalsApi.getTimeline>>);

  vi.spyOn(savingsGoalsApi, "getFreeCash").mockResolvedValue({
    data: {
      free_cash: 0,
      earmarked: 0,
      liquid: 0,
      has_goals: false,
      shortfall: 0,
      cover_plan: [],
      ...pool,
    },
  } as Awaited<ReturnType<typeof savingsGoalsApi.getFreeCash>>);

  // The yearly savings section heads the card; its own tests cover it.
  const yearly: YearlySavings = {
    current_year: 2026,
    years: [{ year: 2026, saved: 0, target: null, is_current: true, months: [] }],
    pace: null,
  };
  vi.spyOn(savingsGoalsApi, "getYearly").mockResolvedValue({
    data: yearly,
  } as Awaited<ReturnType<typeof savingsGoalsApi.getYearly>>);

  vi.spyOn(testingApi, "getDemoModeStatus").mockResolvedValue({
    data: { demo_mode: false, forced: false },
  } as Awaited<ReturnType<typeof testingApi.getDemoModeStatus>>);

  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const result = render(
    <QueryClientProvider client={client}>
      <DemoModeProvider>
        <GoalsSection />
      </DemoModeProvider>
    </QueryClientProvider>,
  );
  await screen.findByText(goals[0].name);
  return result;
}

/** Expand the collapsed-by-default month-by-month panel. */
function expandHistory() {
  fireEvent.click(screen.getByRole("button", { name: /month by month/i }));
}

/** The row container for a goal, found by walking up from its name. */
function rowFor(name: string): HTMLElement {
  const label = within(screen.getByTestId("goals-list")).getByText(name);
  return label.closest("div.group") as HTMLElement;
}

beforeEach(() => {
  vi.restoreAllMocks();
  confirmMock.mockReset();
  confirmMock.mockImplementation(async () => true);
  notifyError.mockClear();
});

describe("GoalsSection", () => {
  describe("priority order", () => {
    it("numbers goals by priority and disables the edge arrows", async () => {
      await renderGoals([
        makeGoal({ id: 1, name: "First", priority: 0 }),
        makeGoal({ id: 2, name: "Second", priority: 1 }),
      ]);

      expect(within(rowFor("First")).getByText("#1")).toBeTruthy();
      expect(within(rowFor("Second")).getByText("#2")).toBeTruthy();
      expect(within(rowFor("First")).getByLabelText(/move up/i)).toBeDisabled();
      expect(within(rowFor("Second")).getByLabelText(/move down/i)).toBeDisabled();
      expect(within(rowFor("First")).getByLabelText(/move down/i)).toBeEnabled();
    });

    it("moves the row at once and persists the new order", async () => {
      const reorder = vi
        .spyOn(savingsGoalsApi, "reorder")
        .mockReturnValue(new Promise(() => {}));
      await renderGoals([
        makeGoal({ id: 7, name: "First", priority: 0 }),
        makeGoal({ id: 9, name: "Second", priority: 1 }),
      ]);

      fireEvent.click(within(rowFor("Second")).getByLabelText(/move up/i));

      await waitFor(() => expect(reorder).toHaveBeenCalledWith([9, 7]));
      // The order is the user's answer, not the server's: it lands first.
      await waitFor(() => expect(within(rowFor("Second")).getByText("#1")).toBeTruthy());
    });

    it("shows nothing about recalculating — a reorder restates nothing", async () => {
      vi.spyOn(savingsGoalsApi, "reorder").mockReturnValue(new Promise(() => {}));
      await renderGoals([
        makeGoal({ id: 1, name: "First", priority: 0 }),
        makeGoal({ id: 2, name: "Second", priority: 1 }),
      ]);

      fireEvent.click(within(rowFor("First")).getByLabelText(/move down/i));

      await waitFor(() => expect(within(rowFor("First")).getByText("#2")).toBeTruthy());
      expect(screen.queryByText(/recalculating/i)).not.toBeInTheDocument();
      expect(within(rowFor("First")).getByTestId("goal-figures")).not.toHaveAttribute("aria-busy");
    });
  });

  describe("status line precedence", () => {
    it("shows the remaining amount for a plain in-progress goal", async () => {
      await renderGoals([makeGoal({ name: "Plain" })]);
      expect(rowFor("Plain").textContent).toContain("to go");
    });

    it("prefers the monthly schedule when the goal has a target date", async () => {
      await renderGoals([
        makeGoal({ name: "Dated", months_remaining: 5, monthly_needed: 1500 }),
      ]);
      const text = rowFor("Dated").textContent ?? "";
      expect(text).toContain("/mo");
      expect(text).not.toContain("to go");
    });

    it("says a goal past its target date is short instead of asking for 0 months", async () => {
      await renderGoals([
        makeGoal({
          name: "Late",
          months_remaining: 0,
          monthly_needed: 5307,
          remaining: 5307,
          is_past_due: true,
        }),
      ]);
      const text = rowFor("Late").textContent ?? "";
      expect(text).toContain("target date passed");
      expect(text).not.toContain("/mo");
    });

    it("asks for what is left this month when the target date is this month", async () => {
      await renderGoals([
        makeGoal({ name: "Soon", months_remaining: 0, monthly_needed: 900 }),
      ]);
      const text = rowFor("Soon").textContent ?? "";
      expect(text).toContain("still needed this month");
      expect(text).not.toContain("/mo");
    });

    it("prefers achieved over the schedule", async () => {
      await renderGoals([
        makeGoal({ name: "Done", is_achieved: true, months_remaining: 5, monthly_needed: 1500 }),
      ]);
      const text = rowFor("Done").textContent ?? "";
      expect(text).toContain("Achieved");
      expect(text).not.toContain("/mo");
    });

    it("prefers closed over achieved", async () => {
      await renderGoals([
        makeGoal({ name: "Spent", is_achieved: true, is_closed: true, status: "closed" }),
      ]);
      const text = rowFor("Spent").textContent ?? "";
      expect(text).toContain("Closed");
      expect(text).not.toContain("Achieved");
    });
  });

  describe("SQLite boolean rendering", () => {
    it("never leaks a literal 0 next to the goal name", async () => {
      await renderGoals([
        makeGoal({
          name: "Vacation",
          is_achieved: 0 as unknown as boolean,
          is_closed: 0 as unknown as boolean,
        }),
      ]);

      const header = within(screen.getByTestId("goals-list")).getByText("Vacation")
        .parentElement as HTMLElement;
      expect(header.textContent).toBe("#1Vacation");
    });

    it("shows the check icon only once a goal is achieved", async () => {
      await renderGoals([
        makeGoal({ id: 1, name: "Open", is_achieved: false }),
        makeGoal({ id: 2, name: "Filled", is_achieved: true }),
      ]);

      expect(rowFor("Filled").querySelectorAll("svg.lucide-check")).toHaveLength(1);
      expect(rowFor("Open").querySelectorAll("svg.lucide-check")).toHaveLength(0);
    });
  });

  describe("figures", () => {
    it("shows what the goal holds against its target", async () => {
      await renderGoals([makeGoal({ name: "Trip", available: 2500, target_amount: 10000 })]);

      const balance = within(rowFor("Trip")).getByTestId("goal-balance").textContent ?? "";
      expect(balance).toMatch(/2,500/);
      expect(balance).toMatch(/10,000/);
    });

    it("shows what was saved, what is left to spend, and the spent part of the bar", async () => {
      await renderGoals([
        makeGoal({
          name: "Wedding",
          saved: 9000,
          spent: 4000,
          available: 5000,
          target_amount: 10000,
          progress_pct: 90,
        }),
      ]);

      const row = within(rowFor("Wedding"));
      expect(row.getByTestId("goal-balance").textContent).toMatch(/9,000.*10,000/);
      expect(row.getByTestId("goal-left-to-spend").textContent).toMatch(/5,000.*left to spend/);
      expect(row.getByTestId("goal-bar-spent").style.width).toBe("40%");
      expect(rowFor("Wedding").textContent).toMatch(/4,000.*spent/);
    });

    it("draws no spent part while the goal has spent nothing", async () => {
      await renderGoals([makeGoal({ name: "Trip", available: 2500, target_amount: 10000 })]);

      expect(within(rowFor("Trip")).queryByTestId("goal-bar-spent")).toBeNull();
      expect(within(rowFor("Trip")).queryByTestId("goal-left-to-spend")).toBeNull();
    });

    it("says what was added this month, and nothing when nothing was", async () => {
      await renderGoals([
        makeGoal({ id: 1, name: "Busy", added_this_month: 400 }),
        makeGoal({ id: 2, name: "Quiet", added_this_month: 0 }),
      ]);

      expect(rowFor("Busy").textContent).toContain("added this month");
      expect(rowFor("Quiet").textContent).not.toContain("added this month");
    });

    it("names what a goal spent ahead of its income", async () => {
      await renderGoals([
        makeGoal({
          name: "Wedding",
          contribution_category: "Other Income",
          balance: -5307,
          available: 0,
          owed: 5307,
          spent: 198878,
        }),
      ]);

      expect(
        within(rowFor("Wedding")).getByText(/spent ahead of its income/i).textContent,
      ).toMatch(/5,307/);
    });

    it("says nothing about owing when what it owes rounds to 0 ₪", async () => {
      await renderGoals([makeGoal({ name: "Wedding", owed: 0.35 })]);

      expect(within(rowFor("Wedding")).queryByText(/ahead of its income/i)).toBeNull();
    });

    it("keeps the progress bar inside 0–100%", async () => {
      await renderGoals([
        makeGoal({ id: 1, name: "Short", progress_pct: -33.4 }),
        makeGoal({ id: 2, name: "Over", progress_pct: 140 }),
      ]);

      const width = (name: string) =>
        rowFor(name).querySelector<HTMLElement>("[style*='width']")?.style.width;
      expect(width("Short")).toBe("0%");
      expect(width("Over")).toBe("100%");
    });
  });

  describe("adding and taking out money", () => {
    it("adds money as a dated entry with an optional note", async () => {
      const addEntry = vi.spyOn(savingsGoalsApi, "addEntry").mockResolvedValue(listAnswer());
      await renderGoals([makeGoal({ id: 3, name: "Trip" })]);

      fireEvent.click(within(rowFor("Trip")).getByRole("button", { name: /add money/i }));
      fireEvent.change(screen.getByLabelText("Amount to add to Trip"), {
        target: { value: "500" },
      });
      fireEvent.change(screen.getByLabelText("Note"), { target: { value: "Bonus" } });
      fireEvent.click(within(rowFor("Trip")).getByRole("button", { name: /^save$/i }));

      await waitFor(() => expect(addEntry).toHaveBeenCalledWith(3, 500, "Bonus"));
      // Saved, so the form closes.
      await waitFor(() =>
        expect(screen.queryByTestId("goal-entry-form")).not.toBeInTheDocument(),
      );
    });

    it("takes money out as a negative entry", async () => {
      const addEntry = vi.spyOn(savingsGoalsApi, "addEntry").mockResolvedValue(listAnswer());
      await renderGoals([makeGoal({ id: 3, name: "Trip", available: 2500 })]);

      fireEvent.click(within(rowFor("Trip")).getByRole("button", { name: /take out/i }));
      fireEvent.change(screen.getByLabelText("Amount to take out of Trip"), {
        target: { value: "300" },
      });
      fireEvent.click(within(rowFor("Trip")).getByRole("button", { name: /^save$/i }));

      await waitFor(() => expect(addEntry).toHaveBeenCalledWith(3, -300, null));
    });

    it("won't take out more than the goal holds", async () => {
      const addEntry = vi.spyOn(savingsGoalsApi, "addEntry");
      await renderGoals([makeGoal({ id: 3, name: "Trip", available: 2500 })]);

      fireEvent.click(within(rowFor("Trip")).getByRole("button", { name: /take out/i }));
      fireEvent.change(screen.getByLabelText("Amount to take out of Trip"), {
        target: { value: "3000" },
      });

      expect(within(rowFor("Trip")).getByRole("button", { name: /^save$/i })).toBeDisabled();
      expect(rowFor("Trip").textContent).toMatch(/2,500.*available to take out/);
      expect(addEntry).not.toHaveBeenCalled();
    });

    it("offers no take-out on an empty goal", async () => {
      await renderGoals([makeGoal({ name: "Empty", available: 0, balance: 0 })]);

      expect(within(rowFor("Empty")).getByRole("button", { name: /take out/i })).toBeDisabled();
    });

    it("says so when the server refuses the entry", async () => {
      vi.spyOn(savingsGoalsApi, "addEntry").mockRejectedValue(new Error("400"));
      await renderGoals([makeGoal({ id: 3, name: "Trip" })]);

      fireEvent.click(within(rowFor("Trip")).getByRole("button", { name: /add money/i }));
      fireEvent.change(screen.getByLabelText("Amount to add to Trip"), {
        target: { value: "50" },
      });
      fireEvent.click(within(rowFor("Trip")).getByRole("button", { name: /^save$/i }));

      await waitFor(() => expect(notifyError).toHaveBeenCalled());
    });
  });

  describe("suggested funding", () => {
    it("offers this month's suggestion on the row and funds just that goal", async () => {
      const fund = vi.spyOn(savingsGoalsApi, "fund").mockResolvedValue(listAnswer());
      await renderGoals([makeGoal({ id: 5, name: "Car", suggested_this_month: 750 })]);

      const chip = within(rowFor("Car")).getByRole("button", { name: /^fund /i });
      expect(chip.textContent).toMatch(/750/);
      fireEvent.click(chip);

      await waitFor(() => expect(fund).toHaveBeenCalledWith([5]));
    });

    it("funds every suggestion from the header", async () => {
      const fund = vi.spyOn(savingsGoalsApi, "fund").mockResolvedValue(listAnswer());
      await renderGoals([
        makeGoal({ id: 1, name: "Car", suggested_this_month: 750 }),
        makeGoal({ id: 2, name: "Trip", suggested_this_month: 0 }),
      ]);

      fireEvent.click(screen.getByRole("button", { name: /fund all/i }));

      await waitFor(() => expect(fund).toHaveBeenCalledWith(null));
    });

    it("offers neither while nothing is suggested", async () => {
      await renderGoals([makeGoal({ name: "Trip", suggested_this_month: 0 })]);

      expect(screen.queryByRole("button", { name: /fund all/i })).not.toBeInTheDocument();
      expect(within(rowFor("Trip")).queryByRole("button", { name: /^fund /i })).toBeNull();
    });
  });

  describe("entries", () => {
    const entries = [
      makeEntry({ id: 11, amount: -200, note: "Flights deposit" }),
      makeEntry({ id: 10, amount: 2700, note: null }),
      makeEntry({ id: 9, amount: -100, source: "close" }),
    ];

    it("stay folded until asked, then list newest first with an undo each", async () => {
      const deleteEntry = vi
        .spyOn(savingsGoalsApi, "deleteEntry")
        .mockResolvedValue(listAnswer());
      await renderGoals([makeGoal({ name: "Trip", entries })]);

      expect(screen.queryByTestId("goal-entries")).not.toBeInTheDocument();
      fireEvent.click(within(rowFor("Trip")).getByRole("button", { name: /3 entries/i }));

      const rows = within(screen.getByTestId("goal-entries")).getAllByTestId("goal-entry");
      expect(rows[0].textContent).toContain("Flights deposit");
      expect(rows[1].textContent).toContain("Added");

      fireEvent.click(within(rows[0]).getByRole("button", { name: /undo/i }));
      await waitFor(() => expect(deleteEntry).toHaveBeenCalledWith(11));
    });

    it("leave a closing entry to reopening rather than undo", async () => {
      await renderGoals([makeGoal({ name: "Trip", entries })]);
      fireEvent.click(within(rowFor("Trip")).getByRole("button", { name: /3 entries/i }));

      const closing = within(screen.getByTestId("goal-entries")).getAllByTestId("goal-entry")[2];
      expect(within(closing).queryByRole("button", { name: /undo/i })).toBeNull();
    });

    it("show five at first and the rest on request", async () => {
      const many = Array.from({ length: 8 }, (_, index) =>
        makeEntry({ id: 50 + index, note: `Entry ${index}` }),
      );
      await renderGoals([makeGoal({ name: "Trip", entries: many })]);
      fireEvent.click(within(rowFor("Trip")).getByRole("button", { name: /8 entries/i }));

      expect(screen.getAllByTestId("goal-entry")).toHaveLength(5);
      fireEvent.click(screen.getByRole("button", { name: /show all 8/i }));
      expect(screen.getAllByTestId("goal-entry")).toHaveLength(8);
    });
  });

  describe("closing and reopening", () => {
    it("closes a goal after saying where its money goes", async () => {
      const close = vi.spyOn(savingsGoalsApi, "close").mockResolvedValue(listAnswer());
      await renderGoals([makeGoal({ id: 4, name: "Trip", available: 1200 })]);

      fireEvent.click(within(rowFor("Trip")).getByRole("button", { name: /close goal/i }));

      await waitFor(() => expect(close).toHaveBeenCalledWith(4));
      expect(confirmMock.mock.calls[0][0].message).toMatch(/1,200.*free cash/);
    });

    it("leaves the goal open when the confirmation is declined", async () => {
      confirmMock.mockImplementation(async () => false);
      const close = vi.spyOn(savingsGoalsApi, "close");
      await renderGoals([makeGoal({ id: 4, name: "Trip" })]);

      fireEvent.click(within(rowFor("Trip")).getByRole("button", { name: /close goal/i }));

      await waitFor(() => expect(confirmMock).toHaveBeenCalled());
      expect(close).not.toHaveBeenCalled();
    });

    it("reopens a closed goal, which takes no money until it is open", async () => {
      const reopen = vi.spyOn(savingsGoalsApi, "reopen").mockResolvedValue(listAnswer());
      await renderGoals([
        makeGoal({ id: 4, name: "Trip", is_closed: true, status: "closed", suggested_this_month: 500 }),
      ]);

      expect(within(rowFor("Trip")).queryByRole("button", { name: /add money/i })).toBeNull();
      expect(within(rowFor("Trip")).queryByRole("button", { name: /^fund /i })).toBeNull();
      fireEvent.click(within(rowFor("Trip")).getByRole("button", { name: /reopen goal/i }));

      await waitFor(() => expect(reopen).toHaveBeenCalledWith(4));
    });
  });

  describe("free cash", () => {
    it("shows bank and cash less what the goals hold", async () => {
      await renderGoals([makeGoal({ name: "Vacation" })], {
        free_cash: 4200,
        earmarked: 2500,
        liquid: 6700,
        has_goals: true,
      });

      const row = await screen.findByTestId("goals-free-cash");
      expect(row.textContent).toMatch(/6,700/);
      expect(within(row).getByTestId("goals-free-cash-amount").className).not.toContain(
        "text-red-400",
      );
      expect(within(row).queryByRole("button", { name: /cover it/i })).toBeNull();
    });

    it("goes red below zero, says by how much, and covers it only once confirmed", async () => {
      const cover = vi.spyOn(savingsGoalsApi, "cover").mockResolvedValue(listAnswer());
      await renderGoals([makeGoal({ name: "Vacation" })], {
        free_cash: -1500,
        earmarked: 8000,
        liquid: 6500,
        has_goals: true,
        shortfall: 1500,
        cover_plan: [
          { goal_id: 2, name: "New Car", amount: 1000 },
          { goal_id: 1, name: "Vacation", amount: 500 },
        ],
      });

      const row = await screen.findByTestId("goals-free-cash");
      const amount = within(row).getByTestId("goals-free-cash-amount");
      expect(amount.textContent).toContain("-");
      expect(amount.className).toContain("text-red-400");
      expect(row.textContent).toMatch(/set aside .*1,500.* more than you have/);

      fireEvent.click(within(row).getByRole("button", { name: /cover it/i }));

      await waitFor(() => expect(cover).toHaveBeenCalledTimes(1));
      const message = confirmMock.mock.calls[0][0].message;
      expect(message).toMatch(/New Car: .*1,000/);
      expect(message).toMatch(/Vacation: .*500/);
    });

    it("moves nothing when the cover plan is declined", async () => {
      confirmMock.mockImplementation(async () => false);
      const cover = vi.spyOn(savingsGoalsApi, "cover");
      await renderGoals([makeGoal({ name: "Vacation" })], {
        free_cash: -100,
        has_goals: true,
        shortfall: 100,
        cover_plan: [{ goal_id: 1, name: "Vacation", amount: 100 }],
      });

      fireEvent.click(await screen.findByRole("button", { name: /cover it/i }));

      await waitFor(() => expect(confirmMock).toHaveBeenCalled());
      expect(cover).not.toHaveBeenCalled();
    });

    it("stays hidden while the user keeps no goals", async () => {
      await renderGoals([makeGoal({ name: "Vacation" })], { has_goals: false });

      expect(screen.queryByTestId("goals-free-cash")).not.toBeInTheDocument();
    });
  });

  describe("card height", () => {
    /**
     * jsdom lays nothing out, so every height it reports is 0. Stand in a
     * content height for the one measurement the cap is decided on.
     */
    function withContentHeight(height: number) {
      const original = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollHeight");
      Object.defineProperty(HTMLElement.prototype, "scrollHeight", {
        configurable: true,
        get: () => height,
      });
      return () => {
        if (original) Object.defineProperty(HTMLElement.prototype, "scrollHeight", original);
      };
    }

    const manyGoals = [
      makeGoal({ id: 1, name: "One", priority: 0 }),
      makeGoal({ id: 2, name: "Two", priority: 1 }),
      makeGoal({ id: 3, name: "Three", priority: 2 }),
      makeGoal({ id: 4, name: "Four", priority: 3 }),
    ];

    it("scrolls the list in place once a cap would hide a row", async () => {
      const restore = withContentHeight(900);
      try {
        await renderGoals(manyGoals);

        const list = screen.getByTestId("goals-list");
        expect(list.className).toMatch(/max-h-\[26rem\]/);
        expect(list.className).toMatch(/overflow-y-auto/);
      } finally {
        restore();
      }
    });

    it("leaves a list that would barely scroll as a plain block", async () => {
      const restore = withContentHeight(436);
      try {
        await renderGoals(manyGoals);

        const list = screen.getByTestId("goals-list");
        expect(list.className).not.toMatch(/max-h-/);
        expect(list.className).not.toMatch(/overflow-y-auto/);
      } finally {
        restore();
      }
    });
  });

  describe("month-by-month history", () => {
    /** A timeline whose single month moved `goalId`. */
    function timelineWith(goalId: number, name: string, totalMonths = 3) {
      return {
        has_goals: true,
        total_months: totalMonths,
        months: [
          {
            month: "2026-08",
            free_cash: 600,
            goals: [{ goal_id: goalId, balance: 2400, change: 900 }],
          },
        ],
        goals: [{ id: goalId, name, priority: 0, status: "active", is_closed: false }],
      };
    }

    it("stays collapsed until asked, and fetches nothing until it is", async () => {
      await renderGoals([makeGoal({ id: 4, name: "Trip" })], {}, timelineWith(4, "Trip"));

      expect(screen.queryByTestId("goals-history-chart")).not.toBeInTheDocument();
      const toggle = screen.getByRole("button", { name: /month by month/i });
      expect(toggle).toHaveAttribute("aria-expanded", "false");
      expect(savingsGoalsApi.getTimeline).not.toHaveBeenCalled();

      fireEvent.click(toggle);

      expect(await screen.findByTestId("goals-history-chart")).toBeInTheDocument();
      expect(toggle).toHaveAttribute("aria-expanded", "true");
    });

    it("collapses again on a second click", async () => {
      await renderGoals([makeGoal({ id: 4, name: "Trip" })], {}, timelineWith(4, "Trip"));
      expandHistory();
      await screen.findByTestId("goals-history-chart");

      expandHistory();

      expect(screen.queryByTestId("goals-history-chart")).not.toBeInTheDocument();
    });

    it("asks for the last 12 months by default", async () => {
      await renderGoals([makeGoal({ id: 4, name: "Trip" })], {}, timelineWith(4, "Trip"));
      expandHistory();

      await waitFor(() => expect(savingsGoalsApi.getTimeline).toHaveBeenCalledWith(12));
      expect(await screen.findByTestId("goals-history-chart")).toBeInTheDocument();
    });

    it("reads the cumulative view off the same window, with no fetch of the whole history", async () => {
      await renderGoals([makeGoal({ id: 4, name: "Trip" })], {}, timelineWith(4, "Trip", 18));
      expandHistory();
      await screen.findByTestId("goals-history-chart");

      fireEvent.click(screen.getByRole("button", { name: "Cumulative" }));

      expect(screen.getByRole("button", { name: "Cumulative" })).toHaveAttribute(
        "aria-pressed",
        "true",
      );
      expect(await screen.findByText(/held at the end of each month/i)).toBeInTheDocument();
      expect(savingsGoalsApi.getTimeline).not.toHaveBeenCalledWith(0);
    });

    it("refetches the window when another range is picked", async () => {
      await renderGoals([makeGoal({ id: 4, name: "Trip" })], {}, timelineWith(4, "Trip"));
      expandHistory();
      await screen.findByTestId("goals-history-chart");

      fireEvent.click(screen.getByRole("button", { name: "6M" }));

      await waitFor(() => expect(savingsGoalsApi.getTimeline).toHaveBeenCalledWith(6));
    });

    it("offers all-time only once there is more history than the widest window", async () => {
      await renderGoals([makeGoal({ id: 4, name: "Trip" })], {}, timelineWith(4, "Trip", 3));
      expandHistory();
      await screen.findByTestId("goals-history-chart");

      expect(screen.getByRole("button", { name: /^all$/i })).toBeDisabled();
    });

    it("enables all-time once the history outgrows the fixed windows", async () => {
      await renderGoals([makeGoal({ id: 4, name: "Trip" })], {}, timelineWith(4, "Trip", 18));
      expandHistory();
      await screen.findByTestId("goals-history-chart");

      fireEvent.click(screen.getByRole("button", { name: /^all$/i }));

      await waitFor(() => expect(savingsGoalsApi.getTimeline).toHaveBeenCalledWith(0));
    });

    it("says so plainly when nothing has moved yet", async () => {
      await renderGoals([makeGoal({ name: "New" })]);
      expandHistory();

      expect(await screen.findByText(/nothing has moved yet/i)).toBeInTheDocument();
      expect(screen.queryByTestId("goals-history-chart")).not.toBeInTheDocument();
    });
  });

  describe("goal editor", () => {
    function stubCategories(categories: Record<string, string[]> = {}) {
      vi.spyOn(taggingApi, "getCategories").mockResolvedValue({
        data: categories,
      } as Awaited<ReturnType<typeof taggingApi.getCategories>>);
    }

    it("picks the start on the same calendar as the target date, keeping the month", async () => {
      stubCategories();
      const update = vi.spyOn(savingsGoalsApi, "update").mockResolvedValue(listAnswer());
      await renderGoals([makeGoal({ name: "Trip", start_month: "2025-01" })]);

      fireEvent.click(within(rowFor("Trip")).getByRole("button", { name: /^edit$/i }));
      const start = await screen.findByLabelText(/start from/i);
      expect(start).toHaveAttribute("type", "date");
      expect(start).toHaveValue("2025-01-01");

      fireEvent.change(start, { target: { value: "2026-03-17" } });
      fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

      await waitFor(() => expect(update).toHaveBeenCalled());
      expect(update.mock.calls[0][1]).toMatchObject({ start_month: "2026-03" });
    });

    it("creates a goal with a monthly amount and a starting amount", async () => {
      stubCategories();
      const create = vi.spyOn(savingsGoalsApi, "create").mockResolvedValue(listAnswer());
      await renderGoals([makeGoal({ name: "Trip" })]);

      fireEvent.click(screen.getByRole("button", { name: /add goal/i }));
      fireEvent.change(await screen.findByLabelText(/goal name/i), {
        target: { value: "Bike" },
      });
      fireEvent.change(screen.getByLabelText(/target amount/i), { target: { value: "4000" } });
      fireEvent.change(screen.getByLabelText(/monthly amount/i), { target: { value: "250" } });
      fireEvent.change(screen.getByLabelText(/starting amount/i), { target: { value: "600" } });
      fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

      await waitFor(() => expect(create).toHaveBeenCalled());
      expect(create.mock.calls[0][0]).toMatchObject({
        name: "Bike",
        target_amount: 4000,
        monthly_amount: 250,
        initial_amount: 600,
      });
    });

    it("offers a starting amount only on a new goal, and no opening balance at all", async () => {
      stubCategories();
      const update = vi.spyOn(savingsGoalsApi, "update").mockResolvedValue(listAnswer());
      await renderGoals([makeGoal({ name: "Trip", monthly_amount: 300 })]);

      fireEvent.click(within(rowFor("Trip")).getByRole("button", { name: /^edit$/i }));
      expect(await screen.findByLabelText(/monthly amount/i)).toHaveValue(300);
      expect(screen.queryByLabelText(/starting amount/i)).not.toBeInTheDocument();
      expect(screen.queryByLabelText(/already saved/i)).not.toBeInTheDocument();
      expect(screen.queryByLabelText(/monthly cap/i)).not.toBeInTheDocument();

      fireEvent.change(screen.getByLabelText(/monthly amount/i), { target: { value: "" } });
      fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

      await waitFor(() => expect(update).toHaveBeenCalled());
      expect(update.mock.calls[0][1]).toMatchObject({ monthly_amount: null });
      expect(update.mock.calls[0][1]).not.toHaveProperty("initial_amount");
    });
  });
});
