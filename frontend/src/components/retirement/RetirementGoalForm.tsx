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
  ChevronDown,
  ChevronUp,
  Info,
  RefreshCw,
} from "lucide-react";
import { retirementApi, type RetirementGoal } from "../../services/api";

interface PendingAdjust {
  field: string;
  value: number;
}

interface Props {
  goal: RetirementGoal | null;
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

function goalToForm(goal: RetirementGoal | null) {
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
  };
}

export function RetirementGoalForm({
  goal,
  isCalculating,
  pendingAdjust,
  onAdjustApplied,
}: Props) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);

  const [form, setForm] = useState(() => goalToForm(goal));

  // Sync form from saved goal on first load
  const [goalLoaded, setGoalLoaded] = useState(!!goal);
  if (!goalLoaded && goal) {
    setGoalLoaded(true);
    setForm(goalToForm(goal));
  }

  const { data: khScraped } = useQuery({
    queryKey: ["retirement", "keren-hishtalmut-balance"],
    queryFn: () =>
      retirementApi.getKerenHishtalmutBalance().then((r) => r.data),
  });

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
    setForm(goalToForm(goal));
    setHasUnsavedChanges(false);
    // Re-preview with saved values
    const payload = formToPayload(goalToForm(goal));
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

  const applyScrapedKh = () => {
    if (khScraped?.balance != null) {
      handleChange("keren_hishtalmut_balance", khScraped.balance);
    }
  };

  const isBusy =
    calculateMutation.isPending ||
    saveMutation.isPending ||
    !!isCalculating;

  return (
    <form onSubmit={handleCalculate} className="space-y-6">
      {/* Core Parameters */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
        <NumberField
          label={t("earlyRetirement.form.currentAge")}
          value={form.current_age}
          onChange={(v) => handleChange("current_age", v)}
          min={18}
          max={100}
          step={1}
        />
        <div>
          <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1">
            {t("earlyRetirement.form.gender")}
          </label>
          <select
            value={form.gender}
            onChange={(e) => handleChange("gender", e.target.value)}
            className="w-full px-2 py-1.5 text-sm bg-[var(--surface)] border border-[var(--surface-light)] rounded-lg text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
          >
            <option value="male">{t("earlyRetirement.form.male")}</option>
            <option value="female">
              {t("earlyRetirement.form.female")}
            </option>
          </select>
          <span className="text-xs text-[var(--text-muted)] mt-0.5 block">
            {t("earlyRetirement.form.genderPensionNote", {
              age: form.gender === "female" ? 65 : 67,
            })}
          </span>
        </div>
        <NumberField
          label={t("earlyRetirement.form.targetRetirementAge")}
          value={form.target_retirement_age}
          onChange={(v) => handleChange("target_retirement_age", v)}
          min={30}
          max={100}
          step={1}
        />
        <NumberField
          label={t("earlyRetirement.form.lifeExpectancy")}
          value={form.life_expectancy}
          onChange={(v) => handleChange("life_expectancy", v)}
          min={60}
          max={120}
          step={1}
        />
        <NumberField
          label={t("earlyRetirement.form.monthlyExpenses")}
          value={form.monthly_expenses_in_retirement}
          onChange={(v) => handleChange("monthly_expenses_in_retirement", v)}
          min={0}
          step={500}
          suffix="₪"
        />
        <NumberField
          label={t("earlyRetirement.form.expectedReturn")}
          value={form.expected_return_rate}
          onChange={(v) => handleChange("expected_return_rate", v)}
          min={-10}
          max={30}
          step={0.5}
          suffix="%"
        />
        <NumberField
          label={t("earlyRetirement.form.withdrawalRate")}
          value={form.withdrawal_rate}
          onChange={(v) => handleChange("withdrawal_rate", v)}
          min={0.5}
          max={10}
          step={0.5}
          suffix="%"
          tooltip={t("earlyRetirement.tooltips.withdrawalRate")}
        />
      </div>

      {/* Israeli Savings Vehicles Toggle */}
      <button
        type="button"
        onClick={() => setShowAdvanced(!showAdvanced)}
        className="flex items-center gap-2 text-sm font-medium text-[var(--primary)] hover:text-blue-300 transition-colors"
      >
        {showAdvanced ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        {t("earlyRetirement.form.israeliVehicles")}
      </button>

      {showAdvanced && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3 p-4 rounded-lg bg-[var(--surface-light)]">
          <NumberField
            label={t("earlyRetirement.form.pensionPayout")}
            value={form.pension_monthly_payout_estimate}
            onChange={(v) =>
              handleChange("pension_monthly_payout_estimate", v)
            }
            min={0}
            step={500}
            suffix="₪"
            tooltip={t("earlyRetirement.tooltips.pension")}
          />
          <div>
            <NumberField
              label={t("earlyRetirement.form.kerenHishtalmutBalance")}
              value={form.keren_hishtalmut_balance}
              onChange={(v) =>
                handleChange("keren_hishtalmut_balance", v)
              }
              min={0}
              step={1000}
              suffix="₪"
            />
            {khScraped?.balance != null && (
              <button
                type="button"
                onClick={applyScrapedKh}
                className="flex items-center gap-1 mt-0.5 text-xs text-[var(--primary)] hover:text-blue-300 transition-colors"
              >
                <RefreshCw size={10} />
                {t("earlyRetirement.form.useScrapedKh", {
                  amount: ILS_FORMAT.format(khScraped.balance),
                })}
              </button>
            )}
          </div>
          <NumberField
            label={t("earlyRetirement.form.kerenHishtalmutMonthly")}
            value={form.keren_hishtalmut_monthly_contribution}
            onChange={(v) =>
              handleChange(
                "keren_hishtalmut_monthly_contribution",
                v,
              )
            }
            min={0}
            step={100}
            suffix="₪"
          />
          <div>
            <NumberField
              label={t("earlyRetirement.form.bituachLeumiEstimate")}
              value={form.bituach_leumi_monthly_estimate}
              onChange={(v) =>
                handleChange("bituach_leumi_monthly_estimate", v)
              }
              min={0}
              step={100}
              suffix="₪"
              tooltip={t("earlyRetirement.tooltips.bituachLeumi")}
              disabled={!form.bituach_leumi_eligible}
            />
            <label className="flex items-center gap-1.5 mt-1 cursor-pointer">
              <input
                type="checkbox"
                checked={form.bituach_leumi_eligible}
                onChange={(e) =>
                  handleChange(
                    "bituach_leumi_eligible",
                    e.target.checked,
                  )
                }
                className="w-3.5 h-3.5 rounded border-gray-600 text-blue-500 focus:ring-blue-500 bg-[var(--surface)]"
              />
              <span className="text-xs text-[var(--text-muted)]">
                {t("earlyRetirement.form.bituachLeumiEligible")}
              </span>
            </label>
          </div>
          <NumberField
            label={t("earlyRetirement.form.otherPassiveIncome")}
            value={form.other_passive_income}
            onChange={(v) => handleChange("other_passive_income", v)}
            min={0}
            step={500}
            suffix="₪"
          />
          <NumberField
            label={t("earlyRetirement.form.inflationRate")}
            value={form.inflation_rate}
            onChange={(v) => handleChange("inflation_rate", v)}
            min={0}
            max={20}
            step={0.5}
            suffix="%"
          />
        </div>
      )}

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

function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  step,
  suffix,
  tooltip,
  disabled,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  suffix?: string;
  tooltip?: string;
  disabled?: boolean;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1">
        <span className="flex items-center gap-1">
          {label}
          {suffix && (
            <span className="text-[var(--text-muted)]">({suffix})</span>
          )}
          {tooltip && (
            <span className="group relative">
              <Info
                size={12}
                className="text-[var(--text-muted)] cursor-help"
              />
              <span className="absolute z-10 hidden group-hover:block w-64 p-2 text-xs text-[var(--text-primary)] bg-[var(--surface)] border border-[var(--surface-light)] rounded-lg shadow-lg -top-2 start-6">
                {tooltip}
              </span>
            </span>
          )}
        </span>
      </label>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        className="w-full px-2 py-1.5 text-sm bg-[var(--surface)] border border-[var(--surface-light)] rounded-lg text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--primary)] disabled:opacity-50 disabled:cursor-not-allowed [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
        dir="ltr"
      />
    </div>
  );
}
