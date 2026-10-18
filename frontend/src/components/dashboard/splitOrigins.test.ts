import { describe, it, expect } from "vitest";
import {
  byOriginalTag,
  hasOrigins,
  mergeOrigins,
  originKey,
  originsOf,
  parseOriginKey,
  seriesLabel,
  toOriginRows,
  withOriginColors,
  withOriginSeries,
} from "./splitOrigins";
import { toYearlyComposition, type CompositionRow } from "./incomeExpensesScope";

/**
 * A ₪3,000 Bit transfer split so that ₪1,000 of it is a bonus: the breakdown
 * counts ₪2,000 under Bit and ₪1,000 under the bonus, and `split_from` says
 * where that ₪1,000 came from.
 */
const BIT = "Other Income / Bit";
const BONUS = "Salary / Bonus";
const api = [
  { month: "2026-05", split_from: { [BONUS]: { [BIT]: 1000 } } },
  { month: "2026-06" },
];
const rows: CompositionRow[] = [
  { month: "2026-05", values: { [BIT]: 2000, [BONUS]: 1000, Salary: 15000 } },
  { month: "2026-06", values: { Salary: 15000 } },
];

describe("origin keys", () => {
  it("round-trips the parent and child through a key", () => {
    expect(parseOriginKey(originKey(BIT, BONUS))).toEqual({ parent: BIT, child: BONUS });
  });

  it("does not read a real series name as an origin", () => {
    expect(parseOriginKey(BIT)).toBeNull();
    expect(seriesLabel(BIT)).toBe(BIT);
  });

  it("names a pseudo-series after its parent and colours it as its child", () => {
    const key = originKey(BIT, BONUS);
    expect(seriesLabel(key)).toBe(BIT);
    const colorOf = withOriginColors((name) => (name === BONUS ? "gold" : "grey"));
    expect(colorOf(key)).toBe("gold");
  });
});

describe("origin rows", () => {
  it("keys each carried amount by parent and child, one row per period", () => {
    const origins = toOriginRows(api);
    expect(origins).toEqual([
      { month: "2026-05", values: { [originKey(BIT, BONUS)]: 1000 } },
      { month: "2026-06", values: {} },
    ]);
    expect(hasOrigins(origins)).toBe(true);
    expect(hasOrigins(toOriginRows([{ month: "2026-06" }]))).toBe(false);
  });

  it("folds into a year like any breakdown row", () => {
    const year = toYearlyComposition(toOriginRows([...api, { month: "2026-07", split_from: { [BONUS]: { [BIT]: 500 } } }]));
    expect(year[0].values[originKey(BIT, BONUS)]).toBe(1500);
  });

  it("lists the parents a series was split from, largest first", () => {
    const row = { month: "2026-05", values: { [originKey(BIT, BONUS)]: 1000, [originKey("Gifts", BONUS)]: 2000 } };
    expect(originsOf(row, BONUS)).toEqual([
      { parent: "Gifts", amount: 2000 },
      { parent: BIT, amount: 1000 },
    ]);
    expect(originsOf(row, BIT)).toEqual([]);
  });
});

describe("byOriginalTag", () => {
  it("moves split money back under its parent without changing the period total", () => {
    const [may, june] = byOriginalTag(rows, toOriginRows(api));
    expect(may.values).toEqual({ [BIT]: 2000, Salary: 15000, [originKey(BIT, BONUS)]: 1000 });
    expect(june).toEqual(rows[1]);
  });

  it("keeps the rest of a child that was only partly split in", () => {
    const partial: CompositionRow[] = [{ month: "2026-05", values: { [BONUS]: 1600 } }];
    const [may] = byOriginalTag(partial, toOriginRows(api));
    expect(may.values[BONUS]).toBe(600);
  });

  it("folds back into the parent for a single-series view", () => {
    const [may] = mergeOrigins(byOriginalTag(rows, toOriginRows(api)));
    expect(may.values).toEqual({ [BIT]: 3000, Salary: 15000 });
  });
});

describe("withOriginSeries", () => {
  it("places each pseudo-series right after its parent", () => {
    expect(withOriginSeries([BIT, BONUS, "Salary"], toOriginRows(api))).toEqual([
      BIT,
      originKey(BIT, BONUS),
      BONUS,
      "Salary",
    ]);
  });

  it("appends a pseudo-series whose parent has no money of its own", () => {
    expect(withOriginSeries([BONUS], toOriginRows(api))).toEqual([BONUS, originKey(BIT, BONUS)]);
  });
});
