import { useTranslation } from "react-i18next";
import { AlertTriangle, CheckCircle2, Plug } from "lucide-react";
import { STALE_SOURCE_DAYS } from "./sourceHealth";

interface SourcesSummaryProps {
  /** Total connected accounts across every service. */
  total: number;
  /** How many have a successful scrape dated today. */
  syncedToday: number;
  /** How many have never synced or are over a week stale. */
  needsAttention: number;
}

/**
 * Three-up sync-health summary above the source cards.
 *
 * Mirrors the summary strip every other data page opens with (Liabilities'
 * totals, Investments' portfolio overview): same card shell, same
 * `text-[10px] uppercase font-black tracking-widest` label over a
 * `text-xl md:text-2xl font-black` value, same coloured label per severity.
 *
 * "Needs attention" uses the same rule as the Sidebar's Data Sources badge
 * (see `sourceHealth.ts`), so clicking a badge that reads 2 lands on a page
 * that also reads 2.
 */
export function SourcesSummary({
  total,
  syncedToday,
  needsAttention,
}: SourcesSummaryProps) {
  const { t } = useTranslation();
  const allFresh = needsAttention === 0;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 md:gap-4">
      <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl p-4 md:p-6">
        <p className="text-[10px] uppercase font-black tracking-widest text-[var(--text-muted)] mb-1 flex items-center gap-1.5">
          <Plug size={12} />
          {t("dataSources.summaryConnected")}
        </p>
        <p className="text-xl md:text-2xl font-black text-white" dir="ltr">
          {total}
        </p>
      </div>

      <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl p-4 md:p-6">
        <p className="text-[10px] uppercase font-black tracking-widest text-emerald-400 mb-1 flex items-center gap-1.5">
          <CheckCircle2 size={12} />
          {t("dataSources.summarySyncedToday")}
        </p>
        {/* One LTR run: the "x / y" pair must not reorder under RTL. */}
        <p className="text-xl md:text-2xl font-black text-white" dir="ltr">
          {syncedToday}
          <span className="text-[var(--text-muted)] text-base font-bold">
            {" / "}
            {total}
          </span>
        </p>
      </div>

      <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl p-4 md:p-6">
        <p
          className={`text-[10px] uppercase font-black tracking-widest mb-1 flex items-center gap-1.5 ${
            allFresh ? "text-[var(--text-muted)]" : "text-amber-400"
          }`}
        >
          <AlertTriangle size={12} />
          {t("dataSources.summaryNeedsAttention")}
        </p>
        <p className="text-xl md:text-2xl font-black text-white" dir="ltr">
          {needsAttention}
        </p>
        <p className="text-[10px] text-[var(--text-muted)] mt-0.5">
          {allFresh
            ? t("dataSources.summaryAllFresh")
            : t("dataSources.summaryNeedsAttentionHint", {
                count: STALE_SOURCE_DAYS,
              })}
        </p>
      </div>
    </div>
  );
}
