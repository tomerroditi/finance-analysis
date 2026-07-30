import { useState } from "react";
import { useNavigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  Flame,
  ChevronRight,
  ChevronLeft,
  Target,
  Calendar,
  TrendingUp,
  Banknote,
  CheckCircle2,
  AlertTriangle,
  XCircle,
} from "lucide-react";
import {
  retirementApi,
  type RetirementProjections,
} from "../../services/api";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { Skeleton } from "../common/Skeleton";
import { formatCurrency } from "../../utils/numberFormatting";
import { NetWorthProjectionChart } from "../retirement/NetWorthProjectionChart";
import { RetirementIncomeChart } from "../retirement/RetirementIncomeChart";

type ChartView = "net_worth" | "income";

const readinessConfig = {
  on_track: {
    icon: CheckCircle2,
    color: "text-emerald-400",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/30",
    bar: "bg-emerald-500",
  },
  close: {
    icon: AlertTriangle,
    color: "text-amber-400",
    bg: "bg-amber-500/10",
    border: "border-amber-500/30",
    bar: "bg-amber-500",
  },
  off_track: {
    icon: XCircle,
    color: "text-rose-400",
    bg: "bg-rose-500/10",
    border: "border-rose-500/30",
    bar: "bg-rose-500",
  },
} as const;

/** Dashboard early-retirement (FIRE) insights card: readiness, headline KPIs
 *  and the projection charts from the saved plan — no plan settings exposed.
 *  Opt-in (hidden by default); the full editor lives on the retirement page. */
