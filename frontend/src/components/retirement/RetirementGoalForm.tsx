import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  Calculator,
  Save,
  RotateCcw,
  Info,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Wallet,
  PiggyBank,
  ArrowUpDown,
  DollarSign,
  Percent,
  User,
  Users,
  Flag,
  Activity,
  Landmark,
  Coins,
  Shield,
} from "lucide-react";
import {
  retirementApi,
  type RetirementGoal,
  type RetirementStatus,
} from "../../services/api";
import { formatCurrency } from "../../utils/numberFormatting";

interface PendingAdjust {
  field: string;
  value: number;
}

interface Props {
  goal: RetirementGoal | null;
  status: RetirementStatus | null;
  isCalculating?: boolean;
  pendingAdjust?: PendingAdjust | null;
  onAdjustApplied?: () => void;
}

const ILS_FORMAT = new Intl.NumberFormat("he-IL", {
  style: "currency",
  currency: "ILS",
  maximumFractionDigits: 0,
});

function formToPayload(form: ReturnType<typeof goalToForm>) {
  return {
    ...form,
    inflation_rate: form.inflation_rate / 100,
    expected_return_rate: form.expected_return_rate / 100,
    withdrawal_rate: form.withdrawal_rate / 100,
  };
}

function goalToForm(
  goal: RetirementGoal | null,
  status: RetirementStatus | null = null,
) {
  if (!goal) {
    return {
      current_age: 30,
      gender: "male" as string,
      target_retirement_age: 50,
      life_expectancy: 90,
      monthly_expenses_in_retirement: 15000,
      inflation_rate: 2.5,
      expected_return_rate: 4,
      withdrawal_rate: 3.5,
      pension_monthly_payout_estimate: 0,
      keren_hishtalmut_balance: 0,
      keren_hishtalmut_monthly_contribution: 0,
      bituach_leumi_eligible: true,
      bituach_leumi_monthly_estimate: 2800,
      other_passive_income: 0,
      monthly_income: Math.round(status?.avg_monthly_income ?? 0),
      net_worth_override: Math.round(status?.net_worth ?? 0),
      monthly_expenses_override: Math.round(status?.avg_monthly_expenses ?? 0),
      total_investments_override: Math.round(status?.total_investments ?? 0),
    };
  }
  return {
    current_age: goal.current_age,
    gender: goal.gender,
    target_retirement_age: goal.target_retirement_age,
    life_expectancy: goal.life_expectancy,
    monthly_expenses_in_retirement: goal.monthly_expenses_in_retirement,
    inflation_rate: Math.round(goal.inflation_rate * 10000) / 100,
    expected_return_rate: Math.round(goal.expected_return_rate * 10000) / 100,
    withdrawal_rate: Math.round(goal.withdrawal_rate * 10000) / 100,
    pension_monthly_payout_estimate: goal.pension_monthly_payout_estimate,
    keren_hishtalmut_balance: goal.keren_hishtalmut_balance,
    keren_hishtalmut_monthly_contribution:
      goal.keren_hishtalmut_monthly_contribution,
    bituach_leumi_eligible: goal.bituach_leumi_eligible,
    bituach_leumi_monthly_estimate: goal.bituach_leumi_monthly_estimate,
    other_passive_income: goal.other_passive_income,
    monthly_income: Math.round(
      goal.monthly_income ?? status?.avg_monthly_income ?? 0,
    ),
    net_worth_override: Math.round(
      goal.net_worth_override ?? status?.net_worth ?? 0,
    ),
    monthly_expenses_override: Math.round(
      goal.monthly_expenses_override ?? status?.avg_monthly_expenses ?? 0,
    ),
    total_investments_override: Math.round(
      goal.total_investments_override ?? status?.total_investments ?? 0,
    ),
  };
}

