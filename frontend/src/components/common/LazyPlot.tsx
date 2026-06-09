import { Suspense, lazy } from "react";
import type { PlotParams } from "react-plotly.js";

// Plotly is ~3 MB minified — loading it lazily keeps it out of the main
// bundle (and under the Workbox per-file precache budget, see
// .claude/rules/frontend_pwa.md). All chart components must import Plot
// from here instead of "react-plotly.js" directly.
const importPlotly = () => import("react-plotly.js");
const Plot = lazy(importPlotly);

// Warm the chunk right after first paint so its fetch/parse overlaps the
// data queries instead of starting only when the first chart mounts.
if (typeof window !== "undefined") {
  const warm = () => void importPlotly();
  if (typeof window.requestIdleCallback === "function") {
    window.requestIdleCallback(warm, { timeout: 2000 });
  } else {
    setTimeout(warm, 1000);
  }
}

export default function LazyPlot(props: PlotParams) {
  return (
    <Suspense
      fallback={
        <div
          className="h-full w-full min-h-[120px] rounded-lg bg-[var(--surface-light)] animate-pulse"
          style={props.style}
        />
      }
    >
      <Plot {...props} />
    </Suspense>
  );
}