export function EarlyRetirementCard() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const qk = useQueryKeys();
  const isRtl = i18n.language === "he";
  const [chartView, setChartView] = useState<ChartView>("net_worth");

  const { data: goal, isLoading: goalLoading } = useQuery({
    queryKey: qk.retirement.goal(),
    queryFn: () => retirementApi.getGoal().then((r) => r.data),
  });

  const hasGoal = !!goal && goal.id !== -1;

  const { data: projections, isLoading: projectionsLoading } = useQuery({
    queryKey: qk.retirement.projections(),
    queryFn: () => retirementApi.getProjections().then((r) => r.data),
    enabled: hasGoal,
  });

  const ViewPlanChevron = isRtl ? ChevronLeft : ChevronRight;

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] p-4 md:p-6">
      <div className="flex items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-orange-500/15 text-orange-400">
            <Flame size={16} />
          </div>
          <p className="text-sm md:text-base font-bold">
            {t("dashboard.retirementCard.title")}
          </p>
        </div>
        <button
          onClick={() => navigate("/early-retirement")}
          className="flex items-center gap-0.5 text-xs md:text-sm font-medium text-[var(--primary)] hover:opacity-80 transition-opacity"
        >
          {t("dashboard.retirementCard.viewPlan")}
          <ViewPlanChevron size={15} />
        </button>
      </div>

      {goalLoading || (hasGoal && projectionsLoading) ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} variant="card" className="h-20" />
            ))}
          </div>
          <Skeleton variant="card" className="h-72" />
        </div>
      ) : !hasGoal ? (
        <NoPlanState onSetup={() => navigate("/early-retirement")} />
      ) : projections ? (
        <div className="space-y-4">
          <KpiRow projections={projections} />

          {/* Chart toggle */}
          <div className="flex justify-end">
            <div className="flex bg-[var(--surface-light)] p-1 rounded-xl overflow-x-auto scrollbar-auto-hide">
              {(
                [
                  { key: "net_worth", label: t("earlyRetirement.charts.netWorthProjection") },
                  { key: "income", label: t("earlyRetirement.charts.retirementIncome") },
                ] as const
              ).map(({ key, label }) => (
                <button
                  key={key}
                  onClick={() => setChartView(key)}
                  className={`px-2 md:px-3 py-1.5 rounded-lg text-xs md:text-sm font-bold transition-all whitespace-nowrap ${
                    chartView === key
                      ? "bg-[var(--surface)] text-[var(--primary)] shadow-sm"
                      : "text-[var(--text-muted)] hover:text-[var(--text-default)]"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div data-testid="retirement-projection-chart">
            {chartView === "net_worth" ? (
              <NetWorthProjectionChart
                data={projections.net_worth_projection}
                fireNumber={projections.fire_number}
                targetAge={projections.target_retirement_age}
                pensionAge={projections.full_pension_age}
              />
            ) : (
              <RetirementIncomeChart data={projections.income_projection} />
            )}
          </div>
        </div>
      ) : (
        <p className="text-[var(--text-muted)] text-sm py-6 text-center">
          {t("common.noData")}
        </p>
      )}
    </div>
  );
}

function NoPlanState({ onSetup }: { onSetup: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-center gap-3 py-10 text-center">
      <div className="p-3 rounded-full bg-orange-500/10 text-orange-400">
        <Flame size={24} />
      </div>
      <p className="text-sm text-[var(--text-muted)] max-w-sm">
        {t("dashboard.retirementCard.noPlan")}
      </p>
      <button
        onClick={onSetup}
        className="px-4 py-2 rounded-lg text-sm font-bold bg-[var(--primary)] text-white hover:opacity-90 transition-opacity"
      >
        {t("dashboard.retirementCard.setupCta")}
      </button>
    </div>
  );
}

function KpiRow({ projections }: { projections: RetirementProjections }) {
  const { t } = useTranslation();
  const readiness = readinessConfig[projections.readiness];
  const ReadinessIcon = readiness.icon;

  const kpis = [
    {
      key: "fireNumber",
      icon: Target,
      value: formatCurrency(projections.fire_number),
      color: "text-blue-400",
    },
    {
      key: "fireAge",
      icon: Calendar,
      value:
        projections.fire_age === -1
          ? t("earlyRetirement.projections.notReachable")
          : `${projections.fire_age}`,
      color:
        projections.fire_age !== -1 &&
        projections.fire_age <= projections.target_retirement_age
          ? "text-emerald-400"
          : "text-amber-400",
    },
    {
      key: "yearsToFire",
      icon: TrendingUp,
      value:
        projections.years_to_fire === -1 ? "—" : `${projections.years_to_fire}`,
      color: "text-purple-400",
    },
    {
      key: "monthlySavingsNeeded",
      icon: Banknote,
      // "On track!" only when the plan actually is — 0 extra savings can
      // coexist with off_track readiness (depleting drawdown).
      value:
        projections.monthly_savings_needed === 0 &&
        projections.readiness === "on_track"
          ? t("earlyRetirement.projections.onTrackNoExtra")
          : formatCurrency(projections.monthly_savings_needed),
      color:
        projections.monthly_savings_needed === 0 &&
        projections.readiness === "on_track"
          ? "text-emerald-400"
          : "text-amber-400",
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
      {/* Readiness + progress toward the FIRE number */}
      <div className={`p-3 rounded-xl ${readiness.bg} border ${readiness.border}`}>
        <div className="flex items-center gap-1.5 mb-1">
          <ReadinessIcon size={14} className={`${readiness.color} shrink-0`} />
          <span className="text-[10px] sm:text-xs text-[var(--text-muted)] truncate">
            {t("earlyRetirement.projections.readiness")}
          </span>
        </div>
        <p className={`text-sm font-bold ${readiness.color} truncate`}>
          {t(`earlyRetirement.projections.readiness_${projections.readiness}`)}
        </p>
        <div className="mt-1.5 h-1.5 bg-[var(--surface)] rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full ${readiness.bar}`}
            style={{ width: `${Math.min(Math.max(projections.progress_pct, 0), 100)}%` }}
          />
        </div>
        <span className="text-[10px] text-[var(--text-muted)]" dir="ltr">
          {projections.progress_pct.toFixed(1)}%
        </span>
      </div>

      {kpis.map((kpi) => (
        <div
          key={kpi.key}
          className="p-3 rounded-xl bg-[var(--surface-light)]/40 border border-[var(--surface-light)]"
        >
          <div className="flex items-center gap-1.5 mb-1">
            <kpi.icon size={14} className={`${kpi.color} shrink-0`} />
            <span className="text-[10px] sm:text-xs text-[var(--text-muted)] truncate">
              {t(`earlyRetirement.projections.${kpi.key}`)}
            </span>
          </div>
          <p className={`text-sm font-bold ${kpi.color} truncate`} dir="ltr">
            {kpi.value}
          </p>
        </div>
      ))}
    </div>
  );
}