export function RetirementGoalForm({
  goal,
  status,
  isCalculating,
  pendingAdjust,
  onAdjustApplied,
}: Props) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);

  const [form, setForm] = useState(() => goalToForm(goal, status));

  // Sync form from saved goal on first load
  const [goalLoaded, setGoalLoaded] = useState(!!goal);
  if (!goalLoaded && goal) {
    setGoalLoaded(true);
    setForm(goalToForm(goal, status));
  }

  // Fill snapshot fields from status when they are still at the default (0)
  // Handles the case where status arrives after the initial form state is set.
  const [statusApplied, setStatusApplied] = useState(!!status);
  if (!statusApplied && status) {
    setStatusApplied(true);
    setForm((prev) => ({
      ...prev,
      ...(prev.net_worth_override === 0 && {
        net_worth_override: Math.round(status.net_worth),
      }),
      ...(prev.monthly_expenses_override === 0 && {
        monthly_expenses_override: Math.round(status.avg_monthly_expenses),
      }),
      ...(prev.total_investments_override === 0 && {
        total_investments_override: Math.round(status.total_investments),
      }),
      ...(prev.monthly_income === 0 && {
        monthly_income: Math.round(status.avg_monthly_income),
      }),
    }));
  }

  const { data: scrapedDefaults } = useQuery({
    queryKey: ["retirement", "scraped-defaults"],
    queryFn: () =>
      retirementApi.getScrapedDefaults().then((r) => r.data),
  });

  // Auto-fill scraped insurance values when no saved goal exists
  const [scrapedApplied, setScrapedApplied] = useState(false);
  if (!scrapedApplied && scrapedDefaults && !goal) {
    setScrapedApplied(true);
    setForm((prev) => ({
      ...prev,
      ...(scrapedDefaults.keren_hishtalmut_balance != null && {
        keren_hishtalmut_balance: scrapedDefaults.keren_hishtalmut_balance,
      }),
      ...(scrapedDefaults.keren_hishtalmut_monthly_contribution != null && {
        keren_hishtalmut_monthly_contribution: scrapedDefaults.keren_hishtalmut_monthly_contribution,
      }),
      ...(scrapedDefaults.pension_monthly_deposit != null && {
        pension_monthly_payout_estimate: scrapedDefaults.pension_monthly_deposit,
      }),
      ...(scrapedDefaults.avg_monthly_salary != null && {
        monthly_income: scrapedDefaults.avg_monthly_salary,
      }),
    }));
  }

  // Calculate: preview projections without saving
  const calculateMutation = useMutation({
    mutationFn: (overrideForm?: ReturnType<typeof goalToForm>) => {
      const payload = formToPayload(overrideForm ?? form);
      return Promise.all([
        retirementApi.previewProjections(payload),
        retirementApi.previewSuggestions(payload),
      ]);
    },
    onSuccess: ([projectionsRes, suggestionsRes]) => {
      queryClient.setQueryData(
        ["retirement", "projections"],
        projectionsRes.data,
      );
      queryClient.setQueryData(
        ["retirement", "suggestions"],
        suggestionsRes.data,
      );
    },
  });

  // Handle pending adjustment from projections "Adjust Plan" buttons
  const [lastAppliedKey, setLastAppliedKey] = useState("");
  const adjustKey = pendingAdjust
    ? `${pendingAdjust.field}:${pendingAdjust.value}`
    : "";
  if (pendingAdjust && adjustKey !== lastAppliedKey) {
    setLastAppliedKey(adjustKey);
    const { field, value } = pendingAdjust;
    // expected_return_rate comes as decimal from solver, form uses percentage
    const formValue =
      field === "expected_return_rate"
        ? Math.round(value * 10000) / 100
        : value;
    const updated = { ...form, [field]: formValue };
    setForm(updated);
    setHasUnsavedChanges(true);
    // Schedule preview after render completes
    setTimeout(() => {
      const payload = formToPayload(updated);
      Promise.all([
        retirementApi.previewProjections(payload),
        retirementApi.previewSuggestions(payload),
      ]).then(([projectionsRes, suggestionsRes]) => {
        queryClient.setQueryData(
          ["retirement", "projections"],
          projectionsRes.data,
        );
        queryClient.setQueryData(
          ["retirement", "suggestions"],
          suggestionsRes.data,
        );
        onAdjustApplied?.();
      });
    }, 0);
  }

  // Save Plan: persist to DB
  const saveMutation = useMutation({
    mutationFn: () => retirementApi.upsertGoal(formToPayload(form)),
    onSuccess: (response) => {
      queryClient.setQueryData(["retirement", "goal"], response.data);
      setHasUnsavedChanges(false);
    },
  });

  const handleChange = (field: string, value: number | boolean | string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
    setHasUnsavedChanges(true);
  };

  const handleCalculate = (e: React.FormEvent) => {
    e.preventDefault();
    calculateMutation.mutate(undefined);
  };

  const handleSave = () => {
    saveMutation.mutate();
  };

  const handleReset = () => {
    if (!goal) return;
    setForm(goalToForm(goal, status));
    setHasUnsavedChanges(false);
    // Re-preview with saved values
    const payload = formToPayload(goalToForm(goal, status));
    Promise.all([
      retirementApi.previewProjections(payload),
      retirementApi.previewSuggestions(payload),
    ]).then(([projectionsRes, suggestionsRes]) => {
      queryClient.setQueryData(
        ["retirement", "projections"],
        projectionsRes.data,
      );
      queryClient.setQueryData(
        ["retirement", "suggestions"],
        suggestionsRes.data,
      );
    });
  };

  const applyScrapedKhBalance = () => {
    if (scrapedDefaults?.keren_hishtalmut_balance != null) {
      handleChange("keren_hishtalmut_balance", scrapedDefaults.keren_hishtalmut_balance);
    }
  };

  const applyScrapedKhMonthly = () => {
    if (scrapedDefaults?.keren_hishtalmut_monthly_contribution != null) {
      handleChange("keren_hishtalmut_monthly_contribution", scrapedDefaults.keren_hishtalmut_monthly_contribution);
    }
  };

  const applyScrapedPension = () => {
    if (scrapedDefaults?.pension_monthly_deposit != null) {
      handleChange("pension_monthly_payout_estimate", scrapedDefaults.pension_monthly_deposit);
    }
  };

  const isBusy =
    calculateMutation.isPending ||
    saveMutation.isPending ||
    !!isCalculating;

  // Compute derived snapshot values from current form inputs
  const effectiveIncome =
    form.monthly_income || (status?.avg_monthly_income ?? 0);
  const effectiveExpenses =
    form.monthly_expenses_override || (status?.avg_monthly_expenses ?? 0);
  const computedSavings = effectiveIncome - effectiveExpenses;
  const computedSavingsRate =
    effectiveIncome > 0 ? (computedSavings / effectiveIncome) * 100 : 0;

  return (
    <form onSubmit={handleCalculate} className="space-y-4 md:space-y-6">
      {/* Financial Snapshot — editable current-status inputs */}
      <div className="space-y-3 p-4 rounded-xl bg-[var(--surface)] border border-[var(--surface-light)]">
        <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
          {t("earlyRetirement.sections.currentStatus")}
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <SnapshotField
            label={t("earlyRetirement.status.netWorth")}
            icon={TrendingUp}
            iconColor="text-emerald-400"
            value={form.net_worth_override}
            statusValue={Math.round(status?.net_worth ?? 0)}
            onChange={(v) => handleChange("net_worth_override", v)}
            onReset={() =>
              handleChange(
                "net_worth_override",
                Math.round(status?.net_worth ?? 0),
              )
            }
          />
          <div>
            <SnapshotField
              label={t("earlyRetirement.status.avgMonthlyIncome")}
              icon={DollarSign}
              iconColor="text-blue-400"
              value={form.monthly_income}
              statusValue={Math.round(status?.avg_monthly_income ?? 0)}
              onChange={(v) => handleChange("monthly_income", v)}
              onReset={() =>
                handleChange(
                  "monthly_income",
                  Math.round(status?.avg_monthly_income ?? 0),
                )
              }
            />
            {scrapedDefaults?.avg_monthly_salary != null && (
              <button
                type="button"
                onClick={() =>
                  handleChange(
                    "monthly_income",
                    scrapedDefaults.avg_monthly_salary!,
                  )
                }
                className="flex items-center gap-1 mt-1 text-xs text-[var(--primary)] hover:text-blue-300 transition-colors"
              >
                <RefreshCw size={10} />
                {t("earlyRetirement.form.useSalaryAvg", {
                  amount: ILS_FORMAT.format(scrapedDefaults.avg_monthly_salary),
                })}
              </button>
            )}
          </div>
          <SnapshotField
            label={t("earlyRetirement.status.avgMonthlyExpenses")}
            icon={Wallet}
            iconColor="text-rose-400"
            value={form.monthly_expenses_override}
            statusValue={Math.round(status?.avg_monthly_expenses ?? 0)}
            onChange={(v) => handleChange("monthly_expenses_override", v)}
            onReset={() =>
              handleChange(
                "monthly_expenses_override",
                Math.round(status?.avg_monthly_expenses ?? 0),
              )
            }
          />
          {/* Monthly Savings — computed */}
          <div className="p-3 rounded-xl bg-[var(--surface-light)] border border-[var(--surface-light)]">
            <div className="flex items-center gap-1.5 mb-2">
              <PiggyBank
                size={14}
                className={
                  computedSavings >= 0 ? "text-emerald-400" : "text-rose-400"
                }
              />
              <span className="text-xs text-[var(--text-muted)] truncate">
                {t("earlyRetirement.status.monthlySavings")}
              </span>
            </div>
            <div
              className={`text-sm font-bold ${computedSavings >= 0 ? "text-emerald-400" : "text-rose-400"}`}
              dir="ltr"
            >
              {formatCurrency(computedSavings)}
            </div>
            <div className="text-xs text-[var(--text-muted)] mt-0.5 italic">
              {t("earlyRetirement.status.computed")}
            </div>
          </div>
          {/* Savings Rate — computed */}
          <div className="p-3 rounded-xl bg-[var(--surface-light)] border border-[var(--surface-light)]">
            <div className="flex items-center gap-1.5 mb-2">
              <Percent
                size={14}
                className={
                  computedSavingsRate >= 50
                    ? "text-emerald-400"
                    : computedSavingsRate >= 20
                      ? "text-amber-400"
                      : "text-rose-400"
                }
              />
              <span className="text-xs text-[var(--text-muted)] truncate">
                {t("earlyRetirement.status.savingsRate")}
              </span>
            </div>
            <div
              className={`text-sm font-bold ${computedSavingsRate >= 50 ? "text-emerald-400" : computedSavingsRate >= 20 ? "text-amber-400" : "text-rose-400"}`}
              dir="ltr"
            >
              {computedSavingsRate.toFixed(1)}%
            </div>
            <div className="text-xs text-[var(--text-muted)] mt-0.5 italic">
              {t("earlyRetirement.status.computed")}
            </div>
          </div>
          <SnapshotField
            label={t("earlyRetirement.status.totalInvestments")}
            icon={ArrowUpDown}
            iconColor="text-purple-400"
            value={form.total_investments_override}
            statusValue={Math.round(status?.total_investments ?? 0)}
            onChange={(v) => handleChange("total_investments_override", v)}
            onReset={() =>
              handleChange(
                "total_investments_override",
                Math.round(status?.total_investments ?? 0),
              )
            }
          />
        </div>
      </div>

      {/* Retirement Parameters */}
      <div className="space-y-3 p-4 rounded-xl bg-[var(--surface)] border border-[var(--surface-light)]">
        <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
          {t("earlyRetirement.sections.parameters")}
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <NumberField
            label={t("earlyRetirement.form.currentAge")}
            icon={User}
            iconColor="text-blue-400"
            value={form.current_age}
            onChange={(v) => handleChange("current_age", v)}
            min={18}
            max={100}
            step={1}
          />
          <SelectField
            label={t("earlyRetirement.form.gender")}
            icon={Users}
            iconColor="text-cyan-400"
            value={form.gender}
            onChange={(v) => handleChange("gender", v)}
            options={[
              { value: "male", label: t("earlyRetirement.form.male") },
              { value: "female", label: t("earlyRetirement.form.female") },
            ]}
          />
          <NumberField
            label={t("earlyRetirement.form.targetRetirementAge")}
            icon={Flag}
            iconColor="text-amber-400"
            value={form.target_retirement_age}
            onChange={(v) => handleChange("target_retirement_age", v)}
            min={30}
            max={100}
            step={1}
          />
          <NumberField
            label={t("earlyRetirement.form.lifeExpectancy")}
            icon={Activity}
            iconColor="text-rose-400"
            value={form.life_expectancy}
            onChange={(v) => handleChange("life_expectancy", v)}
            min={60}
            max={120}
            step={1}
          />
          <NumberField
            label={t("earlyRetirement.form.monthlyExpenses")}
            icon={Wallet}
            iconColor="text-rose-400"
            value={form.monthly_expenses_in_retirement}
            onChange={(v) => handleChange("monthly_expenses_in_retirement", v)}
            min={0}
            suffix="₪"
          />
          <NumberField
            label={t("earlyRetirement.form.expectedReturn")}
            icon={TrendingUp}
            iconColor="text-emerald-400"
            value={form.expected_return_rate}
            onChange={(v) => handleChange("expected_return_rate", v)}
            min={-10}
            max={30}
            step={0.01}
            suffix="%"
          />
          <NumberField
            label={t("earlyRetirement.form.withdrawalRate")}
            icon={Percent}
            iconColor="text-purple-400"
            value={form.withdrawal_rate}
            onChange={(v) => handleChange("withdrawal_rate", v)}
            min={0.5}
            max={10}
            step={0.01}
            suffix="%"
            tooltip={t("earlyRetirement.tooltips.withdrawalRate")}
          />
          <NumberField
            label={t("earlyRetirement.form.inflationRate")}
            icon={TrendingDown}
            iconColor="text-orange-400"
            value={form.inflation_rate}
            onChange={(v) => handleChange("inflation_rate", v)}
            min={0}
            max={20}
            step={0.01}
            suffix="%"
          />
        </div>
      </div>

      {/* Israeli Savings Vehicles */}
      <div className="space-y-3 p-4 rounded-xl bg-[var(--surface)] border border-[var(--surface-light)]">
        <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
          {t("earlyRetirement.form.israeliVehicles")}
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <NumberField
            label={t("earlyRetirement.form.pensionPayout")}
            icon={Landmark}
            iconColor="text-indigo-400"
            value={form.pension_monthly_payout_estimate}
            onChange={(v) => handleChange("pension_monthly_payout_estimate", v)}
            min={0}
            suffix="₪"
            tooltip={t("earlyRetirement.tooltips.pension")}
            footer={
              scrapedDefaults?.pension_monthly_deposit != null ? (
                <ScrapedHint
                  onClick={applyScrapedPension}
                  label={t("earlyRetirement.form.useScrapedPension", {
                    amount: ILS_FORMAT.format(
                      scrapedDefaults.pension_monthly_deposit,
                    ),
                  })}
                />
              ) : null
            }
          />
          <NumberField
            label={t("earlyRetirement.form.kerenHishtalmutBalance")}
            icon={PiggyBank}
            iconColor="text-emerald-400"
            value={form.keren_hishtalmut_balance}
            onChange={(v) => handleChange("keren_hishtalmut_balance", v)}
            min={0}
            suffix="₪"
            footer={
              scrapedDefaults?.keren_hishtalmut_balance != null ? (
                <ScrapedHint
                  onClick={applyScrapedKhBalance}
                  label={t("earlyRetirement.form.useScrapedKh", {
                    amount: ILS_FORMAT.format(
                      scrapedDefaults.keren_hishtalmut_balance,
                    ),
                  })}
                />
              ) : null
            }
          />
          <NumberField
            label={t("earlyRetirement.form.kerenHishtalmutMonthly")}
            icon={Coins}
            iconColor="text-amber-400"
            value={form.keren_hishtalmut_monthly_contribution}
            onChange={(v) =>
              handleChange("keren_hishtalmut_monthly_contribution", v)
            }
            min={0}
            suffix="₪"
            footer={
              scrapedDefaults?.keren_hishtalmut_monthly_contribution != null ? (
                <ScrapedHint
                  onClick={applyScrapedKhMonthly}
                  label={t("earlyRetirement.form.useScrapedKhMonthly", {
                    amount: ILS_FORMAT.format(
                      scrapedDefaults.keren_hishtalmut_monthly_contribution,
                    ),
                  })}
                />
              ) : null
            }
          />
          <NumberField
            label={t("earlyRetirement.form.bituachLeumiEstimate")}
            icon={Shield}
            iconColor="text-teal-400"
            value={form.bituach_leumi_monthly_estimate}
            onChange={(v) =>
              handleChange("bituach_leumi_monthly_estimate", v)
            }
            min={0}
            suffix="₪"
            disabled={!form.bituach_leumi_eligible}
            headerExtra={
              <input
                type="checkbox"
                checked={form.bituach_leumi_eligible}
                onChange={(e) =>
                  handleChange("bituach_leumi_eligible", e.target.checked)
                }
                title={t("earlyRetirement.form.bituachLeumiEligible")}
                aria-label={t("earlyRetirement.form.bituachLeumiEligible")}
                className="shrink-0 w-3.5 h-3.5 rounded border-gray-600 text-blue-500 focus:ring-blue-500 bg-[var(--surface)] cursor-pointer"
              />
            }
          />
          <NumberField
            label={t("earlyRetirement.form.otherPassiveIncome")}
            icon={DollarSign}
            iconColor="text-green-400"
            value={form.other_passive_income}
            onChange={(v) => handleChange("other_passive_income", v)}
            min={0}
            suffix="₪"
          />
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex items-center justify-end gap-3">
        {goal && hasUnsavedChanges && (
          <button
            type="button"
            onClick={handleReset}
            disabled={isBusy}
            className="flex items-center gap-2 px-4 py-2.5 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] border border-[var(--surface-light)] rounded-lg transition-colors disabled:opacity-50"
          >
            <RotateCcw size={15} />
            {t("earlyRetirement.form.resetPlan")}
          </button>
        )}
        <button
          type="button"
          onClick={handleSave}
          disabled={isBusy || !hasUnsavedChanges}
          className="flex items-center gap-2 px-4 py-2.5 text-sm bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-medium transition-colors disabled:opacity-50"
        >
          <Save size={15} />
          {saveMutation.isPending
            ? t("common.loading")
            : t("earlyRetirement.form.savePlan")}
        </button>
        <button
          type="submit"
          disabled={isBusy}
          className="flex items-center gap-2 px-6 py-2.5 bg-[var(--primary)] hover:bg-blue-600 text-white rounded-lg font-medium transition-colors disabled:opacity-50"
        >
          <Calculator size={16} />
          {calculateMutation.isPending || isCalculating
            ? t("common.loading")
            : t("earlyRetirement.form.calculate")}
        </button>
      </div>
    </form>
  );
}

