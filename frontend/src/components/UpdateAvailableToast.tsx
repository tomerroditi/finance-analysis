import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Sparkles, X } from "lucide-react";
import { useUpdateCheck } from "../hooks/useUpdateCheck";

const DISMISS_KEY_PREFIX = "update-toast-dismissed-";
const APPEAR_DELAY_MS = 5000;

function isDismissed(latest: string): boolean {
  try {
    return window.localStorage.getItem(DISMISS_KEY_PREFIX + latest) === "1";
  } catch {
    return false;
  }
}

function rememberDismissed(latest: string): void {
  try {
    window.localStorage.setItem(DISMISS_KEY_PREFIX + latest, "1");
  } catch {
    /* localStorage unavailable (private mode, quota) — ignored. */
  }
}

/**
 * Non-blocking "v1.16.0 is available" toast.
 *
 * Anti-pestering rules in place:
 *   - per-version dismissal stored in localStorage so the user is asked
 *     again only when a *new* version is published
 *   - 5s appear delay so it doesn't dominate the first-paint impression
 *   - hidden in dev (`useUpdateCheck` is `enabled: !import.meta.env.DEV`)
 *   - hidden when the probe failed (`error === "unavailable"`); the
 *     About panel surfaces the muted "couldn't check" copy instead.
 */
export function UpdateAvailableToast() {
  const { t } = useTranslation();
  const { data } = useUpdateCheck();
  const [visible, setVisible] = useState(false);
  const [dismissedLocally, setDismissedLocally] = useState(false);

  const latest = data?.latest ?? null;

  useEffect(() => {
    if (!data?.is_outdated || !latest) return;
    if (isDismissed(latest)) return;
    const handle = window.setTimeout(() => setVisible(true), APPEAR_DELAY_MS);
    return () => window.clearTimeout(handle);
  }, [data?.is_outdated, latest]);

  if (!data?.is_outdated || !latest || dismissedLocally || !visible) return null;

  const downloadHref = data.asset_url ?? data.html_url ?? null;

  const handleDismiss = () => {
    rememberDismissed(latest);
    setDismissedLocally(true);
  };

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-36 inset-x-4 md:inset-x-auto md:end-6 md:bottom-44 z-50 flex justify-center md:justify-end pointer-events-none"
    >
      <div className="pointer-events-auto w-full md:w-auto md:max-w-sm flex items-start gap-3 rounded-xl border border-[var(--primary)]/40 bg-[var(--surface)]/95 backdrop-blur-xl shadow-2xl p-4 animate-in fade-in slide-in-from-bottom-2 duration-200">
        <div className="shrink-0 mt-0.5 text-[var(--primary)]">
          <Sparkles size={20} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-[var(--text)]">
            {t("updates.toastTitle")}
          </p>
          <p className="mt-0.5 text-xs text-[var(--text-muted)]" dir="auto">
            {t("updates.toastMessage", { version: latest })}
          </p>
          {downloadHref && (
            <div className="mt-3 flex items-center gap-2">
              <a
                href={downloadHref}
                target="_blank"
                rel="noreferrer noopener"
                onClick={handleDismiss}
                className="px-3 py-1.5 rounded-lg bg-[var(--primary)] hover:opacity-90 text-white text-xs font-medium transition-opacity"
              >
                {t("updates.download")}
              </a>
              <button
                type="button"
                onClick={handleDismiss}
                className="px-3 py-1.5 rounded-lg bg-[var(--surface-light)] hover:bg-[var(--surface-light)]/70 text-[var(--text)] text-xs font-medium transition-colors"
              >
                {t("updates.later")}
              </button>
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={handleDismiss}
          aria-label={t("updates.dismissAriaLabel")}
          className="shrink-0 -m-1 p-2 rounded-md text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface-light)] transition-colors"
        >
          <X size={16} />
        </button>
      </div>
    </div>
  );
}
