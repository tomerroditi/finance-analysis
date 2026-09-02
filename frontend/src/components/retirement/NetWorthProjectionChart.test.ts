import { describe, expect, it } from "vitest";
import { truncateProjectionAtDepletion } from "./projectionTruncation";

function point(
  age: number,
  optimistic: number,
  baseline: number,
  conservative: number,
) {
  return {
    age,
    net_worth_optimistic: optimistic,
    net_worth_baseline: baseline,
    net_worth_conservative: conservative,
  };
}

describe("truncateProjectionAtDepletion", () => {
  it("keeps the full horizon when no track depletes", () => {
    const data = [
      point(55, 100, 90, 80),
      point(70, 120, 100, 85),
      point(90, 150, 110, 90),
    ];
    const result = truncateProjectionAtDepletion(data);
    expect(result).toHaveLength(3);
    expect(result[2]).toMatchObject({
      net_worth_optimistic: 150,
      net_worth_baseline: 110,
      net_worth_conservative: 90,
    });
  });

  it("keeps the full horizon when at least one track survives", () => {
    // Conservative depletes at 70, but optimistic never does — the
    // longest-surviving track determines the end, so nothing is cut.
    const data = [
      point(60, 100, 60, 30),
      point(70, 110, 40, -5),
      point(90, 130, 20, -50),
    ];
    const result = truncateProjectionAtDepletion(data);
    expect(result).toHaveLength(3);
    // The depleted track touches zero at its crossing, then stops (null)
    // instead of plotting deeper negatives.
    expect(result[1].net_worth_conservative).toBe(0);
    expect(result[2].net_worth_conservative).toBeNull();
    expect(result[2].net_worth_optimistic).toBe(130);
  });

  it("cuts the chart where the longest-surviving track hits zero", () => {
    // conservative depletes at 70, baseline at 80, optimistic at 85 —
    // the figure ends at 85; the age-90 point is dropped entirely.
    const data = [
      point(60, 100, 80, 60),
      point(70, 80, 40, -10),
      point(80, 40, -20, -60),
      point(85, -5, -70, -110),
      point(90, -50, -120, -160),
    ];
    const result = truncateProjectionAtDepletion(data);
    expect(result).toHaveLength(4);
    expect(result[result.length - 1].age).toBe(85);
    // Each track clamps to 0 at its own crossing and is null afterwards.
    expect(result[1].net_worth_conservative).toBe(0);
    expect(result[2].net_worth_conservative).toBeNull();
    expect(result[2].net_worth_baseline).toBe(0);
    expect(result[3].net_worth_baseline).toBeNull();
    expect(result[3].net_worth_optimistic).toBe(0);
  });

  it("keeps a track that dips below zero but recovers", () => {
    // A mortgage-driven negative stretch that climbs back is not
    // depletion — the recovery is the story, so the dip plots as-is.
    const data = [
      point(40, -100, -150, -200),
      point(50, 200, 150, 100),
      point(90, 900, 700, 500),
    ];
    const result = truncateProjectionAtDepletion(data);
    expect(result).toHaveLength(3);
    expect(result[0]).toMatchObject({
      net_worth_optimistic: -100,
      net_worth_baseline: -150,
      net_worth_conservative: -200,
    });
    expect(result[2].net_worth_baseline).toBe(700);
  });

  it("truncates a terminal collapse during accumulation (before target age)", () => {
    // Regression: an underfunded plan whose net worth crosses zero YEARS
    // before the target age and never recovers used to plot the whole
    // negative descent, then clamp the target-age point to 0 — drawing a
    // bogus hook from deep negative back up to zero at the retirement
    // marker. Depletion is phase-agnostic: the line stops at the crossing.
    const data = [
      point(30, 1_100_000, 1_050_000, 1_000_000),
      point(40, 150_000, 100_000, 50_000),
      point(41, 30_000, -20_000, -70_000),
      point(42, -90_000, -140_000, -190_000),
      point(49, -600_000, -650_000, -700_000),
      point(50, -680_000, -730_000, -780_000),
    ];
    const result = truncateProjectionAtDepletion(data);
    // Optimistic survives longest (positive through 41) — cut at index 3.
    expect(result).toHaveLength(4);
    expect(result[result.length - 1].age).toBe(42);
    expect(result[2].net_worth_baseline).toBe(0);
    expect(result[2].net_worth_conservative).toBe(0);
    expect(result[3].net_worth_baseline).toBeNull();
    expect(result[3].net_worth_optimistic).toBe(0);
    // No point anywhere is deep-negative-then-zero — the hook is gone.
    for (const row of result) {
      expect(row.net_worth_baseline === null || row.net_worth_baseline >= -20_000).toBe(true);
    }
  });

  it("treats depletion at exactly the target age as depletion", () => {
    const data = [
      point(59, 10, 5, 1),
      point(60, 5, 0, -3),
      point(61, 1, -4, -8),
    ];
    const result = truncateProjectionAtDepletion(data);
    // baseline and conservative deplete at 60; optimistic survives — full
    // horizon kept, depleted tracks stop after touching zero.
    expect(result).toHaveLength(3);
    expect(result[1].net_worth_baseline).toBe(0);
    expect(result[1].net_worth_conservative).toBe(0);
    expect(result[2].net_worth_baseline).toBeNull();
    expect(result[2].net_worth_conservative).toBeNull();
    expect(result[2].net_worth_optimistic).toBe(1);
  });

  it("plots a never-positive track as-is instead of truncating everything", () => {
    // A plan that is underwater across the whole horizon has no depletion
    // point — clamping index 0 to zero would blank the chart entirely.
    const data = [
      point(30, -10, -50, -90),
      point(40, -20, -70, -120),
    ];
    const result = truncateProjectionAtDepletion(data);
    expect(result).toHaveLength(2);
    expect(result[1].net_worth_baseline).toBe(-70);
  });
});
