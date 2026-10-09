import { useCallback, useEffect, useRef, useState, type CSSProperties, type RefObject } from "react";

/** Sizing for a panel that hangs off a trigger (a dropdown, a picker). */
export interface AnchoredPanelOptions {
  /** Tallest the panel grows, in px. */
  maxHeight: number;
  /** Shortest it is allowed to shrink to, however little room is left. */
  minHeight?: number;
  /** Narrowest it is drawn, before clamping to the screen. */
  minWidth?: number;
  /** Gap between the trigger and the panel. */
  gap?: number;
  /** Room kept between the panel and the edge of what is visible. */
  margin?: number;
}

/**
 * Position a `position: fixed` panel against its trigger, keyboard included.
 *
 * A dropdown's search box summons the on-screen keyboard, and the keyboard is
 * what made these panels jump. Three things go wrong without care:
 *
 * - **Measuring the wrong screen.** `innerHeight` is the layout viewport; the
 *   keyboard only shrinks the *visual* viewport, and on iOS that one also
 *   scrolls inside the layout viewport. Room is measured in the visible area
 *   (`visualViewport.offsetTop` .. `+ height`, in the same layout-viewport
 *   coordinates `getBoundingClientRect` and fixed positioning use), and the
 *   panel follows it as it resizes *and* scrolls.
 * - **Flipping under the finger.** Re-deciding the direction on every resize
 *   meant tapping the search box at the top of a downward panel shrank the
 *   room below, and the whole panel jumped above the trigger — taking the
 *   search box away from the finger that had just tapped it. The direction is
 *   chosen once, when the panel opens; after that the panel only shrinks to
 *   fit.
 * - **Anchoring an upward panel to the visible height.** Its `bottom` is set
 *   from the layout viewport (`innerHeight`), the frame fixed positioning is
 *   relative to, so it stays glued to the trigger when the visible area moves.
 *
 * @param anchorRef - The trigger the panel hangs off.
 * @param open - Whether the panel is showing; closing resets the direction.
 * @param options - Sizing; see {@link AnchoredPanelOptions}.
 * @returns The panel's inline style: `top` or `bottom`, `left`, `width`,
 *   `maxHeight`.
 */
export function useAnchoredPanel(
  anchorRef: RefObject<HTMLElement | null>,
  open: boolean,
  { maxHeight, minHeight = 120, minWidth = 0, gap = 4, margin = 8 }: AnchoredPanelOptions,
): CSSProperties {
  const [style, setStyle] = useState<CSSProperties>({});
  const direction = useRef<"up" | "down" | null>(null);

  const update = useCallback(() => {
    const anchor = anchorRef.current;
    if (!anchor) return;
    const rect = anchor.getBoundingClientRect();
    const viewport = window.visualViewport;
    const visibleTop = viewport ? viewport.offsetTop : 0;
    const visibleBottom = viewport ? viewport.offsetTop + viewport.height : window.innerHeight;
    const below = visibleBottom - rect.bottom - gap - margin;
    const above = rect.top - visibleTop - gap - margin;
    if (direction.current === null) {
      direction.current = below < maxHeight && above > below ? "up" : "down";
    }
    const up = direction.current === "up";
    const screenWidth = window.innerWidth;
    const width = Math.min(Math.max(rect.width, minWidth), screenWidth - 2 * margin);
    const left = Math.max(margin, Math.min(rect.left, screenWidth - width - margin));
    const next: CSSProperties = {
      ...(up
        ? { bottom: window.innerHeight - rect.top + gap }
        : { top: rect.bottom + gap }),
      left,
      width,
      maxHeight: Math.max(minHeight, Math.min(maxHeight, up ? above : below)),
    };
    // Scrolling fires constantly; re-render only when the panel actually moves.
    setStyle((current) => (sameStyle(current, next) ? current : next));
  }, [anchorRef, gap, margin, maxHeight, minHeight, minWidth]);

  useEffect(() => {
    if (!open) {
      direction.current = null;
      return;
    }
    update();
    // Keyboard animations and scrolling fire these many times a frame; one
    // measurement per frame is all the panel can show anyway.
    let frame = 0;
    const schedule = () => {
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        update();
      });
    };
    const viewport = window.visualViewport;
    window.addEventListener("scroll", schedule, true);
    window.addEventListener("resize", schedule);
    viewport?.addEventListener("resize", schedule);
    viewport?.addEventListener("scroll", schedule);
    return () => {
      if (frame) cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule, true);
      window.removeEventListener("resize", schedule);
      viewport?.removeEventListener("resize", schedule);
      viewport?.removeEventListener("scroll", schedule);
    };
  }, [open, update]);

  return style;
}

/** Whether two panel styles place the panel identically. */
function sameStyle(one: CSSProperties, other: CSSProperties): boolean {
  const keys = ["top", "bottom", "left", "width", "maxHeight"] as const;
  return keys.every((key) => one[key] === other[key]);
}
