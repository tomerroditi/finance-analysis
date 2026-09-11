import React from "react";
import { useTranslation } from "react-i18next";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { Link } from "react-router";
import { ChevronLeft, ChevronRight, Clock, Lock } from "lucide-react";
import { budgetApi } from "../../../services/api";
import { Skeleton } from "../../common/Skeleton";
import { useQueryKeys } from "../../../hooks/useQueryKeys";
import { formatMonthYear } from "../../../utils/dateFormatting";
import { formatCurrency } from "../../../utils/numberFormatting";
import { CommitmentBar } from "../../budget/overview/CommitmentBar";
import { percentOf, rankEnvelopes } from "../../budget/overview/envelopeMath";

/** How many long envelopes fit the card before it outgrows the dashboard slot. */
const CARD_ENVELOPES = 2;

/** An envelope is "hot" once this full. */
const HOT = 90;

interface OverviewBudgetTabProps {
  year: number;
  month: number;
  onYearChange: (year: number) => void;
  onMonthChange: (month: number) => void;
}

/**
 * The dashboard budget card's Overview tab: the whole budget in one glance.
 *
 * Says nothing about pace. The card shows where the month's budget stands as
 * four parts (charged, chosen, still owed, free), a verdict built from those
 * parts rather than from elapsed days, and the envelopes that need a decision.
 *
 * The yearly-and-projects block is the card's answer to a question the old
 * design got wrong: those envelopes have no monthly limit, so one column states
 * what this month put in and the other where the envelope stands overall, each
 * under its own heading. On a settled month the second column is headed "now",
 * because that is what it describes.
 */
