import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GoalsSection } from "./GoalsSection";
import {
  savingsGoalsApi,
  testingApi,
  type SavingsGoal,
  type SavingsGoalFreeCash,
} from "../../services/api";
import { DemoModeProvider } from "../../context/DemoModeContext";

/**
 * GoalsSection renders a waterfall: goals are listed in funding order and each
 * row's status line has a strict precedence — closed beats achieved, achieved
 * beats a schedule, and a plain remainder is the fallback.
 *
 * The `is_closed` / `is_achieved` flags arrive from SQLite as 0/1 integers, so
 * the row markup must guard them with `!!` — a bare `{0 && <Icon/>}` renders
 * the literal string "0" beside the goal name.
 */

vi.mock("../../context/DialogContext", () => ({
  useConfirm: () => async () => true,
}));

function makeGoal(overrides: Partial<SavingsGoal> = {}): SavingsGoal {
  return {
    id: 1,
    name: "Vacation",
    target_amount: 10000,
    opening_balance: 0,
    priority: 0,
    monthly_cap: null,
    start_month: "2026-01",
    target_date: null,
    contribution_category: null,
    contribution_tags: null,
    status: "active",
    closed_month: null,
    notes: null,
    allocated: 2500,
    contributed: 0,
    utilized: 0,
    clawed_back: 0,
    funded: 2500,
    available: 2500,
    remaining: 7500,
    progress_pct: 25,
    is_achieved: false,
    is_closed: false,
    this_month_allocation: 0,
    months_remaining: null,
    monthly_needed: null,
    history: [],
    ...overrides,
  };
}

