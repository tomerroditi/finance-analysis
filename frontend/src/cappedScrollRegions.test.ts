import { describe, it, expect } from "vitest";

/**
 * A capped scroll region must not swallow the page's scroll.
 *
 * Once an inner scroller has anywhere at all to go, a touch drag that starts
 * on it scrolls *it* and the page stays put — browsers chain to the page only
 * when the inner scroller could not move at all, and they do not start
 * chaining part-way through a drag. So a list capped at a height its content
 * barely passes traps the finger on a phone while hiding nothing worth
 * reaching, which reads as "the page won't scroll here". The savings-goals
 * card shipped that way.
 *
 * The fix is to cap conditionally — `useScrollCap` measures the content and
 * turns the element into a scroll region only once the cap hides about a row:
 *
 *     const [listRef, capped] = useScrollCap(320, rows.length);
 *     <div ref={listRef} className={capped ? "max-h-[20rem] overflow-y-auto" : ""}>
 *
 * A conditional cap is a template literal or ternary, so this scan only ever
 * fires on a class list that carries the cap and the overflow *unconditionally*
 * in one static string.
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

/** A vertical scrollport. `overflow-x-auto` alone is a horizontal one. */
const SCROLLS_Y = /(?<![\w-])overflow(?:-y)?-(?:auto|scroll)(?![\w-])/;
/** A height cap — the thing that makes the element scroll at all. */
const CAPS_HEIGHT = /(?<![\w-])max-h-(?!none(?![\w-]))/;
/**
 * A floor as well as a cap is a pane whose height the layout fixes (a grid
 * cell that must line up with its neighbour). Dropping its cap would move the
 * layout, so these are out of scope — they are sized to hold many rows, not
 * to trim one.
 */
const FIXED_HEIGHT = /(?<![\w-])min-h-(?!0(?![\w-]))/;

/**
 * Where a trapped gesture is the point rather than the bug: a modal, popup or
 * drawer sits over a page whose scroll is locked (or which is not meant to
 * move under it), so its list has nothing to chain to and capping it always
 * earns its keep.
 */
const SCROLL_LOCKED = [
  "/components/modals/", // dialogs, all scroll-locked by `Modal`
  "/components/common/Modal", // the dialog shell itself
  "/components/categories/", // detail panel's relocate dialog
  "/components/layout/SettingsPopup", // popover over a locked page
  "/components/layout/Sidebar", // fixed rail + mobile drawer
  "/components/dataflow/DataFlowDiagram", // bottom sheet
  "/pages/DataSources", // the connection wizard's provider grid (a modal)
];

function classCandidates(source: string): { line: number; value: string }[] {
  const found = new Map<string, { line: number; value: string }>();
  const lineOf = (index: number) => source.slice(0, index).split("\n").length;
  const add = (index: number, value: string) => {
    const line = lineOf(index);
    found.set(`${line}:${value}`, { line, value });
  };

  // Only static class lists: a `{`-delimited value is an expression, which is
  // where a conditional cap lives.
  for (const match of source.matchAll(/className="([^"\n]*)"/g)) {
    add(match.index, match[1]);
  }
  return [...found.values()];
}

describe("capped scroll regions", () => {
  it("never caps a list's height unconditionally outside a scroll-locked surface", () => {
    const offenders: string[] = [];

    for (const [path, source] of Object.entries(SOURCES)) {
      if (/\.test\.tsx?$/.test(path)) continue;
      if (SCROLL_LOCKED.some((fragment) => path.includes(fragment))) continue;

      for (const { line, value } of classCandidates(source)) {
        if (!CAPS_HEIGHT.test(value) || !SCROLLS_Y.test(value)) continue;
        if (FIXED_HEIGHT.test(value)) continue;

        offenders.push(
          `${path}:${line} — this list is capped and scrollable no matter how ` +
            `little it holds, so a drag that starts on it is swallowed even ` +
            `when there is nothing to scroll to. Cap it through ` +
            `\`useScrollCap\` instead.`,
        );
      }
    }

    expect(offenders).toEqual([]);
  });
});
