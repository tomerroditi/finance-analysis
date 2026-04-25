import { useEffect, useRef, useState } from "react";
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

/**
 * Accessible info tooltip with desktop hover + mobile tap-to-toggle support.
 * Tapping outside the tooltip dismisses it.
 */
export function InfoTooltip({
  text,
  iconSize = 14,
  className = "",
  width = 200,
  placement = "top",
}: InfoTooltipProps) {
  const [show, setShow] = useState(false);
  const wrapRef = useRef<HTMLSpanElement | null>(null);

  useEffect(() => {
    if (!show) return;
    const handler = (e: MouseEvent | TouchEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setShow(false);
      }
    };
    document.addEventListener("mousedown", handler);
    document.addEventListener("touchstart", handler);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("touchstart", handler);
    };
  }, [show]);

  const placementClasses =
    placement === "top" ? "bottom-full mb-2" : "top-full mt-2";

  return (
    <span ref={wrapRef} className={`group/tip relative inline-flex ${className}`}>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setShow((v) => !v);
        }}
        className="text-[var(--text-muted)] hover:text-white transition-colors inline-flex items-center"
        aria-label="More info"
      >
        <Info size={iconSize} />
      </button>
      <span
        style={{ width, maxWidth: "calc(100vw - 3rem)" }}
        className={`absolute start-0 ${placementClasses} p-2 rounded-lg bg-[var(--surface-light)] text-[10px] leading-snug text-white pointer-events-none z-20 shadow-xl border border-white/5 transition-opacity ${show ? "opacity-100" : "opacity-0"} md:group-hover/tip:opacity-100`}
      >
        {text}
      </span>
    </span>
  );
}
