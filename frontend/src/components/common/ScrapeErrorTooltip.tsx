import { useCallback, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Info } from "lucide-react";

interface ScrapeErrorTooltipProps {
  /**
   * Technical detail recorded by the backend — the provider's own message, HTTP
   * body or exception text. Shown as secondary copy, never as the headline.
   */
  message?: string;
  /**
   * Failure category from the backend (`INVALID_PASSWORD`, `TIMEOUT`, …). Picks
   * the translated explanation. Undefined for scrapes recorded before the
   * backend tracked it — those fall back to showing `message` alone.
   */
  errorType?: string;
}

/**
 * Categories with their own translated explanation under
 * `dataSources.scrapeError.*`. Anything else falls back to the generic copy, so
 * a category the backend adds later degrades to "something went wrong" plus the
 * technical detail rather than rendering a raw `dataSources.scrapeError.FOO`
 * key path at the user.
 */
const KNOWN_ERROR_TYPES = [
  "INVALID_PASSWORD",
  "CHANGE_PASSWORD",
  "ACCOUNT_BLOCKED",
  "TWO_FACTOR_RETRIEVER_MISSING",
  "TIMEOUT",
  "NO_ACCOUNTS",
  "INIT_ERROR",
  "BROWSER_NOT_FOUND",
] as const;

/** Gap between the icon and the panel, and the panel and the viewport edge. */
const GAP_PX = 6;
const VIEWPORT_MARGIN_PX = 8;

/**
 * Info badge that explains why a scrape failed.
 *
 * Separates the two audiences that used to share one string: the headline is
 * friendly translated copy chosen by `errorType`, and the provider's raw text
 * sits underneath as opt-in technical detail. Before this the raw text *was*
 * the message, so it had to be either debuggable or readable — never both.
 *
 * Shows on hover (desktop) and on tap (mobile) — touch devices have no hover,
 * so the icon is a real button that toggles the tooltip, with a full-screen
 * backdrop to dismiss it on an outside tap.
 *
 * The panel is portalled to `<body>` with fixed positioning. Anchored inside
 * the icon it was shrink-wrapped to the icon's width (one word per line) and
 * clipped by whatever scroll container held the card; now it is placed from
 * the icon's viewport rect — above when there is room, else below — and
 * clamped so it never leaves the screen.
 */
export function ScrapeErrorTooltip({ message, errorType }: ScrapeErrorTooltipProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const visible = open || hovered;

  const known = errorType
    ? (KNOWN_ERROR_TYPES as readonly string[]).includes(errorType)
    : false;
  const headline = known
    ? t(`dataSources.scrapeError.${errorType}`)
    : t("dataSources.scrapeError.GENERAL_ERROR");
  const detail = (message || "").trim();

  const place = useCallback(() => {
    const button = buttonRef.current;
    const panel = panelRef.current;
    if (!button || !panel) return;
    const anchor = button.getBoundingClientRect();
    const { width, height } = panel.getBoundingClientRect();
    const isRtl = getComputedStyle(button).direction === "rtl";
    const above = anchor.top - GAP_PX - height;
    const top =
      above >= VIEWPORT_MARGIN_PX ? above : anchor.bottom + GAP_PX;
    const preferredLeft = isRtl ? anchor.left : anchor.right - width;
    const maxLeft = window.innerWidth - width - VIEWPORT_MARGIN_PX;
    const left = Math.max(VIEWPORT_MARGIN_PX, Math.min(preferredLeft, maxLeft));
    setPosition({ top, left });
  }, []);

  useLayoutEffect(() => {
    if (!visible) return;
    place();
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [visible, place]);

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <button
        ref={buttonRef}
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        className="-m-1 p-1 text-red-400"
        aria-label={t("dataSources.showErrorDetails")}
        aria-expanded={open}
      >
        <Info size={12} />
      </button>
      {createPortal(
        <div
          ref={panelRef}
          role="tooltip"
          data-testid="scrape-error-tooltip"
          className={`fixed z-[70] w-max max-w-[min(280px,calc(100vw-1rem))] ${
            visible ? "block" : "hidden"
          }`}
          style={
            position
              ? { top: position.top, left: position.left }
              : { top: 0, left: 0, visibility: "hidden" }
          }
        >
          <div className="rounded border border-gray-700 bg-gray-900 p-2 text-[10px] shadow-lg">
            <p className="whitespace-normal break-words font-semibold text-white">
              {headline}
            </p>
            {!!detail && (
              <>
                <p className="mt-1.5 text-[9px] font-bold uppercase tracking-wider text-gray-500">
                  {t("dataSources.errorTechnicalDetails")}
                </p>
                {/* dir="auto" — provider text may be Hebrew, and it must not be
                    forced into the surrounding UI direction. */}
                <p
                  dir="auto"
                  className="whitespace-normal break-words font-mono text-[9px] leading-snug text-gray-400"
                >
                  {detail}
                </p>
              </>
            )}
          </div>
        </div>,
        document.body,
      )}
      {open && (
        <div
          className="fixed inset-0 z-40"
          aria-hidden="true"
          onClick={() => setOpen(false)}
        />
      )}
    </span>
  );
}