async function renderGoals(
  goals: SavingsGoal[],
  pool: Partial<SavingsGoalFreeCash> = {},
) {
  vi.spyOn(savingsGoalsApi, "getAll").mockResolvedValue({
    data: goals,
  } as Awaited<ReturnType<typeof savingsGoalsApi.getAll>>);

  vi.spyOn(savingsGoalsApi, "getFreeCash").mockResolvedValue({
    data: {
      free_cash: 0,
      earmarked: 0,
      liquid: 0,
      clawed_back_this_month: 0,
      has_goals: false,
      ...pool,
    },
  } as Awaited<ReturnType<typeof savingsGoalsApi.getFreeCash>>);

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

/** The row container for a goal, found by walking up from its name. */
function rowFor(name: string): HTMLElement {
  const label = screen.getByText(name);
  return label.closest("div.group") as HTMLElement;
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("GoalsSection", () => {
  describe("waterfall order", () => {
    it("numbers goals by funding position and disables the edge arrows", async () => {
      await renderGoals([
        makeGoal({ id: 1, name: "First", priority: 0 }),
        makeGoal({ id: 2, name: "Second", priority: 1 }),
      ]);

      expect(within(rowFor("First")).getByText("#1")).toBeTruthy();
      expect(within(rowFor("Second")).getByText("#2")).toBeTruthy();

      const topUp = within(rowFor("First")).getByLabelText(/move up/i);
      const bottomDown = within(rowFor("Second")).getByLabelText(/move down/i);
      expect((topUp as HTMLButtonElement).disabled).toBe(true);
      expect((bottomDown as HTMLButtonElement).disabled).toBe(true);

      const topDown = within(rowFor("First")).getByLabelText(/move down/i);
      expect((topDown as HTMLButtonElement).disabled).toBe(false);
    });

    it("swaps a goal with its neighbour and persists the new order", async () => {
      const reorder = vi
        .spyOn(savingsGoalsApi, "reorder")
        .mockResolvedValue({ data: [] } as never);

      await renderGoals([
        makeGoal({ id: 7, name: "First", priority: 0 }),
        makeGoal({ id: 9, name: "Second", priority: 1 }),
      ]);

      fireEvent.click(within(rowFor("Second")).getByLabelText(/move up/i));

      await waitFor(() => expect(reorder).toHaveBeenCalledWith([9, 7]));
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

    it("prefers achieved over the schedule", async () => {
      await renderGoals([
        makeGoal({
          name: "Done",
          is_achieved: true,
          months_remaining: 5,
          monthly_needed: 1500,
        }),
      ]);
      const text = rowFor("Done").textContent ?? "";
      expect(text).toContain("Achieved");
      expect(text).not.toContain("/mo");
    });

    it("prefers closed over achieved", async () => {
      await renderGoals([
        makeGoal({ name: "Spent", is_achieved: true, is_closed: true }),
      ]);
      const text = rowFor("Spent").textContent ?? "";
      expect(text).toContain("Closed");
      expect(text).not.toContain("Achieved");
    });
  });

  describe("SQLite boolean rendering", () => {
    it("never leaks a literal 0 next to the goal name", async () => {
      // SQLite hands booleans back as 0/1 integers; `{0 && <Check/>}` renders
      // the string "0" in JSX, which showed up beside the goal name.
      await renderGoals([
        makeGoal({
          name: "Vacation",
          is_achieved: 0 as unknown as boolean,
          is_closed: 0 as unknown as boolean,
        }),
      ]);

      const header = screen.getByText("Vacation").parentElement as HTMLElement;
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

  describe("ledger detail", () => {
    it("surfaces this month's allocation and what has been used", async () => {
      await renderGoals([
        makeGoal({
          name: "Trip",
          this_month_allocation: 400,
          utilized: 250,
          available: 2250,
        }),
      ]);

      const text = rowFor("Trip").textContent ?? "";
      expect(text).toContain("this month");
      expect(text).toContain("used");
    });

    it("omits the detail line when there is nothing to report", async () => {
      await renderGoals([
        makeGoal({ name: "Quiet", this_month_allocation: 0, utilized: 0 }),
      ]);

      const text = rowFor("Quiet").textContent ?? "";
      expect(text).not.toContain("this month");
      expect(text).not.toContain("used");
    });
  });

  describe("redistribute history", () => {
    /** Open the redistribute modal over a two-goal list. */
    async function openRedistribute(changes: unknown[]) {
      const rebuild = vi.spyOn(savingsGoalsApi, "rebuild").mockResolvedValue({
        data: { from_month: null, dry_run: true, changes, goals: [] },
      } as never);

      await renderGoals([
        makeGoal({ id: 1, name: "First" }),
        makeGoal({ id: 2, name: "Second" }),
      ]);
      fireEvent.click(screen.getByRole("button", { name: /redistribute/i }));
      return rebuild;
    }

    it("previews with a dry run and does not commit on open", async () => {
      // Opening the modal must never write. The dry-run flag is the only thing
      // standing between "show me the diff" and silently restating history.
      const rebuild = await openRedistribute([
        { goal_id: 1, name: "First", before: 500, after: 0, delta: -500 },
      ]);

      await waitFor(() => expect(rebuild).toHaveBeenCalledWith(null, true));
      expect(rebuild).toHaveBeenCalledTimes(1);
    });

    it("renders the before/after diff for every goal that moves", async () => {
      await openRedistribute([
        { goal_id: 1, name: "First", before: 500, after: 0, delta: -500 },
        { goal_id: 2, name: "Second", before: 0, after: 500, delta: 500 },
      ]);

      await screen.findByText(/restates past months/i);
      // Both names also appear in the goal list behind the modal, so scope the
      // assertion to the dialog body.
      const dialog = screen.getByText(/restates past months/i).closest("div")!;
      expect(dialog.textContent).toContain("First");
      expect(dialog.textContent).toContain("Second");
    });

    it("hides goals whose allocation is unchanged", async () => {
      await openRedistribute([
        { goal_id: 1, name: "First", before: 500, after: 0, delta: -500 },
        { goal_id: 2, name: "Second", before: 250, after: 250, delta: 0 },
      ]);

      await screen.findByText("First");
      // "Second" still appears in the goal list behind the modal, so assert on
      // the diff rows themselves rather than on the whole document.
      const dialog = screen.getByText(/restates past months/i).closest("div")!;
      expect(dialog.textContent).not.toContain("Second");
    });

    it("commits with dry_run false once confirmed", async () => {
      const rebuild = await openRedistribute([
        { goal_id: 1, name: "First", before: 500, after: 0, delta: -500 },
      ]);
      await screen.findByText("First");

      const confirm = screen
        .getAllByRole("button", { name: /^redistribute$/i })
        .at(-1)!;
      fireEvent.click(confirm);

      await waitFor(() => expect(rebuild).toHaveBeenCalledWith(null, false));
    });
  });

  describe("free-cash pool", () => {
    it("shows the unearmarked pool under the waterfall", async () => {
      await renderGoals([makeGoal({ name: "Vacation" })], {
        free_cash: 4200,
        earmarked: 2500,
        liquid: 6700,
        has_goals: true,
      });

      expect(await screen.findByText(/free cash/i)).toBeInTheDocument();
      expect(screen.getByText(/4,200/)).toBeInTheDocument();
    });

    it("stays hidden while the user keeps no goals", async () => {
      await renderGoals([makeGoal({ name: "Vacation" })], { has_goals: false });

      expect(screen.queryByText(/free cash/i)).not.toBeInTheDocument();
    });

    it("flags money a deficit pulled back out of a goal", async () => {
      await renderGoals([makeGoal({ name: "Vacation", clawed_back: 800 })], {
        has_goals: true,
      });

      expect(
        within(rowFor("Vacation")).getByText(/taken back/i),
      ).toBeInTheDocument();
    });
  });
});
