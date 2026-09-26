import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GoalsSection } from "./GoalsSection";
import {
  savingsGoalsApi,
  taggingApi,
  testingApi,
  type SavingsGoal,
  type SavingsGoalFreeCash,
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
    utilization_category: null,
    utilization_tags: null,
    kind: "cash",
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

  // The history panel fetches as soon as it is expanded, so the timeline is
  // stubbed here rather than per test — an unmocked call would hit the network.
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

/** Expand the collapsed-by-default month-by-month panel. */
function expandHistory() {
  fireEvent.click(screen.getByRole("button", { name: /month by month/i }));
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

  describe("reordering", () => {
    /** A promise the test settles by hand, standing in for a slow rebuild. */
    function deferred<T>() {
      let resolve!: (value: T) => void;
      const promise = new Promise<T>((r) => {
        resolve = r;
      });
      return { promise, resolve };
    }

    /** The goal names in the order the waterfall currently shows them. */
    function shownOrder(): string[] {
      return within(screen.getByTestId("goals-list"))
        .getAllByText(/^(First|Second|Third)$/)
        .map((el) => el.textContent ?? "");
    }

    /** What the server holds once a rebuild has committed. */
    function serverNowHolds(goals: SavingsGoal[]) {
      vi.mocked(savingsGoalsApi.getAll).mockResolvedValue({
        data: goals,
      } as Awaited<ReturnType<typeof savingsGoalsApi.getAll>>);
    }

    const first = makeGoal({ id: 1, name: "First", priority: 0 });
    const second = makeGoal({ id: 2, name: "Second", priority: 1 });
    const third = makeGoal({ id: 3, name: "Third", priority: 2 });

    it("offers no manual redistribute — reordering restates history itself", async () => {
      await renderGoals([first, second]);

      expect(screen.queryByRole("button", { name: /redistribute/i })).not.toBeInTheDocument();
    });

    it("moves the row at once and shows recalculating until the server answers", async () => {
      const pending = deferred<Awaited<ReturnType<typeof savingsGoalsApi.reorder>>>();
      const reorder = vi.spyOn(savingsGoalsApi, "reorder").mockReturnValue(pending.promise);
      await renderGoals([first, second]);

      fireEvent.click(
        within(rowFor("First")).getByRole("button", { name: /move down/i }),
      );

      // The order is the user's answer, not the server's: it lands before
      // the rebuild does.
      await waitFor(() => expect(shownOrder()).toEqual(["Second", "First"]));
      expect(await screen.findByRole("status")).toHaveTextContent(/recalculating/i);
      expect(
        within(rowFor("First")).getByTestId("goal-figures"),
      ).toHaveAttribute("aria-busy", "true");
      expect(reorder).toHaveBeenCalledWith([2, 1]);

      const rebuilt = [
        { ...second, priority: 0, funded: 4000 },
        { ...first, priority: 1, funded: 0 },
      ];
      serverNowHolds(rebuilt);
      pending.resolve({ data: rebuilt } as Awaited<ReturnType<typeof savingsGoalsApi.reorder>>);

      await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
      expect(shownOrder()).toEqual(["Second", "First"]);
    });

    it("queues rapid moves and keeps the latest order when an older answer lands", async () => {
      const calls: Array<ReturnType<typeof deferred<Awaited<ReturnType<typeof savingsGoalsApi.reorder>>>>> = [];
      const reorder = vi.spyOn(savingsGoalsApi, "reorder").mockImplementation(() => {
        const next = deferred<Awaited<ReturnType<typeof savingsGoalsApi.reorder>>>();
        calls.push(next);
        return next.promise;
      });
      await renderGoals([first, second, third]);

      fireEvent.click(within(rowFor("First")).getByRole("button", { name: /move down/i }));
      await waitFor(() => expect(shownOrder()).toEqual(["Second", "First", "Third"]));
      fireEvent.click(within(rowFor("First")).getByRole("button", { name: /move down/i }));

      // Both clicks already show; the second built on the first.
      await waitFor(() => expect(shownOrder()).toEqual(["Second", "Third", "First"]));
      // The server calls run one at a time, oldest first.
      await waitFor(() => expect(reorder).toHaveBeenCalledTimes(1));
      expect(reorder).toHaveBeenLastCalledWith([2, 1, 3]);

      calls[0].resolve({
        data: [second, first, third],
      } as Awaited<ReturnType<typeof savingsGoalsApi.reorder>>);

      await waitFor(() => expect(reorder).toHaveBeenCalledTimes(2));
      expect(reorder).toHaveBeenLastCalledWith([2, 3, 1]);
      // The first answer is for an order already left behind; it must not
      // snap the list back.
      expect(shownOrder()).toEqual(["Second", "Third", "First"]);

      serverNowHolds([second, third, first]);
      calls[1].resolve({
        data: [second, third, first],
      } as Awaited<ReturnType<typeof savingsGoalsApi.reorder>>);
      await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
      expect(shownOrder()).toEqual(["Second", "Third", "First"]);
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

    it("does not tally a goal's lifetime clawbacks on its row", async () => {
      await renderGoals([makeGoal({ name: "Vacation", clawed_back: 800 })], {
        has_goals: true,
      });

      expect(within(rowFor("Vacation")).queryByText(/800/)).not.toBeInTheDocument();
    });
  });

  describe("card height", () => {
    /**
     * jsdom lays nothing out, so every height it reports is 0. Stand in a
     * content height for the one measurement the cap is decided on.
     */
    function withContentHeight(height: number) {
      const original = Object.getOwnPropertyDescriptor(
        HTMLElement.prototype,
        "scrollHeight",
      );
      Object.defineProperty(HTMLElement.prototype, "scrollHeight", {
        configurable: true,
        get: () => height,
      });
      return () => {
        if (original) {
          Object.defineProperty(HTMLElement.prototype, "scrollHeight", original);
        }
      };
    }

    const manyGoals = [
      makeGoal({ id: 1, name: "One", priority: 0 }),
      makeGoal({ id: 2, name: "Two", priority: 1 }),
      makeGoal({ id: 3, name: "Three", priority: 2 }),
      makeGoal({ id: 4, name: "Four", priority: 3 }),
    ];

    it("scrolls the waterfall in place once a cap would hide a row", async () => {
      // Taller than the 26rem cap by more than a row, so capping it reaches
      // something: the card keeps its free-cash row and history panel instead
      // of carrying them down the page.
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
      // 26rem is 416px, so this overflows by 20 — nothing worth reaching, and
      // a scroll region here would swallow the drag that was meant to scroll
      // the page on a phone.
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

    it("stays collapsed until asked, and fetches nothing until it is", async () => {
      await renderGoals([makeGoal({ id: 4, name: "Trip" })], {}, timelineWith(4, "Trip"));

      // The standings are what the card is opened for; the ledger behind them
      // is a second question, so it costs neither screen nor a request until
      // someone asks it.
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

      await waitFor(() =>
        expect(savingsGoalsApi.getTimeline).toHaveBeenCalledWith(12),
      );
      expect(await screen.findByTestId("goals-history-chart")).toBeInTheDocument();
    });

    it("refetches the window when another range is picked", async () => {
      await renderGoals([makeGoal({ id: 4, name: "Trip" })], {}, timelineWith(4, "Trip"));
      expandHistory();
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
      expandHistory();
      await screen.findByTestId("goals-history-chart");

      expect(
        (screen.getByRole("button", { name: /^all$/i }) as HTMLButtonElement)
          .disabled,
      ).toBe(true);
    });

    it("enables all-time once the ledger outgrows the fixed windows", async () => {
      await renderGoals([makeGoal({ id: 4, name: "Trip" })], {}, timelineWith(4, "Trip", 18));
      expandHistory();
      await screen.findByTestId("goals-history-chart");

      fireEvent.click(screen.getByRole("button", { name: /^all$/i }));

      // Zero is how the client asks for the whole timeline.
      await waitFor(() =>
        expect(savingsGoalsApi.getTimeline).toHaveBeenCalledWith(0),
      );
    });

    it("says so plainly when nothing has been allocated yet", async () => {
      await renderGoals([makeGoal({ name: "New" })]);
      expandHistory();

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

  describe("goal editor", () => {
    it("picks the start on the same calendar as the target date, keeping the month", async () => {
      vi.spyOn(taggingApi, "getCategories").mockResolvedValue({
        data: {},
      } as Awaited<ReturnType<typeof taggingApi.getCategories>>);
      vi.spyOn(savingsGoalsApi, "getFreeCashBefore").mockResolvedValue({
        data: { month: "2025-01", free_cash: 0 },
      } as Awaited<ReturnType<typeof savingsGoalsApi.getFreeCashBefore>>);
      const update = vi.spyOn(savingsGoalsApi, "update").mockResolvedValue({
        data: [] as SavingsGoal[],
      } as Awaited<ReturnType<typeof savingsGoalsApi.update>>);
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
  });

  describe("investment goals", () => {
    const invest = (overrides: Partial<SavingsGoal> = {}) =>
      makeGoal({
        name: "Pakam",
        kind: "investment",
        contribution_category: "Investments",
        contribution_tags: "Pakam",
        ...overrides,
      });

    it("marks the row and drops the cash-goal actions", async () => {
      await renderGoals([invest()]);

      const row = rowFor("Pakam");
      expect(within(row).getByLabelText("Invest")).toBeInTheDocument();
      expect(
        within(row).queryByRole("button", { name: /free cash/i }),
      ).not.toBeInTheDocument();
    });

    it("names this month's net transfers as invested or withdrawn", async () => {
      await renderGoals([
        invest({ this_month_allocation: 75000 }),
        invest({ id: 2, name: "Bonds", this_month_allocation: -12000 }),
      ]);

      expect(within(rowFor("Pakam")).getByText(/invested this month/i).textContent).toMatch(
        /75,000/,
      );
      expect(within(rowFor("Bonds")).getByText(/withdrawn this month/i).textContent).toMatch(
        /12,000/,
      );
    });

    it("still keeps a cash goal's clawback month off the row", async () => {
      await renderGoals([makeGoal({ name: "Trip", this_month_allocation: -800 })]);

      expect(within(rowFor("Trip")).queryByText(/this month/i)).not.toBeInTheDocument();
    });

    it("creates one from the editor with only the settings it uses", async () => {
      vi.spyOn(taggingApi, "getCategories").mockResolvedValue({
        data: { Investments: ["Pakam", "Stocks"], Food: ["Groceries"] },
      } as Awaited<ReturnType<typeof taggingApi.getCategories>>);
      vi.spyOn(savingsGoalsApi, "getFreeCashBefore").mockResolvedValue({
        data: { month: "2026-09", free_cash: 0 },
      } as Awaited<ReturnType<typeof savingsGoalsApi.getFreeCashBefore>>);
      const create = vi.spyOn(savingsGoalsApi, "create").mockResolvedValue({
        data: [] as SavingsGoal[],
      } as Awaited<ReturnType<typeof savingsGoalsApi.create>>);
      await renderGoals([makeGoal({ name: "Trip" })]);

      fireEvent.click(screen.getByRole("button", { name: /add goal/i }));
      fireEvent.click(await screen.findByRole("radio", { name: /invest/i }));

      // The cash-goal settings have nothing to act on.
      expect(screen.queryByLabelText(/monthly cap/i)).not.toBeInTheDocument();
      expect(screen.queryByLabelText(/already saved/i)).not.toBeInTheDocument();
      expect(screen.queryByTestId("goal-auto-link-spend")).not.toBeInTheDocument();

      fireEvent.change(screen.getByLabelText(/name/i), { target: { value: "Pakam" } });
      fireEvent.change(screen.getByLabelText(/target amount/i), { target: { value: "120000" } });
      const save = screen.getByRole("button", { name: /^save$/i });
      // Without the transfers it counts, the goal could never move.
      expect(save).toBeDisabled();

      const rule = screen.getByTestId("goal-invest-rule");
      fireEvent.click(within(rule).getAllByRole("button")[0]);
      fireEvent.click(await screen.findByRole("option", { name: "Investments" }));
      fireEvent.click(save);

      await waitFor(() => expect(create).toHaveBeenCalled());
      const payload = create.mock.calls[0][0];
      expect(payload).toMatchObject({
        kind: "investment",
        name: "Pakam",
        target_amount: 120000,
        contribution_category: "Investments",
      });
      expect(payload).not.toHaveProperty("monthly_cap");
      expect(payload).not.toHaveProperty("opening_balance");
      expect(payload).not.toHaveProperty("utilization_category");
    });
  });
});
