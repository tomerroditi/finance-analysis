import { describe, it, expect } from "vitest";
import { classifyStatement } from "./insuranceStatement";

/**
 * Row titles are the provider's own generic strings; the amounts are invented.
 * Real account balances never belong in a committed fixture.
 */
const HEBREW_STATEMENT = JSON.stringify([
  { title: "יתרה לתחילת שנה", amount: 200000 },
  { title: "הפקדות", amount: 46000 },
  { title: "רווחים", amount: 12000 },
  { title: "דמי ניהול", amount: -600 },
  { title: "עלות הביטוח לסיכוני נכות", amount: -1000 },
  { title: "עלות הביטוח למקרה מוות", amount: -500 },
  { title: "איזון אקטוארי", amount: -90 },
  { title: "יתרה נוכחית", amount: 255810 },
]);

const DEMO_STATEMENT = JSON.stringify([
  { title: "Opening balance", amount: 268470 },
  { title: "Deposits", amount: 55500 },
  { title: "Gains", amount: 9100 },
  { title: "Management fee", amount: -820 },
  { title: "Disability risk cost", amount: -1440 },
  { title: "Death risk cost", amount: -690 },
  { title: "Actuarial balance", amount: -120 },
  { title: "Closing balance", amount: 330000 },
]);

describe("classifyStatement", () => {
  it("sums only the risk-cost rows, ignoring balances, deposits and gains", () => {
    // Σ|amount| over every row would be 515,000 — the bug this replaces.
    expect(classifyStatement(HEBREW_STATEMENT).riskCost).toBe(1500);
  });

  it("reports the management fee separately from the risk cost", () => {
    expect(classifyStatement(HEBREW_STATEMENT).managementFee).toBe(600);
  });

  it("keeps the actuarial balance signed — it is legitimately ± per policy", () => {
    expect(classifyStatement(HEBREW_STATEMENT).actuarial).toBe(-90);
    const positive = JSON.stringify([{ title: "איזון אקטוארי", amount: 35 }]);
    expect(classifyStatement(positive).actuarial).toBe(35);
  });

  it("classifies the English demo statement through the same code path", () => {
    expect(classifyStatement(DEMO_STATEMENT)).toEqual({
      riskCost: 2130,
      managementFee: 820,
      actuarial: -120,
      unclassified: 0,
    });
  });

  it("ignores an unrecognised row rather than counting it as cost", () => {
    const withNewRow = JSON.stringify([
      { title: "עלות הביטוח למקרה מוות", amount: -500 },
      { title: "עמלת נאמן חדשה", amount: -9999 },
    ]);
    expect(classifyStatement(withNewRow).riskCost).toBe(500);
    expect(classifyStatement(withNewRow).managementFee).toBe(0);
  });

  it("reports a renamed risk-cost row as unclassified instead of a silent zero", () => {
    // The detector's whole reason to exist: HaPhoenix drops the definite
    // article from `עלות הביטוח` and every risk key stops matching. Without
    // `unclassified` the card loses its red line and the page KPI reads 0 —
    // a user would reasonably read that as "my pension has no risk cost".
    const renamed = JSON.stringify([
      { title: "יתרה לתחילת שנה", amount: 200000 },
      { title: "דמי ניהול", amount: -600 },
      { title: "עלות ביטוח לסיכוני נכות", amount: -1000 },
      { title: "עלות ביטוח למקרה מוות", amount: -500 },
    ]);
    const breakdown = classifyStatement(renamed);
    expect(breakdown.riskCost).toBe(0);
    expect(breakdown.managementFee).toBe(600);
    expect(breakdown.unclassified).toBe(1500);
  });

  it("keeps unmatched positive rows out of unclassified — they are not deductions", () => {
    // Opening balance, deposits, gains and closing balance all match no key.
    // Counting them would resurrect the 514,082 bug under a new name.
    expect(classifyStatement(HEBREW_STATEMENT).unclassified).toBe(0);
    expect(classifyStatement(DEMO_STATEMENT).unclassified).toBe(0);
  });

  it("ignores a positive-signed cost row — a cost is always a deduction", () => {
    const positiveCost = JSON.stringify([
      { title: "דמי ניהול", amount: 820 },
      { title: "Disability risk cost", amount: 1440 },
    ]);
    expect(classifyStatement(positiveCost)).toEqual({
      riskCost: 0,
      managementFee: 0,
      actuarial: 0,
      unclassified: 0,
    });
  });

  it("returns zeroed buckets for null, malformed JSON and non-array JSON", () => {
    const zero = { riskCost: 0, managementFee: 0, actuarial: 0, unclassified: 0 };
    expect(classifyStatement(null)).toEqual(zero);
    expect(classifyStatement("not json")).toEqual(zero);
    expect(classifyStatement('{"title":"x"}')).toEqual(zero);
  });

  it("skips rows with a missing or non-numeric amount without throwing", () => {
    const messy = JSON.stringify([
      { title: "דמי ניהול" },
      { title: "עלות הביטוח למקרה מוות", amount: "-500" },
      { title: "עלות הביטוח לסיכוני נכות", amount: -300 },
    ]);
    expect(classifyStatement(messy).riskCost).toBe(300);
  });
});
