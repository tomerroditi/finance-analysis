import { describe, it, expect } from "vitest";
import { matchesSource, sourceOptions } from "./transactionSources";
import type { Transaction } from "../types/transaction";

const tx = (overrides: Partial<Transaction>): Transaction => ({
  amount: -100,
  date: "2026-10-01",
  ...overrides,
});

const visa = tx({ source: "credit_card_transactions", provider: "max", account_name: "Visa", account_number: "11111234" });
const amex = tx({ source: "credit_card_transactions", provider: "amex", account_name: "Gold", account_number: "99995678" });
const bank = tx({ source: "bank_transactions", provider: "hapoalim", account_name: "Main" });
const cash = tx({ source: "cash_transactions", account_name: "Wallet" });

describe("transactionSources", () => {
  it("offers every source, then every kind, then the accounts of kinds with several", () => {
    const options = sourceOptions([bank, cash, visa, amex, visa]);
    expect(options.map((option) => option.label)).toEqual([
      "All sources",
      "All credit cards",
      "All bank accounts",
      "Cash",
      "Amex · Gold ••5678",
      "Max · Visa ••1234",
    ]);
  });

  it("matches a whole kind of source or a single account", () => {
    const options = sourceOptions([bank, visa, amex]);
    const value = (label: string) => options.find((option) => option.label === label)!.value;

    expect(matchesSource(visa, "")).toBe(true);
    expect(matchesSource(visa, value("All credit cards"))).toBe(true);
    expect(matchesSource(amex, value("All credit cards"))).toBe(true);
    expect(matchesSource(bank, value("All credit cards"))).toBe(false);
    expect(matchesSource(visa, value("Max · Visa ••1234"))).toBe(true);
    expect(matchesSource(amex, value("Max · Visa ••1234"))).toBe(false);
  });
});
