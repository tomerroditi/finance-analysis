import Plotly from "plotly.js/dist/plotly";

/**
 * Touch "double-tap-then-drag" zoom for Plotly charts.
 *
 * On touch devices the shared chart theme sets `dragmode: false` so a normal
 * one-finger drag scrolls the page instead of being hijacked into a Plotly zoom
 * box (see utils/plotlyLocale.ts). That trades away the ability to zoom a
 * figure at all. This module gives it back behind an explicit gesture, the same
 * one map apps use for one-finger zoom:
 *
 *   tap once, then on the second tap keep the finger down and drag —
 *   drag up zooms in, drag down zooms out, centered on where you tapped.
 *
 * A plain double-tap (no drag) resets the figure to autorange. A single drag is
 * left untouched, so the page keeps scrolling.
 *
 * It's installed once globally and works on every chart via event delegation
 * (`closest(".js-plotly-plot")`), so individual chart components need no wiring.
 * Pie / donut / Sankey charts have no cartesian axes and are skipped — the
 * gesture falls through to a normal tap/scroll there.
 */

/** ms between the two taps to count as a double-tap. */
const DOUBLE_TAP_MS = 300;
/** px the second tap may sit from the first and still pair as a double-tap. */
const TAP_RADIUS = 30;
/** px of movement on a pending first tap that reclassifies it as a scroll. */
const MOVE_CANCEL = 12;
/** px of vertical drag that halves / doubles the visible range. */
const ZOOM_SENSITIVITY = 220;
/** below this total drag the gesture is treated as a plain double-tap (reset). */
const RESET_MOVE = 8;
/** clamp the per-gesture zoom factor so a frantic drag can't invert the axes. */
const MIN_SCALE = 1 / 40;
const MAX_SCALE = 40;

interface PlotlyAxis {
  range?: [number | string, number | string];
  _offset?: number;
  _length?: number;
  r2l?: (v: number | string) => number;
  l2r?: (v: number) => number | string;
}

interface PlotlyGraphDiv extends HTMLElement {
  _fullLayout?: { xaxis?: PlotlyAxis; yaxis?: PlotlyAxis };
}

/** A cartesian axis we can zoom needs a 2-point range and the lin/range maps. */
function zoomableAxis(ax: PlotlyAxis | undefined): ax is Required<
  Pick<PlotlyAxis, "range" | "r2l" | "l2r">
> &
  PlotlyAxis {
  return (
    !!ax &&
    Array.isArray(ax.range) &&
    ax.range.length === 2 &&
    typeof ax.r2l === "function" &&
    typeof ax.l2r === "function"
  );
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v));
}

interface AxisState {
  ax: PlotlyAxis;
  key: "xaxis" | "yaxis";
  /** range endpoints in linear space, captured at gesture start. */
  base0: number;
  base1: number;
  /** the tapped point in linear space — the zoom stays anchored here. */
  anchor: number;
}

interface ActiveGesture {
  gd: PlotlyGraphDiv;
  axes: AxisState[];
  startY: number;
  maxMove: number;
}

/** Build the per-axis zoom state, anchored at the second tap's pixel position. */
function axisState(
  ax: PlotlyAxis | undefined,
  key: "xaxis" | "yaxis",
  gdRect: DOMRect,
  clientPx: number,
  /** y axes grow upward in data but downward in pixels — flip the fraction. */
  invert: boolean,
): AxisState | null {
  if (!zoomableAxis(ax)) return null;
  const base0 = ax.r2l(ax.range[0]);
  const base1 = ax.r2l(ax.range[1]);
  const offset = ax._offset ?? 0;
  const length = ax._length ?? 1;
  const start = (key === "xaxis" ? gdRect.left : gdRect.top) + offset;
  let frac = clamp((clientPx - start) / length, 0, 1);
  if (invert) frac = 1 - frac;
  const anchor = base0 + frac * (base1 - base0);
  return { ax, key, base0, base1, anchor };
}

