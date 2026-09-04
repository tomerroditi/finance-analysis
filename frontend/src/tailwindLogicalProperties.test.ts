import { describe, it, expect } from "vitest";

/**
 * Tailwind 4 names its logical utilities after the *shorthand*, not the CSS
 * property: `start-0`, not `inset-inline-start-0`. A class spelled after the
 * property matches no utility, so Tailwind emits nothing and the browser
 * silently ignores it — the element falls back to its static position rather
 * than raising anything. That failure mode survives review, type-checking,
 * and any test that asserts on className strings, and it shipped five times
 * before it was caught.
 *
 * Some of those five *looked* correct, because the static position happened
 * to coincide with the intended one. Those are the dangerous ones: no
 * behavioural test can catch them, only a source scan can. The behavioural
 * half of this guard lives in `e2e/rtl-logical-insets.spec.ts`.
 *
 * Source is read through `import.meta.glob` rather than `node:fs` because
 * `tsconfig.app.json` is browser-only — a `node:fs` import here fails
 * `npm run build`, not just this test.
 */

const SOURCES = import.meta.glob("./**/*.{ts,tsx}", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

/** Longest property names first — the regex alternation is order-sensitive. */
const PROPERTY_SPELLED_CLASS =
  /(?<![\w-])(inset-inline-start|inset-inline-end|inset-block-start|inset-block-end|inset-inline|inset-block|padding-inline|padding-block|margin-inline|margin-block|border-inline|border-block)-(?=[\w[])/g;

const CORRECT_UTILITY: Record<string, string> = {
  "inset-inline-start": "start-*",
  "inset-inline-end": "end-*",
  "inset-block-start": "top-*",
  "inset-block-end": "bottom-*",
  "inset-inline": "inset-x-*",
  "inset-block": "inset-y-*",
  "padding-inline": "px-* (or ps-* / pe-*)",
  "padding-block": "py-*",
  "margin-inline": "mx-* (or ms-* / me-*)",
  "margin-block": "my-*",
  "border-inline": "border-x-* (or border-s-* / border-e-*)",
  "border-block": "border-y-*",
};

describe("Tailwind logical properties", () => {
  it("uses utility names, not CSS property names, for logical classes", () => {
    const offenders: string[] = [];

    for (const [path, source] of Object.entries(SOURCES)) {
      // This file names the bad classes on purpose.
      if (/\.test\.tsx?$/.test(path)) continue;

      source.split("\n").forEach((line, i) => {
        for (const match of line.matchAll(PROPERTY_SPELLED_CLASS)) {
          const property = match[1];
          offenders.push(
            `${path}:${i + 1} — "${property}-…" is not a Tailwind utility and ` +
              `generates no CSS; use \`${CORRECT_UTILITY[property]}\``,
          );
        }
      });
    }

    expect(offenders).toEqual([]);
  });
});
