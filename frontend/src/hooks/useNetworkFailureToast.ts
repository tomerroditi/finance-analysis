import { useEffect, useRef, useState } from "react";

const TOAST_VISIBLE_MS = 3500;
const FAILURE_DEBOUNCE_MS = 5000;

/**
 * Subscribes to the `api-network-failed` window event dispatched from our
 * axios response interceptor whenever an API request never reached the
 * server. Returns a transient `visible` flag so the host component can
 * render a toast for a few seconds.
 *
 * Debouncing: a single toast covers a burst of failures from parallel
 * queries. After it dismisses we wait `FAILURE_DEBOUNCE_MS` before another
 * toast can appear, so a steady outage doesn't spam the UI.
 *
 * Note: with the SW's NetworkFirst strategy, requests that fail the
 * network but hit the cache resolve successfully from axios's view, so
 * those silent fallbacks aren't surfaced here. Only true failures (no
 * cache, or mutation/cred/scraping endpoints that bypass the cache) fire.
 */
export function useNetworkFailureToast(): {
  visible: boolean;
  dismiss: () => void;
} {
  const [visible, setVisible] = useState(false);
  const lastShownRef = useRef<number>(0);
  const hideTimerRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    const handler = () => {
      const now = Date.now();
      if (now - lastShownRef.current < FAILURE_DEBOUNCE_MS) return;
      lastShownRef.current = now;
      setVisible(true);
      window.clearTimeout(hideTimerRef.current);
      hideTimerRef.current = window.setTimeout(() => {
        setVisible(false);
      }, TOAST_VISIBLE_MS);
    };

    window.addEventListener("api-network-failed", handler);
    return () => {
      window.removeEventListener("api-network-failed", handler);
      window.clearTimeout(hideTimerRef.current);
    };
  }, []);

  const dismiss = () => {
    window.clearTimeout(hideTimerRef.current);
    setVisible(false);
  };

  return { visible, dismiss };
}
