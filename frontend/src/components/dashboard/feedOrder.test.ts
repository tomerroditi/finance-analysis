import { describe, expect, it } from "vitest";
import type { Transaction } from "../../types/transaction";
import { compareFeedRows } from "./feedOrder";

const row = (source: string, unique_id: string, date: string, extra: Partial<Transaction> = {}) =>
  ({ source, unique_id, date, amount: -10, ...extra }) as Transaction;

const keys = (rows: Transaction[]) =>
  [...rows].sort(compareFeedRows).map((tx) => `${tx.source}_${tx.unique_id}${tx.split_id ?? ""}`);

describe("compareFeedRows", () => {
  it("puts newer dates first", () => {
    expect(
      keys([row("bank_transactions", "1", "2026-10-01"), row("bank_transactions", "2", "2026-10-05")]),
    ).toEqual(["bank_transactions_2", "bank_transactions_1"]);
  });

  it("orders a day's rows the same whatever order they arrive in", () => {
    const a = row("bank_transactions", "4", "2026-10-03");
    const b = row("credit_card_transactions", "9", "2026-10-03");
    const c = row("credit_card_transactions", "12", "2026-10-03");
    // A retag moves a row from one rule's list to the end of another's, so
    // the pool's union reaches the feed in a different order.
    expect(keys([a, b, c])).toEqual(keys([c, a, b]));
    expect(keys([b, c, a])).toEqual([
      "bank_transactions_4",
      "credit_card_transactions_12",
      "credit_card_transactions_9",
    ]);
  });

  it("keeps a split's parts in part order", () => {
    const first = row("bank_transactions", "7", "2026-10-03", { split_id: 1 });
    const second = row("bank_transactions", "7", "2026-10-03", { split_id: 2 });
    expect(keys([second, first])).toEqual(["bank_transactions_71", "bank_transactions_72"]);
  });
});
