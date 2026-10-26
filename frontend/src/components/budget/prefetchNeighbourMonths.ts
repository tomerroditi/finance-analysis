import type { FetchQueryOptions, QueryClient } from "@tanstack/react-query";

/** Nearest first: the months a user steps to next. */
export const NEIGHBOUR_OFFSETS = [-1, 1, -2, 2] as const;

/**
 * The neighbouring months worth prefetching around a viewed month.
 *
 * Never a month after the current calendar month: the first read of an
 * empty current-or-future month makes the backend auto-fill it (copy the
 * latest rules in), which is a write — it discards the server's cache for
 * every client and would copy this month's rules before the user finished
 * editing them. Navigating there still fetches it normally.
 *
 * @param year - Viewed year.
 * @param month - Viewed month, 1–12.
 * @param today - The current date (injectable for tests).
 */
export function neighbourMonths(
  year: number,
  month: number,
  today: Date = new Date(),
): { year: number; month: number }[] {
  const current = today.getFullYear() * 12 + today.getMonth();
  return NEIGHBOUR_OFFSETS.map((offset) => new Date(year, month - 1 + offset))
    .filter((date) => date.getFullYear() * 12 + date.getMonth() <= current)
    .map((date) => ({ year: date.getFullYear(), month: date.getMonth() + 1 }));
}

/**
 * Prefetch a month's neighbours one at a time, nearest first.
 *
 * Call once the viewed month has arrived: requests that run together share
 * the server's CPU, so fired alongside it they made the viewed month wait,
 * and fired together each took several times longer than in turn.
 *
 * @param client - The query client.
 * @param year - Viewed year.
 * @param month - Viewed month, 1–12.
 * @param options - The query options for a month.
 * @returns A cleanup that stops the chain before its next month.
 */
export function prefetchNeighbourMonths(
  client: QueryClient,
  year: number,
  month: number,
  options: (year: number, month: number) => FetchQueryOptions,
): () => void {
  let cancelled = false;
  void (async () => {
    for (const neighbour of neighbourMonths(year, month)) {
      if (cancelled) return;
      await client.prefetchQuery(options(neighbour.year, neighbour.month));
    }
  })();
  return () => {
    cancelled = true;
  };
}