export function installChartTouchZoom(): () => void {
  let pendingTime = 0;
  let pendingX = 0;
  let pendingY = 0;
  let pendingGd: PlotlyGraphDiv | null = null;
  let active: ActiveGesture | null = null;

  const clearPending = () => {
    pendingTime = 0;
    pendingGd = null;
  };

  const endGesture = () => {
    if (!active) return;
    const { gd, axes, maxMove } = active;
    // A double-tap with (almost) no drag means "reset" — restore autorange.
    // The range must be nulled alongside autorange; setting autorange alone
    // leaves the explicit zoomed range in place on these charts.
    if (maxMove < RESET_MOVE) {
      const reset: Record<string, null | true> = {};
      for (const a of axes) {
        reset[`${a.key}.range`] = null;
        reset[`${a.key}.autorange`] = true;
      }
      void Plotly.relayout(gd, reset);
    }
    active = null;
    window.removeEventListener("touchmove", onMove);
    window.removeEventListener("touchend", onEnd);
    window.removeEventListener("touchcancel", onEnd);
  };

  const onMove = (e: TouchEvent) => {
    if (!active) return;
    if (e.touches.length !== 1) {
      endGesture();
      return;
    }
    // We own this gesture now — stop the page from scrolling underneath it.
    e.preventDefault();
    const touch = e.touches[0];
    const dy = active.startY - touch.clientY;
    active.maxMove = Math.max(active.maxMove, Math.abs(dy));
    // Sub-pixel jitter isn't a zoom. Skipping it also keeps a plain double-tap
    // (all dy≈0) from emitting an explicit-range relayout that would otherwise
    // race the autorange reset issued on touchend.
    if (Math.abs(dy) < 2) return;
    const scale = clamp(Math.pow(2, -dy / ZOOM_SENSITIVITY), MIN_SCALE, MAX_SCALE);

    const update: Record<string, [number | string, number | string]> = {};
    for (const a of active.axes) {
      const lo = a.anchor - (a.anchor - a.base0) * scale;
      const hi = a.anchor + (a.base1 - a.anchor) * scale;
      update[`${a.key}.range`] = [a.ax.l2r!(lo), a.ax.l2r!(hi)];
    }
    void Plotly.relayout(active.gd, update);
  };

  const onEnd = (e: TouchEvent) => {
    if (e.touches.length === 0) endGesture();
  };

  const onStart = (e: TouchEvent) => {
    if (active) return;
    if (e.touches.length !== 1) {
      clearPending();
      return;
    }
    const touch = e.touches[0];
    const target = e.target as Element | null;
    const gd = (target?.closest?.(".js-plotly-plot") as PlotlyGraphDiv | null) ?? null;
    if (!gd) {
      clearPending();
      return;
    }
    const now = performance.now();
    const isDoubleTap =
      pendingTime > 0 &&
      gd === pendingGd &&
      now - pendingTime < DOUBLE_TAP_MS &&
      Math.hypot(touch.clientX - pendingX, touch.clientY - pendingY) < TAP_RADIUS;

    if (!isDoubleTap) {
      // First tap — remember it so the next tap can pair with it. Charts with no
      // zoomable axes still record a tap, but begin-zoom below filters them out.
      pendingTime = now;
      pendingX = touch.clientX;
      pendingY = touch.clientY;
      pendingGd = gd;
      return;
    }
    clearPending();

    const fl = gd._fullLayout;
    const rect = gd.getBoundingClientRect();
    const axes: AxisState[] = [];
    const xs = axisState(fl?.xaxis, "xaxis", rect, touch.clientX, false);
    if (xs) axes.push(xs);
    const ys = axisState(fl?.yaxis, "yaxis", rect, touch.clientY, true);
    if (ys) axes.push(ys);
    if (axes.length === 0) return; // pie / sankey / not ready — leave the tap alone

    e.preventDefault();
    active = { gd, axes, startY: touch.clientY, maxMove: 0 };
    window.addEventListener("touchmove", onMove, { passive: false });
    window.addEventListener("touchend", onEnd, { passive: false });
    window.addEventListener("touchcancel", onEnd, { passive: false });
  };

  // Cancel a pending first tap if the finger actually drags (i.e. it was a
  // scroll, not a tap). Passive — we never block scrolling here.
  const onScrollCancel = (e: TouchEvent) => {
    if (active || pendingTime === 0) return;
    const touch = e.touches[0];
    if (!touch) return;
    if (Math.hypot(touch.clientX - pendingX, touch.clientY - pendingY) > MOVE_CANCEL) {
      clearPending();
    }
  };

  document.addEventListener("touchstart", onStart, { passive: false });
  document.addEventListener("touchmove", onScrollCancel, { passive: true });

  return () => {
    document.removeEventListener("touchstart", onStart);
    document.removeEventListener("touchmove", onScrollCancel);
    endGesture();
  };
}
