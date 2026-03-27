import { useTranslation } from "react-i18next";
import {
  Target,
  Calendar,
  TrendingUp,
  Banknote,
  Clock,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Info,
  Wand2,
} from "lucide-react";
import type {
  RetirementProjections as ProjectionsType,
  RetirementSuggestions,
} from "../../services/api";
import { NetWorthProjectionChart } from "./NetWorthProjectionChart";
import { RetirementIncomeChart } from "./RetirementIncomeChart";

type SuggestionField = keyof RetirementSuggestions;

interface Props {
  projections: ProjectionsType;
  suggestions?: RetirementSuggestions | null;
  onAdjust?: (field: SuggestionField, value: number) => void;
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

function formatSuggestionValue(field: SuggestionField, value: number): string {
  if (field === "target_retirement_age") return `${value}`;
  if (field === "monthly_expenses_in_retirement") return formatCurrency(value);
  if (field === "expected_return_rate") return `${(value * 100).toFixed(1)}%`;
  return `${value}`;
}

function InfoTooltip({ text }: { text: string }) {
  return (
    <span className="group relative">
      <Info size={12} className="text-[var(--text-muted)] cursor-help inline" />
      <span className="absolute z-10 hidden group-hover:block w-64 p-2 text-xs font-normal text-[var(--text-primary)] bg-[var(--surface)] border border-[var(--surface-light)] rounded-lg shadow-lg -top-2 start-5">
        {text}
      </span>
    </span>
  );
}

export function RetirementProjections({
  projections,
  suggestions,
  onAdjust,
}: Props) {
  const { t } = useTranslation();
  const readiness = readinessConfig[projections.readiness];
  const ReadinessIcon = readiness.icon;

  const kpis = [
    {
      key: "fireNumber",
      icon: Target,
      value: formatCurrency(projections.fire_number),
      color: "text-blue-400",
      tooltip: t("earlyRetirement.tooltips.fireNumber"),
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
      tooltip: t("earlyRetirement.tooltips.fireAge"),
    },
    {
      key: "earliestRetirement",
      icon: Clock,
      value:
        projections.earliest_possible_retirement_age === -1
          ? t("earlyRetirement.projections.notReachable")
          : `${projections.earliest_possible_retirement_age}`,
      color:
        projections.earliest_possible_retirement_age !== -1 &&
        projections.earliest_possible_retirement_age <=
          projections.target_retirement_age
          ? "text-emerald-400"
          : "text-amber-400",
      tooltip: t("earlyRetirement.tooltips.earliestRetirement"),
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
      tooltip: t("earlyRetirement.tooltips.monthlySavings"),
    },
  ];

  const showSuggestions =
    projections.readiness !== "on_track" && suggestions && onAdjust;

  // Build suggestion items, filtering out -1 (not achievable)
  const suggestionItems: {
    field: SuggestionField;
    label: string;
    value: number;
    display: string;
  }[] = [];
  if (showSuggestions) {
    if (suggestions.target_retirement_age !== -1) {
      suggestionItems.push({
        field: "target_retirement_age",
        label: t("earlyRetirement.form.targetRetirementAge"),
        value: suggestions.target_retirement_age,
        display: formatSuggestionValue(
          "target_retirement_age",
          suggestions.target_retirement_age,
        ),
      });
    }
    if (suggestions.monthly_expenses_in_retirement !== -1) {
      suggestionItems.push({
        field: "monthly_expenses_in_retirement",
        label: t("earlyRetirement.form.monthlyExpenses"),
        value: suggestions.monthly_expenses_in_retirement,
        display: formatSuggestionValue(
          "monthly_expenses_in_retirement",
          suggestions.monthly_expenses_in_retirement,
        ),
      });
    }
    if (suggestions.expected_return_rate !== -1) {
      suggestionItems.push({
        field: "expected_return_rate",
        label: t("earlyRetirement.form.expectedReturn"),
        value: suggestions.expected_return_rate,
        display: formatSuggestionValue(
          "expected_return_rate",
          suggestions.expected_return_rate,
        ),
      });
    }
  }

  return (
    <div className="space-y-6">
      {/* KPI Cards + Readiness */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
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
              {kpi.tooltip && <InfoTooltip text={kpi.tooltip} />}
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

      {/* Adjust Plan Suggestions */}
      {suggestionItems.length > 0 && onAdjust && (
        <div className="flex flex-wrap items-center gap-3 p-4 rounded-xl bg-amber-500/5 border border-amber-500/20">
          <div className="flex items-center gap-2 text-sm text-amber-400 font-medium">
            <Wand2 size={16} />
            {t("earlyRetirement.projections.adjustPlan")}
          </div>
          {suggestionItems.map((item) => (
            <button
              key={item.field}
              type="button"
              onClick={() => onAdjust(item.field, item.value)}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-sm text-amber-300 hover:bg-amber-500/20 hover:border-amber-500/50 transition-colors disabled:opacity-50"
            >
              <span className="text-[var(--text-muted)]">{item.label}:</span>
              <span className="font-semibold" dir="ltr">
                {item.display}
              </span>
            </button>
          ))}
        </div>
      )}

      {/* Charts */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <div className="p-4 rounded-xl bg-[var(--surface)] border border-[var(--surface-light)]">
          <div className="flex items-center gap-2 mb-4">
            <h3 className="text-sm font-medium text-[var(--text-secondary)]">
              {t("earlyRetirement.charts.netWorthProjection")}
            </h3>
            <InfoTooltip
              text={t("earlyRetirement.tooltips.netWorthChart")}
            />
          </div>
          <NetWorthProjectionChart
            data={projections.net_worth_projection}
            fireNumber={projections.fire_number}
            targetAge={projections.target_retirement_age}
          />
        </div>
        <div className="p-4 rounded-xl bg-[var(--surface)] border border-[var(--surface-light)]">
          <div className="flex items-center gap-2 mb-4">
            <h3 className="text-sm font-medium text-[var(--text-secondary)]">
              {t("earlyRetirement.charts.retirementIncome")}
            </h3>
            <InfoTooltip
              text={t("earlyRetirement.tooltips.incomeChart")}
            />
          </div>
          <RetirementIncomeChart data={projections.income_projection} />
        </div>
      </div>
    </div>
  );
}
