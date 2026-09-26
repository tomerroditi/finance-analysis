import { useTranslation } from "react-i18next";
import { useDemoMode } from "../../context/DemoModeContext";

/**
 * Warns visitors of a hosted demo whose per-browser sandbox is not backed by
 * durable storage: their edits live only on the serverless instance that
 * handled them and disappear when it recycles. Renders nothing everywhere
 * else (local Demo Mode, or a deployment with a Blob store connected).
 */
export function DemoSandboxNotice() {
  const { t } = useTranslation();
  const { sandboxEphemeral } = useDemoMode();
  if (!sandboxEphemeral) return null;
  return (
    <div
      role="status"
      data-testid="demo-sandbox-notice"
      className="mb-3 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-[var(--text)]"
    >
      <span className="font-semibold">{t("settings.demoSandboxEphemeralTitle")}</span>{" "}
      {t("settings.demoSandboxEphemeral")}
    </div>
  );
}
