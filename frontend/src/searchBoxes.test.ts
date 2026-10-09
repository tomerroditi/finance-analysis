import { describe, it, expect } from "vitest";

/**
 * Search boxes must not make the screen jump when the phone keyboard opens.
 *
 * A search box is where the on-screen keyboard comes up, and the keyboard is
 * what shoved the dropdown pickers around: one focused its search box on every
 * open, popping the keyboard before anyone chose to type, and the panel then
 * flipped to the other side of its trigger as the keyboard took the room —
 * away from the finger on the search box. The standard (see
 * `.claude/rules/frontend_pitfalls.md` → "Search Boxes and the On-Screen
 * Keyboard"):
 *
 * 1. Every search box asks for the search keyboard and no suggestions:
 *    `inputMode="search"`, `enterKeyHint="search"`, `autoComplete="off"`.
 * 2. No search box is `autoFocus`ed — that pops the keyboard on open.
 * 3. A search box focused from code is focused with `preventScroll: true`,
 *    and only off touch screens (`isTouchDevice`).
 * 4. A search box in a floating (portaled) panel positions that panel with
 *    `useAnchoredPanel`, never by hand against `innerHeight`.
 *
 * The behavioural half lives in `e2e/budget-savings-goal.spec.ts`, which opens
 * a picker on a phone viewport and shrinks it as a keyboard would.
 *
 * Source is read through `import.meta.glob` rather than `node:fs` because
 * `tsconfig.app.json` is browser-only.
 */

const SOURCES = import.meta.glob("./**/*.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

/** Component sources, without their tests. */
const COMPONENTS = Object.entries(SOURCES).filter(
  ([path]) => !path.endsWith(".test.tsx"),
);

/** Every `<input … />` element in a source file. */
function inputs(source: string): string[] {
  return source.match(/<input\b[\s\S]*?\/>/g) ?? [];
}

/**
 * Whether an input is a search box: `type="search"`, or a placeholder or
 * label drawn from a translation key about searching.
 */
function isSearchBox(element: string): boolean {
  return (
    /type="search"/.test(element) ||
    /(placeholder|aria-label)=\{t\("[^"]*[Ss]earch[^"]*"\)/.test(element)
  );
}

/** `[file, element]` for every search box in the app. */
const SEARCH_BOXES = COMPONENTS.flatMap(([path, source]) =>
  inputs(source)
    .filter(isSearchBox)
    .map((element) => [path, element] as const),
);

describe("search boxes", () => {
  it("are found (the scan itself works)", () => {
    // The pickers and the page-level search fields: if this drops to zero
    // the detection broke, and every assertion below would pass vacuously.
    expect(SEARCH_BOXES.length).toBeGreaterThanOrEqual(7);
  });

  it.each(SEARCH_BOXES)("%s asks for the search keyboard without suggestions", (_path, element) => {
    expect(element).toContain('inputMode="search"');
    expect(element).toContain('enterKeyHint="search"');
    expect(element).toContain('autoComplete="off"');
  });

  it.each(SEARCH_BOXES)("%s is never autofocused", (_path, element) => {
    expect(element).not.toMatch(/\bautoFocus\b/);
  });

  it("are only focused from code off touch screens, without scrolling", () => {
    const offenders = COMPONENTS.flatMap(([path, source]) => {
      const focusCalls = source.match(/search\w*Ref\.current\??\.focus\([^)]*\)/g) ?? [];
      return focusCalls
        .filter((call) => !call.includes("preventScroll") || !source.includes("isTouchDevice"))
        .map((call) => `${path}: ${call}`);
    });
    expect(offenders).toEqual([]);
  });

  it("in a floating panel position it with useAnchoredPanel", () => {
    const offenders = COMPONENTS.filter(
      ([, source]) =>
        source.includes("createPortal") &&
        inputs(source).some(isSearchBox) &&
        !source.includes("useAnchoredPanel"),
    ).map(([path]) => path);
    expect(offenders).toEqual([]);
  });
});
