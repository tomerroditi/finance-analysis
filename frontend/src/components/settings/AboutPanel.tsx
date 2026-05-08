import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useState } from "react";
import { ExternalLink, RefreshCw } from "lucide-react";
import { useUpdateCheck } from "../../hooks/useUpdateCheck";
import { useVersionInfo } from "../../hooks/useVersionInfo";
import { updatesApi, type UpdateInfo } from "../../services/api";
import { queryClient } from "../../queryClient";

function formatRelative(iso: string | null | undefined, lang: string): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  return new Intl.DateTimeFormat(lang === "he" ? "he-IL" : "en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(then);
}

/**
 * About panel inside Settings: shows current vs latest version with a
 * manual "Check now" button. Falls back to the `versionInfo` query when
 * the update check is disabled (dev) or errored.
 */
export function AboutPanel() {
  const { t, i18n } = useTranslation();
  const { data: version } = useVersionInfo();
  const { data: update } = useUpdateCheck();
  const [pending, setPending] = useState<UpdateInfo | null>(null);

  const refreshMutation = useMutation({
    mutationFn: () => updatesApi.refresh().then((res) => res.data),
    onSuccess: (data) => {
      setPending(data);
      queryClient.setQueryData(["updateCheck"], data);
    },
  });

  const effective = pending ?? update ?? null;
  const current = effective?.current ?? version?.version ?? "";
  const latest = effective?.latest ?? null;
  const isOutdated = effective?.is_outdated ?? false;
  const downloadHref = effective?.asset_url ?? effective?.html_url ?? null;
  const checkedAt = effective?.checked_at ?? null;
  const probeFailed = effective?.error === "unavailable";

  const statusLine = probeFailed
    ? t("updates.checkFailed")
    : isOutdated
      ? t("updates.outdated")
      : t("updates.upToDate");

  return (
    <div>
      <label className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2 block">
        {t("updates.aboutTitle")}
      </label>
      <div className="space-y-2 rounded-lg bg-[var(--surface-light)]/40 p-3">
        <div className="flex items-center justify-between text-xs">
          <span className="text-[var(--text-muted)]">{t("updates.currentVersion")}</span>
          <span className="font-mono text-[var(--text)]" dir="ltr">
            {current || "—"}
          </span>
        </div>
        {latest && (
          <div className="flex items-center justify-between text-xs">
            <span className="text-[var(--text-muted)]">{t("updates.latestVersion")}</span>
            <span className="font-mono text-[var(--text)]" dir="ltr">
              {latest}
            </span>
          </div>
        )}
        <div className="text-xs text-[var(--text)] pt-1" dir="auto">
          {statusLine}
        </div>
        {checkedAt && (
          <div className="text-[10px] text-[var(--text-muted)]" dir="auto">
            {t("updates.lastCheckedAt", {
              when: formatRelative(checkedAt, i18n.language),
            })}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <button
            type="button"
            onClick={() => refreshMutation.mutate()}
            disabled={refreshMutation.isPending}
            className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-[var(--surface-light)] text-[var(--text)] hover:bg-[var(--surface-light)]/70 transition-colors disabled:opacity-50"
          >
            <RefreshCw size={12} className={refreshMutation.isPending ? "animate-spin" : ""} />
            {refreshMutation.isPending ? t("updates.checking") : t("updates.checkNow")}
          </button>
          {isOutdated && downloadHref && (
            <a
              href={downloadHref}
              target="_blank"
              rel="noreferrer noopener"
              className="text-xs font-medium px-3 py-1.5 rounded-lg bg-[var(--primary)] text-white hover:opacity-90 transition-opacity"
            >
              {t("updates.download")}
            </a>
          )}
          <a
            href="https://github.com/tomerroditi/finance-analysis/releases"
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-1 text-[10px] text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
          >
            {t("updates.openReleases")}
            <ExternalLink size={10} />
          </a>
        </div>
      </div>
    </div>
  );
}
