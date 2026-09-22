import { useEffect, useRef, useState } from "react";

/**
 * Default slack: roughly one list row. Below this, capping hides too little
 * to be worth what it costs.
 */
const DEFAULT_SLACK_PX = 96;

/**
 * Cap a list's height, but only once the cap reaches something worth reaching.
 *
 * A scroll region swallows the gesture that starts on it: once an inner
 * scroller has anywhere at all to go, a touch drag scrolls it and the page
 * stays put — browsers chain to the page only when the inner scroller could
 * not move at all, and they do not resume chaining part-way through a drag.
 * So a list that scrolls by a hair traps the finger on a phone while hiding
 * nothing, which reads as "the page won't scroll here".
 *
 * Applying the cap conditionally fixes that: below the threshold the element
 * is a plain block and a drag across it scrolls the page like any other
 * content. The measurement is `scrollHeight`, which is the content's height
 * whether or not the cap is on, so the reading cannot flip-flop.
 *
 * ```tsx
 * const [listRef, capped] = useScrollCap(320, rows.length);
 * <div ref={listRef} className={capped ? "max-h-[20rem] overflow-y-auto" : ""}>
 * ```
 *
 * Parameters
 * ----------
 * capPx
 *   The capped height in pixels — the same number the class applies.
 * contentKey
 *   Anything that changes when the content does (a length, the data array).
 *   A capped element's own box stops changing size, so a resize observer
 *   alone would not notice rows being added.
 * slackPx
 *   How far past the cap the content must reach before capping is applied.
 *
 * Returns
 * -------
 * A ref to put on the scroll region, and whether to cap it.
 */
export function useScrollCap<T extends HTMLElement = HTMLDivElement>(
  capPx: number,
  contentKey?: unknown,
  slackPx: number = DEFAULT_SLACK_PX,
) {
  const ref = useRef<T>(null);
  const [capped, setCapped] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => setCapped(el.scrollHeight > capPx + slackPx);
    measure();
    // Width changes wrap text and grow rows, so the reading is re-taken on
    // resize as well as on a change of content.
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [capPx, slackPx, contentKey]);

  return [ref, capped] as const;
}
