import React, { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { AlertTriangle, HelpCircle, Lock, Target, Undo2, Wallet } from "lucide-react";
import i18n from "../../i18n";
import { budgetApi, type BudgetLongEnvelope } from "../../services/api";
import { formatCurrency } from "../../utils/numberFormatting";
import { formatShortDate } from "../../utils/dateFormatting";
import { Skeleton } from "../common/Skeleton";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { useBudgetTrend } from "../../hooks/useBudgetTrend";
import { BAR_CONTROL, BudgetCommandBar, PeriodNav } from "./BudgetCommandBar";
import { RuleSparkline } from "./RuleSparkline";
import { CommitmentBar } from "./overview/CommitmentBar";
import { AcrossAllThree } from "./overview/AcrossAllThree";
import { LongEnvelopes } from "./overview/LongEnvelopes";
import { percentOf, rankEnvelopes } from "./overview/envelopeMath";

/** Months in the budget-vs-actual figure. Closed months compare cleanly. */
const TREND_MONTHS = 12;

/** An envelope is "hot" once this full — the same threshold the ledger rows use. */
const HOT = 90;

interface AttentionItem {
  key: string;
  name: string;
  kind: "monthly" | "yearly" | "project";
  percent: number;
  /** Signed: positive is headroom left, negative is the overspend. */
  remaining: number;
}

interface MonthlyAlert {
  rule_id: number;
  name: string;
  amount: number;
  spent: number;
  percentage: number;
}

function Kpi({
  label,
  value,
  sub,
  tone = "muted",
}: {
  label: string;
  value: string;
  sub: string;
  tone?: "muted" | "good" | "bad";
}) {
  const subColor =
    tone === "good"
      ? "text-emerald-400"
      : tone === "bad"
        ? "text-rose-400"
        : "text-[var(--text-muted)]";
  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] shadow-sm px-4 py-3.5 flex flex-col gap-1.5 min-w-0">
      <p className="text-xs uppercase tracking-wide text-[var(--text-muted)] truncate">
        {label}
      </p>
      <p dir="ltr" className="text-xl md:text-[22px] font-bold font-mono leading-tight">
        {value}
      </p>
      <span className={`text-[11px] ${subColor}`}>{sub}</span>
    </div>
  );
}

function LooseEnd({
  icon: Icon,
  figure,
  caption,
  tone,
}: {
  icon: typeof Wallet;
  figure: string;
  caption: string;
  tone?: "warn";
}) {
  return (
    <div className="flex items-center gap-2.5 min-w-0">
      <span className="inline-flex p-1.5 rounded-lg bg-[var(--surface-light)]/60 text-[var(--text-muted)] shrink-0">
        <Icon size={16} />
      </span>
      <div className="flex flex-col min-w-0">
        <span
          dir="ltr"
          className={`text-[13px] font-bold font-mono ${tone === "warn" ? "text-amber-400" : ""}`}
        >
          {figure}
        </span>
        <span className="text-[11px] text-[var(--text-muted)] truncate">{caption}</span>
      </div>
    </div>
  );
}

interface OverviewBudgetViewProps {
  /** Tab group rendered into the shared command bar. */
  tabs: React.ReactNode;
}

/**
 * The Budget page's Overview tab: one month read across all three kinds.
 *
 * Deliberately free of pacing. Spend is not spread evenly through a month —
 * rent, school fees and insurances land in the first days — so a "you should be
 * 63% through by now" reading calls every first week an overspend. Instead the
 * month is decomposed into what was always going to happen (recurring charges),
 * what was chosen day to day, what is still owed before month end, and what is
 * genuinely free; the projection is built from those parts rather than from
 * elapsed days.
 *
 * Stepping back to a settled month changes the question from "can I still act?"
 * to "how did it close?", so the screen changes with it: nothing is committed,
 * the projection becomes a final figure, and only monthly envelopes keep a
 * percentage — yearly and project envelopes report what that month contributed,
 * because their own percentages always describe today.
 */
