import { useEffect, useRef, useState } from "react";

const TOAST_VISIBLE_MS = 3500;
const FAILURE_DEBOUNCE_MS = 5000;

/**
 * Subscribes to the `API_NETWORK_FAILED` postMessage broadcast from our
 * service worker (see `src/sw.ts`). Returns a transient `visible` flag so
 * the host component can render a toast for a few seconds.
 *
 * Debouncing: a single toast covers a burst of failures from parallel
 * queries. After it dismisses we wait `FAILURE_DEBOUNCE_MS` before another
 * toast can appear, so a steady network outage doesn't spam the UI.
 */
export function useNetworkFailureToast(): {
  visible: boolean;
  dismiss: () => void;
} {
  const [visible, setVisible] = useState(false);
  const lastShownRef = useRef<number>(0);
  const hideTimerRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;

    const handler = (event: MessageEvent) => {
      if (event.data?.type !== "API_NETWORK_FAILED") return;
      const now = Date.now();
      if (now - lastShownRef.current < FAILURE_DEBOUNCE_MS) return;
      lastShownRef.current = now;
      setVisible(true);
      window.clearTimeout(hideTimerRef.current);
      hideTimerRef.current = window.setTimeout(() => {
        setVisible(false);
      }, TOAST_VISIBLE_MS);
    };

    navigator.serviceWorker.addEventListener("message", handler);
    return () => {
      navigator.serviceWorker.removeEventListener("message", handler);
      window.clearTimeout(hideTimerRef.current);
    };
  }, []);

  const dismiss = () => {
    window.clearTimeout(hideTimerRef.current);
    setVisible(false);
  };

  return { visible, dismiss };
}
