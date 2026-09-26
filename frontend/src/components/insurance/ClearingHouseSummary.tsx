import { useTranslation } from "react-i18next";
import { AlertTriangle, ShieldCheck, Sunrise } from "lucide-react";
import type { ClearingHouseReport } from "../../services/api";
import { formatDate } from "../../utils/dateFormatting";
import { formatChange, formatCurrency } from "../../utils/numberFormatting";
import { isSubscriptionEndingSoon } from "../../utils/policyDetails";

function fmtDate(value: string | null): string {
  return value ? formatDate(new Date(value)) : "—";
}

function Figure({
  label,
  value,
  sub,
  testId,
}: {
  label: string;
  value: number | null;
  sub?: string | null;
  testId?: string;
}) {
  return (
    <div className="min-w-0">
      <p className="text-[var(--text-muted)] text-[11px] leading-snug">{label}</p>
      <p data-testid={testId} className="text-white font-black text-base md:text-lg whitespace-nowrap mt-0.5">
        {value == null ? "—" : formatCurrency(value)}
      </p>
      {sub && <p className="text-[var(--text-muted)] text-[10px] mt-0.5">{sub}</p>}
    </div>
  );
}

function CoverTile({
  label,
  value,
  monthly,
  testId,
}: {
  label: string;
  value: number | null;
  monthly: boolean;
  testId?: string;
}) {
  const { t } = useTranslation();
  const none = !value;
  return (
    <div className="bg-[var(--background)]/50 rounded-xl p-3 min-w-0">
      <p className="text-[var(--text-muted)] text-[11px] leading-snug">{label}</p>
      <p
        data-testid={testId}
        className={`font-bold text-sm md:text-base mt-1 whitespace-nowrap ${none ? "text-[var(--text-muted)]" : "text-white"}`}
      >
        {none ? t("insurance.clearingHouse.noCover") : formatCurrency(value)}
        {!none && monthly && (
          <span className="text-[var(--text-muted)] text-[10px] font-medium ms-1">
            {t("insurance.perMonth")}
          </span>
        )}
      </p>
    </div>
  );
}

/**
 * The clearing house's latest household summary: what the saver can expect
 * at retirement and what their insurance pays out today. Its reports cover
 * every fund the saver holds, so these figures belong to no single policy.
 *
 * The expected pension leads — it is the one number the whole page exists to
 * answer — with the lump sum and projected balance beneath it and the cover a
 * glanceable grid beside it.
 */
export function ClearingHouseSummary({ reports }: { reports: ClearingHouseReport[] }) {
  const { t } = useTranslation();
  const latest = reports[reports.length - 1];
  if (!latest) return null;
  const previous = reports.length > 1 ? reports[reports.length - 2] : undefined;
  const pensionChange =
    previous?.forecast_monthly_pension != null && latest.forecast_monthly_pension != null
      ? latest.forecast_monthly_pension - previous.forecast_monthly_pension
      : null;

  return (
    <section
      data-testid="clearing-house-summary"
      className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] p-4 md:p-6"
    >
      <div className="flex flex-col sm:flex-row sm:items-baseline sm:justify-between gap-0.5 mb-4">
        <h2 className="text-white font-bold text-base md:text-lg">
          {t("insurance.clearingHouse.title")}
        </h2>
        <p className="text-[var(--text-muted)] text-xs">
          {t("insurance.clearingHouse.source")} ·{" "}
          {latest.report_number != null && latest.report_count != null
            ? t("insurance.clearingHouse.asOfReport", {
                date: fmtDate(latest.calc_date),
                number: latest.report_number,
                count: latest.report_count,
              })
            : t("insurance.clearingHouse.asOf", { date: fmtDate(latest.calc_date) })}
        </p>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div className="rounded-xl p-4 bg-gradient-to-br from-amber-500/10 via-[var(--background)]/50 to-[var(--background)]/50 border border-amber-500/15">
          <p className="flex items-center gap-1.5 text-amber-300/90 text-[10px] uppercase tracking-widest font-bold">
            <Sunrise size={12} className="text-amber-400" />
            {t("insurance.clearingHouse.monthlyPension")}
          </p>
          <p className="flex items-baseline gap-1.5 flex-wrap mt-1">
            <span
              data-testid="clearing-house-monthly-pension"
              className="text-white font-black text-3xl md:text-4xl whitespace-nowrap"
            >
              {latest.forecast_monthly_pension == null
                ? "—"
                : formatCurrency(latest.forecast_monthly_pension)}
            </span>
            <span className="text-[var(--text-muted)] text-xs">{t("insurance.perMonth")}</span>
          </p>
          {pensionChange ? (
            <span
              className={`inline-block mt-1.5 px-2 py-0.5 rounded-full text-[11px] font-bold ${
                pensionChange > 0
                  ? "bg-emerald-500/15 text-emerald-400"
                  : "bg-rose-500/15 text-rose-400"
              }`}
            >
              {t("insurance.clearingHouse.sinceLastReport", {
                change: formatChange(pensionChange),
              })}
            </span>
          ) : null}
          <div className="grid grid-cols-2 gap-3 mt-4 pt-3 border-t border-[var(--surface-light)]/40">
            <Figure label={t("insurance.clearingHouse.lumpSum")} value={latest.forecast_lump_sum} />
            <Figure
              label={t("insurance.clearingHouse.projectedSavings")}
              value={latest.forecast_total_balance}
              sub={
                latest.total_savings != null
                  ? t("insurance.clearingHouse.fromToday", {
                      amount: formatCurrency(latest.total_savings),
                    })
                  : null
              }
            />
          </div>
        </div>
        <div>
          <p className="flex items-center gap-1.5 text-[var(--text-muted)] text-[10px] uppercase tracking-widest font-bold mb-2">
            <ShieldCheck size={12} className="text-blue-400" />
            {t("insurance.clearingHouse.cover")}
          </p>
          <div className="grid grid-cols-2 gap-2">
            <CoverTile
              label={t("insurance.clearingHouse.disabilityMonthly")}
              value={latest.disability_monthly}
              monthly
              testId="clearing-house-disability"
            />
            <CoverTile
              label={t("insurance.clearingHouse.survivorSpouseMonthly")}
              value={latest.survivor_spouse_monthly}
              monthly
            />
            <CoverTile
              label={t("insurance.clearingHouse.survivorChildMonthly")}
              value={latest.survivor_child_monthly}
              monthly
            />
            <CoverTile
              label={t("insurance.clearingHouse.deathLumpSum")}
              value={latest.death_lump_sum}
              monthly={false}
            />
          </div>
        </div>
      </div>
      <p className="text-[var(--text-muted)] text-[10px] mt-3">
        {t("insurance.clearingHouse.forecastNote")}
      </p>
    </section>
  );
}

/** Warns that the monthly clearing-house reports are about to stop arriving. */
export function SubscriptionNotice({ reports }: { reports: ClearingHouseReport[] }) {
  const { t } = useTranslation();
  const latest = reports[reports.length - 1];
  if (!isSubscriptionEndingSoon(latest)) return null;
  return (
    <div
      role="status"
      data-testid="clearing-house-subscription-notice"
      className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-200"
    >
      <AlertTriangle size={14} className="shrink-0 mt-0.5 text-amber-400" />
      <span>
        {latest.subscription_expires
          ? t("insurance.clearingHouse.subscriptionEnding", {
              date: fmtDate(latest.subscription_expires),
              count: latest.subscription_months_left ?? 0,
            })
          : t("insurance.clearingHouse.subscriptionEndingNoDate", {
              count: latest.subscription_months_left ?? 0,
            })}
      </span>
    </div>
  );
}
