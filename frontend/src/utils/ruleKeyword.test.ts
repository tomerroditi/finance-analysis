import { describe, it, expect } from "vitest";
import { deriveRuleKeyword } from "./ruleKeyword";

describe("deriveRuleKeyword", () => {
  it("returns an empty string for empty / nullish input", () => {
    expect(deriveRuleKeyword("")).toBe("");
    expect(deriveRuleKeyword(undefined)).toBe("");
    expect(deriveRuleKeyword(null)).toBe("");
    expect(deriveRuleKeyword("   ")).toBe("");
  });

  it("always returns a verbatim substring of the original (the core invariant)", () => {
    // A contains-rule matches the RAW description via LIKE, so the keyword must
    // appear literally. We must never mutate interior characters.
    const samples = [
      "SHUFERSAL DEAL 405",
      "AMAZON.COM*A1B2",
      "WOLT - TEL AVIV",
      "PAYPAL *NETFLIX 12",
    ];
    for (const s of samples) {
      const k = deriveRuleKeyword(s);
      if (k) expect(s.includes(k)).toBe(true);
    }
  });

  it("keeps the merchant prefix up to the first digit, verbatim", () => {
    // Dashes/dots are preserved (not turned into spaces) so the result stays a
    // substring.
    expect(deriveRuleKeyword("SHUFERSAL DEAL 405")).toBe("SHUFERSAL DEAL");
    expect(deriveRuleKeyword("WOLT - TEL AVIV 99")).toBe("WOLT - TEL AVIV");
    expect(deriveRuleKeyword("RAMI LEVY")).toBe("RAMI LEVY");
  });

  it("cuts at a generic statement word and trims the trailing separator", () => {
    // "CREDIT" is generic and leads the string -> nothing before it -> empty.
    expect(deriveRuleKeyword("CREDIT CARD BILL - MAX")).toBe("");
    // Real merchant before the generic word -> keep the merchant prefix.
    expect(deriveRuleKeyword("MAX - CREDIT CARD BILL")).toBe("MAX");
    expect(deriveRuleKeyword("ISRACARD PAYMENT")).toBe("ISRACARD");
  });

  it("returns empty when the description leads with a number", () => {
    expect(deriveRuleKeyword("12345 SOME REF")).toBe("");
  });

  it("returns empty when only a single character would survive", () => {
    expect(deriveRuleKeyword("A 12345")).toBe("");
    expect(deriveRuleKeyword("X")).toBe("");
  });

  it("handles Hebrew merchant prefixes and generic words", () => {
    // Generic Hebrew word "חיוב" (billing) leads -> empty.
    expect(deriveRuleKeyword("חיוב כרטיס אשראי")).toBe("");
    // Hebrew merchant before a generic word -> keep the merchant.
    expect(deriveRuleKeyword("רמי לוי תשלום")).toBe("רמי לוי");
  });

  it("trims surrounding separator punctuation from the ends only", () => {
    expect(deriveRuleKeyword("*SPOTIFY* 9")).toBe("SPOTIFY");
  });
});
