import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { BudgetTotalBar } from "./BudgetTotalBar";

function fill(container: HTMLElement) {
  return container.querySelector('[data-testid="budget-total-bar-fill"]')!;
}

describe("BudgetTotalBar", () => {
  it("renders spent out of total with the remaining pill", () => {
    render(<BudgetTotalBar spent={66} total={12000} />);
    expect(screen.getByText(/66/)).toBeInTheDocument();
    expect(screen.getByText(/12,000/)).toBeInTheDocument();
    expect(screen.getByText(/11,934.*remaining/)).toBeInTheDocument();
  });

  it("is emerald and proportionally filled while comfortably under budget", () => {
    const { container } = render(<BudgetTotalBar spent={250} total={1000} />);
    expect(fill(container).className).toContain("bg-emerald-500");
    expect(fill(container).getAttribute("style")).toContain("width: 25%");
  });

  it("turns amber past 90% without being over", () => {
    const { container } = render(<BudgetTotalBar spent={950} total={1000} />);
    expect(fill(container).className).toContain("bg-amber-500");
  });

  it("turns rose and reports the overage once spend exceeds the total", () => {
    const { container } = render(<BudgetTotalBar spent={1200} total={1000} />);
    expect(fill(container).className).toContain("bg-rose-500");
    expect(screen.getByText(/200.*over/)).toBeInTheDocument();
  });

  it("caps the bar at 100% so an overspend cannot overflow its track", () => {
    const { container } = render(<BudgetTotalBar spent={5000} total={1000} />);
    expect(fill(container).getAttribute("style")).toContain("width: 100%");
  });

  // Regression: a zero budget with spend against it used to render a full
  // emerald bar, reading as healthy when nothing was budgeted at all.
  it("treats spend against a zero budget as fully over", () => {
    const { container } = render(<BudgetTotalBar spent={80} total={0} />);
    expect(fill(container).className).toContain("bg-rose-500");
    expect(fill(container).getAttribute("style")).toContain("width: 100%");
    expect(screen.getByText(/80.*over/)).toBeInTheDocument();
  });

  it("shows an empty bar and no pill when nothing is budgeted or spent", () => {
    const { container } = render(<BudgetTotalBar spent={0} total={0} />);
    expect(fill(container).getAttribute("style")).toContain("width: 0%");
    expect(screen.queryByText(/remaining|over/)).not.toBeInTheDocument();
  });

  it("clamps a negative spend (net refund) to zero", () => {
    const { container } = render(<BudgetTotalBar spent={-40} total={1000} />);
    expect(fill(container).getAttribute("style")).toContain("width: 0%");
    expect(fill(container).className).toContain("bg-emerald-500");
  });
});
