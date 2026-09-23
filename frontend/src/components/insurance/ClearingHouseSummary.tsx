import { useTranslation } from "react-i18next";
import { AlertTriangle, ShieldCheck, Sunrise } from "lucide-react";
import type { ClearingHouseReport } from "../../services/api";
import { formatDate } from "../../utils/dateFormatting";
import { formatChange, formatCurrency } from "../../utils/numberFormatting";
import { isSubscriptionEndingSoon } from "../../utils/policyDetails";

function fmtDate(value: string | null): string {
  return value ? formatDate(new Date(value)) : "—";
}

function Row({
  label,
  value,
  note,
  testId,
}: {
  label: string;
  value: number | null;
  note?: string | null;
  testId?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5 border-b border-[var(--surface-light)]/30 last:border-0">
      <span className="text-[var(--text-muted)] text-xs">{label}</span>
      <span className="flex items-baseline gap-2 shrink-0">
        {note && <span className="text-[10px] font-bold text-emerald-400">{note}</span>}
        <span data-testid={testId} className="text-white font-mono font-bold text-sm whitespace-nowrap">
          {value == null ? "—" : formatCurrency(value)}
        </span>
      </span>
    </div>
  );
}

/**
 * The clearing house's latest household summary: what the saver can expect
 * at retirement and what their insurance pays out today. Its reports cover
 * every fund the saver holds, so these figures belong to no single policy.
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
      <div className="flex flex-col sm:flex-row sm:items-baseline sm:justify-between gap-1 mb-3">
        <h2 className="text-white font-bold text-base md:text-lg">
          {t("insurance.clearingHouse.title")}
        </h2>
        <p className="text-[var(--text-muted)] text-xs">
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
        <div className="bg-[var(--background)]/50 rounded-xl p-3">
          <p className="flex items-center gap-1.5 text-[var(--text-muted)] text-[10px] uppercase tracking-widest font-bold mb-1">
            <Sunrise size={12} className="text-amber-400" />
            {t("insurance.clearingHouse.atRetirement")}
          </p>
          <Row
            label={t("insurance.clearingHouse.monthlyPension")}
            value={latest.forecast_monthly_pension}
            note={
              pensionChange
                ? t("insurance.clearingHouse.sinceLastReport", {
                    change: formatChange(pensionChange),
                  })
                : null
            }
            testId="clearing-house-monthly-pension"
          />
          <Row label={t("insurance.clearingHouse.lumpSum")} value={latest.forecast_lump_sum} />
          <Row
            label={t("insurance.clearingHouse.projectedSavings")}
            value={latest.forecast_total_balance}
          />
          <Row label={t("insurance.clearingHouse.savedToday")} value={latest.total_savings} />
        </div>
        <div className="bg-[var(--background)]/50 rounded-xl p-3">
          <p className="flex items-center gap-1.5 text-[var(--text-muted)] text-[10px] uppercase tracking-widest font-bold mb-1">
            <ShieldCheck size={12} className="text-blue-400" />
            {t("insurance.clearingHouse.cover")}
          </p>
          <Row
            label={t("insurance.clearingHouse.disabilityMonthly")}
            value={latest.disability_monthly}
            testId="clearing-house-disability"
          />
          <Row
            label={t("insurance.clearingHouse.survivorSpouseMonthly")}
            value={latest.survivor_spouse_monthly}
          />
          <Row
            label={t("insurance.clearingHouse.survivorChildMonthly")}
            value={latest.survivor_child_monthly}
          />
          <Row label={t("insurance.clearingHouse.deathLumpSum")} value={latest.death_lump_sum} />
        </div>
      </div>
      <p className="text-[var(--text-muted)] text-[10px] mt-2">
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
