/**
 * Derive a generalized keyword from a transaction description, suitable as the
 * value for a `description contains` auto-tagging condition.
 *
 * Raw scraped descriptions often carry noise that defeats generalization across
 * a merchant's transactions: URL schemes / TLDs (`AMAZON.COM`), separators
 * (dashes, slashes, dots), and standalone reference / card / invoice numbers.
 * Stripping them yields a stable merchant token that a `contains` rule can use
 * to catch future transactions from the same source. The user can still refine
 * it in the rule editor before saving.
 *
 * Falls back to the trimmed original when stripping would leave nothing.
 */
export function deriveRuleKeyword(description: string | undefined | null): string {
  const original = (description ?? "").trim();
  if (!original) return "";

  let s = original;
  // Drop URL scheme.
  s = s.replace(/https?:\/\//gi, " ");
  // Drop common domain suffixes (.com, .co.il, .net, ...).
  s = s.replace(
    /\.(com|co\.il|org\.il|gov\.il|ac\.il|net|org|io|co|biz|info|shop|store)\b/gi,
    " ",
  );
  // Separators and noise punctuation -> space.
  s = s.replace(/[-_/\\.|*#@]+/g, " ");
  // Standalone digit runs (2+ digits: reference / card / invoice numbers) -> space.
  s = s.replace(/\b\d{2,}\b/g, " ");
  // Collapse whitespace.
  s = s.replace(/\s+/g, " ").trim();

  return s || original;
}
