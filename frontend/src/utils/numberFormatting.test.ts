import { describe, it, expect } from "vitest";
import {
  formatCompactCurrency,
  formatChange,
  formatPercentChange,
} from "./numberFormatting";

describe("formatCompactCurrency", () => {
  it("renders positive millions with M suffix and currency before number", () => {
    expect(formatCompactCurrency(1_100_000)).toBe("₪1.1M");
  });

  it("renders negative millions with sign before currency", () => {
    expect(formatCompactCurrency(-1_100_000)).toBe("-₪1.1M");
  });

  it("renders large thousands with K suffix", () => {
    expect(formatCompactCurrency(35_000)).toBe("₪35K");
  });

  it("renders negative large thousands with sign before currency", () => {
    expect(formatCompactCurrency(-20_000)).toBe("-₪20K");
  });

  it("renders small thousands with one decimal place", () => {
    expect(formatCompactCurrency(1_500)).toBe("₪1.5K");
    expect(formatCompactCurrency(-1_500)).toBe("-₪1.5K");
  });

  it("renders sub-thousand values with same sign-currency-magnitude layout", () => {
    expect(formatCompactCurrency(132)).toBe("₪132");
    expect(formatCompactCurrency(-132)).toBe("-₪132");
    expect(formatCompactCurrency(-482)).toBe("-₪482");
  });

  it("renders zero without a sign", () => {
    expect(formatCompactCurrency(0)).toBe("₪0");
  });
});

describe("formatChange", () => {
  it("always includes a leading + on non-negative values", () => {
    expect(formatChange(35_000)).toBe("+₪35K");
    expect(formatChange(0)).toBe("+₪0");
  });

  it("always includes a leading - on negative values", () => {
    expect(formatChange(-20_000)).toBe("-₪20K");
    expect(formatChange(-482)).toBe("-₪482");
  });

  it("uses M suffix for millions", () => {
    expect(formatChange(1_100_000)).toBe("+₪1.1M");
    expect(formatChange(-603_000)).toBe("-₪603K");
  });

  it("renders sub-thousand deltas without abbreviation but in canonical layout", () => {
    expect(formatChange(150)).toBe("+₪150");
    expect(formatChange(-132)).toBe("-₪132");
  });

  it("respects compact: false to disable K/M abbreviation", () => {
    expect(formatChange(35_000, { compact: false })).toBe("+₪35,000");
    expect(formatChange(-1_234_567, { compact: false })).toBe("-₪1,234,567");
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
