import { useEffect, useState } from "react";
import { useIsRestoring, useQueryClient } from "@tanstack/react-query";

/** How long the first load may hold the deferred cards back at most. */
export const FIRST_LOAD_FALLBACK_MS = 4000;

/**
 * Whether the page's first burst of reads has finished — or the user has
 * started scrolling, or the fallback has passed.
 *
 * The dashboard defers its lower cards until they scroll near the viewport,
 * but on a cold load the eager cards above them are still short loading
 * skeletons, so the deferred placeholders sat inside the observer's margin
 * and mounted at once — firing the heaviest analytics requests alongside the
 * cards the user is looking at. Arming the deferral only once this turns
 * true measures "near the viewport" against the real layout.
 *
 * Latches: once true it stays true.
 *
 * @param fallbackMs - Upper bound on the wait, so a slow read cannot keep
 *   the lower cards from ever mounting.
 */
export function useFirstLoadSettled(fallbackMs: number = FIRST_LOAD_FALLBACK_MS): boolean {
  const queryClient = useQueryClient();
  const restoring = useIsRestoring();
  const [settled, setSettled] = useState(false);

  useEffect(() => {
    // While the persisted cache is restoring nothing fetches yet, so an idle
    // client says nothing about whether the page has loaded.
    if (settled || restoring) return;
    const settle = () => setSettled(true);
    const check = () => {
      if (queryClient.isFetching() === 0) settle();
    };
    let unsubscribe = () => {};
    // A tick later, so the reads this commit mounted have started.
    const start = setTimeout(() => {
      check();
      unsubscribe = queryClient.getQueryCache().subscribe(check);
    }, 0);
    const fallback = setTimeout(settle, fallbackMs);
    // Captured, so a scroll of whichever element holds the page counts.
    document.addEventListener("scroll", settle, { capture: true, passive: true, once: true });
    return () => {
      clearTimeout(start);
      clearTimeout(fallback);
      unsubscribe();
      document.removeEventListener("scroll", settle, { capture: true });
    };
  }, [settled, restoring, queryClient, fallbackMs]);

  return settled;
}
