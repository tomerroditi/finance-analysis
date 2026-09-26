import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../../test-utils";
import { ProjectGoalLink } from "./ProjectGoalLink";
import { savingsGoalsApi, type SavingsGoal } from "../../services/api";
import type * as ApiModule from "../../services/api";

/**
 * The project tab's savings-goal action links a whole project to one goal in a
 * single write, instead of one transaction at a time.
 */
vi.mock("../../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof ApiModule>();
  return {
    ...actual,
    savingsGoalsApi: {
      ...actual.savingsGoalsApi,
      getAll: vi.fn(),
      setFundingProject: vi.fn(),
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
    funding_project: null,
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

describe("ProjectGoalLink", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(savingsGoalsApi.setFundingProject).mockResolvedValue({
      data: [],
    } as unknown as Awaited<ReturnType<typeof savingsGoalsApi.setFundingProject>>);
  });

  it("renders nothing when the user keeps no goals", async () => {
    mockGoals([]);
    const { container } = renderWithProviders(<ProjectGoalLink project="Wedding" />);
    await waitFor(() => expect(savingsGoalsApi.getAll).toHaveBeenCalled());
    expect(container.querySelector("[data-testid='project-goal-link']")).toBeNull();
  });

  it("links the whole project to the picked goal in one call", async () => {
    mockGoals([makeGoal(), makeGoal({ id: 2, name: "Car" })]);
    renderWithProviders(<ProjectGoalLink project="Wedding" />);

    fireEvent.click(await screen.findByTestId("project-goal-link"));
    fireEvent.click(await screen.findByText("Car"));

    await waitFor(() =>
      expect(savingsGoalsApi.setFundingProject).toHaveBeenCalledWith(2, "Wedding"),
    );
    expect(savingsGoalsApi.setFundingProject).toHaveBeenCalledTimes(1);
  });

  it("names the funding goal and can detach it", async () => {
    mockGoals([makeGoal({ funding_project: "Wedding" })]);
    renderWithProviders(<ProjectGoalLink project="Wedding" />);

    const button = await screen.findByTestId("project-goal-link");
    expect(button.textContent).toContain("Wedding fund");

    fireEvent.click(button);
    fireEvent.click(await screen.findByText("Remove link"));

    await waitFor(() =>
      expect(savingsGoalsApi.setFundingProject).toHaveBeenCalledWith(1, null),
    );
  });
});