const CARD_INPUT_CLASS =
  "w-full px-1.5 py-1 text-sm font-semibold bg-[var(--surface)] border border-[var(--surface-light)] rounded-lg text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--primary)] disabled:opacity-50 disabled:cursor-not-allowed [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none";

/**
 * Shared card shell for every form field. Header row holds an icon, the
 * label, an optional suffix/tooltip and an optional right-aligned extra
 * (reset button, eligibility checkbox); the control renders below it.
 */
function FieldCard({
  label,
  icon: Icon,
  iconColor,
  suffix,
  tooltip,
  headerExtra,
  footer,
  children,
}: {
  label: string;
  icon?: React.ElementType;
  iconColor?: string;
  suffix?: string;
  tooltip?: string;
  headerExtra?: React.ReactNode;
  footer?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="p-3 rounded-xl bg-[var(--surface-light)] border border-[var(--surface-light)]">
      <div className="flex items-center justify-between gap-1 mb-2">
        <div className="flex items-center gap-1.5 min-w-0">
          {Icon && (
            <Icon size={14} className={`shrink-0 ${iconColor ?? ""}`} />
          )}
          <span className="text-xs text-[var(--text-muted)] truncate">
            {label}
          </span>
          {suffix && (
            <span className="text-[10px] text-[var(--text-muted)] shrink-0">
              ({suffix})
            </span>
          )}
          {tooltip && <FieldTooltip text={tooltip} />}
        </div>
        {headerExtra}
      </div>
      {children}
      {footer}
    </div>
  );
}

