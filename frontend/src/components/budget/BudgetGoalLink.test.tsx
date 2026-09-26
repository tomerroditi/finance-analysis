import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../../test-utils";
import { BudgetGoalLink } from "./BudgetGoalLink";
import { joinRuleTags, splitRuleTags } from "../../utils/goalRuleTags";
import { savingsGoalsApi, type SavingsGoal } from "../../services/api";
import type * as ApiModule from "../../services/api";

/**
 * The budget's savings-goal action links a whole project or yearly envelope
 * to one goal in a single write, instead of one transaction at a time.
 */
vi.mock("../../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof ApiModule>();
  return {
    ...actual,
    savingsGoalsApi: {
      ...actual.savingsGoalsApi,
      getAll: vi.fn(),
      setSpendingLink: vi.fn(),
    },
  };
});

function makeGoal(overrides: Partial<SavingsGoal> = {}): SavingsGoal {
  return {
    id: 1,
    name: "Wedding fund",
    target_amount: 50000,
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
    allocated: 0,
    contributed: 0,
    utilized: 0,
    clawed_back: 0,
    investment_backed: 0,
    funded: 0,
    available: 0,
    remaining: 50000,
    progress_pct: 0,
    is_achieved: false,
    is_closed: false,
    this_month_allocation: 0,
    months_remaining: null,
    monthly_needed: null,
    history: [],
    ...overrides,
  };
}

function mockGoals(goals: SavingsGoal[]) {
  vi.mocked(savingsGoalsApi.getAll).mockResolvedValue({
    data: goals,
  } as Awaited<ReturnType<typeof savingsGoalsApi.getAll>>);
}

describe("BudgetGoalLink", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(savingsGoalsApi.setSpendingLink).mockResolvedValue({
      data: [],
    } as unknown as Awaited<ReturnType<typeof savingsGoalsApi.setSpendingLink>>);
  });

  it("renders nothing when the user keeps no goals", async () => {
    mockGoals([]);
    const { container } = renderWithProviders(<BudgetGoalLink category="Wedding" name="Wedding" />);
    await waitFor(() => expect(savingsGoalsApi.getAll).toHaveBeenCalled());
    expect(container.querySelector("[data-testid='budget-goal-link']")).toBeNull();
  });

  it("links the whole project to the picked goal in one call", async () => {
    mockGoals([makeGoal(), makeGoal({ id: 2, name: "Car" })]);
    renderWithProviders(<BudgetGoalLink category="Wedding" name="Wedding" />);

    fireEvent.click(await screen.findByTestId("budget-goal-link"));
    fireEvent.click(await screen.findByText("Car"));

    await waitFor(() =>
      expect(savingsGoalsApi.setSpendingLink).toHaveBeenCalledWith(2, "Wedding", null),
    );
    expect(savingsGoalsApi.setSpendingLink).toHaveBeenCalledTimes(1);
  });

  it("names the funding goal and can detach it", async () => {
    mockGoals([makeGoal({ utilization_category: "Wedding" })]);
    renderWithProviders(<BudgetGoalLink category="Wedding" name="Wedding" />);

    const button = await screen.findByTestId("budget-goal-link");
    expect(button.textContent).toContain("Wedding fund");

    fireEvent.click(button);
    fireEvent.click(await screen.findByText("Remove link"));

    await waitFor(() =>
      expect(savingsGoalsApi.setSpendingLink).toHaveBeenCalledWith(1, null),
    );
  });

  it("links a yearly envelope with its category and tags", async () => {
    mockGoals([makeGoal()]);
    renderWithProviders(
      <BudgetGoalLink
        category="Leisure"
        tags={["Vacation", "Flights"]}
        name="Summer trip"
        variant="icon"
      />,
    );

    fireEvent.click(await screen.findByTestId("budget-goal-link"));
    fireEvent.click(await screen.findByText("Wedding fund"));

    await waitFor(() =>
      expect(savingsGoalsApi.setSpendingLink).toHaveBeenCalledWith(1, "Leisure", [
        "Vacation",
        "Flights",
      ]),
    );
  });

  it("recognises the goal already paying for the envelope", async () => {
    mockGoals([
      makeGoal({ utilization_category: "Leisure", utilization_tags: "Flights;Vacation" }),
    ]);
    renderWithProviders(
      <BudgetGoalLink category="Leisure" tags={["Vacation", "Flights"]} name="Trip" />,
    );
    expect((await screen.findByTestId("budget-goal-link")).textContent).toContain(
      "Wedding fund",
    );
  });

  it("stores tags like the backend: sorted, all_tags as the whole category", () => {
    expect(joinRuleTags(["b", "a"])).toBe("a;b");
    expect(joinRuleTags(["all_tags"])).toBeNull();
    expect(joinRuleTags([])).toBeNull();
    expect(splitRuleTags("a;b")).toEqual(["a", "b"]);
    expect(splitRuleTags(null)).toEqual([]);
  });
});
