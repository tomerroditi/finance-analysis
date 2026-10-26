import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GoalLinkAction } from "./GoalLinkAction";
import { savingsGoalsApi, testingApi, type SavingsGoal } from "../../services/api";
import { DemoModeProvider } from "../../context/DemoModeContext";
import { makeQueryKeys } from "../../services/queryKeys";
import type { Transaction } from "../../types/transaction";

/**
 * Only incoming money can be saved into a goal: setting money aside is the
 * goal's own "Add money", so the backend refuses a contribution link on
 * spending and the action never offers one.
 *
 * The goal list is the full computed savings-goals read, so a row fetches
 * it only once its popover opens — a table of rows used to fetch it up
 * front, and again after every retag.
 */

const goal = { id: 1, name: "Trip", is_closed: false } as SavingsGoal;

function mount(amount: number, cachedGoals?: SavingsGoal[]) {
  vi.spyOn(savingsGoalsApi, "getAll").mockResolvedValue({
    data: [goal],
  } as Awaited<ReturnType<typeof savingsGoalsApi.getAll>>);
  vi.spyOn(savingsGoalsApi, "getLinks").mockResolvedValue({
    data: [],
  } as unknown as Awaited<ReturnType<typeof savingsGoalsApi.getLinks>>);
  vi.spyOn(testingApi, "getDemoModeStatus").mockResolvedValue({
    data: { demo_mode: false, forced: false },
  } as Awaited<ReturnType<typeof testingApi.getDemoModeStatus>>);

  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  if (cachedGoals) client.setQueryData(makeQueryKeys(false).savingsGoals.all(), cachedGoals);
  const transaction = {
    unique_id: "7",
    source: "bank_transactions",
    amount,
    date: "2026-09-01",
  } as Transaction;
  return render(
    <QueryClientProvider client={client}>
      <DemoModeProvider>
        <GoalLinkAction transaction={transaction} />
      </DemoModeProvider>
    </QueryClientProvider>,
  );
}

async function renderAction(amount: number) {
  mount(amount);
  fireEvent.click(await screen.findByRole("button", { name: /link to a savings goal/i }));
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("GoalLinkAction", () => {
  it("offers spending only to be paid from a goal", async () => {
    await renderAction(-250);

    expect(await screen.findByRole("button", { name: "Paid from" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Saved into" })).not.toBeInTheDocument();
  });

  it("offers incoming money both roles", async () => {
    await renderAction(1200);

    expect(await screen.findByRole("button", { name: "Saved into" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Paid from" })).toBeInTheDocument();
  });

  it("fetches the goals only once the popover opens", async () => {
    mount(-250);
    const button = await screen.findByRole("button", { name: /link to a savings goal/i });
    await waitFor(() => expect(savingsGoalsApi.getLinks).toHaveBeenCalled());
    expect(savingsGoalsApi.getAll).not.toHaveBeenCalled();

    fireEvent.click(button);

    await waitFor(() => expect(savingsGoalsApi.getAll).toHaveBeenCalledTimes(1));
  });

  it("hides itself when the cached goal list holds no open goal", async () => {
    mount(-250, [{ ...goal, is_closed: true }]);
    await waitFor(() => expect(savingsGoalsApi.getLinks).toHaveBeenCalled());

    expect(screen.queryByRole("button", { name: /link to a savings goal/i })).toBeNull();
    expect(savingsGoalsApi.getAll).not.toHaveBeenCalled();
  });

  it("says so when the goals it fetched on open hold no open goal", async () => {
    mount(-250);
    vi.mocked(savingsGoalsApi.getAll).mockResolvedValue({
      data: [],
    } as unknown as Awaited<ReturnType<typeof savingsGoalsApi.getAll>>);
    fireEvent.click(await screen.findByRole("button", { name: /link to a savings goal/i }));

    expect(await screen.findByTestId("goal-link-no-goals")).toBeInTheDocument();
  });
});
