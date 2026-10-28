import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useDialog } from "../context/DialogContext";
import { WRITE_FAILED_EVENT, type WriteFailedDetail } from "../queryInvalidation";

/** A burst of failed writes (a bulk retag across tables) gets one notice. */
const BURST_MS = 2000;

/**
 * Tells the user when a write failed and nothing else said so.
 *
 * Most writes answer on click and put the screen back if the request fails;
 * without a word, that reads as the app taking the change and then losing
 * it. A write that waits for the server just stops spinning, which reads no
 * better. Listens for the `write-failed` window event the app-wide mutation
 * cache dispatches for both.
 */
export function useWriteFailedToast(): void {
  const { t } = useTranslation();
  const { notifyError } = useDialog();
  const lastShown = useRef(0);

  useEffect(() => {
    const handler = (event: Event) => {
      const now = Date.now();
      if (now - lastShown.current < BURST_MS) return;
      lastShown.current = now;
      const reverted = (event as CustomEvent<WriteFailedDetail>).detail?.reverted ?? false;
      notifyError(t(reverted ? "common.writeReverted" : "common.writeFailed"));
    };
    window.addEventListener(WRITE_FAILED_EVENT, handler);
    return () => window.removeEventListener(WRITE_FAILED_EVENT, handler);
  }, [notifyError, t]);
}
