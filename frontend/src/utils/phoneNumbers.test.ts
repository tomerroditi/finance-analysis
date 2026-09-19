import { describe, it, expect } from "vitest";
import {
  isValidIsraeliMobile,
  toInternationalMobile,
  toSubscriberDigits,
} from "./phoneNumbers";

describe("phoneNumbers", () => {
  it.each([
    "0501234567",
    "050-1234567",
    "501234567",
    "972501234567",
    "+972 50-123-4567",
    "+972501234567",
  ])("folds %s into the +972 form", (raw) => {
    expect(toSubscriberDigits(raw)).toBe("501234567");
    expect(toInternationalMobile(raw)).toBe("+972501234567");
  });

  it("caps the subscriber part at nine digits", () => {
    expect(toSubscriberDigits("05012345678999")).toBe("501234567");
  });

  it("keeps an empty field empty rather than storing a bare prefix", () => {
    expect(toInternationalMobile("")).toBe("");
  });

  it("accepts only 5 followed by eight digits after +972", () => {
    expect(isValidIsraeliMobile("+972501234567")).toBe(true);
    expect(isValidIsraeliMobile("0501234567")).toBe(false);
    expect(isValidIsraeliMobile("+97250123456")).toBe(false);
    expect(isValidIsraeliMobile("+972212345678")).toBe(false);
    expect(isValidIsraeliMobile("+15551234567")).toBe(false);
  });
});
