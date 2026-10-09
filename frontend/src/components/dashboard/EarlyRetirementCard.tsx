import { useMemo } from "react";
import { useNavigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Flame,
  ChevronRight,
  ChevronLeft,
  Calendar,
  Landmark,
  Wallet,
  ListChecks,
} from "lucide-react";
import { fireApi, type FireProjection } from "../../services/api";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { Skeleton } from "../common/Skeleton";
import { formatCurrency } from "../../utils/numberFormatting";

/** Dashboard early-retirement card: the saved plan's verdict, headline figures
 *  and net-worth path, run on today's tracked data. No plan settings here —
 *  the full editor is the early-retirement page. Opt-in (hidden by default). */
export function EarlyRetirementCard() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const qk = useQueryKeys();
  const ViewPlanChevron = i18n.language === "he" ? ChevronLeft : ChevronRight;

  const { data: projection, isLoading } = useQuery({
    queryKey: qk.fire.planProjection(),
    queryFn: () => fireApi.getPlanProjection().then((r) => r.data),
  });

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] p-4 md:p-6">
      <div className="flex items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-orange-500/15 text-orange-400">
            <Flame size={16} />
          </div>
          <p className="text-sm md:text-base font-bold">{t("dashboard.retirementCard.title")}</p>
        </div>
        <button
          onClick={() => navigate("/early-retirement")}
          className="flex items-center gap-0.5 text-xs md:text-sm font-medium text-[var(--primary)] hover:opacity-80 transition-opacity"
        >
          {t("dashboard.retirementCard.viewPlan")}
          <ViewPlanChevron size={15} />
        </button>
      </div>

      {isLoading ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} variant="card" className="h-20" />
            ))}
          </div>
          <Skeleton variant="card" className="h-64" />
        </div>
      ) : !projection || projection.status === "needs_setup" ? (
        <NoPlanState onSetup={() => navigate("/early-retirement")} />
      ) : projection.status === "no_result" ? (
        <p className="text-[var(--text-muted)] text-sm py-6 text-center">{t("fire.result.noResult")}</p>
      ) : (
        <div className="space-y-4">
          <KpiRow projection={projection} />
          <NetWorthPath projection={projection} />
        </div>
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
      <p className="text-sm text-[var(--text-muted)] max-w-sm">{t("dashboard.retirementCard.noPlan")}</p>
      <button
        onClick={onSetup}
        className="px-4 py-2 rounded-lg text-sm font-bold bg-[var(--primary)] text-white hover:opacity-90 transition-opacity"
      >
        {t("dashboard.retirementCard.setupCta")}
      </button>
    </div>
  );
}

function KpiRow({ projection }: { projection: FireProjection }) {
  const { t } = useTranslation();
  const succeeded = projection.status === "success";
  const atRetirement = projection.snapshots.find((s) => s.label === "retirement");
  const pension = projection.pension_income.reduce((sum, row) => sum + row.monthly, 0);
  const met = projection.goals.filter((g) => g.met).length;

  const kpis = [
    {
      key: "retireAt",
      icon: Calendar,
      value: succeeded
        ? `${String(projection.retire_month).padStart(2, "0")}/${projection.retire_year} · ${projection.retire_age?.toFixed(1)}`
        : t("dashboard.retirementCard.notReachable"),
      color: succeeded ? "text-emerald-400" : "text-amber-400",
      testId: "retirement-card-verdict",
    },
    {
      key: "netWorthAtRetirement",
      icon: Wallet,
      value: atRetirement ? formatCurrency(atRetirement.net_worth) : "—",
      color: "text-blue-400",
    },
    {
      key: "monthlyPension",
      icon: Landmark,
      value: pension > 0 ? formatCurrency(pension) : "—",
      color: "text-purple-400",
    },
    {
      key: "goalsMet",
      icon: ListChecks,
      value: `${met}/${projection.goals.length}`,
      color: met === projection.goals.length ? "text-emerald-400" : "text-amber-400",
    },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {kpis.map((kpi) => (
        <div
          key={kpi.key}
          className="p-3 rounded-xl bg-[var(--surface-light)]/40 border border-[var(--surface-light)]"
          data-testid={kpi.testId}
        >
          <div className="flex items-center gap-1.5 mb-1">
            <kpi.icon size={14} className={`${kpi.color} shrink-0`} />
            <span className="text-[10px] sm:text-xs text-[var(--text-muted)] truncate">
              {t(`dashboard.retirementCard.${kpi.key}`)}
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

function NetWorthPath({ projection }: { projection: FireProjection }) {
  const { t } = useTranslation();
  // Yearly points: 500-odd months is more than a card-sized chart can show.
  const data = useMemo(
    () =>
      projection.months
        .filter((_, index) => index % 12 === 0)
        .map((m) => ({ age: Number(m.age.toFixed(1)), value: m.net_worth })),
    [projection.months],
  );
  return (
    <div data-testid="retirement-projection-chart">
      <p className="mb-2 text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
        {t("fire.chart.netWorth")}
      </p>
      <div className="h-64" dir="ltr">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-light)" />
            <XAxis dataKey="age" tick={{ fontSize: 11 }} stroke="var(--text-muted)" />
            <YAxis
              tick={{ fontSize: 11 }}
              stroke="var(--text-muted)"
              tickFormatter={(v: number) => `${Math.round(v / 1000)}k`}
              width={56}
            />
            <Tooltip
              formatter={(value) => formatCurrency(Number(value ?? 0))}
              labelFormatter={(age) => t("dashboard.retirementCard.atAge", { age })}
              contentStyle={{ background: "var(--surface)", border: "1px solid var(--surface-light)" }}
            />
            <Area type="monotone" dataKey="value" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.15} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
