import { useTranslation } from "react-i18next";
import { useRegisterSW } from "virtual:pwa-register/react";
import { CloudCheck, Download, X } from "lucide-react";

/**
 * Floating toast that surfaces service worker lifecycle events:
 *   - one-shot "ready to work offline" confirmation after the SW first installs
 *   - persistent "update available" prompt with a reload button when a new
 *     build is detected
 *
 * Registration uses the prompt strategy configured in `vite.config.ts`, so
 * the user is always in control of when the new bundle replaces the
 * current session.
 */
export function ServiceWorkerUpdatePrompt() {
  const { t } = useTranslation();
  const {
    offlineReady: [offlineReady, setOfflineReady],
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    onRegisterError(error) {
      console.error("Service worker registration failed", error);
    },
  });

  if (!offlineReady && !needRefresh) return null;

  const handleClose = () => {
    setOfflineReady(false);
    setNeedRefresh(false);
  };

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-4 inset-x-4 md:inset-x-auto md:end-6 md:bottom-6 z-50 flex justify-center md:justify-end pointer-events-none"
    >
      <div className="pointer-events-auto w-full md:w-auto md:max-w-sm flex items-start gap-3 rounded-xl border border-[var(--surface-light)] bg-[var(--surface)]/95 backdrop-blur-xl shadow-2xl p-4">
        <div className="shrink-0 mt-0.5 text-[var(--primary)]">
          {needRefresh ? <Download size={20} /> : <CloudCheck size={20} />}
        </div>
        <div className="flex-1 min-w-0">
          {needRefresh ? (
            <>
              <p className="text-sm font-semibold text-[var(--text)]">
                {t("pwa.updateAvailableTitle")}
              </p>
              <p className="mt-0.5 text-xs text-[var(--text-muted)]">
                {t("pwa.updateAvailableMessage")}
              </p>
              <div className="mt-3 flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => updateServiceWorker(true)}
                  className="px-3 py-1.5 rounded-lg bg-[var(--primary)] hover:bg-[var(--primary-dark)] text-white text-xs font-medium transition-colors"
                >
                  {t("pwa.reload")}
                </button>
                <button
                  type="button"
                  onClick={handleClose}
                  className="px-3 py-1.5 rounded-lg bg-[var(--surface-light)] hover:bg-[var(--surface-light)]/70 text-[var(--text)] text-xs font-medium transition-colors"
                >
                  {t("pwa.dismiss")}
                </button>
              </div>
            </>
          ) : (
            <p className="text-sm text-[var(--text)]">{t("pwa.offlineReady")}</p>
          )}
        </div>
        <button
          type="button"
          onClick={handleClose}
          aria-label={t("pwa.dismiss")}
          className="shrink-0 -m-1 p-2 rounded-md text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface-light)] transition-colors"
        >
          <X size={16} />
        </button>
      </div>
    </div>
  );
}
