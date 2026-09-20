import { describe, it, expect } from "vitest";

/**
 * A scroll container cannot round its own scrollbar away.
 *
 * Blink paints a scrollbar inside the element's *border box*, and
 * `border-radius` clips content, not scrollbar gutters. So an element that is
 * both rounded and its own scroll container gets the scrollbar drawn across
 * its rounded corners and over its border — the Settings popup shipped that
 * way (`rounded-2xl … p-4 sm:p-6 overflow-y-auto`) and the 8px track visibly
 * cut the corner. Nothing in type-checking, lint, or a className assertion
 * notices, and the app's own `::-webkit-scrollbar` styling makes it more
 * obvious than a native overlay scrollbar would: it is a reviewer's-eye bug
 * that only a scan can hold down.
 *
 * The same defect has a second shape: a rounded *panel* that clamps its
 * height, stacks children in a column and lets one of them scroll. The panel
 * clips nothing, so the child's scrollbar runs over the panel's rounded
 * corners instead. `BudgetAlertsPopup` and both dropdown popovers were that.
 *
 * The fix for either is the same — the radius goes on a non-scrolling parent
 * that carries `overflow-hidden`, so the corner clips the scrollbar, and the
 * scrolling element sits inside it:
 *
 *     <div className="rounded-2xl border overflow-hidden flex flex-col max-h-[90vh]">
 *       <div className="flex-1 min-h-0 overflow-y-auto p-4">…</div>
 *     </div>
 *
 * The behavioural half of this guard lives in `e2e/dashboard-layout.spec.ts`,
 * which reads the Settings popup's geometry in a real browser.
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

/** `rounded`, `rounded-xl`, `rounded-se-lg`, `rounded-full`, … */
const ROUNDED =
  /(?<![\w-])rounded(?:-(?:s|e|t|b|ss|se|es|ee|tl|tr|bl|br))?(?:-(?:sm|md|lg|xl|2xl|3xl|full))?(?![\w-])/;
/** Anything that makes the element its own scrollport. */
const SCROLLS = /(?<![\w-])overflow(?:-x|-y)?-(?:auto|scroll)(?![\w-])/;
/** Anything that makes the element clip — what a rounded parent needs. */
const CLIPS = /(?<![\w-])overflow(?:-x|-y)?-(?:hidden|clip)(?![\w-])/;
/** A height clamp, i.e. "something in here is expected to scroll". */
const CLAMPS_HEIGHT = /(?<![\w-])max-h-(?!none(?![\w-]))/;
const COLUMN = /(?<![\w-])flex-col(?![\w-])/;

/**
 * Every class list a file can produce: each `className` value as written,
 * plus every bare string and template literal (a class list extracted to a
 * constant is still a class list).
 *
 * The `className` pass is brace-balanced rather than regex-delimited, so a
 * template literal (`` className={`${BAR_CONTROL} rounded-xl …`} ``) is read
 * whole — its `${…}` closes a brace and truncates a naive match, which is
 * exactly how the budget command bar's strip hid from the first version of
 * this scan. It also keeps concatenations and ternaries intact, where the
 * radius and the overflow sit in different literals.
 */
function classCandidates(source: string): { line: number; value: string }[] {
  const found = new Map<string, { line: number; value: string }>();
  const lineOf = (index: number) => source.slice(0, index).split("\n").length;

  const add = (index: number, value: string) => {
    const line = lineOf(index);
    found.set(`${line}:${value}`, { line, value });
  };

  for (const match of source.matchAll(/className=/g)) {
    const start = match.index + match[0].length;

    if (source[start] === '"') {
      const end = source.indexOf('"', start + 1);
      if (end !== -1) add(match.index, source.slice(start + 1, end));
    } else if (source[start] === "{") {
      let depth = 0;
      for (let i = start; i < source.length; i++) {
        if (source[i] === "{") depth++;
        else if (source[i] === "}" && --depth === 0) {
          add(match.index, source.slice(start + 1, i));
          break;
        }
      }
    }
  }

  for (const match of source.matchAll(/"([^"\n]*)"|'([^'\n]*)'|`([^`]*)`/g)) {
    add(match.index, match[1] ?? match[2] ?? match[3] ?? "");
  }

  return [...found.values()];
}

describe("rounded scroll containers", () => {
  it("never puts a corner radius on the element that scrolls", () => {
    const offenders: string[] = [];

    for (const [path, source] of Object.entries(SOURCES)) {
      if (/\.test\.tsx?$/.test(path)) continue;

      for (const { line, value } of classCandidates(source)) {
        if (SCROLLS.test(value) && ROUNDED.test(value)) {
          offenders.push(
            `${path}:${line} — this element is rounded and scrolls, so its ` +
              `scrollbar paints over its own rounded corners. Move the radius ` +
              `(and any border/background) to a parent with \`overflow-hidden\` ` +
              `and leave the scrolling on the child.`,
          );
        }
      }
    }

    expect(offenders).toEqual([]);
  });

  it("clips rounded panels that hold a scrolling child", () => {
    const offenders: string[] = [];

    for (const [path, source] of Object.entries(SOURCES)) {
      if (/\.test\.tsx?$/.test(path)) continue;

      for (const { line, value } of classCandidates(source)) {
        const isClampedPanel =
          ROUNDED.test(value) && CLAMPS_HEIGHT.test(value) && COLUMN.test(value);

        if (isClampedPanel && !CLIPS.test(value) && !SCROLLS.test(value)) {
          offenders.push(
            `${path}:${line} — a rounded panel that clamps its height and ` +
              `stacks children in a column has something scrolling inside it, ` +
              `and without \`overflow-hidden\` that child's scrollbar runs over ` +
              `the panel's rounded corners.`,
          );
        }
      }
    }

    expect(offenders).toEqual([]);
  });
});
