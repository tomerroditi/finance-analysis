/**
 * A "→" that points the way the text reads: mirrored under RTL.
 *
 * The arrow glyph is not bidi-mirrored (only brackets are), so a bare `→` or
 * `&rarr;` keeps pointing right in Hebrew — backwards, away from where a
 * "View all →" link leads. `rtlArrows.test.ts` keeps raw arrows out of markup.
 */
export function ForwardArrow({ className = "" }: { className?: string }) {
  return (
    <span aria-hidden="true" className={`inline-block rtl:-scale-x-100 ${className}`}>
      →
    </span>
  );
}
