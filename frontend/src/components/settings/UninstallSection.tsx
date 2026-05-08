import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";
import { useConfirm, useNotify } from "../../context/DialogContext";
import { uninstallApi } from "../../services/api";
import { useVersionInfo } from "../../hooks/useVersionInfo";

/**
 * Settings → Advanced → Uninstall (macOS only).
 *
 * Renders nothing on Windows/Linux: Windows uninstalls happen through
 * Add/Remove Programs (NSIS), and Linux has no installer to uninstall.
 * The visibility check uses ``versionApi.platform`` rather than the
 * browser's ``navigator.platform`` so we test against where the
 * backend is running (the Mac), not where the request originates.
 */
export function UninstallSection() {
  const { t } = useTranslation();
  const { data: version } = useVersionInfo();
  const confirm = useConfirm();
  const notify = useNotify();
  const [wipeData, setWipeData] = useState(false);

  const uninstallMutation = useMutation({
    mutationFn: (wipe: boolean) =>
      uninstallApi.uninstall(wipe).then((res) => res.data),
    onSuccess: () => {
      notify.success(t("uninstall.running"));
      // Backend will exit shortly; close the popup window after a moment.
      window.setTimeout(() => {
        try {
          window.close();
        } catch {
          /* close blocked by browser; user closes manually */
        }
      }, 1500);
    },
    onError: () => {
      notify.error(t("uninstall.failed"));
    },
  });

  if (version?.platform !== "darwin") return null;

  const handleClick = async () => {
    const ok = await confirm({
      title: t("uninstall.confirmTitle"),
      message: wipeData
        ? t("uninstall.confirmWipeBody")
        : t("uninstall.confirmKeepBody"),
      confirmLabel: t("uninstall.confirmAction"),
      cancelLabel: t("uninstall.confirmCancel"),
      isDestructive: true,
    });
    if (!ok) return;
    uninstallMutation.mutate(wipeData);
  };

  return (
    <div>
      <label className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2 block">
        {t("uninstall.sectionTitle")}
      </label>
      <p className="text-xs text-[var(--text-muted)] mb-3" dir="auto">
        {t("uninstall.sectionBlurb")}
      </p>

      <label className="flex items-start gap-2 mb-3 cursor-pointer">
        <input
          type="checkbox"
          checked={wipeData}
          onChange={(e) => setWipeData(e.target.checked)}
          className="mt-0.5 accent-[var(--danger)]"
        />
        <span className="text-xs">
          <span className="text-[var(--text)] font-medium block">
            {t("uninstall.wipeCheckboxLabel")}
          </span>
          <span className="text-[var(--text-muted)]">
            {t("uninstall.wipeCheckboxHelp")}
          </span>
        </span>
      </label>

      <button
        type="button"
        onClick={handleClick}
        disabled={uninstallMutation.isPending}
        className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-[var(--danger)]/15 text-[var(--danger)] hover:bg-[var(--danger)]/25 transition-colors disabled:opacity-50"
      >
        <Trash2 size={12} />
        {t("uninstall.openButton")}
      </button>
    </div>
  );
}