function FieldTooltip({ text }: { text: string }) {
  return (
    <span className="group relative shrink-0">
      <Info size={12} className="text-[var(--text-muted)] cursor-help" />
      <span className="absolute z-10 hidden group-hover:block w-48 sm:w-64 max-w-[calc(100vw-3rem)] p-2 text-xs text-[var(--text-primary)] bg-[var(--surface)] border border-[var(--surface-light)] rounded-lg shadow-lg -top-2 start-6">
        {text}
      </span>
    </span>
  );
}

function ScrapedHint({
  onClick,
  label,
}: {
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center gap-1 mt-1 text-[11px] text-[var(--primary)] hover:text-blue-300 transition-colors"
    >
      <RefreshCw size={10} className="shrink-0" />
      <span className="truncate">{label}</span>
    </button>
  );
}

function NumberField({
  label,
  icon,
  iconColor,
  value,
  onChange,
  min,
  max,
  step,
  suffix,
  tooltip,
  disabled,
  headerExtra,
  footer,
}: {
  label: string;
  icon?: React.ElementType;
  iconColor?: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  suffix?: string;
  tooltip?: string;
  disabled?: boolean;
  headerExtra?: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <FieldCard
      label={label}
      icon={icon}
      iconColor={iconColor}
      suffix={suffix}
      tooltip={tooltip}
      headerExtra={headerExtra}
      footer={footer}
    >
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        className={CARD_INPUT_CLASS}
        dir="ltr"
      />
    </FieldCard>
  );
}

