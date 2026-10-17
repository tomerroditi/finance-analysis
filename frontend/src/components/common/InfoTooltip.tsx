import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Info } from "lucide-react";

interface InfoTooltipProps {
  text: string;
  iconSize?: number;
  className?: string;
  /** Tooltip width in pixels for the inner panel. Defaults to 200. */
  width?: number;
  /** Where the tooltip pops up relative to the icon. */
  placement?: "top" | "bottom";
}

/** Breathing room kept between the panel and whatever edge would clip it. */
const EDGE_MARGIN = 8;

/**
 * Horizontal bounds the panel must stay inside: the viewport, narrowed by
 * every clipping ancestor. Modal bodies scroll vertically with
 * `overflow-x-hidden`, so a panel anchored near their end edge is cut off long
 * before it reaches the viewport edge.
 */
function clipBounds(el: HTMLElement): { start: number; end: number } {
  let start = 0;
  let end = document.documentElement.clientWidth;
  let parent = el.parentElement;
  while (parent) {
    if (getComputedStyle(parent).overflowX !== "visible") {
      const rect = parent.getBoundingClientRect();
      start = Math.max(start, rect.left);
      end = Math.min(end, rect.right);
    }
    parent = parent.parentElement;
  }
  return { start: start + EDGE_MARGIN, end: end - EDGE_MARGIN };
}

/**
 * Accessible info tooltip with desktop hover + mobile tap-to-toggle support.
 * Tapping outside the tooltip dismisses it.
 *
 * The panel is anchored to the icon, so on a card near the container's end
 * edge it would render past it. Before it becomes visible the panel is
 * placed and shifted back inside its clipping bounds (and capped to their
 * width), which works the same in LTR and RTL.
 *
 * A closed panel is `display: none`, not just transparent: a transparent one
 * still occupies layout at its unshifted spot, and on a phone a page full of
 * them near the end edge scrolls sideways into empty space.
 */
export function InfoTooltip({
  text,
  iconSize = 14,
  className = "",
  width = 200,
  placement = "top",
}: InfoTooltipProps) {
  const { t } = useTranslation();
  const [show, setShow] = useState(false);
  const wrapRef = useRef<HTMLSpanElement | null>(null);
  const panelRef = useRef<HTMLSpanElement | null>(null);
  const [shift, setShift] = useState(0);
  const [maxWidth, setMaxWidth] = useState<number | null>(null);

  /**
   * Work out where the panel lands and shift it back inside its clipping
   * bounds. Called before the panel is revealed — on tap, on focus, and on
   * pointer enter for the CSS-driven desktop hover — so it never paints in the
   * clipped spot.
   *
   * The unshifted spot is computed from the anchor rather than measured: the
   * panel is pinned to the anchor's start edge at a known width, and laying it
   * out there even for a moment is enough for a mobile browser to widen its
   * layout viewport to fit it, leaving the page scrollable sideways for good.
   */
  const reposition = useCallback(() => {
    const panel = panelRef.current;
    const anchor = wrapRef.current;
    if (!panel || !anchor) return;
    const { start, end } = clipBounds(panel);
    const available = Math.max(0, end - start);
    const nextMaxWidth = Math.min(width, available);
    const box = anchor.getBoundingClientRect();
    const rtl = getComputedStyle(anchor).direction === "rtl";
    const left = rtl ? box.right - nextMaxWidth : box.left;
    let next = 0;
    if (left + nextMaxWidth > end) next = end - (left + nextMaxWidth);
    if (left + next < start) next = start - left;
    panel.style.maxWidth = `${nextMaxWidth}px`;
    panel.style.transform = `translateX(${next}px)`;
    setMaxWidth(nextMaxWidth);
    setShift(next);
  }, [width]);

  useLayoutEffect(() => {
    if (show) reposition();
  }, [show, reposition]);

  useEffect(() => {
    if (!show) return;
    const handler = (e: MouseEvent | TouchEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setShow(false);
      }
    };
    document.addEventListener("mousedown", handler);
    document.addEventListener("touchstart", handler);
    window.addEventListener("resize", reposition);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("touchstart", handler);
      window.removeEventListener("resize", reposition);
    };
  }, [show, reposition]);

  const placementClasses =
    placement === "top" ? "bottom-full mb-2" : "top-full mt-2";

  return (
    <span
      ref={wrapRef}
      className={`group/tip relative inline-flex ${className}`}
      onPointerEnter={reposition}
    >
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setShow((v) => !v);
        }}
        onFocus={reposition}
        className="p-2 -m-2 text-[var(--text-muted)] hover:text-white transition-colors inline-flex items-center"
        aria-label={t("common.moreInfo")}
      >
        <Info size={iconSize} />
      </button>
      <span
        ref={panelRef}
        data-testid="info-tooltip-panel"
        style={{
          width,
          maxWidth: maxWidth ?? "calc(100vw - 3rem)",
          transform: `translateX(${shift}px)`,
        }}
        className={`absolute start-0 ${placementClasses} p-2 rounded-lg bg-[var(--surface-light)] text-[10px] leading-snug text-white pointer-events-none z-20 shadow-xl border border-white/5 ${show ? "block" : "hidden"} md:group-hover/tip:block`}
      >
        {text}
      </span>
    </span>
  );
}
