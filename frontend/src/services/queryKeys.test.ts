import { describe, expect, it } from "vitest";
import { makeQueryKeys, qkPrefix } from "./queryKeys";

describe("makeQueryKeys", () => {
  it("appends the demo flag as the last segment of every key", () => {
    const k = makeQueryKeys(true);
    expect(k.transactions.list("all", false)).toEqual([
      "transactions", "list", "all", false, true,
    ]);
    expect(k.analytics.sankey()).toEqual(["analytics", "sankey", true]);
    expect(k.budget.analysis(2026, 7, false)).toEqual([
      "budget", "analysis", 2026, 7, false, true,
    ]);
  });

  it("produces keys that start with their invalidation prefix", () => {
    const k = makeQueryKeys(false);
    const cases: Array<[readonly unknown[], readonly unknown[]]> = [
      [k.transactions.uncategorizedCount(), qkPrefix.transactions],
      [k.analytics.netWorthOverTime(), qkPrefix.analytics],
      [k.budget.monthOverrides(), qkPrefix.budget],
      [k.investments.portfolio(), qkPrefix.investments],
      [k.liabilities.debtOverTime(), qkPrefix.liabilities],
      [k.pendingRefunds.all(), qkPrefix.pendingRefunds],
    ];
    for (const [key, prefix] of cases) {
      expect(key.slice(0, prefix.length)).toEqual([...prefix]);
    }
  });

  it("keeps persistence-excluded heads stable", () => {
    const k = makeQueryKeys(false);
    expect(k.scraping.lastScrapes()[0]).toBe("last-scrapes");
    expect(k.credentials.providers()[0]).toBe("providers");
    expect(k.credentials.accounts()[0]).toBe("credentials-accounts");
  });

  it("gives the two income-by-source endpoints distinct keys", () => {
    const k = makeQueryKeys(false);
    expect(k.analytics.incomeBySourceOverTime()).not.toEqual(
      k.analytics.incomeBySource(undefined, undefined),
    );
  });

  it("transactionsList prefix matches list keys but not the count key", () => {
    const k = makeQueryKeys(false);
    const list = k.transactions.list("all", false);
    const count = k.transactions.uncategorizedCount();
    expect(list.slice(0, qkPrefix.transactionsList.length)).toEqual([...qkPrefix.transactionsList]);
    expect(count.slice(0, qkPrefix.transactionsList.length)).not.toEqual([...qkPrefix.transactionsList]);
  });
});
