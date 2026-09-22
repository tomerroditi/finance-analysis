import { describe, it, expect } from "vitest";
import {
  allTimeKpi,
  barCap,
  formatPeriodLabel,
  isYearKey,
  sliceWindow,
  toAllComposition,
  toAllLedger,
  toYearlyComposition,
  toYearlyLedger,
  totalsByYear,
  yearlyKpi,
  type CompositionRow,
} from "./incomeExpensesScope";

/**
 * The yearly scope is a client-side fold over the same monthly series the
 * card already holds, so these are the only place the year totals and the
 * trend baseline behind the toggle are checked.
 */

/** Twelve months of a year, each carrying the same figures. */
function fullYear(year: string, income: number, expenses: number) {
  return Array.from({ length: 12 }, (_, i) => ({
    month: `${year}-${String(i + 1).padStart(2, "0")}`,
    income,
    expenses,
  }));
}

describe("period keys", () => {
  it("tells a year key from a month key", () => {
    expect(isYearKey("2026")).toBe(true);
    expect(isYearKey("2026-06")).toBe(false);
  });

  it("labels a year key with the bare year", () => {
    expect(formatPeriodLabel("2026")).toBe("2026");
  });

  it("labels a month key with its short month", () => {
    expect(formatPeriodLabel("2026-06")).toBe("Jun '26");
  });

  it("is not a year key that the all-scope fold happens to spell", () => {
    expect(isYearKey("all")).toBe(false);
  });

  it("labels the all-scope key with the caller's translated phrase", () => {
    expect(formatPeriodLabel("all", "כל הזמן")).toBe("כל הזמן");
  });
});

describe("toYearlyLedger", () => {
  it("sums income and expenses per calendar year, oldest first", () => {
    const rows = [...fullYear("2025", 100, 60), ...fullYear("2026", 200, 90)];

    expect(toYearlyLedger(rows)).toEqual([
      { month: "2025", income: 1200, expenses: 720 },
      { month: "2026", income: 2400, expenses: 1080 },
    ]);
  });

  it("keeps a net-refund month's negative expenses", () => {
    const rows = [
      { month: "2026-01", income: 100, expenses: 80 },
      { month: "2026-02", income: 100, expenses: -30 },
    ];

    expect(toYearlyLedger(rows)).toEqual([{ month: "2026", income: 200, expenses: 50 }]);
  });

  it("returns nothing for an empty series", () => {
    expect(toYearlyLedger([])).toEqual([]);
  });
});

describe("toYearlyComposition", () => {
  it("sums each series separately and carries one that appears in a single month", () => {
    const rows: CompositionRow[] = [
      { month: "2026-01", values: { Food: 100, Transport: 50 } },
      { month: "2026-02", values: { Food: 120 } },
      { month: "2025-12", values: { Food: 90, Gifts: 300 } },
    ];

    expect(toYearlyComposition(rows)).toEqual([
      { month: "2025", values: { Food: 90, Gifts: 300 } },
      { month: "2026", values: { Food: 220, Transport: 50 } },
    ]);
  });
});

describe("totalsByYear", () => {
  it("counts the months each year actually covers", () => {
    const rows = [
      { month: "2025-11", value: 10 },
      { month: "2025-12", value: 20 },
      { month: "2026-01", value: 5 },
    ];

    expect(totalsByYear(rows)).toEqual([
      { year: "2025", value: 30, months: 2 },
      { year: "2026", value: 5, months: 1 },
    ]);
  });
});

