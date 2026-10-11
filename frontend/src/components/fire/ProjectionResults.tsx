import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Check, X, AlertTriangle, Lightbulb } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { FireProjection } from "../../services/api";

interface Props {
  projection: FireProjection;
}

const SERIES_COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#a78bfa", "#ef4444", "#14b8a6"];

function useMoney() {
  const { i18n } = useTranslation();
  return useMemo(
    () =>
      new Intl.NumberFormat(i18n.language === "he" ? "he-IL" : "en-US", {
        style: "currency",
        currency: "ILS",
        maximumFractionDigits: 0,
      }),
    [i18n.language],
  );
}

/** Down-sample to yearly points — 533 monthly points is more than a chart can show. */
function yearly<T extends { age: number }>(rows: T[]): T[] {
  return rows.filter((_, index) => index % 12 === 0);
}

function ChartCard({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div
      data-testid={`fire-chart-${id}`}
      className="p-4 rounded-xl bg-[var(--surface)] border border-[var(--surface-light)]"
    >
      <h4 className="mb-3 text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
        {title}
      </h4>
      <div className="h-64" dir="ltr">
        <ResponsiveContainer width="100%" height="100%">
          {children as React.ReactElement}
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/** Name a cash-flow row. Indexed rows (`portfolio2`, `keren0`) keep their number. */
function flowLabel(key: string, t: (k: string) => string): string {
  const match = /^([a-z_]+?)(\d+)$/.exec(key);
  const stem = match ? match[1] : key;
  const label = t(`fire.flow.${stem}`);
  return match ? `${label} ${Number(match[2]) + 1}` : label;
}

/** The rows of one cash-flow chart, and the keys that actually carry money. */
function useFlowSeries(projection: FireProjection, side: "incomes" | "expenses") {
  return useMemo(() => {
    const keys = new Set<string>();
    for (const month of projection.months) {
      for (const [key, value] of Object.entries(month[side])) if (value !== 0) keys.add(key);
    }
    const ordered = [...keys];
    return {
      keys: ordered,
      rows: yearly(
        projection.months.map((m) => ({
          age: Number(m.age.toFixed(2)),
          ...Object.fromEntries(ordered.map((key) => [key, m[side][key] ?? 0])),
        })),
      ),
    };
  }, [projection.months, side]);
}

export function ProjectionResults({ projection }: Props) {
  const { t } = useTranslation();
  const money = useMoney();

  const netWorth = useMemo(
    () => yearly(projection.months.map((m) => ({ age: Number(m.age.toFixed(2)), value: m.net_worth }))),
    [projection.months],
  );

  const assetKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const month of projection.months) {
      for (const [key, value] of Object.entries(month.assets)) if (value !== 0) keys.add(key);
    }
    return [...keys];
  }, [projection.months]);

  const assets = useMemo(
    () =>
      yearly(
        projection.months.map((m) => ({
          age: Number(m.age.toFixed(2)),
          ...Object.fromEntries(assetKeys.map((key) => [key, m.assets[key] ?? 0])),
        })),
      ),
    [projection.months, assetKeys],
  );

  const income = useFlowSeries(projection, "incomes");
  const spending = useFlowSeries(projection, "expenses");

  if (projection.status === "no_result") {
    return (
      <div className="p-4 rounded-xl bg-[var(--surface)] border border-[var(--surface-light)]">
        <p className="text-sm text-[var(--text-secondary)]">{t("fire.result.noResult")}</p>
      </div>
    );
  }

  const succeeded = projection.status === "success";

  return (
    <div className="space-y-4 md:space-y-6" data-testid="fire-results">
      <div className="p-4 rounded-xl bg-[var(--surface)] border border-[var(--surface-light)]">
        <h3
          className={`text-lg font-semibold ${succeeded ? "text-emerald-400" : "text-amber-400"}`}
          data-testid="fire-verdict"
        >
          {succeeded
            ? t("fire.result.success", {
                month: String(projection.retire_month).padStart(2, "0"),
                year: projection.retire_year,
                age: projection.retire_age?.toFixed(1),
              })
            : t("fire.result.goalsNotMet", { months: projection.search_limit_months })}
        </h3>
        {projection.inferred && (
          <p className="flex items-start gap-1.5 mt-2 text-xs text-amber-400">
            <AlertTriangle className="shrink-0 w-3.5 h-3.5 mt-0.5" />
            {t("fire.result.inferredMode")}
          </p>
        )}
      </div>

      <div className="p-4 rounded-xl bg-[var(--surface)] border border-[var(--surface-light)]">
        <h4 className="mb-3 text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
          {t("fire.result.goals")}
        </h4>
        <ul className="space-y-2">
          {projection.goals.map((goal) => (
            <li key={goal.key} className="flex items-start gap-2 text-sm" data-testid={`fire-goal-${goal.key}`}>
              {goal.met ? (
                <Check className="shrink-0 w-4 h-4 mt-0.5 text-emerald-400" />
              ) : (
                <X className="shrink-0 w-4 h-4 mt-0.5 text-red-400" />
              )}
              <span className="min-w-0 break-words text-[var(--text-primary)]">
                {t(`fire.goal.${goal.key}`, { defaultValue: goal.label })}
                {!goal.met && goal.shortfall > 0 && (
                  <span className="ms-2 text-xs text-[var(--text-muted)]" dir="ltr">
                    ({money.format(goal.shortfall)})
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      </div>

      {projection.recommendation && (
        <div className="p-4 rounded-xl bg-[var(--surface)] border border-[var(--surface-light)]">
          <h4 className="flex items-center gap-2 mb-2 text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
            <Lightbulb className="w-3.5 h-3.5" />
            {t("fire.result.advice")}
          </h4>
          <p className="text-sm text-[var(--text-primary)]" data-testid="fire-advice">
            {t(`fire.advice.${projection.recommendation.reason}`, {
              defaultValue: projection.recommendation.action,
            })}
          </p>
          <p className="mt-1 text-xs text-[var(--text-muted)]">
            {projection.recommendation.months_saved > 0
              ? t("fire.advice.monthsSaved", { months: projection.recommendation.months_saved })
              : t("fire.advice.noBenefit")}
          </p>
        </div>
      )}

      {projection.pension_income.length > 0 && (
        <div
          data-testid="fire-pension-income"
          className="p-4 rounded-xl bg-[var(--surface)] border border-[var(--surface-light)]"
        >
          {projection.pension_income.map((row) => (
            <p key={row.owner} className="text-sm text-[var(--text-secondary)]">
              {t("fire.result.pensionIncome", {
                owner: row.owner,
                age: row.age.toFixed(1),
                amount: money.format(row.monthly),
              })}
            </p>
          ))}
        </div>
      )}

      {projection.snapshots.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2" data-testid="fire-snapshots">
          {projection.snapshots.map((snapshot) => (
            <div
              key={snapshot.label}
              data-testid={`fire-snapshot-${snapshot.label}`}
              className="p-4 rounded-xl bg-[var(--surface)] border border-[var(--surface-light)]"
            >
              <h4 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
                {t(`fire.snapshot.${snapshot.label}`, {
                  month: String(snapshot.month).padStart(2, "0"),
                  year: snapshot.year,
                })}
              </h4>
              <p className="mt-1 text-xl font-semibold text-[var(--text-primary)]" dir="ltr">
                {money.format(snapshot.net_worth)}
              </p>
              <ul className="mt-2 space-y-1 text-xs text-[var(--text-secondary)]">
                {Object.keys(snapshot.breakdown).length === 0 && (
                  <li>{t("fire.snapshot.nothingYet")}</li>
                )}
                {Object.entries(snapshot.breakdown).map(([group, value]) => (
                  <li key={group} className="flex justify-between gap-4">
                    <span>{t(`fire.assetClass.${group}`)}</span>
                    <span dir="ltr">{money.format(value)}</span>
                  </li>
                ))}
                {snapshot.shortfall_capital > 0.5 && (
                  <li className="flex justify-between gap-4 text-amber-400">
                    <span>{t("fire.snapshot.shortfall")}</span>
                    <span dir="ltr">{money.format(snapshot.shortfall_capital)}</span>
                  </li>
                )}
              </ul>
            </div>
          ))}
        </div>
      )}

      {projection.annuities.length > 0 && (
        <div
          data-testid="fire-annuities"
          className="p-4 rounded-xl bg-[var(--surface)] border border-[var(--surface-light)]"
        >
          <h4 className="mb-3 text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
            {t("fire.section.annuities")}
          </h4>
          <ul className="space-y-1 text-sm text-[var(--text-secondary)]">
            {projection.annuities.map((annuity, index) => (
              <li key={index} className="flex justify-between gap-4">
                <span>
                  {t(annuity.owner ? "fire.annuity.row" : "fire.annuity.rowUnnamed", {
                    owner: annuity.owner,
                    source: annuity.description
                      || t(`fire.annuitySource.${annuity.source}`),
                    component: t(`fire.annuityComponent.${annuity.component}`),
                    kind: t(annuity.recognised ? "fire.annuity.recognised" : "fire.annuity.entitling"),
                    age: annuity.claim_age.toFixed(0),
                  })}
                </span>
                <span dir="ltr" className="whitespace-nowrap">
                  {money.format(annuity.monthly)}
                  {annuity.factor ? ` (${annuity.factor.toFixed(1)})` : ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {projection.withdrawal_plan.length > 0 && (
        <div
          data-testid="fire-withdrawal-plan"
          className="p-4 rounded-xl bg-[var(--surface)] border border-[var(--surface-light)]"
        >
          <h4 className="mb-3 text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
            {t("fire.section.withdrawalPlan")}
          </h4>
          <ul className="space-y-1 text-sm text-[var(--text-secondary)]">
            {projection.withdrawal_plan.map((segment, index) => (
              <li key={index} className="flex justify-between gap-4">
                <span>
                  {t("fire.withdrawal.row", {
                    source: segment.description || flowLabel(segment.source, t),
                    from: segment.from_age.toFixed(1),
                    to: segment.to_age.toFixed(1),
                  })}
                </span>
                <span dir="ltr" className="whitespace-nowrap">
                  {money.format(segment.monthly_average)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <ChartCard id="net-worth" title={t("fire.chart.netWorth")}>
        <AreaChart data={netWorth}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-light)" />
          <XAxis dataKey="age" tick={{ fontSize: 11 }} stroke="var(--text-muted)" />
          <YAxis tick={{ fontSize: 11 }} stroke="var(--text-muted)" width={70} />
          <Tooltip formatter={(value) => money.format(Number(value ?? 0))} />
          <Area type="monotone" dataKey="value" stroke={SERIES_COLORS[0]} fill={SERIES_COLORS[0]} fillOpacity={0.2} />
        </AreaChart>
      </ChartCard>

      <ChartCard id="assets" title={t("fire.chart.assets")}>
        <AreaChart data={assets}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-light)" />
          <XAxis dataKey="age" tick={{ fontSize: 11 }} stroke="var(--text-muted)" />
          <YAxis tick={{ fontSize: 11 }} stroke="var(--text-muted)" width={70} />
          <Tooltip formatter={(value) => money.format(Number(value ?? 0))} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          {assetKeys.map((key, index) => (
            <Area
              key={key}
              type="monotone"
              dataKey={key}
              stackId="assets"
              stroke={SERIES_COLORS[index % SERIES_COLORS.length]}
              fill={SERIES_COLORS[index % SERIES_COLORS.length]}
              fillOpacity={0.25}
            />
          ))}
        </AreaChart>
      </ChartCard>

      <ChartCard id="income" title={t("fire.chart.income")}>
        <AreaChart data={income.rows}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-light)" />
          <XAxis dataKey="age" tick={{ fontSize: 11 }} stroke="var(--text-muted)" />
          <YAxis tick={{ fontSize: 11 }} stroke="var(--text-muted)" width={70} />
          <Tooltip formatter={(value) => money.format(Number(value ?? 0))} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          {income.keys.map((key, index) => (
            <Area
              key={key}
              type="monotone"
              dataKey={key}
              name={flowLabel(key, t)}
              stackId="income"
              stroke={SERIES_COLORS[index % SERIES_COLORS.length]}
              fill={SERIES_COLORS[index % SERIES_COLORS.length]}
              fillOpacity={0.25}
            />
          ))}
        </AreaChart>
      </ChartCard>

      <ChartCard id="spending" title={t("fire.chart.spending")}>
        <AreaChart data={spending.rows}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-light)" />
          <XAxis dataKey="age" tick={{ fontSize: 11 }} stroke="var(--text-muted)" />
          <YAxis tick={{ fontSize: 11 }} stroke="var(--text-muted)" width={70} />
          <Tooltip formatter={(value) => money.format(Number(value ?? 0))} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          {spending.keys.map((key, index) => (
            <Area
              key={key}
              type="monotone"
              dataKey={key}
              name={flowLabel(key, t)}
              stackId="spending"
              stroke={SERIES_COLORS[index % SERIES_COLORS.length]}
              fill={SERIES_COLORS[index % SERIES_COLORS.length]}
              fillOpacity={0.25}
            />
          ))}
        </AreaChart>
      </ChartCard>
    </div>
  );
}
