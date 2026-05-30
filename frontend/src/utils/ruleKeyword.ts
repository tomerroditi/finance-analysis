/**
 * Generic transaction-statement boilerplate that precedes (or stands in for) a
 * real merchant name. These act as cut points: the meaningful merchant prefix
 * is whatever comes *before* the first generic word. Bilingual (English +
 * Hebrew). Conservative on purpose — over-listing would chop legitimate
 * merchant names (e.g. "Credit Suisse").
 */
const GENERIC_WORDS = new Set<string>([
  // English bank / card statement boilerplate
  "credit", "card", "bill", "billing", "payment", "payments", "pmt", "debit",
  "charge", "fee", "transaction", "txn", "transfer", "withdrawal", "deposit",
  "purchase", "pos", "ref", "reference", "invoice", "receipt",
  // Hebrew equivalents
  "אשראי", "כרטיס", "חיוב", "תשלום", "תשלומים", "עסקה", "העברה", "משיכה",
  "הפקדה", "חשבונית", "עמלה", "קנייה",
]);

// Whitespace + separator punctuation. Used to trim the ENDS of a slice only.
const EDGE_TRIM = /^[\s\-_/\\.|*#@,:;&]+|[\s\-_/\\.|*#@,:;&]+$/gu;

// Word tokens for generic-word detection (Latin + Hebrew letter runs).
const WORD_RE = /[A-Za-z֐-׿]+/g;

/**
 * Derive a keyword from a transaction description, suitable as the value for a
 * `description contains` auto-tagging condition.
 *
 * **Correctness invariant:** the returned keyword is always a *verbatim
 * substring* of the original description. A `contains` rule matches via SQL
 * `LIKE '%value%'` against the raw stored text, so the value must appear in it
 * literally. The previous implementation *mutated* the text (e.g. replaced `-`
 * with a space), producing keywords that were no longer substrings —
 * `"CREDIT CARD BILL - MAX"` became `"CREDIT CARD BILL MAX"` and matched zero
 * transactions. We therefore only ever *slice* the original and *trim its
 * ends*; interior characters (dashes, dots, separators) are left untouched.
 *
 * Strategy: keep the leading portion of the description up to the first of
 * either a digit (reference / card / invoice numbers, dates, amounts — all
 * per-transaction noise) or a generic statement word (see {@link
 * GENERIC_WORDS}). Then trim whitespace / separator punctuation from both ends.
 *
 * Returns `""` when nothing usable remains — e.g. the description leads with a
 * generic word (`"CREDIT CARD BILL - MAX"`) or a number, or only a single
 * character survives. The caller then offers no initial condition and opens an
 * empty rule builder instead of seeding one that would match nothing.
 */
export function deriveRuleKeyword(description: string | undefined | null): string {
  const original = (description ?? "").trim();
  if (!original) return "";

  // Cut point 1: the first digit.
  const firstDigit = original.search(/\d/);
  let cutAt = firstDigit === -1 ? original.length : firstDigit;

  // Cut point 2: the first generic word that starts before cutAt.
  WORD_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = WORD_RE.exec(original)) !== null) {
    if (match.index >= cutAt) break;
    if (GENERIC_WORDS.has(match[0].toLowerCase())) {
      cutAt = match.index;
      break;
    }
  }

  // Slice + trim ends only — keeps the result a contiguous substring.
  const keyword = original.slice(0, cutAt).replace(EDGE_TRIM, "");

  // A single leftover character is noise, not a merchant name.
  return keyword.length >= 2 ? keyword : "";
}
