import { describe, it, expect } from "vitest";
import {
  formatCurrency,
  formatCompactCurrency,
  formatChange,
  formatPercentChange,
} from "./numberFormatting";

// LRI ... PDI envelope + NBSP between digits and ₪.
const LRI = "⁦";
const PDI = "⁩";
const NBSP = " ";
const wrap = (inner: string) => `${LRI}${inner}${NBSP}₪${PDI}`;

describe("formatCurrency", () => {
  it("renders positives with sign-magnitude-currency wrapped in LRI/PDI", () => {
    expect(formatCurrency(1_003_211)).toBe(wrap("1,003,211"));
    expect(formatCurrency(700)).toBe(wrap("700"));
  });

  it("renders negatives with sign-magnitude-shekel", () => {
    expect(formatCurrency(-25_000)).toBe(wrap("-25,000"));
    expect(formatCurrency(-1_234_567)).toBe(wrap("-1,234,567"));
  });

  it("renders zero without a sign", () => {
    expect(formatCurrency(0)).toBe(wrap("0"));
  });

  it("respects maximumFractionDigits", () => {
    expect(formatCurrency(1234.5678, 2)).toBe(wrap("1,234.57"));
    expect(formatCurrency(-1234.5678, 2)).toBe(wrap("-1,234.57"));
  });

  it("uses non-breaking space so digits and ₪ never line-wrap apart", () => {
    expect(formatCurrency(1_000)).toContain(NBSP);
    expect(formatCurrency(1_000)).not.toContain(" ₪"); // regular space + ₪ would be wrappable
  });
});

describe("formatCompactCurrency", () => {
  it("renders positive millions with M suffix and currency after number", () => {
    expect(formatCompactCurrency(1_100_000)).toBe(wrap("1.1M"));
  });

  it("renders negative millions with sign before magnitude and currency after", () => {
    expect(formatCompactCurrency(-1_100_000)).toBe(wrap("-1.1M"));
  });

  it("renders large thousands with K suffix", () => {
    expect(formatCompactCurrency(35_000)).toBe(wrap("35K"));
  });

  it("renders negative large thousands with sign-magnitude-currency", () => {
    expect(formatCompactCurrency(-20_000)).toBe(wrap("-20K"));
  });

  it("renders small thousands with one decimal place", () => {
    expect(formatCompactCurrency(1_500)).toBe(wrap("1.5K"));
    expect(formatCompactCurrency(-1_500)).toBe(wrap("-1.5K"));
  });

  it("renders sub-thousand values with same sign-magnitude-currency layout", () => {
    expect(formatCompactCurrency(132)).toBe(wrap("132"));
    expect(formatCompactCurrency(-132)).toBe(wrap("-132"));
    expect(formatCompactCurrency(-482)).toBe(wrap("-482"));
  });

  it("renders zero without a sign", () => {
    expect(formatCompactCurrency(0)).toBe(wrap("0"));
  });
});

describe("formatChange", () => {
  it("always includes a leading + on non-negative values", () => {
    expect(formatChange(35_000)).toBe(wrap("+35K"));
    expect(formatChange(0)).toBe(wrap("+0"));
  });

  it("always includes a leading - on negative values", () => {
    expect(formatChange(-20_000)).toBe(wrap("-20K"));
    expect(formatChange(-482)).toBe(wrap("-482"));
  });

  it("uses M suffix for millions", () => {
    expect(formatChange(1_100_000)).toBe(wrap("+1.1M"));
    expect(formatChange(-603_000)).toBe(wrap("-603K"));
  });

  it("renders sub-thousand deltas without abbreviation but in canonical layout", () => {
    expect(formatChange(150)).toBe(wrap("+150"));
    expect(formatChange(-132)).toBe(wrap("-132"));
  });

  it("respects compact: false to disable K/M abbreviation", () => {
    expect(formatChange(35_000, { compact: false })).toBe(wrap("+35,000"));
    expect(formatChange(-1_234_567, { compact: false })).toBe(wrap("-1,234,567"));
  });
});

describe("formatPercentChange", () => {
  it("always includes a leading sign", () => {
    expect(formatPercentChange(2.5)).toBe("+2.5%");
    expect(formatPercentChange(-1.6)).toBe("-1.6%");
    expect(formatPercentChange(0)).toBe("+0.0%");
  });

  it("respects fractionDigits", () => {
    expect(formatPercentChange(614.4, 1)).toBe("+614.4%");
    expect(formatPercentChange(2.5, 2)).toBe("+2.50%");
  });
});
