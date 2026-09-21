import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GoalsSection } from "./GoalsSection";
import {
  savingsGoalsApi,
  testingApi,
  type SavingsGoal,
  type SavingsGoalFreeCash,
  type SavingsGoalInvestment,
  type SavingsGoalTimeline,
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

const { notifyInfo } = vi.hoisted(() => ({ notifyInfo: vi.fn() }));

vi.mock("../../context/DialogContext", () => ({
  useConfirm: () => async () => true,
  useNotify: () => ({ info: notifyInfo }),
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
    investment_backed: 0,
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
  timeline: Partial<SavingsGoalTimeline> = {},
  /**
   * How long a fetched query counts as fresh, mirroring `queryClient.ts`.
   * Defaults to React Query's own 0 — pass the app's real value to exercise
   * code that reads through the cache while an entry is still fresh.
   */
  staleTime = 0,
) {
  vi.spyOn(savingsGoalsApi, "getAll").mockResolvedValue({
    data: goals,
  } as Awaited<ReturnType<typeof savingsGoalsApi.getAll>>);

  // Every render draws the history panel, so the timeline is stubbed here
  // rather than per test — an unmocked call would hit the network.
  if (!vi.isMockFunction(savingsGoalsApi.getTimeline)) {
    vi.spyOn(savingsGoalsApi, "getTimeline").mockResolvedValue({
      data: {
        has_goals: true,
        total_months: 0,
        months: [],
        goals: [],
        ...timeline,
      },
    } as Awaited<ReturnType<typeof savingsGoalsApi.getTimeline>>);
  }

  vi.spyOn(savingsGoalsApi, "getFreeCash").mockResolvedValue({
    data: {
      free_cash: 0,
      earmarked: 0,
      liquid: 0,
      investment_backed: 0,
      clawed_back_this_month: 0,
      has_goals: false,
      ...pool,
    },
  } as Awaited<ReturnType<typeof savingsGoalsApi.getFreeCash>>);

  vi.spyOn(testingApi, "getDemoModeStatus").mockResolvedValue({
    data: { demo_mode: false, forced: false },
  } as Awaited<ReturnType<typeof testingApi.getDemoModeStatus>>);

  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime } },
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
  notifyInfo.mockClear();
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

  describe("month-by-month history", () => {
    /** A timeline whose single month funded `goalId`. */
    function timelineWith(goalId: number, name: string, totalMonths = 3) {
      return {
        has_goals: true,
        total_months: totalMonths,
        months: [
          {
            month: "2026-08",
            goals: [
              { goal_id: goalId, name, allocated: 900, contributed: 0, total: 900 },
            ],
            allocated: 900,
            clawed_back: 0,
            surplus: 1500,
            free_cash: 600,
            is_provisional: false,
          },
        ],
        goals: [
          { id: goalId, name, priority: 0, status: "active", is_closed: false },
        ],
      };
    }

    it("asks for the last 12 months by default", async () => {
      await renderGoals([makeGoal({ id: 4, name: "Trip" })], {}, timelineWith(4, "Trip"));

      await waitFor(() =>
        expect(savingsGoalsApi.getTimeline).toHaveBeenCalledWith(12),
      );
      expect(await screen.findByTestId("goals-history-chart")).toBeInTheDocument();
      // The pool gets its own panel: a monthly flow and a standing balance
      // must not share one scale.
      expect(screen.getByText(/free cash left at month end/i)).toBeInTheDocument();
    });

    it("refetches the window when another range is picked", async () => {
      await renderGoals([makeGoal({ id: 4, name: "Trip" })], {}, timelineWith(4, "Trip"));
      await screen.findByTestId("goals-history-chart");

      fireEvent.click(screen.getByRole("button", { name: "6M" }));

      await waitFor(() =>
        expect(savingsGoalsApi.getTimeline).toHaveBeenCalledWith(6),
      );
    });

    it("offers all-time only once there is more history than the widest window", async () => {
      // "All" over a 3-month history would show the same months as "12M",
      // so it stays disabled until the ledger outgrows the fixed windows.
      await renderGoals([makeGoal({ id: 4, name: "Trip" })], {}, timelineWith(4, "Trip", 3));
      await screen.findByTestId("goals-history-chart");

      expect(
        (screen.getByRole("button", { name: /^all$/i }) as HTMLButtonElement)
          .disabled,
      ).toBe(true);
    });

    it("enables all-time once the ledger outgrows the fixed windows", async () => {
      await renderGoals([makeGoal({ id: 4, name: "Trip" })], {}, timelineWith(4, "Trip", 18));
      await screen.findByTestId("goals-history-chart");

      fireEvent.click(screen.getByRole("button", { name: /^all$/i }));

      // Zero is how the client asks for the whole timeline.
      await waitFor(() =>
        expect(savingsGoalsApi.getTimeline).toHaveBeenCalledWith(0),
      );
    });

    it("says so plainly when nothing has been allocated yet", async () => {
      await renderGoals([makeGoal({ name: "New" })]);

      expect(
        await screen.findByText(/nothing allocated yet/i),
      ).toBeInTheDocument();
      expect(screen.queryByTestId("goals-history-chart")).not.toBeInTheDocument();
    });
  });

  describe("earmarking earlier free cash from the row", () => {
    function stubFreeCashBefore(freeCash: number) {
      return vi.spyOn(savingsGoalsApi, "getFreeCashBefore").mockResolvedValue({
        data: { month: "2026-01", free_cash: freeCash },
      } as Awaited<ReturnType<typeof savingsGoalsApi.getFreeCashBefore>>);
    }

    it("sets the opening balance and restates from the goal's start", async () => {
      await renderGoals([makeGoal({ name: "Vacation", start_month: "2026-01" })]);
      stubFreeCashBefore(24000);
      const update = vi
        .spyOn(savingsGoalsApi, "update")
        .mockResolvedValue({ data: [] } as unknown as Awaited<
          ReturnType<typeof savingsGoalsApi.update>
        >);
      const rebuild = vi
        .spyOn(savingsGoalsApi, "rebuild")
        .mockResolvedValue({ data: {} } as unknown as Awaited<
          ReturnType<typeof savingsGoalsApi.rebuild>
        >);

      fireEvent.click(
        within(rowFor("Vacation")).getByRole("button", {
          name: /earmark the free cash from before/i,
        }),
      );

      await waitFor(() =>
        expect(update).toHaveBeenCalledWith(1, { opening_balance: 24000 }),
      );
      await waitFor(() => expect(rebuild).toHaveBeenCalledWith("2026-01", false));
    });

    it("says so and writes nothing when the goal already holds it", async () => {
      await renderGoals([makeGoal({ name: "Vacation", opening_balance: 24000 })]);
      stubFreeCashBefore(24000);
      const update = vi.spyOn(savingsGoalsApi, "update");

      fireEvent.click(
        within(rowFor("Vacation")).getByRole("button", {
          name: /earmark the free cash from before/i,
        }),
      );

      await waitFor(() => expect(notifyInfo).toHaveBeenCalled());
      expect(update).not.toHaveBeenCalled();
    });

    it("re-reads the server before deciding there is nothing left to claim", async () => {
      // The app keeps a query fresh for five minutes, and `fetchQuery` serves
      // a fresh entry straight from cache. A claim that has reached the server
      // but whose mutation has not yet settled into an invalidation therefore
      // leaves the cached list holding the *old* opening balance. Deciding
      // against that copy re-offered a claim that had already been applied.
      await renderGoals(
        [makeGoal({ name: "Vacation", opening_balance: 0 })],
        {},
        {},
        5 * 60 * 1000,
      );
      stubFreeCashBefore(24000);
      const update = vi.spyOn(savingsGoalsApi, "update");
      // The server now holds the claim; only a re-read can see it.
      vi.spyOn(savingsGoalsApi, "getAll").mockResolvedValue({
        data: [makeGoal({ name: "Vacation", opening_balance: 24000 })],
      } as Awaited<ReturnType<typeof savingsGoalsApi.getAll>>);

      fireEvent.click(
        within(rowFor("Vacation")).getByRole("button", {
          name: /earmark the free cash from before/i,
        }),
      );

      await waitFor(() => expect(notifyInfo).toHaveBeenCalled());
      expect(update).not.toHaveBeenCalled();
    });

    it("is not offered on a closed goal", async () => {
      await renderGoals([makeGoal({ name: "Vacation", status: "closed", is_closed: true })]);

      expect(
        within(rowFor("Vacation")).queryByRole("button", {
          name: /earmark the free cash from before/i,
        }),
      ).not.toBeInTheDocument();
    });
  });

  describe("investment backing", () => {
    it("shows how much of a goal is backed by holdings", async () => {
      await renderGoals([
        makeGoal({ name: "Car", investment_backed: 40000, funded: 40000 }),
      ]);

      // The amount also appears as the goal's funded total, so assert on the
      // backing line itself rather than on a bare number in the row.
      expect(
        within(rowFor("Car")).getByText(/backed by investments/i).textContent,
      ).toMatch(/40,000/);
    });

    it("stays quiet on a goal backed only by cash", async () => {
      await renderGoals([makeGoal({ name: "Vacation" })]);

      expect(
        within(rowFor("Vacation")).queryByText(/backed by investments/i),
      ).not.toBeInTheDocument();
    });

    it("opens the earmark modal from the goal row", async () => {
      vi.spyOn(savingsGoalsApi, "getInvestments").mockResolvedValue({
        data: [] as SavingsGoalInvestment[],
      } as Awaited<ReturnType<typeof savingsGoalsApi.getInvestments>>);
      vi.spyOn(savingsGoalsApi, "getAvailableInvestments").mockResolvedValue({
        data: [
          {
            id: 7,
            name: "Govt Bonds",
            type: "bonds",
            value: 40000,
            earmarked: 0,
            available: 40000,
            fully_claimed: false,
          },
        ],
      } as Awaited<ReturnType<typeof savingsGoalsApi.getAvailableInvestments>>);

      await renderGoals([makeGoal({ name: "Car" })]);
      fireEvent.click(
        within(rowFor("Car")).getByRole("button", {
          name: /back with investments/i,
        }),
      );

      // The picker offers the holding with the headroom it still has.
      expect(await screen.findByText(/Govt Bonds/)).toBeInTheDocument();
    });

    it("earmarks the whole holding when no amount is given", async () => {
      const link = vi
        .spyOn(savingsGoalsApi, "linkInvestment")
        .mockResolvedValue({ data: [] as SavingsGoal[] } as Awaited<
          ReturnType<typeof savingsGoalsApi.linkInvestment>
        >);
      vi.spyOn(savingsGoalsApi, "getInvestments").mockResolvedValue({
        data: [] as SavingsGoalInvestment[],
      } as Awaited<ReturnType<typeof savingsGoalsApi.getInvestments>>);
      vi.spyOn(savingsGoalsApi, "getAvailableInvestments").mockResolvedValue({
        data: [
          {
            id: 7,
            name: "Govt Bonds",
            type: "bonds",
            value: 40000,
            earmarked: 0,
            available: 40000,
            fully_claimed: false,
          },
        ],
      } as Awaited<ReturnType<typeof savingsGoalsApi.getAvailableInvestments>>);

      await renderGoals([makeGoal({ id: 3, name: "Car" })]);
      fireEvent.click(
        within(rowFor("Car")).getByRole("button", {
          name: /back with investments/i,
        }),
      );
      await screen.findByText(/Govt Bonds/);

      fireEvent.change(screen.getByLabelText(/^investment$/i), {
        target: { value: "7" },
      });
      fireEvent.click(screen.getByRole("button", { name: /earmark investment/i }));

      // A blank amount means "whatever is left of it", sent as null.
      await waitFor(() =>
        expect(link).toHaveBeenCalledWith(3, {
          investment_id: 7,
          amount: null,
        }),
      );
    });
  });
});
