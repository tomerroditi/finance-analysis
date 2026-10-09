import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import type { RefObject } from "react";
import { useAnchoredPanel } from "./useAnchoredPanel";

/**
 * The on-screen keyboard shrinks (and on iOS scrolls) the *visual* viewport,
 * which is what made dropdown panels jump: they measured `innerHeight`,
 * re-decided their direction on every resize, and flipped above their
 * trigger the moment the search box summoned the keyboard. jsdom has no
 * visual viewport, so a minimal one stands in.
 */
class FakeViewport extends EventTarget {
  height: number;
  offsetTop = 0;
  constructor(height: number) {
    super();
    this.height = height;
  }
  /** Simulate the keyboard: shrink (and optionally scroll) the visible area. */
  keyboard(height: number, offsetTop = 0) {
    this.height = height;
    this.offsetTop = offsetTop;
    this.dispatchEvent(new Event("resize"));
    this.dispatchEvent(new Event("scroll"));
  }
}

let viewport: FakeViewport;

/** A trigger whose box sits at `top`..`bottom` of an 800px-tall layout viewport. */
function anchorAt(top: number, bottom: number): RefObject<HTMLElement> {
  const element = document.createElement("button");
  element.getBoundingClientRect = () =>
    ({ top, bottom, left: 20, right: 320, width: 300, height: bottom - top, x: 20, y: top }) as DOMRect;
  return { current: element };
}

beforeEach(() => {
  viewport = new FakeViewport(800);
  vi.stubGlobal("visualViewport", viewport);
  vi.spyOn(window, "innerHeight", "get").mockReturnValue(800);
  vi.spyOn(window, "innerWidth", "get").mockReturnValue(400);
  // Run each scheduled frame at once so a resize lands synchronously. The
  // id is 0, as if the frame had already run, so the next event schedules
  // another rather than waiting on this one.
  vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
    cb(0);
    return 0;
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("useAnchoredPanel", () => {
  it("opens below a trigger with room under it", () => {
    const anchor = anchorAt(100, 140);
    const { result } = renderHook(() => useAnchoredPanel(anchor, true, { maxHeight: 208 }));

    expect(result.current).toMatchObject({ top: 144, maxHeight: 208 });
    expect(result.current.bottom).toBeUndefined();
  });

  it("keeps opening downward when the keyboard takes the room below", () => {
    // A trigger mid-screen opens down; tapping its search box raises a
    // keyboard that leaves 200px visible. The panel shrinks to fit rather
    // than jumping above the trigger, away from the finger.
    const anchor = anchorAt(300, 340);
    const { result } = renderHook(() => useAnchoredPanel(anchor, true, { maxHeight: 208 }));
    expect(result.current.top).toBe(344);

    act(() => viewport.keyboard(500));

    expect(result.current.top).toBe(344);
    expect(result.current.bottom).toBeUndefined();
    // 500 visible - 340 trigger bottom - 4 gap - 8 margin.
    expect(result.current.maxHeight).toBe(148);
  });

  it("measures the visible area, not the layout viewport", () => {
    // With the keyboard up only 400px are visible, so a trigger at 300 opens
    // upward even though the layout viewport has 460px below it.
    viewport.height = 400;
    const anchor = anchorAt(300, 340);
    const { result } = renderHook(() => useAnchoredPanel(anchor, true, { maxHeight: 208 }));

    expect(result.current.top).toBeUndefined();
    // An upward panel is anchored in the layout viewport fixed positioning
    // uses: 800 - 300 trigger top + 4 gap.
    expect(result.current.bottom).toBe(504);
  });

  it("follows the visible area when it scrolls under the keyboard", () => {
    const anchor = anchorAt(600, 640);
    const { result } = renderHook(() => useAnchoredPanel(anchor, true, { maxHeight: 208 }));
    expect(result.current.bottom).toBe(204);

    // iOS scrolls the visual viewport down by 250px to show the field: there
    // is now more room above the trigger within what is visible.
    act(() => viewport.keyboard(450, 250));

    expect(result.current.bottom).toBe(204);
    // 600 trigger top - 250 visible top - 4 gap - 8 margin, capped at 208.
    expect(result.current.maxHeight).toBe(208);
  });

  it("chooses its direction afresh each time it opens", () => {
    let open = true;
    const anchor = anchorAt(300, 340);
    const { result, rerender } = renderHook(() =>
      useAnchoredPanel(anchor, open, { maxHeight: 208 }),
    );
    expect(result.current.top).toBe(344);

    open = false;
    rerender();
    viewport.height = 400;
    open = true;
    rerender();

    expect(result.current.bottom).toBe(504);
  });

  it("never shrinks below its minimum", () => {
    // 150px visible, with a trigger in the middle: 48px free above, 38 below.
    viewport.height = 150;
    const anchor = anchorAt(60, 100);
    const { result } = renderHook(() => useAnchoredPanel(anchor, true, { maxHeight: 208, minHeight: 120 }));

    expect(result.current.maxHeight).toBe(120);
  });
});
