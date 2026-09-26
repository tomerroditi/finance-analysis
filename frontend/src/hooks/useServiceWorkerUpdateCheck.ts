import { useEffect } from "react";

/**
 * How often an open tab asks the server whether a new build has shipped.
 *
 * Nothing else bounds this. The browser re-fetches `sw.js` only on a
 * navigation inside the service worker's scope, or on a functional event
 * once 24 h have passed — and this is an SPA, so route changes are
 * client-side history pushes and every `/api` call is a `fetch` the service
 * worker *handles*. None of that is a navigation, so without this timer a
 * tab left open never discovers a deploy at all.
 */
export const SW_UPDATE_CHECK_INTERVAL_MS = 60_000;

/**
 * Poll for a new service worker while the tab is open.
 *
 * `registration.update()` re-fetches the worker script; the registration's
 * default `updateViaCache: "imports"` makes the browser bypass the HTTP
 * cache for it, so a new build is seen as soon as it is on disk. When one
 * is found the worker installs in the background and `useRegisterSW` flips
 * `needRefresh`, which is what raises the reload toast.
 *
 * Checks are skipped while the tab is hidden (a background tab has nobody
 * to show the toast to) and while offline; both cases are picked back up by
 * the `visibilitychange` and `online` listeners rather than waiting out the
 * interval. A check is also pointless once an update is already installing
 * or waiting — the toast is up, or about to be.
 *
 * @param registration - The active registration, once `onRegisteredSW` has
 *   handed it over. Undefined until then, and on browsers with no service
 *   worker support.
 */
export function useServiceWorkerUpdateCheck(
  registration: ServiceWorkerRegistration | undefined,
): void {
  useEffect(() => {
    if (!registration) return;

    const check = () => {
      if (document.visibilityState === "hidden") return;
      if (!navigator.onLine) return;
      if (registration.installing || registration.waiting) return;
      void registration.update().catch(() => {
        // A failed check is not actionable: the next one is a minute away,
        // and an unreachable server is already surfaced by the API layer.
      });
    };

    const timer = window.setInterval(check, SW_UPDATE_CHECK_INTERVAL_MS);
    document.addEventListener("visibilitychange", check);
    window.addEventListener("online", check);

    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", check);
      window.removeEventListener("online", check);
    };
  }, [registration]);
}