describe("yearlyKpi", () => {
  it("has nothing to show for an empty series", () => {
    expect(yearlyKpi([])).toBeNull();
  });

  it("compares a running year to the same months of the previous one", () => {
    const rows = [
      ...Array.from({ length: 12 }, (_, i) => ({
        month: `2025-${String(i + 1).padStart(2, "0")}`,
        value: i < 3 ? 100 : 1000,
      })),
      { month: "2026-01", value: 150 },
      { month: "2026-02", value: 150 },
      { month: "2026-03", value: 150 },
    ];

    const kpi = yearlyKpi(rows);

    expect(kpi?.latest).toEqual({ year: "2026", value: 450, months: 3 });
    expect(kpi?.partial).toBe(true);
    // The first three months of 2025, not its 9,300 full-year total — a
    // quarter against a year would read as a collapse every January.
    expect(kpi?.baseline).toBe(300);
  });

  it("compares a complete year to the whole of the previous one", () => {
    const rows = [
      ...fullYear("2025", 100, 0).map((r) => ({ month: r.month, value: r.income })),
      ...fullYear("2026", 150, 0).map((r) => ({ month: r.month, value: r.income })),
    ];

    const kpi = yearlyKpi(rows);

    expect(kpi?.partial).toBe(false);
    expect(kpi?.latest.value).toBe(1800);
    expect(kpi?.baseline).toBe(1200);
  });

  it("offers the two preceding years, newest first, and no baseline when alone", () => {
    const rows = ["2023", "2024", "2025", "2026"].flatMap((year) =>
      fullYear(year, 10, 0).map((r) => ({ month: r.month, value: r.income })),
    );

    expect(yearlyKpi(rows)?.earlier.map((y) => y.year)).toEqual(["2025", "2024"]);
    expect(yearlyKpi([{ month: "2026-01", value: 10 }])?.baseline).toBe(0);
  });
});


describe("toAllLedger", () => {
  it("sums the whole series into one row", () => {
    const rows = [...fullYear("2025", 100, 60), ...fullYear("2026", 200, 90)];

    expect(toAllLedger(rows)).toEqual([{ month: "all", income: 3600, expenses: 1800 }]);
  });

  it("has no row at all for an empty series", () => {
    expect(toAllLedger([])).toEqual([]);
  });
});

describe("toAllComposition", () => {
  it("sums every series across every month into one row", () => {
    const rows: CompositionRow[] = [
      { month: "2025-11", values: { Salary: 100, Rent: 20 } },
      { month: "2026-01", values: { Salary: 150, Bonus: 5 } },
    ];

    expect(toAllComposition(rows)).toEqual([
      { month: "all", values: { Salary: 250, Rent: 20, Bonus: 5 } },
    ]);
  });

  it("has no row at all for an empty series", () => {
    expect(toAllComposition([])).toEqual([]);
  });
});

describe("sliceWindow", () => {
  const rows = [
    { month: "2024-12" },
    { month: "2025-09" },
    { month: "2025-10" },
    { month: "2026-01" },
    { month: "2026-09" },
  ];
  const today = new Date(2026, 8, 22); // 2026-09-22, local time

  it("keeps everything for the all-time window", () => {
    expect(sliceWindow(rows, "all", today)).toEqual(rows);
  });

  it("keeps the calendar year to date", () => {
    expect(sliceWindow(rows, "year", today).map((r) => r.month)).toEqual([
      "2026-01",
      "2026-09",
    ]);
  });

  it("keeps the current month and the eleven before it", () => {
    // The window opens at 2025-10, so the month before it is out and the
    // boundary month itself is in.
    expect(sliceWindow(rows, "last12m", today).map((r) => r.month)).toEqual([
      "2025-10",
      "2026-01",
      "2026-09",
    ]);
  });

  it("reads a month key as a local month, not a UTC instant", () => {
    // A `Date` built from "2026-01" is UTC midnight, which is still December
    // west of Greenwich — the bound has to be a string comparison.
    const newYear = new Date(2026, 0, 5);
    expect(sliceWindow([{ month: "2026-01" }], "year", newYear)).toEqual([
      { month: "2026-01" },
    ]);
  });
});

describe("allTimeKpi", () => {
  it("averages over the months the series carries, not the calendar span", () => {
    // Tracking began in November, so the average is over two months.
    const kpi = allTimeKpi([
      { month: "2026-11", value: 100 },
      { month: "2026-12", value: 300 },
    ]);

    expect(kpi).toEqual({ total: 400, months: 2, perMonth: 200 });
  });

  it("has no average to give for an empty series", () => {
    expect(allTimeKpi([])).toEqual({ total: 0, months: 0, perMonth: 0 });
  });
});

describe("barCap", () => {
  it("anchors on the median so a single outlier cannot flatten the rest", () => {
    expect(barCap([10, 10, 10, 1000])).toBe(16);
  });

  it("ignores zero and negative values", () => {
    expect(barCap([0, -50, 10])).toBe(16);
  });

  it("falls back to 1 when nothing is positive", () => {
    expect(barCap([])).toBe(1);
    expect(barCap([0, -1])).toBe(1);
  });
});
