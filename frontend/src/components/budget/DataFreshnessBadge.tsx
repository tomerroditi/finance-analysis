import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  CheckCircle2,
  Clock,
  AlertTriangle,
  RefreshCw,
  ArrowRight,
} from "lucide-react";
import type { FreshnessTier, StaleAccount } from "../../hooks/useBudgetFreshness";
import { formatRelativeDate } from "../../utils/dateFormatting";
import { humanizeProvider } from "../../utils/textFormatting";

interface DataFreshnessBadgeProps {
  tier: FreshnessTier;
  oldestSyncDate: string | null;
  staleAccounts: StaleAccount[];
  isSyncing: boolean;
}

interface TierStyle {
  icon: React.ReactNode;
  chip: string;
  text: string;
}

/**
 * Compact "last synced" chip for the budget month view. Quiet when data is
 * fresh; escalates color + iconography as the weakest-link sync ages, and
 * exposes a tap/hover popover that names the stale accounts and links to
 * Data Sources for a re-sync. Pure presentation — freshness is computed by
 * `useBudgetFreshness`.
 */
export const DataFreshnessBadge: React.FC<DataFreshnessBadgeProps> = ({
  tier,
  oldestSyncDate,
  staleAccounts,
  isSyncing,
}) => {
  const { t } = useTranslation();
  const [showDetails, setShowDetails] = useState(false);

  const styles: Record<FreshnessTier | "syncing", TierStyle> = {
    syncing: {
      icon: <RefreshCw size={13} className="animate-spin shrink-0" />,
      chip: "bg-blue-500/10 border-blue-500/20 text-blue-400",
      text: "text-blue-400",
    },
    fresh: {
      icon: <CheckCircle2 size={13} className="shrink-0" />,
      chip: "bg-emerald-500/10 border-emerald-500/20 text-emerald-400",
      text: "text-emerald-400",
    },
    aging: {
      icon: <Clock size={13} className="shrink-0" />,
      chip: "bg-[var(--surface-light)]/40 border-[var(--surface-light)] text-[var(--text-muted)]",
      text: "text-[var(--text-muted)]",
    },
    stale: {
      icon: <Clock size={13} className="shrink-0" />,
      chip: "bg-amber-500/10 border-amber-500/20 text-amber-400",
      text: "text-amber-400",
    },
    veryStale: {
      icon: <AlertTriangle size={13} className="shrink-0" />,
      chip: "bg-rose-500/10 border-rose-500/20 text-rose-400",
      text: "text-rose-400",
    },
    never: {
      icon: <AlertTriangle size={13} className="shrink-0" />,
      chip: "bg-rose-500/10 border-rose-500/20 text-rose-400",
      text: "text-rose-400",
    },
    none: {
      icon: null,
      chip: "",
      text: "",
    },
  };

  if (tier === "none") return null;

  // Very-stale / never escalate to the banner, which carries the full account
  // list and the call to action. Don't also render a redundant chip — except
  // while syncing, when the chip shows live progress and the banner is hidden.
  if (!isSyncing && (tier === "veryStale" || tier === "never")) return null;

  const effectiveTier = isSyncing ? "syncing" : tier;
  const style = styles[effectiveTier];

  const label = (() => {
    if (isSyncing) return t("budget.freshness.syncing");
    if (tier === "fresh") return t("budget.freshness.upToDate");
    if (tier === "never") return t("budget.freshness.neverSynced");
    return t("budget.freshness.updated", {
      time: oldestSyncDate ? formatRelativeDate(oldestSyncDate) : "",
    });
  })();

  // Popover only carries weight when there are accounts to act on and we're
  // not mid-sync.
  const hasDetails = !isSyncing && staleAccounts.length > 0;

  const chip = (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium ${style.chip} ${
        hasDetails ? "cursor-pointer" : ""
      }`}
      onClick={hasDetails ? () => setShowDetails((v) => !v) : undefined}
      role={hasDetails ? "button" : undefined}
      tabIndex={hasDetails ? 0 : undefined}
      onKeyDown={
        hasDetails
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setShowDetails((v) => !v);
              }
            }
          : undefined
      }
      aria-label={hasDetails ? t("budget.freshness.showDetails") : undefined}
    >
      {style.icon}
      <span dir="auto">{label}</span>
    </span>
  );

  if (!hasDetails) {
    return <div className="flex items-center">{chip}</div>;
  }

  return (
    <div className="relative flex items-center">
      {chip}
      {showDetails && (
        <>
          {/* Click-away backdrop (works for touch + mouse). */}
          <div
            className="fixed inset-0 z-[19]"
            onClick={() => setShowDetails(false)}
          />
          <div
            className="absolute top-full mt-2 inset-inline-start-0 z-20 w-full max-w-[calc(100vw-2rem)] sm:w-72 rounded-xl border border-[var(--surface-light)] bg-[var(--surface)] p-3 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <p className="text-xs font-semibold text-[var(--text-default)] mb-2">
              {t("budget.freshness.staleTitle")}
            </p>
            <ul className="space-y-1.5 mb-3">
              {staleAccounts.map((acc) => (
                <li
                  key={`${acc.provider}_${acc.accountName}`}
                  className="flex items-center justify-between gap-2 text-xs"
                >
                  <span className="truncate text-[var(--text-default)]" dir="auto">
                    {humanizeProvider(acc.provider)}
                    <span className="text-[var(--text-muted)]"> · </span>
                    <span dir="auto">{acc.accountName}</span>
                  </span>
                  <span className="shrink-0 text-[10px] text-[var(--text-muted)]" dir="auto">
                    {acc.lastScrapeDate
                      ? formatRelativeDate(acc.lastScrapeDate)
                      : t("dataSources.neverSynced")}
                  </span>
                </li>
              ))}
            </ul>
            <Link
              to="/data-sources"
              onClick={() => setShowDetails(false)}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--primary)] hover:underline"
            >
              {t("budget.freshness.syncNow")}
              <ArrowRight size={13} className="shrink-0 rtl:rotate-180" />
            </Link>
          </div>
        </>
      )}
    </div>
  );
};
