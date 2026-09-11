import React from "react";
import { useTranslation } from "react-i18next";
import { CalendarRange, Layers } from "lucide-react";
import type { BudgetLongEnvelope } from "../../../services/api";
import { formatCurrency } from "../../../utils/numberFormatting";
import { envelopeColor, envelopeTextColor, percentOf, rankEnvelopes } from "./envelopeMath";

function KindTag({ kind }: { kind: BudgetLongEnvelope["kind"] }) {
  const { t } = useTranslation();
  const Icon = kind === "project" ? Layers : CalendarRange;
  return (
    <span className="inline-flex items-center gap-1 text-[10px] tracking-wide uppercase text-[var(--text-muted)] whitespace-nowrap">
      <Icon size={11} className="shrink-0" />
      {kind === "project" ? t("budget.project") : t("budget.yearly.tab")}
    </span>
  );
}

interface LongEnvelopesProps {
  envelopes: BudgetLongEnvelope[];
  /** Month label for the contribution column, e.g. "September". */
  monthLabel: string;
  /** A settled month: the standing column describes today, not that month. */
  isPast: boolean;
}

/**
 * Yearly and project envelopes, each showing two figures that must never be
 * mistaken for one another.
 *
 * A yearly or project envelope has no monthly limit, so it has no percentage
 * that belongs to the month being viewed — the backend filters yearly spend by
 * year alone and project spend not at all, so a percentage here always
 * describes today. Only the contribution is scoped to the month. Showing one
 * without the other is what made the old by-kind card misleading: on the live
 * month it showed the lifetime figure, and on a past month the contribution,
 * under headings that looked identical.
 *
 * Hence two columns with their own headings, and on a settled month the
 * standing column says so out loud.
 */
export const LongEnvelopes: React.FC<LongEnvelopesProps> = ({
  envelopes,
  monthLabel,
  isPast,
}) => {
  const { t } = useTranslation();
  if (envelopes.length === 0) return null;

  const ranked = rankEnvelopes(envelopes);
  const columns =
    "grid-cols-[minmax(0,1.4fr)_96px_minmax(0,1fr)_120px_168px_44px]";

  return (
    <div
      data-testid="budget-long-envelopes"
      className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] shadow-sm p-4 md:p-5 flex flex-col gap-3"
    >
      <div className="flex items-center justify-between gap-2">
        <p className="font-bold text-sm md:text-base">
          {t("budget.overview.longEnvelopes")}
        </p>
        <span className="text-xs text-[var(--text-muted)]">
          {t("budget.overview.longEnvelopesCount", { count: envelopes.length })}
        </span>
      </div>

      {/* Column headings exist so neither figure can be read as the other. */}
      <div className={`hidden md:grid ${columns} gap-3 px-3`}>
        <span />
        <span />
        <span />
        <span className="text-end text-[10px] uppercase tracking-wide text-[var(--text-muted)]">
          {t("budget.overview.inMonth", { month: monthLabel })}
        </span>
        <span className="text-end text-[10px] uppercase tracking-wide text-[var(--text-muted)]">
          {isPast ? t("budget.overview.overallNow") : t("budget.overview.overall")}
        </span>
        <span />
      </div>

      <div className="flex flex-col gap-1.5">
        {ranked.map((envelope) => {
          const percent = percentOf(envelope);
          return (
            <div
              key={`${envelope.kind}-${envelope.name}`}
              data-testid="long-envelope-row"
              className="rounded-xl border border-[var(--surface-light)] bg-[var(--surface)] px-3 py-2.5"
            >
              {/* Desktop: one line, both figures under their headings. */}
              <div className={`hidden md:grid ${columns} gap-3 items-center`}>
                <span className="font-semibold text-sm truncate" dir="auto">
                  {envelope.name}
                </span>
                <KindTag kind={envelope.kind} />
                <span className="relative block h-1.5 w-full rounded-full bg-[var(--surface-light)] overflow-hidden">
                  <span
                    className={`absolute inset-y-0 start-0 rounded-full ${envelopeColor(percent)}`}
                    style={{ width: `${Math.min(percent, 100)}%` }}
                  />
                </span>
                <span
                  dir="ltr"
                  data-testid="long-envelope-contribution"
                  className="text-end text-xs font-mono font-bold whitespace-nowrap"
                >
                  {envelope.month_contribution
                    ? formatCurrency(envelope.month_contribution)
                    : "—"}
                </span>
                <span
                  dir="ltr"
                  data-testid="long-envelope-standing"
                  className="text-end text-xs font-mono whitespace-nowrap"
                >
                  <span className="font-bold">{formatCurrency(envelope.spent)}</span>
                  <span className="text-[var(--text-muted)] font-normal">
                    {" / "}
                    {envelope.budget > 0 ? formatCurrency(envelope.budget) : "—"}
                  </span>
                </span>
                <span
                  dir="ltr"
                  className={`text-end text-xs font-mono font-bold ${envelopeTextColor(percent)}`}
                >
                  {envelope.budget > 0 ? `${percent}%` : "—"}
                </span>
              </div>

              {/* Mobile: the two figures stack, each still labelled. */}
              <div className="md:hidden flex flex-col gap-1.5">
                <span className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2 min-w-0">
                    <span className="font-semibold text-sm truncate" dir="auto">
                      {envelope.name}
                    </span>
                    <KindTag kind={envelope.kind} />
                  </span>
                  <span
                    dir="ltr"
                    className={`text-xs font-mono font-bold shrink-0 ${envelopeTextColor(percent)}`}
                  >
                    {envelope.budget > 0 ? `${percent}%` : "—"}
                  </span>
                </span>
                <span className="flex items-center justify-between gap-2 text-[11px] text-[var(--text-muted)]">
                  <span>
                    {t("budget.overview.inMonth", { month: monthLabel })}:{" "}
                    <span dir="ltr" className="font-mono text-[var(--text-default)]">
                      {envelope.month_contribution
                        ? formatCurrency(envelope.month_contribution)
                        : "—"}
                    </span>
                  </span>
                  <span>
                    {isPast
                      ? t("budget.overview.overallNow")
                      : t("budget.overview.overall")}
                    :{" "}
                    <span dir="ltr" className="font-mono text-[var(--text-default)]">
                      {formatCurrency(envelope.spent)}
                    </span>
                  </span>
                </span>
              </div>
            </div>
          );
        })}
      </div>

      <p className="text-[11px] text-[var(--text-muted)] text-pretty">
        {isPast
          ? t("budget.overview.longNotePast", { month: monthLabel })
          : t("budget.overview.longNoteLive", { month: monthLabel })}
      </p>
    </div>
  );
};
