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
 * measured and shifted back inside its clipping bounds (and capped to their
 * width), which works the same in LTR and RTL.
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
   * Re-measure the panel and shift it back inside its clipping bounds. Called
   * before the panel is revealed — on tap, on focus, and on pointer enter for
   * the CSS-driven desktop hover — so it never paints in the clipped spot.
   */
  const reposition = useCallback(() => {
    const panel = panelRef.current;
    if (!panel) return;
    const { start, end } = clipBounds(panel);
    const available = Math.max(0, end - start);
    const nextMaxWidth = Math.min(width, available);
    // Measure unshifted and at the width we are about to apply, so repeated
    // openings correct from the same baseline instead of compounding.
    panel.style.transform = "translateX(0px)";
    panel.style.maxWidth = `${nextMaxWidth}px`;
    const rect = panel.getBoundingClientRect();
    let next = 0;
    if (rect.right > end) next = end - rect.right;
    if (rect.left + next < start) next = start - rect.left;
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
        className={`absolute start-0 ${placementClasses} p-2 rounded-lg bg-[var(--surface-light)] text-[10px] leading-snug text-white pointer-events-none z-20 shadow-xl border border-white/5 transition-opacity ${show ? "opacity-100" : "opacity-0"} md:group-hover/tip:opacity-100`}
      >
        {text}
      </span>
    </span>
  );
}
