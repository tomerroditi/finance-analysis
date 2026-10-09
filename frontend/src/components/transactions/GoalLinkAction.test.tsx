import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GoalLinkAction } from "./GoalLinkAction";
import { savingsGoalsApi, testingApi, type SavingsGoal } from "../../services/api";
import { DemoModeProvider } from "../../context/DemoModeContext";
import type { Transaction } from "../../types/transaction";

/**
 * Only incoming money can be saved into a goal: setting money aside is the
 * goal's own "Add money", so the backend refuses a contribution link on
 * spending and the action never offers one.
 */

const goal = { id: 1, name: "Trip", is_closed: false } as SavingsGoal;

async function renderAction(amount: number) {
  vi.spyOn(savingsGoalsApi, "getAll").mockResolvedValue({
    data: [goal],
  } as Awaited<ReturnType<typeof savingsGoalsApi.getAll>>);
  vi.spyOn(savingsGoalsApi, "getLinks").mockResolvedValue({
    data: [],
  } as unknown as Awaited<ReturnType<typeof savingsGoalsApi.getLinks>>);
  vi.spyOn(testingApi, "getDemoModeStatus").mockResolvedValue({
    data: { demo_mode: false, forced: false },
  } as Awaited<ReturnType<typeof testingApi.getDemoModeStatus>>);

  const transaction = {
    unique_id: "7",
    source: "bank_transactions",
    amount,
    date: "2026-09-01",
  } as Transaction;
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <DemoModeProvider>
        <GoalLinkAction transaction={transaction} />
      </DemoModeProvider>
    </QueryClientProvider>,
  );
  fireEvent.click(await screen.findByRole("button", { name: /link to a savings goal/i }));
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("GoalLinkAction", () => {
  it("offers spending only to be paid from a goal", async () => {
    await renderAction(-250);

    expect(screen.getByRole("button", { name: "Paid from" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Saved into" })).not.toBeInTheDocument();
  });

  it("offers incoming money both roles", async () => {
    await renderAction(1200);

    expect(screen.getByRole("button", { name: "Saved into" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Paid from" })).toBeInTheDocument();
  });
});
