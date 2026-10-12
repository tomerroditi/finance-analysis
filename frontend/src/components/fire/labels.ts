/**
 * Names for the engine's series keys (`portfolio0`, `keren2`, `cash`).
 *
 * A key is a kind and a 0-based row. Where the plan's own row has a name —
 * a portfolio called "Excellence Trade" — that name is used; otherwise the
 * kind, numbered from 1.
 */
import type { FireProjection } from "../../services/api";

type T = (key: string) => string;

/** Row names by series key, from the drawdown plan, which carries each row's description. */
export function seriesNames(projection: FireProjection): Record<string, string> {
  const names: Record<string, string> = {};
  for (const segment of projection.withdrawal_plan) {
    if (segment.description) names[segment.source] = segment.description;
  }
  return names;
}

function label(key: string, t: T, prefix: string, names: Record<string, string>): string {
  if (names[key]) return names[key];
  const match = /^([a-z_]+?)(\d+)$/.exec(key);
  const stem = match ? match[1] : key;
  const kind = t(`${prefix}.${stem}`);
  return match ? `${kind} ${Number(match[2]) + 1}` : kind;
}

/** A cash-flow series: income or spending. */
export function flowLabel(key: string, t: T, names: Record<string, string> = {}): string {
  return label(key, t, "fire.flow", names);
}

/** An asset series: what the money is held in. */
export function assetLabel(key: string, t: T, names: Record<string, string> = {}): string {
  return label(key, t, "fire.assetSeries", names);
}
