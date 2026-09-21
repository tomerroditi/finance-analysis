import { describe, expect, it } from "vitest";

/**
 * The dashboard feed's sticky date header covers the band above it with an
 * upward box-shadow, and that only works while three numbers stay equal: the
 * header's own height, how far the shadow reaches above it, and the gap it has
 * to fill between one date group and the next.
 *
 * Let them drift and the thin line comes back — a shadow shorter than the
 * header leaves a clipped band of the outgoing date on screen during the
 * handover, and one longer than the gap paints over the previous row. Neither
 * shows up in a type-check, and the e2e that catches it needs a browser, so
 * this reads the numbers straight out of the source.
 *
 * Source comes from `import.meta.glob` rather than `node:fs` for the same
 * reason as `roundedScrollContainers.test.ts`: `tsconfig.app.json` is
 * browser-only, so a `node:fs` import here would fail `npm run build`.
 */

const SOURCES = import.meta.glob("./components/dashboard/*.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;
describe("RecentTransactionsSection sticky date header", () => {
  const source = SOURCES["./components/dashboard/RecentTransactionsSection.tsx"];

  /** Tailwind's spacing scale: one step is 4px. */
  const step = (n: string) => Number(n) * 4;

  /** `text-xs` line height. Bump this if the header's type scale changes. */
  const LINE_HEIGHT = 16;

  const header = source.match(/data-testid="recent-tx-date"[\s\S]{0,600}?`}/);

  it("declares the classes this guard reads", () => {
    expect(header).not.toBeNull();
  });

  it("keeps header height, shadow reach and group gap equal", () => {
    const classes = header![0];
    const paddingTop = classes.match(/\bpt-(\d+)\b/);
    const paddingBottom = classes.match(/\bpb-(\d+)\b/);
    const gap = classes.match(/\bmt-(\d+)\b/);
    const shadow = classes.match(
      /shadow-\[0_-(\d+)px_0_(\d+)px_var\(--surface\)\]/,
    );

    expect(paddingTop, "header should declare pt-*").not.toBeNull();
    expect(paddingBottom, "header should declare pb-*").not.toBeNull();
    expect(gap, "groups after the first should declare mt-*").not.toBeNull();
    expect(shadow, "header should declare an upward --surface box-shadow").not.toBeNull();

    const height = step(paddingTop![1]) + LINE_HEIGHT + step(paddingBottom![1]);
    const offset = Number(shadow![1]);
    const spread = Number(shadow![2]);

    expect(offset + spread, "shadow must reach exactly the header's height")
      .toBe(height);
    expect(step(gap![1]), "group gap must match the shadow's reach")
      .toBe(offset + spread);
    // A bare offset makes the shadow abut the header's background instead of
    // overlapping it, and the two edges snap to device pixels independently.
    expect(spread, "shadow needs spread to overlap the header").toBeGreaterThan(0);
  });

  it("paints the header opaque and above the rows", () => {
    expect(header![0]).toMatch(/bg-\[var\(--surface\)\]/);
    expect(header![0]).toMatch(/\bz-10\b/);
    expect(header![0]).toMatch(/\bsticky\b/);
    expect(header![0]).toMatch(/\btop-0\b/);
  });
});
