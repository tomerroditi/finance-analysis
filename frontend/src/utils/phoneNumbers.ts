/**
 * Israeli mobile numbers for providers (OneZero) whose API only accepts the
 * international `+9725XXXXXXXX` form. The input shows a fixed `+972` prefix
 * and the user types only the subscriber part; these helpers translate
 * between that and the stored value. Mirrors `backend/utils/phone_numbers.py`,
 * which re-validates on save.
 */

export const ISRAEL_DIAL_PREFIX = "+972";

const ISRAELI_MOBILE_RE = /^\+9725\d{8}$/;

/** Providers whose `phoneNumber` field must be an Israeli mobile number. */
export const INTERNATIONAL_PHONE_PROVIDERS: ReadonlySet<string> = new Set(["onezero"]);

/**
 * Subscriber digits (`5XXXXXXXX`) from whatever was typed or pasted —
 * `050-1234567`, `+972 50 123 4567` and `972501234567` all yield
 * `501234567`. Capped at nine digits.
 */
export function toSubscriberDigits(value: string): string {
  let digits = value.replace(/\D/g, "");
  if (digits.startsWith("972")) digits = digits.slice(3);
  digits = digits.replace(/^0+/, "");
  return digits.slice(0, 9);
}

/** Stored value for a subscriber-digit string; empty stays empty. */
export function toInternationalMobile(value: string): string {
  const digits = toSubscriberDigits(value);
  return digits ? `${ISRAEL_DIAL_PREFIX}${digits}` : "";
}

export function isValidIsraeliMobile(value: string): boolean {
  return ISRAELI_MOBILE_RE.test(value);
}
