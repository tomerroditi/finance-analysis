import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import type { FireAnnuity, FireWithdrawal } from "../../services/api";
import { formatCurrency } from "../../utils/numberFormatting";
import { flowLabel } from "./labels";

const cardClass = "p-4 rounded-xl bg-[var(--surface)] border border-[var(--surface-light)]";
const titleClass = "mb-3 text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider";
const headClass =
  "px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)] whitespace-nowrap";
const cellClass = "px-2 py-2 align-top";

/** A span of months in words: months under two years, years with a decimal above. */
function duration(fromAge: number, toAge: number, t: TFunction): string {
  const months = Math.max(1, Math.round((toAge - fromAge) * 12));
  if (months < 24) return t("fire.withdrawal.months", { count: months });
  return t("fire.withdrawal.years", { years: (months / 12).toFixed(1) });
}

function KindBadge({ recognised }: { recognised: boolean }) {
  const { t } = useTranslation();
  return (
    <span
      className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${
        recognised ? "bg-emerald-500/15 text-emerald-400" : "bg-amber-500/15 text-amber-400"
      }`}
    >
      {t(recognised ? "fire.annuity.recognised" : "fire.annuity.entitling")}
    </span>
  );
}

/**
 * Every annuity the plan will draw, one table row each, grouped by person:
 * what it is, whether it is recognised or entitling, from what age, how much.
 */
export function AnnuitiesTable({ annuities }: { annuities: FireAnnuity[] }) {
  const { t } = useTranslation();
  const owners = [...new Set(annuities.map((a) => a.owner))];
  const total = annuities.reduce((sum, a) => sum + a.monthly, 0);

  return (
    <div data-testid="fire-annuities" className={cardClass}>
      <h4 className={titleClass}>{t("fire.section.annuities")}</h4>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[var(--surface-light)]">
            <th className={`${headClass} text-start`}>{t("fire.annuity.colSource")}</th>
            <th className={`${headClass} text-center`}>{t("fire.annuity.colFrom")}</th>
            <th className={`${headClass} text-end`}>{t("fire.annuity.colMonthly")}</th>
          </tr>
        </thead>
        {owners.map((owner) => (
          <tbody key={owner} data-testid="fire-annuity-group">
            {owner && owners.length > 1 && (
              <tr>
                <td colSpan={3} className="px-2 pt-3 pb-1 text-xs font-semibold text-[var(--text-primary)]" dir="auto">
                  {owner}
                </td>
              </tr>
            )}
            {annuities
              .filter((a) => a.owner === owner)
              .map((annuity, index) => (
                <tr key={index} className="border-b border-[var(--surface-light)]/50">
                  <td className={`${cellClass} text-[var(--text-primary)]`}>
                    <div dir="auto">
                      {annuity.description || t(`fire.annuitySource.${annuity.source}`)}
                      <span className="text-[var(--text-muted)]">
                        {" · "}
                        {t(`fire.annuityComponent.${annuity.component}`)}
                      </span>
                    </div>
                    <div className="mt-1">
                      <KindBadge recognised={annuity.recognised} />
                    </div>
                  </td>
                  <td className={`${cellClass} text-center whitespace-nowrap text-[var(--text-secondary)]`}>
                    {annuity.claim_age.toFixed(0)}
                  </td>
                  <td className={`${cellClass} text-end whitespace-nowrap`}>
                    <div className="font-medium text-[var(--text-primary)]">
                      {formatCurrency(annuity.monthly)}
                    </div>
                    {annuity.factor ? (
                      <div className="text-[10px] text-[var(--text-muted)]">
                        {t("fire.annuity.factor", { factor: annuity.factor.toFixed(1) })}
                      </div>
                    ) : null}
                  </td>
                </tr>
              ))}
          </tbody>
        ))}
        <tfoot>
          <tr>
            <td colSpan={2} className={`${cellClass} text-xs text-[var(--text-muted)]`}>
              {t("fire.annuity.total")}
            </td>
            <td className={`${cellClass} text-end whitespace-nowrap font-semibold text-[var(--text-primary)]`}>
              {formatCurrency(total)}
            </td>
          </tr>
        </tfoot>
      </table>
      <p className="mt-2 text-[11px] text-[var(--text-muted)]">{t("fire.annuity.legend")}</p>
    </div>
  );
}

/**
 * The order the plan draws on its money after retirement: each source, the
 * ages it covers with a bar on the drawdown's own timeline, and its average
 * monthly draw.
 */
export function DrawdownTable({ segments }: { segments: FireWithdrawal[] }) {
  const { t } = useTranslation();
  const start = Math.min(...segments.map((s) => s.from_age));
  const end = Math.max(...segments.map((s) => s.to_age));
  const span = Math.max(end - start, 1 / 12);

  return (
    <div data-testid="fire-withdrawal-plan" className={cardClass}>
      <h4 className={titleClass}>{t("fire.section.withdrawalPlan")}</h4>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[var(--surface-light)]">
            <th className={`${headClass} text-start`}>{t("fire.withdrawal.colSource")}</th>
            <th className={`${headClass} text-start`}>{t("fire.withdrawal.colAges")}</th>
            <th className={`${headClass} text-end`}>{t("fire.withdrawal.colMonthly")}</th>
          </tr>
        </thead>
        <tbody>
          {segments.map((segment, index) => {
            const offset = ((segment.from_age - start) / span) * 100;
            const width = Math.max(((segment.to_age - segment.from_age) / span) * 100, 1.5);
            return (
              <tr key={index} className="border-b border-[var(--surface-light)]/50" data-testid="fire-withdrawal-row">
                <td className={`${cellClass} text-[var(--text-primary)]`} dir="auto">
                  {segment.description || flowLabel(segment.source, t)}
                </td>
                <td className={`${cellClass} w-[40%]`}>
                  <div className="flex items-baseline justify-between gap-2 whitespace-nowrap">
                    <span dir="ltr" className="text-[var(--text-secondary)]">
                      {segment.from_age.toFixed(1)}–{segment.to_age.toFixed(1)}
                    </span>
                    <span className="text-[10px] text-[var(--text-muted)]">
                      {duration(segment.from_age, segment.to_age, t)}
                    </span>
                  </div>
                  <div className="relative mt-1 h-1.5 rounded-full bg-[var(--surface-light)]" dir="ltr">
                    <div
                      className="absolute inset-y-0 rounded-full bg-sky-500"
                      style={{ left: `${offset}%`, width: `${Math.min(width, 100 - offset)}%` }}
                    />
                  </div>
                </td>
                <td className={`${cellClass} text-end whitespace-nowrap font-medium text-[var(--text-primary)]`}>
                  {formatCurrency(segment.monthly_average)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