export const OverviewBudgetTab: React.FC<OverviewBudgetTabProps> = ({
  year,
  month,
  onYearChange,
  onMonthChange,
}) => {
  const { t, i18n } = useTranslation();
  const isRtl = i18n.language === "he";
  const qk = useQueryKeys();

  const { data: overview, isLoading } = useQuery({
    queryKey: qk.budget.overview(year, month, false),
    queryFn: () => budgetApi.getOverview(year, month).then((res) => res.data),
    placeholderData: keepPreviousData,
  });

  const monthName = formatMonthYear(new Date(year, month - 1));
  const shortMonth = new Date(year, month - 1).toLocaleString(
    isRtl ? "he-IL" : "en-US",
    { month: "short" },
  );

  const step = (delta: number) => {
    const next = new Date(year, month - 1 + delta);
    onYearChange(next.getFullYear());
    onMonthChange(next.getMonth() + 1);
  };

  const nav = (
    <div className="h-9 flex items-center justify-between w-full mb-4">
      <div className="flex items-center gap-2">
        <button
          onClick={() => step(-1)}
          aria-label={t("common.previous")}
          className="p-1 rounded-lg hover:bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
        >
          {isRtl ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)] w-36 text-center">
          {monthName}
        </p>
        <button
          onClick={() => step(1)}
          aria-label={t("common.next")}
          className="p-1 rounded-lg hover:bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
        >
          {isRtl ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
        </button>
      </div>
      {overview && (
        <span className="inline-flex items-center gap-1 text-xs text-[var(--text-muted)]">
          {overview.is_current_month ? (
            <>
              <Clock size={12} />
              {t("dashboard.daysRemaining", { count: overview.days_left })}
            </>
          ) : (
            <>
              <Lock size={12} />
              {t("budget.overview.closed")}
            </>
          )}
        </span>
      )}
    </div>
  );

  if (isLoading || !overview) {
    return (
      <div className="flex flex-1 flex-col min-h-0">
        {nav}
        <Skeleton variant="card" className="h-40" />
      </div>
    );
  }

  const {
    is_current_month: isCurrent,
    monthly_spent: spent,
    monthly_budget: budget,
    free_to_spend: free,
    projected,
    long_envelopes: longEnvelopes,
  } = overview;

  if (budget <= 0 && spent === 0) {
    return (
      <div className="flex flex-1 flex-col min-h-0">
        {nav}
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <p className="text-sm text-[var(--text-muted)] mb-3">
            {t("budget.overview.noBudgetForMonth")}
          </p>
          <Link
            to="/budget"
            className="text-sm font-medium text-[var(--primary)] hover:text-[var(--primary-dark)] transition-colors"
          >
            {t("budget.overview.openOverview")} &rarr;
          </Link>
        </div>
      </div>
    );
  }

  const finalOrProjected = projected ?? spent;
  const delta = budget - finalOrProjected;
  const ranked = rankEnvelopes(longEnvelopes);
  const shown = ranked.slice(0, CARD_ENVELOPES);
  const remaining = ranked.length - shown.length;
  const troubled = ranked.filter((envelope) => percentOf(envelope) >= HOT).length;

  return (
    <div className="flex flex-1 flex-col min-h-0">
      {nav}

      <div className="flex items-baseline gap-2 flex-wrap mb-2.5">
        <span dir="ltr" className="text-2xl font-bold font-mono">
          {formatCurrency(spent)}
        </span>
        <span dir="ltr" className="text-sm text-[var(--text-muted)] font-mono">
          / {budget > 0 ? formatCurrency(budget) : "—"}
        </span>
        <span
          className={`text-xs font-medium px-2 py-0.5 rounded-full ${
            (isCurrent ? free : delta) < 0
              ? "bg-rose-500/10 text-rose-400"
              : "bg-emerald-500/10 text-emerald-400"
          }`}
        >
          {isCurrent
            ? t("budget.overview.freeAfterCommitments", {
                amount: formatCurrency(free),
              })
            : delta < 0
              ? t("budget.overview.overBudget", {
                  amount: formatCurrency(Math.abs(delta)),
                })
              : t("budget.overview.underBudget", {
                  amount: formatCurrency(delta),
                })}
        </span>
      </div>

      <CommitmentBar overview={overview} height={12} compact hideFreeInLegend />

      <p className="text-sm text-[var(--text-muted)] text-pretty mt-3">
        <span
          className={`font-semibold ${delta < 0 ? "text-rose-400" : "text-emerald-400"}`}
        >
          {isCurrent
            ? delta < 0
              ? t("budget.overview.headingOver")
              : t("budget.overview.headingUnder")
            : delta < 0
              ? t("budget.overview.closedOver")
              : t("budget.overview.closedUnder")}
        </span>{" "}
        &mdash;{" "}
        {t("budget.overview.verdictLive", {
          amount: formatCurrency(finalOrProjected),
          delta:
            delta < 0
              ? t("budget.overview.overBudget", {
                  amount: formatCurrency(Math.abs(delta)),
                })
              : t("budget.overview.underBudget", {
                  amount: formatCurrency(delta),
                }),
        })}
      </p>

      {shown.length > 0 && (
        <div className="mt-3.5 pt-3 border-t border-[var(--surface-light)]">
          {/* Two headings, because the two figures mean different things. */}
          <div className="grid grid-cols-[minmax(0,1fr)_72px_52px] gap-2 mb-0.5">
            <span className="text-xs font-bold uppercase tracking-wide text-[var(--text-muted)]">
              {t("budget.overview.longEnvelopesShort")}
            </span>
            <span className="text-end text-[10px] uppercase text-[var(--text-muted)]">
              {t("budget.overview.inMonth", { month: shortMonth })}
            </span>
            <span className="text-end text-[10px] uppercase text-[var(--text-muted)]">
              {isCurrent
                ? t("budget.overview.overall")
                : t("budget.overview.overallNow")}
            </span>
          </div>
          {shown.map((envelope) => {
            const percent = percentOf(envelope);
            return (
              <div
                key={`${envelope.kind}-${envelope.name}`}
                data-testid="card-long-envelope"
                className="grid grid-cols-[minmax(0,1fr)_72px_52px] gap-2 items-center py-1.5 border-b border-[var(--surface-light)] last:border-b-0"
              >
                <span className="font-semibold text-[13px] truncate" dir="auto">
                  {envelope.name}
                </span>
                <span dir="ltr" className="text-end text-[11px] font-mono font-bold">
                  {envelope.month_contribution
                    ? formatCurrency(envelope.month_contribution)
                    : "—"}
                </span>
                <span
                  dir="ltr"
                  className={`text-end text-[11px] font-mono font-bold ${
                    percent > 100
                      ? "text-rose-400"
                      : percent > HOT
                        ? "text-amber-400"
                        : "text-[var(--text-default)]"
                  }`}
                >
                  {envelope.budget > 0 ? `${percent}%` : "—"}
                </span>
              </div>
            );
          })}
          <p className="text-[11px] text-[var(--text-muted)] mt-1.5">
            {remaining > 0
              ? t("budget.overview.moreOutside", { count: remaining })
              : t("budget.overview.separatePools", {
                  amount: formatCurrency(budget),
                })}
          </p>
        </div>
      )}

      <div className="text-end mt-auto pt-3">
        <Link
          to="/budget"
          className="text-sm font-medium text-[var(--primary)] hover:underline"
        >
          {t("budget.overview.openOverview")}{" "}
          {troubled > 0 ? `(${troubled})` : ""} &rarr;
        </Link>
      </div>
    </div>
  );
};
