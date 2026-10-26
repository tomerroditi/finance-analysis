import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RulesSection } from "./RulesSection";
import { taggingApi, testingApi, type TaggingRule } from "../../services/api";
import { DemoModeProvider } from "../../context/DemoModeContext";

/**
 * Deleting a tagging rule untags nothing, so the rule list is all it
 * changes: the row goes on click and comes back if the server refuses.
 */

vi.mock("../../context/DialogContext", () => ({
  useConfirm: () => async () => true,
  useNotify: () => ({ error: vi.fn(), info: vi.fn() }),
}));

const rule = (id: number, name: string): TaggingRule => ({
  id,
  name,
  category: "Food",
  tag: "Groceries",
  conditions: { type: "AND", subconditions: [] } as unknown as TaggingRule["conditions"],
});

async function openManager() {
  vi.spyOn(taggingApi, "getRules").mockResolvedValue({
    data: [rule(1, "Supermarket"), rule(2, "Bakery")],
  } as Awaited<ReturnType<typeof taggingApi.getRules>>);
  vi.spyOn(testingApi, "getDemoModeStatus").mockResolvedValue({
    data: { demo_mode: false, forced: false },
  } as Awaited<ReturnType<typeof testingApi.getDemoModeStatus>>);
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <DemoModeProvider>
        <RulesSection />
      </DemoModeProvider>
    </QueryClientProvider>,
  );
  fireEvent.click(await screen.findByText("2 rules"));
  await screen.findByText("Bakery");
}

describe("RulesSection delete", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("drops the rule before the server answers", async () => {
    vi.spyOn(taggingApi, "deleteRule").mockReturnValue(new Promise(() => {}));
    await openManager();

    fireEvent.click(screen.getAllByTitle("Delete")[0]);

    await waitFor(() => expect(screen.queryByText("Bakery")).toBeNull());
    expect(screen.getByText("Supermarket")).toBeInTheDocument();
  });

  it("puts the rule back when the delete fails", async () => {
    vi.spyOn(taggingApi, "deleteRule").mockRejectedValue(new Error("boom"));
    await openManager();

    fireEvent.click(screen.getAllByTitle("Delete")[0]);

    await waitFor(() => expect(taggingApi.deleteRule).toHaveBeenCalledWith(2));
    expect(await screen.findByText("Bakery")).toBeInTheDocument();
  });
});
