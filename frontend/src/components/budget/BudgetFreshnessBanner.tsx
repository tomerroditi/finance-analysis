import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { AlertTriangle, X, ArrowRight } from "lucide-react";
import type { BudgetFreshness } from "../../hooks/useBudgetFreshness";
import { groupStaleAccountsByMonth } from "../../hooks/useBudgetFreshness";
import { humanizeProvider } from "../../utils/textFormatting";

interface BudgetFreshnessBannerProps {
  freshness: BudgetFreshness;
  isSyncing: boolean;
  /** Only the current month gets the staleness nudge; history is settled. */
  show: boolean;
  /** Viewed month — missing ranges are clamped to it. */
  year: number;
  month: number;
}

/**
 * Amber nudge shown when the budget's weakest-link sync is very stale (≥ 7
 * days) or an account has never synced — i.e. the KPI figures are materially
 * incomplete. Dismissible for the session; re-appears if the staleness state
 * changes. Always mounted (visibility is internal) so the dismissal survives
 * month navigation.
 */
export const BudgetFreshnessBanner: React.FC<BudgetFreshnessBannerProps> = ({
  freshness,
  isSyncing,
  show,
  year,
  month,
}) => {
  const { t } = useTranslation();
  const [dismissedKey, setDismissedKey] = useState<string | null>(null);

  const { tier, staleAccounts, oldestSyncDate } = freshness;
  const isSevere = tier === "veryStale" || tier === "never";
  const dismissKey = `${tier}:${oldestSyncDate ?? "never"}`;

  // Accounts sharing a missing window (clamped to the viewed month) collapse
  // into one row, so a common window is shown once instead of per account.
  const groups = groupStaleAccountsByMonth(staleAccounts, year, month);

  if (!show || isSyncing || !isSevere || groups.length === 0 || dismissedKey === dismissKey) {
    return null;
  }

  return (
    <div className="flex items-start justify-between gap-3 bg-amber-500/10 border border-amber-500/20 text-amber-400 px-4 py-3 rounded-xl text-sm font-medium">
      <div className="flex items-start gap-2 min-w-0">
        <AlertTriangle size={18} className="shrink-0 mt-0.5" />
        <div className="min-w-0">
          <p>{t("budget.freshness.bannerTitle")}</p>
          <ul className="mt-1.5 space-y-1.5">
            {groups.map((group) => (
              <li
                key={group.range ?? "__never__"}
                className="text-xs font-normal text-amber-400/90"
              >
                <span className="font-medium" dir={group.range ? "ltr" : "auto"}>
                  {group.range ?? t("budget.freshness.neverSynced")}
                </span>
                <span className="opacity-70" dir="auto">
                  {" — "}
                  {group.accounts
                    .map((acc) => `${humanizeProvider(acc.provider)} · ${acc.accountName}`)
                    .join(", ")}
                </span>
              </li>
            ))}
          </ul>
          <Link
            to="/data-sources"
            className="inline-flex items-center gap-1.5 mt-2 text-xs font-semibold hover:underline"
          >
            {t("budget.freshness.syncNow")}
            <ArrowRight size={13} className="shrink-0 rtl:rotate-180" />
          </Link>
        </div>
      </div>
      <button
        onClick={() => setDismissedKey(dismissKey)}
        aria-label={t("common.dismiss")}
        className="shrink-0 text-amber-400/60 hover:text-amber-400 transition-colors"
      >
        <X size={16} />
      </button>
    </div>
  );
};
