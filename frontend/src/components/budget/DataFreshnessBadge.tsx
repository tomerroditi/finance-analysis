import React, { useCallback, useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import {
  CheckCircle2,
  Clock,
  AlertTriangle,
  RefreshCw,
  ArrowRight,
} from "lucide-react";
import type { FreshnessTier, StaleAccount } from "../../hooks/useBudgetFreshness";
import { groupStaleAccountsByMonth } from "../../hooks/useBudgetFreshness";
import { formatMissingRange } from "../../utils/dateFormatting";
import { humanizeProvider } from "../../utils/textFormatting";

interface DataFreshnessBadgeProps {
  tier: FreshnessTier;
  oldestSyncDate: string | null;
  staleAccounts: StaleAccount[];
  isSyncing: boolean;
  /** Viewed month — missing ranges are clamped to it. */
  year: number;
  month: number;
}

interface TierStyle {
  icon: React.ReactNode;
  chip: string;
  text: string;
}

/**
 * Compact "last synced" chip for the budget month view. Quiet when data is
 * fresh; escalates color + iconography as the weakest-link sync ages, and
 * exposes a hover/tap popover that names the stale accounts and links to
 * Data Sources for a re-sync. Pure presentation — freshness is computed by
 * `useBudgetFreshness`.
 *
 * The severe tiers (very stale / never synced) used to suppress the chip and
 * hand off to a full-width amber banner above the budget. That banner is gone:
 * it repeated what the popover already says and cost a whole row before any
 * budget figure appeared. They now render here as a bare warning triangle —
 * the detail is one hover (or tap) away, same as every other tier.
 */
export const DataFreshnessBadge: React.FC<DataFreshnessBadgeProps> = ({
  tier,
  oldestSyncDate,
  staleAccounts,
  isSyncing,
  year,
  month,
}) => {
  const { t } = useTranslation();
  const [showDetails, setShowDetails] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  // The chip sits in the command bar's right-hand group, so the panel opens
  // end-anchored — but on a phone it is wider than the room to the chip's
  // start, and its leading edge lands off-screen where nothing scrolls to it.
  // Nudge it back inside the viewport. Written straight to the node (not
  // state) so one measurement settles it without a second render; clearing
  // the transform first keeps the measurement independent of the last nudge.
  // Declared above the tier early-returns — React requires unconditional hooks.
  const nudgeIntoView = useCallback(() => {
    const panel = panelRef.current;
    if (!panel) return;
    panel.style.transform = "";
    const { left, right } = panel.getBoundingClientRect();
    const dx = left < 8 ? 8 - left : Math.min(0, window.innerWidth - 8 - right);
    if (dx) panel.style.transform = `translateX(${dx}px)`;
  }, []);

  useLayoutEffect(() => {
    if (showDetails) nudgeIntoView();
  }, [showDetails, nudgeIntoView]);

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

  const isSevere = !isSyncing && (tier === "veryStale" || tier === "never");
  const effectiveTier = isSyncing ? "syncing" : tier;
  const style = styles[effectiveTier];

  // The range is LTR date content; keep it isolated from any surrounding RTL
  // label so the month/day order survives in Hebrew.
  const labelNode = isSyncing ? (
    <span>{t("budget.freshness.syncing")}</span>
  ) : tier === "fresh" ? (
    <span>{t("budget.freshness.upToDate")}</span>
  ) : tier === "never" ? (
    <span>{t("budget.freshness.neverSynced")}</span>
  ) : (
    <>
      <span>{t("budget.freshness.missingLabel")}</span>
      {oldestSyncDate && (
        <span dir="ltr">{formatMissingRange(oldestSyncDate, year, month)}</span>
      )}
    </>
  );

  // Accounts missing data within the viewed month, grouped by shared window.
  const groups = groupStaleAccountsByMonth(staleAccounts, year, month);

  // Popover only carries weight when there are accounts to act on and we're
  // not mid-sync.
  const hasDetails = !isSyncing && groups.length > 0;

  const chip = (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border py-1 text-[11px] font-medium ${
        isSevere ? "px-1.5" : "px-2.5"
      } ${style.chip} ${hasDetails ? "cursor-pointer" : ""}`}
      // Opens rather than toggles: a mouse click is preceded by a hover, which
      // already revealed the panel, so toggling here closed it on the way in.
      // Closing is the pointer leaving (hover) or the backdrop (tap).
      onClick={hasDetails ? () => setShowDetails(true) : undefined}
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
      aria-label={
        isSevere || hasDetails ? t("budget.freshness.showDetails") : undefined
      }
      title={isSevere ? t("budget.freshness.bannerTitle") : undefined}
    >
      {isSevere ? <AlertTriangle size={15} className="shrink-0" /> : style.icon}
      {!isSevere && labelNode}
    </span>
  );

  if (!hasDetails) {
    return <div className="flex items-center">{chip}</div>;
  }

  return (
    // Two ways in, because they need different mechanics. A mouse uses CSS
    // `group-hover`, which needs no state and — unlike a JS `mouseleave` — is
    // not defeated by the full-screen backdrop being a descendant. Touch fires
    // neither, so a tap sets `showDetails`, and the backdrop (rendered only on
    // that path) is what dismisses it.
    <div
      className="group relative flex items-center"
      onMouseEnter={() => requestAnimationFrame(nudgeIntoView)}
    >
      {chip}
      {showDetails && (
        <div className="fixed inset-0 z-[19]" onClick={() => setShowDetails(false)} />
      )}
      <div
        ref={panelRef}
        className={`absolute top-full mt-2 end-0 z-20 w-[calc(100vw-2rem)] sm:w-72 rounded-xl border border-[var(--surface-light)] bg-[var(--surface)] p-3 shadow-xl ${
          showDetails ? "block" : "hidden group-hover:block"
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        <p className="text-xs font-semibold text-[var(--text-default)] mb-2">
          {t("budget.freshness.staleTitle")}
        </p>
        <ul className="space-y-2 mb-3">
          {groups.map((group) => (
            <li key={group.range ?? "__never__"} className="text-xs">
              <p
                className="font-medium text-[var(--text-default)]"
                dir={group.range ? "ltr" : "auto"}
              >
                {group.range ?? t("budget.freshness.neverSynced")}
              </p>
              <p className="text-[10px] text-[var(--text-muted)]" dir="auto">
                {group.accounts
                  .map((acc) => `${humanizeProvider(acc.provider)} · ${acc.accountName}`)
                  .join(", ")}
              </p>
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
    </div>
  );
};
