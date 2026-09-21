import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { RuleSparkline } from "./RuleSparkline";

const LABELS = ["Feb", "Mar", "Apr"];

function bars(container: HTMLElement) {
  return Array.from(container.querySelectorAll("rect"));
}

function reference(container: HTMLElement) {
  return container.querySelector('[data-testid="budget-reference"]');
}

/** Every y the reference path visits, in order. */
function heights(d: string): number[] {
  return Array.from(d.matchAll(/[ML] [\d.]+,([\d.]+)/g)).map((m) => Number(m[1]));
}

describe("RuleSparkline", () => {
  describe("bars variant (monthly envelopes)", () => {
    it("colours only the months that crossed the budget as over", () => {
      const { container } = render(
        <RuleSparkline
          variant="bars"
          series={[100, 400, 250]}
          labels={LABELS}
          budget={300}
        />,
      );
      const fills = bars(container).map((r) => r.getAttribute("fill"));
      expect(fills).toEqual(["#10b981", "#f43f5e", "#10b981"]);
    });

    it("emphasises the current period and dims the history", () => {
      const { container } = render(
        <RuleSparkline variant="bars" series={[100, 200]} labels={["Feb", "Mar"]} budget={300} />,
      );
      const opacity = bars(container).map((r) => r.getAttribute("opacity"));
      expect(opacity).toEqual(["0.45", "1"]);
    });

    it("draws no budget reference line for an unbudgeted envelope", () => {
      const { container } = render(
        <RuleSparkline variant="bars" series={[100, 200]} labels={["Feb", "Mar"]} budget={0} />,
      );
      expect(reference(container)).toBeNull();
      // Neutral, not a status colour — there is no budget to be over.
      expect(bars(container)[0].getAttribute("fill")).toBe("#64748b");
    });

    it("runs the reference flat when no per-month limits are given", () => {
      // A caller with no history of its caps keeps the single line it had
      // before: one subpath, one height, edge to edge.
      const { container } = render(
        <RuleSparkline variant="bars" series={[100, 200]} labels={["Feb", "Mar"]} budget={300} />,
      );
      const d = reference(container)?.getAttribute("d") ?? "";
      expect(d.match(/M /g)).toHaveLength(1);
      expect(new Set(heights(d)).size).toBe(1);
    });

    it("steps the reference where the limit moved", () => {
      // The same envelope cut from 2,000 to 1,000: the older months keep
      // their own line, so the chart stops claiming they were over budget.
      const { container } = render(
        <RuleSparkline
          variant="bars"
          series={[1800, 1800, 900]}
          labels={LABELS}
          budget={1000}
          budgets={[2000, 2000, 1000]}
        />,
      );
      const d = reference(container)?.getAttribute("d") ?? "";
      // One subpath — the steps are risers inside it, not separate lines.
      expect(d.match(/M /g)).toHaveLength(1);
      const levels = heights(d);
      // Two distinct heights, and the later (smaller) limit sits lower.
      expect(new Set(levels).size).toBe(2);
      expect(levels[levels.length - 1]).toBeGreaterThan(levels[0]);
    });

    it("judges each month against the limit it actually carried", () => {
      // 1,800 spent under an 1,800 envelope is not an overspend, and cutting
      // the envelope to 1,500 afterwards must not repaint that month red.
      const { container } = render(
        <RuleSparkline
          variant="bars"
          series={[1800, 1800, 1400]}
          labels={LABELS}
          budget={1500}
          budgets={[2000, 2000, 1500]}
        />,
      );
      const fills = bars(container).map((r) => r.getAttribute("fill"));
      expect(fills).toEqual(["#10b981", "#10b981", "#f59e0b"]);
    });

    it("breaks the reference over a month the envelope did not exist in", () => {
      const { container } = render(
        <RuleSparkline
          variant="bars"
          series={[0, 400, 300]}
          labels={LABELS}
          budget={500}
          budgets={[0, 500, 500]}
        />,
      );
      const d = reference(container)?.getAttribute("d") ?? "";
      // The gap is where the path starts, not a line along the floor: the
      // first bar's slot is left bare, so nothing is drawn before it.
      expect(d.match(/M /g)).toHaveLength(1);
      const firstX = Number(d.match(/M ([\d.]+),/)?.[1]);
      // Default width 74, 2px gaps → the first of three bars ends at ~23.3.
      expect(firstX).toBeGreaterThan(23);
      // And nothing sits at the floor (y = height) either.
      expect(heights(d).every((y) => y < 22)).toBe(true);
    });

    it("scales to the tallest limit in the window, not just the latest", () => {
      // A raised-then-cut envelope: the old, higher reference must stay
      // inside the viewport instead of being clipped off the top.
      const { container } = render(
        <RuleSparkline
          variant="bars"
          series={[100, 100]}
          labels={["Feb", "Mar"]}
          budget={200}
          budgets={[4000, 200]}
        />,
      );
      expect(heights(reference(container)?.getAttribute("d") ?? "").every((y) => y >= 0)).toBe(
        true,
      );
    });
  });

  describe("burn variant (yearly and project envelopes)", () => {
    it("draws a pace diagonal only when asked", () => {
      const withPace = render(
        <RuleSparkline
          variant="burn"
          series={[100, 100, 100]}
          labels={LABELS}
          budget={1200}
          totalPeriods={12}
          showPace
        />,
      );
      expect(withPace.container.querySelectorAll("line")).toHaveLength(2);

      const withoutPace = render(
        <RuleSparkline
          variant="burn"
          series={[100, 100, 100]}
          labels={LABELS}
          budget={1200}
          totalPeriods={12}
        />,
      );
      expect(withoutPace.container.querySelectorAll("line")).toHaveLength(1);
    });

    it("warns on the pace diagonal — not the line — when a row is ahead of pace", () => {
      // 3 of 12 months elapsed → pace is 300 of 1200. Spending 600 is twice
      // the pace but only half the ceiling: the row's dot, bar and percentage
      // all call that on track, so the line stays green and the diagonal
      // carries the warning instead of the two disagreeing in one palette.
      const { container } = render(
        <RuleSparkline
          variant="burn"
          series={[200, 200, 200]}
          labels={LABELS}
          budget={1200}
          totalPeriods={12}
          elapsedPeriods={3}
          showPace
        />,
      );
      expect(container.querySelector("polyline")?.getAttribute("stroke")).toBe("#10b981");
      expect(
        container.querySelector('[data-testid="pace-line"]')?.getAttribute("stroke"),
      ).toBe("#f59e0b");
    });

    it("keeps the line's colour on the same thresholds as the ledger row", () => {
      // The reported mismatch: 85% of the ceiling with 9 of 12 months gone.
      // The row paints that green (under 90%), so the trend must too.
      const { container } = render(
        <RuleSparkline
          variant="burn"
          series={[0, 0, 0, 0, 0, 0, 0, 1086, 4000]}
          labels={LABELS}
          budget={6000}
          totalPeriods={12}
          elapsedPeriods={9}
          showPace
        />,
      );
      expect(container.querySelector("polyline")?.getAttribute("stroke")).toBe("#10b981");
      expect(container.querySelector("circle")?.getAttribute("fill")).toBe("#10b981");
    });

    it("turns the line amber once the envelope is nearly spent out", () => {
      const { container } = render(
        <RuleSparkline
          variant="burn"
          series={[600, 500]}
          labels={["Feb", "Mar"]}
          budget={1200}
          totalPeriods={12}
          elapsedPeriods={2}
          showPace
        />,
      );
      expect(container.querySelector("polyline")?.getAttribute("stroke")).toBe("#f59e0b");
    });

    it("stays green when spending is behind pace", () => {
      const { container } = render(
        <RuleSparkline
          variant="burn"
          series={[10, 10, 10]}
          labels={LABELS}
          budget={1200}
          totalPeriods={12}
          elapsedPeriods={3}
          showPace
        />,
      );
      expect(container.querySelector("polyline")?.getAttribute("stroke")).toBe("#10b981");
      expect(
        container.querySelector('[data-testid="pace-line"]')?.getAttribute("stroke"),
      ).toBe("#94a3b8");
    });

    it("measures pace against the calendar, not the last month with a charge", () => {
      // 8,600 of 20,000 spent in a single May charge, now that September is
      // here. Against May's clock that was ahead of pace; four quiet months
      // later it is not, and the diagonal must stop claiming otherwise.
      const series = [0, 0, 0, 0, 8600, 0, 0, 0, 0, 0, 0, 0];
      const labels = series.map((_, i) => `M${i + 1}`);
      const stale = render(
        <RuleSparkline
          variant="burn"
          series={series}
          labels={labels}
          budget={20000}
          totalPeriods={12}
          showPace
        />,
      );
      expect(
        stale.container.querySelector('[data-testid="pace-line"]')?.getAttribute("stroke"),
      ).toBe("#f59e0b");

      const current = render(
        <RuleSparkline
          variant="burn"
          series={series}
          labels={labels}
          budget={20000}
          totalPeriods={12}
          elapsedPeriods={9}
          showPace
        />,
      );
      expect(
        current.container.querySelector('[data-testid="pace-line"]')?.getAttribute("stroke"),
      ).toBe("#94a3b8");
    });

    it("says it in words, so the pace warning is not colour-only", () => {
      const { container } = render(
        <RuleSparkline
          variant="burn"
          series={[200, 200, 200]}
          labels={LABELS}
          budget={1200}
          totalPeriods={12}
          elapsedPeriods={3}
          showPace
        />,
      );
      expect(container.querySelector("svg")?.getAttribute("aria-label")).toContain(
        "Ahead of pace",
      );
    });

    it("goes rose once cumulative spend passes the ceiling", () => {
      const { container } = render(
        <RuleSparkline
          variant="burn"
          series={[700, 700]}
          labels={["Feb", "Mar"]}
          budget={1000}
          totalPeriods={12}
          elapsedPeriods={2}
          showPace
        />,
      );
      expect(container.querySelector("polyline")?.getAttribute("stroke")).toBe("#f43f5e");
    });
  });

  describe("empty state", () => {
    it("renders a dash rather than an empty chart when nothing was spent", () => {
      const { container } = render(
        <RuleSparkline variant="bars" series={[0, 0]} labels={["Feb", "Mar"]} budget={500} />,
      );
      expect(container.querySelector("svg")).toBeNull();
      expect(container.textContent).toContain("—");
    });
  });

  describe("accessibility", () => {
    it("summarises every period in the label, so the mark is never the only channel", () => {
      const { container } = render(
        <RuleSparkline variant="bars" series={[100, 200]} labels={["Feb", "Mar"]} budget={300} />,
      );
      const label = container.querySelector("svg")?.getAttribute("aria-label") ?? "";
      expect(label).toContain("Feb");
      expect(label).toContain("Mar");
    });

    it("names each month's own limit once they stop agreeing", () => {
      // A stepped line says nothing to a screen reader, so the limit each
      // month was measured against has to be in the text.
      const { container } = render(
        <RuleSparkline
          variant="bars"
          series={[1800, 1400]}
          labels={["Feb", "Mar"]}
          budget={1500}
          budgets={[2000, 1500]}
        />,
      );
      const label = container.querySelector("svg")?.getAttribute("aria-label") ?? "";
      expect(label).toContain("2.0K");
      expect(label).toContain("1.5K");
    });
  });
});