export const OverviewBudgetView: React.FC<OverviewBudgetViewProps> = ({ tabs }) => {
  const { t } = useTranslation();
  const qk = useQueryKeys();
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);

  const { data: overview, isLoading } = useQuery({
    queryKey: qk.budget.overview(year, month, false),
    queryFn: () => budgetApi.getOverview(year, month).then((res) => res.data),
    placeholderData: keepPreviousData,
  });

  // Warm from the other tabs' prefetch in practice — the Overview only needs
  // its leftovers (unbudgeted, uncategorized, refunds, goals), which ride along
  // on the month analysis rather than being duplicated into a second endpoint.
  const { data: analysis } = useQuery({
    queryKey: qk.budget.analysis(year, month, false),
    queryFn: () => budgetApi.getAnalysis(year, month, false).then((res) => res.data),
    placeholderData: keepPreviousData,
  });

  const { data: alerts } = useQuery({
    queryKey: qk.budget.alertsMonth(year, month, 0.9),
    queryFn: () =>
      budgetApi.getMonthAlerts(year, month, 0.9).then((res) => res.data),
    placeholderData: keepPreviousData,
  });

  const trend = useBudgetTrend(year, month, TREND_MONTHS, false);
  const trendLabels = useMemo(
    () => trend.data.map((point) => point.key),
    [trend.data],
  );

  const locale = i18n.language === "he" ? "he-IL" : "en-US";
  const monthLabel = new Date(year, month - 1).toLocaleString(locale, { month: "long" });
  const periodLabel = new Date(year, month - 1).toLocaleString(locale, {
    month: "long",
    year: "numeric",
  });
  const isCurrentMonth =
    year === today.getFullYear() && month === today.getMonth() + 1;

  const step = (delta: number) => {
    const next = new Date(year, month - 1 + delta);
    setYear(next.getFullYear());
    setMonth(next.getMonth() + 1);
  };

  const commandBar = (
    <BudgetCommandBar tabs={tabs}>
      <PeriodNav
        label={periodLabel}
        isCurrent={isCurrentMonth}
        onPrev={() => step(-1)}
        onNext={() => step(1)}
        onToday={() => {
          setYear(today.getFullYear());
          setMonth(today.getMonth() + 1);
        }}
        todayTitle={t("budget.currentMonth")}
      />
      {!isCurrentMonth && (
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 rounded-lg text-xs font-medium text-[var(--text-muted)] bg-[var(--surface-light)]/40 ${BAR_CONTROL}`}
        >
          <Lock size={12} />
          {t("budget.overview.closed")}
        </span>
      )}
    </BudgetCommandBar>
  );

  if (isLoading || !overview) {
    return (
      <div className="space-y-3 md:space-y-4">
        {commandBar}
        <Skeleton variant="card" className="h-24" />
        <Skeleton variant="card" className="h-64" />
        <Skeleton variant="card" className="h-40" />
      </div>
    );
  }

  const {
    is_current_month: isCurrent,
    monthly_spent: spent,
    monthly_budget: budget,
    committed_remaining: committed,
    free_to_spend: free,
    projected,
    charges_due: chargesDue,
    days_left: daysLeft,
    long_envelopes: longEnvelopes,
  } = overview;

  const spentPercent =
    budget > 0 ? Math.round((Math.max(spent, 0) / budget) * 100) : 0;
  const finalOrProjected = projected ?? spent;
  const delta = budget - finalOrProjected;

  // Monthly alerts come from the server (they know each rule's tags); the long
  // envelopes are already in the overview payload, so their trouble is derived
  // here rather than fetched twice.
  const monthlyAttention: AttentionItem[] = (alerts?.alerts ?? []).map(
    (alert: MonthlyAlert) => ({
      key: `monthly-${alert.rule_id}`,
      name: alert.name,
      kind: "monthly" as const,
      percent: Math.round(alert.percentage * 100),
      remaining: alert.amount - alert.spent,
    }),
  );
  const longAttention: AttentionItem[] = longEnvelopes
    .filter((envelope) => percentOf(envelope) >= HOT)
    .map((envelope: BudgetLongEnvelope) => ({
      key: `${envelope.kind}-${envelope.name}`,
      name: envelope.name,
      kind: envelope.kind,
      percent: percentOf(envelope),
      remaining: envelope.budget - envelope.spent,
    }));
  const attention = [...monthlyAttention, ...longAttention].sort(
    (a, b) => b.percent - a.percent,
  );
  const overCount = attention.filter((item) => item.percent > 100).length;
  const hotCount = attention.length - overCount;

  const totalRow = (analysis?.rules ?? []).find(
    (item: { rule: { name: string } }) => item.rule.name === "Total Budget",
  );
  const otherRow = (analysis?.rules ?? []).find(
    (item: { rule: { name: string } }) => item.rule.name === "Other Expenses",
  );
  const monthTransactions: { category?: string | null; amount?: number }[] =
    totalRow?.data ?? [];
  const uncategorized = monthTransactions.filter((txn) => !txn.category);
  const uncategorizedAmount = uncategorized.reduce(
    (sum, txn) => sum + Math.abs(txn.amount ?? 0),
    0,
  );
  const refunds = analysis?.pending_refunds;
  const goals = analysis?.savings_goals;

  const envelopeCount =
    (analysis?.rules ?? []).filter(
      (item: { rule: { name: string } }) =>
        item.rule.name !== "Total Budget" && item.rule.name !== "Other Expenses",
    ).length + longEnvelopes.length;

  return (
    <div className="space-y-3 md:space-y-4">
      {commandBar}

      {/* KPI strip. On a settled month the forward-looking tiles become
          backward-looking ones — there is no commitment or projection left. */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-2 md:gap-3">
        <Kpi
          label={t("budget.overview.spent")}
          value={formatCurrency(spent)}
          sub={t("budget.overview.ofMonthly", {
            amount: formatCurrency(budget),
            percent: spentPercent,
          })}
        />
        {isCurrent ? (
          <Kpi
            label={t("budget.overview.stillCommitted")}
            value={formatCurrency(committed)}
            sub={t("budget.overview.chargesDueCount", { count: chargesDue.length })}
          />
        ) : (
          <Kpi
            label={
              delta < 0
                ? t("budget.overview.overBudgetSegment")
                : t("budget.overview.freeToSpend")
            }
            value={formatCurrency(Math.abs(delta))}
            sub={
              delta < 0
                ? t("budget.overview.closedOver")
                : t("budget.overview.closedUnder")
            }
            tone={delta < 0 ? "bad" : "good"}
          />
        )}
        {isCurrent && (
          <Kpi
            label={t("budget.overview.freeToSpend")}
            value={formatCurrency(free)}
            sub={t("budget.overview.perDay", {
              amount: formatCurrency(daysLeft > 0 ? free / daysLeft : free),
              count: daysLeft,
            })}
            tone={free < 0 ? "bad" : "good"}
          />
        )}
        {isCurrent && (
          <Kpi
            label={t("budget.overview.projected")}
            value={formatCurrency(finalOrProjected)}
            sub={
              delta < 0
                ? t("budget.overview.overBudget", {
                    amount: formatCurrency(Math.abs(delta)),
                  })
                : t("budget.overview.underBudget", {
                    amount: formatCurrency(delta),
                  })
            }
            tone={delta < 0 ? "bad" : "good"}
          />
        )}
        <Kpi
          label={t("budget.overview.attention")}
          value={t("budget.overview.attentionCounts", {
            over: overCount,
            hot: hotCount,
          })}
          sub={t("budget.overview.ofEnvelopes", { count: envelopeCount })}
          tone={overCount > 0 ? "bad" : "muted"}
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-3 md:gap-4">
        {/* Where the month stands / how it closed. */}
        <div className="xl:col-span-7 bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] shadow-sm p-4 md:p-5 flex flex-col gap-3">
          <p className="font-bold text-sm md:text-base">
            {isCurrent
              ? t("budget.overview.whereItStands")
              : t("budget.overview.howItClosed", { month: monthLabel })}
          </p>

          <CommitmentBar overview={overview} height={16} />

          {isCurrent && (
            <div className="border-t border-[var(--surface-light)] pt-3 flex flex-col gap-1">
              <p className="text-xs uppercase tracking-wide text-[var(--text-muted)]">
                {t("budget.overview.stillToLand")}
              </p>
              <p className="text-[13px]">
                {chargesDue.length === 0
                  ? t("budget.overview.nothingToLand")
                  : chargesDue
                      .map(
                        (charge) =>
                          `${charge.label} ${formatCurrency(charge.amount)} (${formatShortDate(charge.expected_date)})`,
                      )
                      .join(" · ")}
              </p>
            </div>
          )}

          <div className="border-t border-[var(--surface-light)] pt-3 flex flex-col gap-2.5">
            <p className="text-xs uppercase tracking-wide text-[var(--text-muted)]">
              {t("budget.overview.looseEnds")}
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <LooseEnd
                icon={Wallet}
                figure={formatCurrency(otherRow?.current_amount ?? 0)}
                caption={`${t("budget.overview.unbudgetedSpend")} · ${t("budget.overview.transactionCount", { count: otherRow?.data?.length ?? 0 })}`}
                tone={(otherRow?.current_amount ?? 0) > 0 ? "warn" : undefined}
              />
              <LooseEnd
                icon={HelpCircle}
                figure={t("budget.overview.transactionCount", {
                  count: uncategorized.length,
                })}
                caption={`${t("budget.overview.uncategorized")} · ${t("budget.overview.notCounted", { amount: formatCurrency(uncategorizedAmount) })}`}
                tone={uncategorized.length > 0 ? "warn" : undefined}
              />
              <LooseEnd
                icon={Undo2}
                figure={formatCurrency(refunds?.total_expected ?? 0)}
                caption={`${t("budget.pendingRefunds")} · ${t("budget.overview.expectedBackCount", { count: refunds?.items?.length ?? 0 })}`}
              />
              <LooseEnd
                icon={Target}
                figure={formatCurrency(goals?.total_allocated ?? 0)}
                caption={t("budget.goals.title")}
              />
            </div>
          </div>
        </div>

        {/* Needs attention / envelope by envelope. */}
        <div className="xl:col-span-5 bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] shadow-sm p-4 md:p-5 flex flex-col gap-3">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <span className="inline-flex p-1.5 rounded-lg bg-rose-500/15 text-rose-400 shrink-0">
                <AlertTriangle size={16} />
              </span>
              <p className="font-bold text-sm md:text-base truncate">
                {isCurrent
                  ? t("budget.overview.needsAttention")
                  : t("budget.overview.monthlyEnvelopes")}
              </p>
            </div>
            <span className="text-xs text-[var(--text-muted)] shrink-0">
              {isCurrent
                ? attention.length
                : t("budget.overview.monthlyEnvelopesOnly")}
            </span>
          </div>

          <div className="flex flex-col gap-1.5">
            {(isCurrent
              ? attention
              : monthlyAttention.sort((a, b) => b.percent - a.percent)
            ).map((item) => (
              <div
                key={item.key}
                data-testid="overview-attention-row"
                className="flex items-center gap-3 px-3 py-2 rounded-xl border border-[var(--surface-light)]"
              >
                <span
                  className={`w-2.5 h-2.5 rounded-full shrink-0 ${item.percent > 100 ? "bg-rose-500" : "bg-amber-500"}`}
                />
                <span className="flex-1 min-w-0 font-semibold text-sm truncate" dir="auto">
                  {item.name}
                </span>
                <span
                  dir="ltr"
                  className={`text-xs font-mono font-bold shrink-0 ${item.percent > 100 ? "text-rose-400" : "text-amber-400"}`}
                >
                  {item.percent}%
                </span>
                <span dir="ltr" className="text-xs font-mono text-[var(--text-muted)] shrink-0">
                  {item.remaining < 0
                    ? t("budget.overByAmount", {
                        amount: formatCurrency(Math.abs(item.remaining)),
                      })
                    : t("budget.remainingAmount", {
                        amount: formatCurrency(item.remaining),
                      })}
                </span>
              </div>
            ))}
            {(isCurrent ? attention : monthlyAttention).length === 0 && (
              <p className="text-sm text-emerald-400 py-2">{t("budget.allGood")}</p>
            )}
          </div>

          {!isCurrent && (
            <p className="text-[11px] text-[var(--text-muted)] text-pretty mt-auto">
              {t("budget.overview.closedAgainstLimit", { month: monthLabel })}
            </p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-3 md:gap-4">
        <div className="xl:col-span-7 bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] shadow-sm p-4 md:p-5 flex flex-col gap-3">
          <p className="font-bold text-sm md:text-base">{t("budget.trend.title")}</p>
          {trend.hasData ? (
            <RuleSparkline
              variant="bars"
              series={trend.data.map((point) => point.actual)}
              labels={trendLabels}
              budget={trend.data[trend.data.length - 1]?.budget ?? 0}
              height={96}
              fluid
            />
          ) : (
            <p className="text-sm text-[var(--text-muted)]">
              {t("budget.spendOverTimeEmpty")}
            </p>
          )}
        </div>
        <div className="xl:col-span-5">
          <AcrossAllThree overview={overview} monthLabel={monthLabel} />
        </div>
      </div>

      <LongEnvelopes
        envelopes={rankEnvelopes(longEnvelopes)}
        monthLabel={monthLabel}
        isPast={!isCurrent}
      />
    </div>
  );
};
