import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { BudgetLedgerRow } from "./BudgetLedgerRow";

/**
 * BudgetLedgerRow renders a signed `current` amount (the backend negates so
 * that spend is positive and a net refund is negative). These tests lock in
 * the edge case where a rule's period nets to a refund (refunds exceed spend)
 * — it must never be rendered as spending or as "over budget". Ported from
 * BudgetRuleRow, which this row replaced.
 */
function renderRow(current: number, total: number) {
  return render(
    <BudgetLedgerRow
      label="Other Expenses"
      current={current}
      total={total}
      isExpanded={false}
      onToggleExpand={() => {}}
    />,
  );
}

function fillWidth(container: HTMLElement): string {
  const fill = container.querySelector<HTMLElement>('[style*="width"]');
  return fill?.style.width ?? "";
}

describe("BudgetLedgerRow", () => {
  describe("normal spend", () => {
    it("fills the bar proportionally and shows the remaining amount", () => {
      const { container } = renderRow(1000, 3000);
      expect(fillWidth(container)).toBe("33.33333333333333%");
      expect(container.textContent).toContain("remaining");
      expect(container.textContent).not.toContain("net refund");
    });

    it("marks genuine overspend as over budget with a full bar", () => {
      const { container } = renderRow(4000, 3000);
      expect(fillWidth(container)).toBe("100%");
      expect(container.textContent).toContain("over");
    });
  });

  describe("net refund (refunds exceed spend)", () => {
    it("does NOT render a net refund as over budget even when it exceeds the budget", () => {
      const { container } = renderRow(-5000, 3000);
      // The bug: Math.abs(-5000)=5000 > 3000 rendered a red 'over budget' bar.
      expect(container.textContent).not.toContain("over");
      expect(fillWidth(container)).toBe("0%");
    });

    it("shows the net refund as a signed credit, not positive spending", () => {
      const { container } = renderRow(-1200, 3000);
      // Figure must read as a negative (credit), not "1,200" spent.
      expect(container.textContent).toContain("-1,200");
      expect(container.textContent).toContain("net refund");
      expect(fillWidth(container)).toBe("0%");
    });
  });

  describe("percentage column", () => {
    it("reads 0% for a net refund rather than a negative percentage", () => {
      const { container } = renderRow(-1200, 3000);
      expect(container.textContent).toContain("0%");
      expect(container.textContent).not.toContain("-40%");
    });

    it("shows an em dash when the envelope has no budget", () => {
      const { container } = renderRow(500, 0);
      expect(container.textContent).toContain("—");
    });
  });
});
