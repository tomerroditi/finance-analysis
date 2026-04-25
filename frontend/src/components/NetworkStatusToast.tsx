import { useTranslation } from "react-i18next";
import { CloudOff, X } from "lucide-react";
import { useNetworkFailureToast } from "../hooks/useNetworkFailureToast";

/**
 * Auto-dismissing toast that surfaces "we couldn't reach the server"
 * events broadcast from the service worker. Sits above the bottom safe
 * area on mobile and bottom-end on desktop, mirroring the placement of
 * the SW update prompt without overlapping it.
 */
export function NetworkStatusToast() {
  const { t } = useTranslation();
  const { visible, dismiss } = useNetworkFailureToast();

  if (!visible) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-20 inset-x-4 md:inset-x-auto md:end-6 md:bottom-24 z-50 flex justify-center md:justify-end pointer-events-none"
    >
      <div className="pointer-events-auto w-full md:w-auto md:max-w-sm flex items-start gap-3 rounded-xl border border-[var(--warning)]/40 bg-[var(--surface)]/95 backdrop-blur-xl shadow-2xl p-4 animate-in fade-in slide-in-from-bottom-2 duration-150">
        <div className="shrink-0 mt-0.5 text-[var(--warning)]">
          <CloudOff size={20} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-[var(--text)]">
            {t("pwa.networkFailedTitle")}
          </p>
          <p className="mt-0.5 text-xs text-[var(--text-muted)]">
            {t("pwa.networkFailedMessage")}
          </p>
        </div>
        <button
          type="button"
          onClick={dismiss}
          aria-label={t("pwa.dismiss")}
          className="shrink-0 -m-1 p-2 rounded-md text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface-light)] transition-colors"
        >
          <X size={16} />
        </button>
      </div>
    </div>
  );
}