function SelectField({
  label,
  icon,
  iconColor,
  value,
  onChange,
  options,
}: {
  label: string;
  icon?: React.ElementType;
  iconColor?: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <FieldCard label={label} icon={icon} iconColor={iconColor}>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-1.5 py-1 text-sm font-semibold bg-[var(--surface)] border border-[var(--surface-light)] rounded-lg text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </FieldCard>
  );
}

function SnapshotField({
  label,
  icon,
  iconColor,
  value,
  statusValue,
  onChange,
  onReset,
}: {
  label: string;
  icon: React.ElementType;
  iconColor: string;
  value: number;
  statusValue: number;
  onChange: (value: number) => void;
  onReset: () => void;
}) {
  const { t } = useTranslation();
  const isOverridden = value !== statusValue && value !== 0;
  return (
    <FieldCard
      label={label}
      icon={icon}
      iconColor={iconColor}
      headerExtra={
        isOverridden ? (
          <button
            type="button"
            onClick={onReset}
            title={t("earlyRetirement.status.resetToCalculated")}
            aria-label={t("earlyRetirement.status.resetToCalculated")}
            className="shrink-0 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors ms-1"
          >
            <RotateCcw size={11} />
          </button>
        ) : null
      }
    >
      <input
        type="number"
        value={value || ""}
        onChange={(e) =>
          onChange(e.target.value === "" ? statusValue : Number(e.target.value))
        }
        min={0}
        className={CARD_INPUT_CLASS}
        dir="ltr"
      />
    </FieldCard>
  );
}
