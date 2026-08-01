import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { RuleSparkline } from "./RuleSparkline";

const LABELS = ["Feb", "Mar", "Apr"];

function bars(container: HTMLElement) {
  return Array.from(container.querySelectorAll("rect"));
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
      expect(container.querySelectorAll("line")).toHaveLength(0);
      // Neutral, not a status colour — there is no budget to be over.
      expect(bars(container)[0].getAttribute("fill")).toBe("#64748b");
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

    it("flags a row that is under its ceiling but ahead of pace", () => {
      // 3 of 12 months elapsed → pace is 300 of 1200. Spending 600 is only
      // half the ceiling, but twice the pace: the percentage column would
      // call this fine, the trend must not.
      const { container } = render(
        <RuleSparkline
          variant="burn"
          series={[200, 200, 200]}
          labels={LABELS}
          budget={1200}
          totalPeriods={12}
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
          showPace
        />,
      );
      expect(container.querySelector("polyline")?.getAttribute("stroke")).toBe("#10b981");
    });

    it("goes rose once cumulative spend passes the ceiling", () => {
      const { container } = render(
        <RuleSparkline
          variant="burn"
          series={[700, 700]}
          labels={["Feb", "Mar"]}
          budget={1000}
          totalPeriods={12}
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
  });
});
