import { useTranslation } from "react-i18next";
import {
  Target,
  Calendar,
  TrendingUp,
  Banknote,
  CheckCircle2,
  AlertTriangle,
  XCircle,
} from "lucide-react";
import type { RetirementProjections as ProjectionsType } from "../../services/api";
import { NetWorthProjectionChart } from "./NetWorthProjectionChart";
import { RetirementIncomeChart } from "./RetirementIncomeChart";

interface Props {
  projections: ProjectionsType;
}

const formatCurrency = (value: number) =>
  new Intl.NumberFormat("he-IL", {
    style: "currency",
    currency: "ILS",
    maximumFractionDigits: 0,
  }).format(value);

const readinessConfig = {
  on_track: {
    icon: CheckCircle2,
    color: "text-emerald-400",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/30",
  },
  close: {
    icon: AlertTriangle,
    color: "text-amber-400",
    bg: "bg-amber-500/10",
    border: "border-amber-500/30",
  },
  off_track: {
    icon: XCircle,
    color: "text-rose-400",
    bg: "bg-rose-500/10",
    border: "border-rose-500/30",
  },
};

export function RetirementProjections({ projections }: Props) {
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
        projections.years_to_fire === -1
          ? "—"
          : `${projections.years_to_fire}`,
      color: "text-purple-400",
    },
    {
      key: "monthlySavingsNeeded",
      icon: Banknote,
      value:
        projections.monthly_savings_needed === 0
          ? t("earlyRetirement.projections.onTrackNoExtra")
          : formatCurrency(projections.monthly_savings_needed),
      color:
        projections.monthly_savings_needed === 0
          ? "text-emerald-400"
          : "text-amber-400",
    },
  ];

  return (
    <div className="space-y-6">
      {/* KPI Cards + Readiness */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {kpis.map((kpi) => (
          <div
            key={kpi.key}
            className="p-4 rounded-xl bg-[var(--surface)] border border-[var(--surface-light)]"
          >
            <div className="flex items-center gap-2 mb-2">
              <kpi.icon size={16} className={kpi.color} />
              <span className="text-xs text-[var(--text-muted)]">
                {t(`earlyRetirement.projections.${kpi.key}`)}
              </span>
            </div>
            <div className={`text-lg font-bold ${kpi.color}`} dir="ltr">
              {kpi.value}
            </div>
          </div>
        ))}

        {/* Readiness + Progress */}
        <div
          className={`p-4 rounded-xl ${readiness.bg} border ${readiness.border}`}
        >
          <div className="flex items-center gap-2 mb-2">
            <ReadinessIcon size={16} className={readiness.color} />
            <span className="text-xs text-[var(--text-muted)]">
              {t("earlyRetirement.projections.readiness")}
            </span>
          </div>
          <div className={`text-lg font-bold ${readiness.color}`}>
            {t(`earlyRetirement.projections.readiness_${projections.readiness}`)}
          </div>
          <div className="mt-2">
            <div className="h-2 bg-[var(--surface)] rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  projections.readiness === "on_track"
                    ? "bg-emerald-500"
                    : projections.readiness === "close"
                      ? "bg-amber-500"
                      : "bg-rose-500"
                }`}
                style={{ width: `${Math.min(projections.progress_pct, 100)}%` }}
              />
            </div>
            <span className="text-xs text-[var(--text-muted)] mt-1" dir="ltr">
              {projections.progress_pct.toFixed(1)}%
            </span>
          </div>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <div className="p-4 rounded-xl bg-[var(--surface)] border border-[var(--surface-light)]">
          <h3 className="text-sm font-medium text-[var(--text-secondary)] mb-4">
            {t("earlyRetirement.charts.netWorthProjection")}
          </h3>
          <NetWorthProjectionChart
            data={projections.net_worth_projection}
            fireNumber={projections.fire_number}
            targetAge={projections.target_retirement_age}
          />
        </div>
        <div className="p-4 rounded-xl bg-[var(--surface)] border border-[var(--surface-light)]">
          <h3 className="text-sm font-medium text-[var(--text-secondary)] mb-4">
            {t("earlyRetirement.charts.retirementIncome")}
          </h3>
          <RetirementIncomeChart data={projections.income_projection} />
        </div>
      </div>
    </div>
  );
}
