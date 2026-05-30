/**
 * `react-plotly.js` bundles Plotly from `plotly.js/dist/plotly`. Importing that
 * same path elsewhere (e.g. utils/chartTouchZoom.ts) reuses the one bundled
 * instance instead of pulling a second ~3 MB Plotly build. That dist entry ships
 * no types, so re-expose the typed default from the package root.
 *
 * Kept script-style (no top-level import) so the ambient module declaration is
 * picked up globally; the inline import-type below is the only way to reference
 * the package types from inside that ambient block.
 */
declare module "plotly.js/dist/plotly" {
  // eslint-disable-next-line @typescript-eslint/consistent-type-imports
  const Plotly: typeof import("plotly.js");
  export default Plotly;
}
