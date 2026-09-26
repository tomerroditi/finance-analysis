import { describe, it, expect } from "vitest";

/**
 * A dialog must scroll itself, never the page behind it.
 *
 * The savings-goal editor outgrew a laptop screen and nothing inside it could
 * scroll: the panel capped its height and clipped the rest (Save included),
 * and a scroll gesture over it had nowhere to go but the dashboard behind.
 * The transaction delete confirmation and the Settings popup had the other
 * half of the bug — no scroll lock, so the page scrolled under them freely.
 *
 * Two rules hold it down:
 *
 * 1. The shared `Modal` owns a scroll body (`flex-1 min-h-0 overflow-y-auto
 *    overscroll-contain`) around its children, so every `<Modal>` scrolls its
 *    own content however tall it grows.
 * 2. A hand-rolled overlay (anything `fixed inset-0` that dims or centres a
 *    dialog, rather than a transparent click-catcher) must do the same by
 *    hand: lock the page with `useScrollLock`, carry the `modal-overlay`
 *    class, cap its panel's height and give it a scroll region.
 *
 * The behavioural half lives in `e2e/budget-savings-goal.spec.ts`, which
 * scrolls the goal editor on a short viewport and checks the page stays put.
 *
 * Source is read through `import.meta.glob` rather than `node:fs` because
 * `tsconfig.app.json` is browser-only.
 */

const SOURCES = import.meta.glob("./**/*.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

/** A `fixed inset-0` class list that is a dialog backdrop, not a click-catcher. */
function overlayLines(source: string): string[] {
  return source
    .split("\n")
    .filter(
      (line) =>
        /(?<![\w-])fixed inset-0(?![\w-])/.test(line) &&
        /modal-overlay|bg-black\/|justify-center/.test(line),
    );
}

const HAND_ROLLED = Object.entries(SOURCES).filter(
  ([path, source]) =>
    !path.endsWith(".test.tsx") &&
    path !== "./components/common/Modal.tsx" &&
    overlayLines(source).length > 0,
);

describe("dialogs scroll themselves, never the page", () => {
  it("the shared Modal wraps its children in a scroll body", () => {
    const modal = SOURCES["./components/common/Modal.tsx"];
    expect(modal).toBeDefined();
    const body = modal.match(/<div className="([^"]*)">\s*\{children\}/);
    expect(body, "Modal must wrap {children} in a scroll body").not.toBeNull();
    for (const cls of ["min-h-0", "overflow-y-auto", "overscroll-contain"]) {
      expect(body![1].split(/\s+/)).toContain(cls);
    }
    expect(modal).toMatch(/useScrollLock\(isOpen\)/);
    expect(modal).toMatch(/max-h-\[/);
  });

  it("finds the hand-rolled overlays it is meant to police", () => {
    expect(HAND_ROLLED.length).toBeGreaterThan(5);
  });

  it.each(HAND_ROLLED.map(([path]) => [path]))(
    "%s locks the page, caps its panel and scrolls its body",
    (path) => {
      const source = SOURCES[path];
      const problems: string[] = [];
      if (!/useScrollLock\(/.test(source)) problems.push("no useScrollLock()");
      if (!overlayLines(source).some((line) => line.includes("modal-overlay"))) {
        problems.push("overlay lacks the modal-overlay class");
      }
      if (!/(?<![\w-])(?:max-h-|h-dvh|sm:h-\[)/.test(source)) {
        problems.push("panel height is never capped");
      }
      if (!/(?<![\w-])overflow(?:-y)?-(?:auto|scroll)(?![\w-])/.test(source)) {
        problems.push("no scroll region inside the dialog");
      }
      expect(problems, `${path}: prefer <Modal>, or fix by hand`).toEqual([]);
    },
  );
});
