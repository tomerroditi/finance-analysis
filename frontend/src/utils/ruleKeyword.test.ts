import { describe, it, expect } from "vitest";
import { deriveRuleKeyword } from "./ruleKeyword";

describe("deriveRuleKeyword", () => {
  it("returns an empty string for empty / nullish input", () => {
    expect(deriveRuleKeyword("")).toBe("");
    expect(deriveRuleKeyword(undefined)).toBe("");
    expect(deriveRuleKeyword(null)).toBe("");
    expect(deriveRuleKeyword("   ")).toBe("");
  });

  it("strips URL schemes and domain suffixes", () => {
    expect(deriveRuleKeyword("https://AMAZON.COM")).toBe("AMAZON");
    expect(deriveRuleKeyword("WWW.WOLT.CO.IL")).toBe("WWW WOLT");
  });

  it("replaces separators and noise punctuation with spaces", () => {
    expect(deriveRuleKeyword("SHUFERSAL-DEAL/405")).toBe("SHUFERSAL DEAL");
    expect(deriveRuleKeyword("PAYPAL *NETFLIX")).toBe("PAYPAL NETFLIX");
  });

  it("drops standalone reference / card / invoice numbers", () => {
    expect(deriveRuleKeyword("RIDE 12345 TLV")).toBe("RIDE TLV");
    expect(deriveRuleKeyword("INVOICE 0099 SHOP")).toBe("INVOICE SHOP");
  });

  it("keeps single digits attached to letters intact", () => {
    // A lone single digit is not a 2+ digit run, so it survives.
    expect(deriveRuleKeyword("STORE 7")).toBe("STORE 7");
  });

  it("falls back to the trimmed original when stripping leaves nothing", () => {
    expect(deriveRuleKeyword("12345")).toBe("12345");
    expect(deriveRuleKeyword(".com")).toBe(".com");
  });

  it("collapses repeated whitespace", () => {
    expect(deriveRuleKeyword("FOO    BAR")).toBe("FOO BAR");
  });
});
