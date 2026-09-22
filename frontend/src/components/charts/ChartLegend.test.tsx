import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ChartLegend } from "./ChartLegend";

const PAYLOAD = [
  { value: "Emergency Fund", dataKey: "g1", color: "#3b82f6" },
  { value: "Free cash", dataKey: "free_cash", color: "#94a3b8" },
];

describe("ChartLegend", () => {
  it("stays a plain row when no handler is given", () => {
    render(<ChartLegend payload={PAYLOAD} />);

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText("Free cash")).toBeInTheDocument();
  });

  it("toggles one series by its key, not its label", async () => {
    const onToggle = vi.fn();
    render(<ChartLegend payload={PAYLOAD} onToggle={onToggle} />);

    fireEvent.click(screen.getByRole("button", { name: "Free cash" }));
    // Held back in case a second click follows.
    expect(onToggle).not.toHaveBeenCalled();

    // The key, not the label: two series can share a name, and the chart
    // addresses its bars by `dataKey`.
    await vi.waitFor(() => expect(onToggle).toHaveBeenCalledWith("free_cash"));
  });

  it("isolates on a double-click instead of toggling twice", async () => {
    const onToggle = vi.fn();
    const onIsolate = vi.fn();
    render(
      <ChartLegend payload={PAYLOAD} onToggle={onToggle} onIsolate={onIsolate} />,
    );

    const entry = screen.getByRole("button", { name: "Emergency Fund" });
    fireEvent.click(entry);
    fireEvent.doubleClick(entry);

    await vi.waitFor(() => expect(onIsolate).toHaveBeenCalledWith("g1"));
    // The click that opened the double-click must not also fire.
    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(onToggle).not.toHaveBeenCalled();
  });

  it("dims a hidden series and says so", () => {
    render(
      <ChartLegend
        payload={PAYLOAD}
        hidden={new Set(["free_cash"])}
        onToggle={vi.fn()}
      />,
    );

    const hiddenEntry = screen.getByRole("button", { name: "Free cash" });
    expect(hiddenEntry).toHaveAttribute("aria-pressed", "false");
    expect(hiddenEntry.className).toMatch(/opacity-40/);
    expect(screen.getByRole("button", { name: "Emergency Fund" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});
