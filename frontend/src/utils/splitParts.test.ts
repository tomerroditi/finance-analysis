import { describe, it, expect } from "vitest";
import { isSplitPart, parentTagLabel, splitSiblings } from "./splitParts";
import type { Transaction } from "../types/transaction";

/** A ₪3,000 Bit transfer split into two parts, plus a bank row with the same parent id. */
const part = (id: number, amount: number, source = "bank_transactions"): Transaction => ({
  unique_id: `split_${id}`,
  amount,
  date: "2026-05-01",
  source,
  type: "split_child",
  parent_unique_id: 7,
  parent_category: "Other Income",
  parent_tag: "Bit",
  parent_amount: 3000,
});

describe("splitParts", () => {
  it("recognises a split part and names its parent's tag", () => {
    expect(isSplitPart(part(1, 1000))).toBe(true);
    expect(isSplitPart({ amount: 5, date: "2026-05-01" })).toBe(false);
    expect(parentTagLabel(part(1, 1000))).toBe("Other Income / Bit");
    expect(parentTagLabel({ ...part(1, 1000), parent_tag: null })).toBe("Other Income");
    expect(parentTagLabel({ ...part(1, 1000), parent_category: null })).toBeNull();
  });

  it("lists the parts of the same split, largest first, never another table's", () => {
    const rows = [part(1, 1000), part(2, 2000), part(3, 50, "credit_card_transactions")];
    expect(splitSiblings(rows, rows[0]).map((t) => t.unique_id)).toEqual(["split_2", "split_1"]);
  });
});
