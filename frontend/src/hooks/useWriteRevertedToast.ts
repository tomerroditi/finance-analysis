import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useDialog } from "../context/DialogContext";
import { WRITE_REVERTED_EVENT } from "../queryInvalidation";

/** A burst of refused writes (a bulk retag across tables) gets one notice. */
const BURST_MS = 2000;

/**
 * Tells the user when the server refused a change the screen had already
 * shown.
 *
 * Most writes answer on click and put the screen back if the request fails;
 * without a word, that reads as the app taking the change and then losing
 * it. Listens for the `write-reverted` window event the app-wide mutation
 * cache dispatches for every such write.
 */
export function useWriteRevertedToast(): void {
  const { t } = useTranslation();
  const { notifyError } = useDialog();
  const lastShown = useRef(0);

  useEffect(() => {
    const handler = () => {
      const now = Date.now();
      if (now - lastShown.current < BURST_MS) return;
      lastShown.current = now;
      notifyError(t("common.writeReverted"));
    };
    window.addEventListener(WRITE_REVERTED_EVENT, handler);
    return () => window.removeEventListener(WRITE_REVERTED_EVENT, handler);
  }, [notifyError, t]);
}
