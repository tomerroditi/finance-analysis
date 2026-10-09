import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { YearlySavingsSection } from "./YearlySavingsSection";
import { savingsGoalsApi, testingApi, type YearlySavings } from "../../services/api";
import { DemoModeProvider } from "../../context/DemoModeContext";

/**
 * The "this year" header of the goals card: what the year saved against its
 * target, the pace toward it, and the inline editor that sets the target.
 */

function yearly(overrides: Partial<YearlySavings> = {}): YearlySavings {
  return {
    current_year: 2026,
    years: [
      {
        year: 2025,
        saved: 41200,
        target: 100000,
        is_current: false,
        months: [{ month: "2025-12", saved: 41200 }],
      },
      {
        year: 2026,
        saved: 84300,
        target: 120000,
        is_current: true,
        months: [
          { month: "2026-01", saved: 20000 },
          { month: "2026-02", saved: -5000 },
        ],
      },
    ],
    pace: { expected_by_today: 92000, ahead_by: -7700, needed_per_month: 11900, months_left: 3 },
    ...overrides,
  };
}

async function renderSection(data: YearlySavings) {
  vi.spyOn(savingsGoalsApi, "getYearly").mockResolvedValue({
    data,
  } as Awaited<ReturnType<typeof savingsGoalsApi.getYearly>>);
  vi.spyOn(testingApi, "getDemoModeStatus").mockResolvedValue({
    data: { demo_mode: false, forced: false },
  } as Awaited<ReturnType<typeof testingApi.getDemoModeStatus>>);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <DemoModeProvider>
        <YearlySavingsSection />
      </DemoModeProvider>
    </QueryClientProvider>,
  );
  return screen.findByTestId("yearly-savings");
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("YearlySavingsSection", () => {
  it("shows this year's savings against its target, and the pace", async () => {
    const section = await renderSection(yearly());

    expect(within(section).getByText(/2026 savings/)).toBeInTheDocument();
    expect(within(section).getByTestId("yearly-saved").textContent).toMatch(/84,300.*120,000/);
    expect(section.textContent).toContain("70%");
    expect(section.textContent).toMatch(/Expected by today.*92,000/);
    expect(section.textContent).toMatch(/7,700.*behind/);
    expect(section.textContent).toMatch(/Need .*11,900.*3 months left/);
    expect(within(section).getByTestId("yearly-past").textContent).toMatch(/2025.*41,200.*100,000/);
  });

  it("shows a year that saved less than nothing in red, with an empty bar", async () => {
    const data = yearly();
    data.years[1] = { ...data.years[1], saved: -4000 };
    const section = await renderSection({
      ...data,
      pace: { expected_by_today: 92000, ahead_by: -96000, needed_per_month: 41333, months_left: 3 },
    });

    const saved = within(section).getByTestId("yearly-saved");
    expect(saved.querySelector(".text-red-400")?.textContent).toMatch(/-4,000/);
    const bar = section.querySelector<HTMLElement>("[style*='width']");
    expect(bar?.style.width).toBe("0%");
  });

  it("offers to set a target when the year has none", async () => {
    const data = yearly({ pace: null });
    data.years[1] = { ...data.years[1], target: null };
    const section = await renderSection(data);

    expect(within(section).getByRole("button", { name: /set target/i })).toBeInTheDocument();
    expect(section.textContent).not.toContain("Expected by today");
  });

  it("saves the target typed into the inline editor", async () => {
    const section = await renderSection(yearly());
    const update = vi.spyOn(savingsGoalsApi, "setYearlyTarget").mockResolvedValue({
      data: yearly(),
    } as Awaited<ReturnType<typeof savingsGoalsApi.setYearlyTarget>>);

    fireEvent.click(within(section).getByRole("button", { name: /edit target/i }));
    const input = within(section).getByLabelText(/savings target for 2026/i);
    fireEvent.change(input, { target: { value: "150000" } });
    fireEvent.click(within(section).getByRole("button", { name: /save/i }));

    await waitFor(() => expect(update).toHaveBeenCalledWith(2026, 150000));
  });

  it("clears the target when the editor is left empty", async () => {
    const section = await renderSection(yearly());
    const update = vi.spyOn(savingsGoalsApi, "setYearlyTarget").mockResolvedValue({
      data: yearly(),
    } as Awaited<ReturnType<typeof savingsGoalsApi.setYearlyTarget>>);

    fireEvent.click(within(section).getByRole("button", { name: /edit target/i }));
    fireEvent.change(within(section).getByLabelText(/savings target for 2026/i), {
      target: { value: "" },
    });
    fireEvent.click(within(section).getByRole("button", { name: /save/i }));

    await waitFor(() => expect(update).toHaveBeenCalledWith(2026, null));
  });
});
