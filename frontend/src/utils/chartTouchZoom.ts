import Plotly from "plotly.js/dist/plotly";
import i18n from "../i18n";

/**
 * Touch "double-tap to enter zoom mode" for Plotly charts.
 *
 * On touch devices the shared chart theme sets `dragmode: false` so a normal
 * one-finger swipe scrolls the page instead of being hijacked into a Plotly
 * zoom box (see utils/plotlyLocale.ts). That trades away the ability to zoom a
 * figure. This module gives it back behind an explicit gesture without
 * reinventing the interaction:
 *
 *   Double-tap a chart → it enters Plotly's native zoom mode
 *   (`dragmode: "zoom"`). Now a one-finger drag marks a rectangle and zooms
 *   into it, exactly like Plotly on desktop. Double-tap again (inside) resets
 *   to autorange — Plotly's own double-click behaviour. Touch anywhere outside
 *   the chart leaves zoom mode; the page scrolls normally again.
 *
 * The zoom persists after lifting the finger because it's a native Plotly GUI
 * interaction and `chartTheme.uirevision` keeps it across re-renders.
 *
 * Installed once globally and wired to every chart via event delegation
 * (`closest(".js-plotly-plot")`), so chart components need no changes. Pie /
 * donut / Sankey charts have no cartesian axes and never enter zoom mode.
 */

/** ms between the two taps to count as a double-tap. */
const DOUBLE_TAP_MS = 300;
/** px the second tap may sit from the first and still pair as a double-tap. */
const TAP_RADIUS = 30;
/** px of movement on a pending first tap that reclassifies it as a scroll. */
const MOVE_CANCEL = 12;

interface PlotlyGraphDiv extends HTMLElement {
  _fullLayout?: { xaxis?: { range?: unknown }; dragmode?: unknown };
}

/** Only cartesian charts (with an x-axis range) can be zoomed. */
function isCartesian(gd: PlotlyGraphDiv): boolean {
  return Array.isArray(gd._fullLayout?.xaxis?.range);
}

export function installChartTouchZoom(): () => void {
  let pendingTime = 0;
  let pendingX = 0;
  let pendingY = 0;
  let pendingGd: PlotlyGraphDiv | null = null;
  let zoomGd: PlotlyGraphDiv | null = null;
  let hint: HTMLDivElement | null = null;

  const clearPending = () => {
    pendingTime = 0;
    pendingGd = null;
  };

  const showHint = (gd: PlotlyGraphDiv) => {
    hint = document.createElement("div");
    hint.className = "chart-zoom-hint";
    hint.dir = document.documentElement.dir || "ltr";
    hint.textContent = i18n.t("charts.zoomHint");
    if (getComputedStyle(gd).position === "static") gd.style.position = "relative";
    gd.appendChild(hint);
  };

  const enterZoom = (gd: PlotlyGraphDiv) => {
    zoomGd = gd;
    gd.classList.add("chart-zoom-active");
    showHint(gd);
    void Plotly.relayout(gd, { dragmode: "zoom" });
  };

  const exitZoom = () => {
    if (!zoomGd) return;
    const gd = zoomGd;
    zoomGd = null;
    gd.classList.remove("chart-zoom-active");
    hint?.remove();
    hint = null;
    // Drop back to scroll mode; the zoom itself stays (uirevision preserves it).
    void Plotly.relayout(gd, { dragmode: false });
  };

  const onStart = (e: TouchEvent) => {
    const target = e.target as Element | null;
    const gd = (target?.closest?.(".js-plotly-plot") as PlotlyGraphDiv | null) ?? null;

    if (zoomGd) {
      // Inside the active chart: let Plotly handle the drag (zoom box) and a
      // double-tap (its native reset). Re-assert dragmode in case a re-render
      // reset it back to the themed default.
      if (gd === zoomGd) {
        if (gd._fullLayout?.dragmode !== "zoom") void Plotly.relayout(gd, { dragmode: "zoom" });
        return;
      }
      // Touched elsewhere → leave zoom mode, then fall through so this touch is
      // handled normally (scroll, or arming a double-tap on another chart).
      exitZoom();
    }

    if (e.touches.length !== 1 || !gd || !isCartesian(gd)) {
      clearPending();
      return;
    }

    const touch = e.touches[0];
    const now = performance.now();
    const isDoubleTap =
      pendingTime > 0 &&
      gd === pendingGd &&
      now - pendingTime < DOUBLE_TAP_MS &&
      Math.hypot(touch.clientX - pendingX, touch.clientY - pendingY) < TAP_RADIUS;

    if (isDoubleTap) {
      clearPending();
      enterZoom(gd);
      return;
    }
    pendingTime = now;
    pendingX = touch.clientX;
    pendingY = touch.clientY;
    pendingGd = gd;
  };

  // Cancel a pending first tap if the finger actually drags (i.e. it was a
  // scroll, not a tap) so a later tap can't pair into a false double-tap.
  const onScrollCancel = (e: TouchEvent) => {
    if (zoomGd || pendingTime === 0) return;
    const touch = e.touches[0];
    if (!touch) return;
    if (Math.hypot(touch.clientX - pendingX, touch.clientY - pendingY) > MOVE_CANCEL) {
      clearPending();
    }
  };

  document.addEventListener("touchstart", onStart, { passive: true });
  document.addEventListener("touchmove", onScrollCancel, { passive: true });

  return () => {
    document.removeEventListener("touchstart", onStart);
    document.removeEventListener("touchmove", onScrollCancel);
    exitZoom();
  };
}
