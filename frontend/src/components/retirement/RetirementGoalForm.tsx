import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  Save,
  ChevronDown,
  ChevronUp,
  Info,
  RefreshCw,
  Wand2,
} from "lucide-react";
import { retirementApi, type RetirementGoal } from "../../services/api";

interface Props {
  goal: RetirementGoal | null;
  isCalculating?: boolean;
}

type AutoAdjustField =
  | "target_retirement_age"
  | "monthly_expenses_in_retirement"
  | "expected_return_rate"
  | null;

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
    inflation_rate: goal.inflation_rate * 100,
    expected_return_rate: goal.expected_return_rate * 100,
    withdrawal_rate: goal.withdrawal_rate * 100,
    pension_monthly_payout_estimate: goal.pension_monthly_payout_estimate,
    keren_hishtalmut_balance: goal.keren_hishtalmut_balance,
    keren_hishtalmut_monthly_contribution:
      goal.keren_hishtalmut_monthly_contribution,
    bituach_leumi_eligible: goal.bituach_leumi_eligible,
    bituach_leumi_monthly_estimate: goal.bituach_leumi_monthly_estimate,
    other_passive_income: goal.other_passive_income,
  };
}

const SOLVE_FIELD_MAP: Record<
  Exclude<AutoAdjustField, null>,
  string
> = {
  target_retirement_age: "target_retirement_age",
  monthly_expenses_in_retirement: "monthly_expenses_in_retirement",
  expected_return_rate: "expected_return_rate",
};

export function RetirementGoalForm({ goal, isCalculating }: Props) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [autoAdjustField, setAutoAdjustField] =
    useState<AutoAdjustField>(null);

  const [form, setForm] = useState(() => goalToForm(goal));

  // Only populate form from server goal on initial load (when goal
  // transitions from null/undefined to an actual object for the first time).
  // After that, the form is the source of truth — saves should NOT reset it.
  const [goalLoaded, setGoalLoaded] = useState(!!goal);
  if (!goalLoaded && goal) {
    setGoalLoaded(true);
    setForm(goalToForm(goal));
  }

  // Auto-detect Keren Hishtalmut balance from scraped data
  const { data: khScraped } = useQuery({
    queryKey: ["retirement", "keren-hishtalmut-balance"],
    queryFn: () =>
      retirementApi.getKerenHishtalmutBalance().then((r) => r.data),
  });

  // Solve for auto-adjusted field (only when goal exists and a field is selected)
  const { data: solvedData, isFetching: isSolving } = useQuery({
    queryKey: ["retirement", "solve", autoAdjustField],
    queryFn: () =>
      retirementApi
        .solveForField(SOLVE_FIELD_MAP[autoAdjustField!])
        .then((r) => r.data),
    enabled: !!goal && !!autoAdjustField,
  });

  const mutation = useMutation({
    mutationFn: () =>
      retirementApi.upsertGoal({
        ...form,
        inflation_rate: form.inflation_rate / 100,
        expected_return_rate: form.expected_return_rate / 100,
        withdrawal_rate: form.withdrawal_rate / 100,
      }),
    onSuccess: (response) => {
      // Update goal cache so projections section appears immediately
      queryClient.setQueryData(["retirement", "goal"], response.data);
      // Refetch projections, status, and solve queries
      queryClient.invalidateQueries({
        queryKey: ["retirement", "projections"],
      });
      queryClient.invalidateQueries({
        queryKey: ["retirement", "status"],
      });
      queryClient.invalidateQueries({
        queryKey: ["retirement", "solve"],
      });
    },
  });

  const handleChange = (field: string, value: number | boolean | string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    mutation.mutate();
  };

  const applyScrapedKh = () => {
    if (khScraped?.balance != null) {
      handleChange("keren_hishtalmut_balance", khScraped.balance);
    }
  };

  const toggleAutoAdjust = (field: Exclude<AutoAdjustField, null>) => {
    setAutoAdjustField((prev) => (prev === field ? null : field));
  };

  const getSolvedDisplayValue = (): string | null => {
    if (!solvedData || !autoAdjustField) return null;
    if (solvedData.value === -1)
      return t("earlyRetirement.projections.notReachable");

    if (autoAdjustField === "target_retirement_age") {
      return `${solvedData.value}`;
    }
    if (autoAdjustField === "monthly_expenses_in_retirement") {
      return new Intl.NumberFormat("he-IL", {
        style: "currency",
        currency: "ILS",
        maximumFractionDigits: 0,
      }).format(solvedData.value);
    }
    if (autoAdjustField === "expected_return_rate") {
      return `${(solvedData.value * 100).toFixed(1)}%`;
    }
    return null;
  };

  const isBusy = mutation.isPending || !!isCalculating;

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Core Parameters */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <NumberField
          label={t("earlyRetirement.form.currentAge")}
          value={form.current_age}
          onChange={(v) => handleChange("current_age", v)}
          min={18}
          max={100}
          step={1}
        />
        <div>
          <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
            {t("earlyRetirement.form.gender")}
          </label>
          <select
            value={form.gender}
            onChange={(e) => handleChange("gender", e.target.value)}
            className="w-full px-3 py-2 bg-[var(--surface)] border border-[var(--surface-light)] rounded-lg text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
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
        <AutoAdjustableField
          fieldKey="target_retirement_age"
          autoAdjustField={autoAdjustField}
          solvedDisplayValue={getSolvedDisplayValue()}
          isSolving={isSolving}
          onToggle={toggleAutoAdjust}
          hasGoal={!!goal}
          autoTooltip={t("earlyRetirement.form.autoAdjustTooltip")}
        >
          <NumberField
            label={t("earlyRetirement.form.targetRetirementAge")}
            value={form.target_retirement_age}
            onChange={(v) => handleChange("target_retirement_age", v)}
            min={30}
            max={100}
            step={1}
            disabled={autoAdjustField === "target_retirement_age"}
          />
        </AutoAdjustableField>
        <AutoAdjustableField
          fieldKey="monthly_expenses_in_retirement"
          autoAdjustField={autoAdjustField}
          solvedDisplayValue={getSolvedDisplayValue()}
          isSolving={isSolving}
          onToggle={toggleAutoAdjust}
          hasGoal={!!goal}
          autoTooltip={t("earlyRetirement.form.autoAdjustTooltip")}
        >
          <NumberField
            label={t("earlyRetirement.form.monthlyExpenses")}
            value={form.monthly_expenses_in_retirement}
            onChange={(v) =>
              handleChange("monthly_expenses_in_retirement", v)
            }
            min={0}
            step={500}
            suffix="₪"
            disabled={
              autoAdjustField === "monthly_expenses_in_retirement"
            }
          />
        </AutoAdjustableField>
        <NumberField
          label={t("earlyRetirement.form.lifeExpectancy")}
          value={form.life_expectancy}
          onChange={(v) => handleChange("life_expectancy", v)}
          min={60}
          max={120}
          step={1}
        />
        <AutoAdjustableField
          fieldKey="expected_return_rate"
          autoAdjustField={autoAdjustField}
          solvedDisplayValue={getSolvedDisplayValue()}
          isSolving={isSolving}
          onToggle={toggleAutoAdjust}
          hasGoal={!!goal}
          autoTooltip={t("earlyRetirement.form.autoAdjustTooltip")}
        >
          <NumberField
            label={t("earlyRetirement.form.expectedReturn")}
            value={form.expected_return_rate}
            onChange={(v) => handleChange("expected_return_rate", v)}
            min={-10}
            max={30}
            step={0.5}
            suffix="%"
            disabled={autoAdjustField === "expected_return_rate"}
          />
        </AutoAdjustableField>
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
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 p-4 rounded-lg bg-[var(--surface-light)]">
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
                className="flex items-center gap-1 mt-1 text-xs text-[var(--primary)] hover:text-blue-300 transition-colors"
              >
                <RefreshCw size={12} />
                {t("earlyRetirement.form.useScrapedKh", {
                  amount: new Intl.NumberFormat("he-IL", {
                    style: "currency",
                    currency: "ILS",
                    maximumFractionDigits: 0,
                  }).format(khScraped.balance),
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
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={form.bituach_leumi_eligible}
                onChange={(e) =>
                  handleChange(
                    "bituach_leumi_eligible",
                    e.target.checked,
                  )
                }
                className="w-4 h-4 rounded border-gray-600 text-blue-500 focus:ring-blue-500 bg-[var(--surface)]"
              />
              <span className="text-sm text-[var(--text-secondary)]">
                {t("earlyRetirement.form.bituachLeumiEligible")}
              </span>
            </label>
          </div>
          {form.bituach_leumi_eligible && (
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
            />
          )}
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

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={isBusy}
          className="flex items-center gap-2 px-6 py-2.5 bg-[var(--primary)] hover:bg-blue-600 text-white rounded-lg font-medium transition-colors disabled:opacity-50"
        >
          <Save size={16} />
          {isBusy
            ? t("common.loading")
            : t("earlyRetirement.form.calculate")}
        </button>
      </div>
    </form>
  );
}

function AutoAdjustableField({
  fieldKey,
  autoAdjustField,
  solvedDisplayValue,
  isSolving,
  onToggle,
  hasGoal,
  autoTooltip,
  children,
}: {
  fieldKey: Exclude<AutoAdjustField, null>;
  autoAdjustField: AutoAdjustField;
  solvedDisplayValue: string | null;
  isSolving: boolean;
  onToggle: (field: Exclude<AutoAdjustField, null>) => void;
  hasGoal: boolean;
  autoTooltip: string;
  children: React.ReactNode;
}) {
  const { t } = useTranslation();
  const isActive = autoAdjustField === fieldKey;

  return (
    <div className="relative">
      {children}
      <div className="flex items-center gap-2 mt-1">
        {hasGoal && (
          <button
            type="button"
            onClick={() => onToggle(fieldKey)}
            className={`flex items-center gap-1 text-xs transition-colors ${
              isActive
                ? "text-amber-400 font-medium"
                : "text-[var(--text-muted)] hover:text-[var(--primary)]"
            }`}
            title={autoTooltip}
          >
            <Wand2 size={12} />
            {t("earlyRetirement.form.autoAdjust")}
          </button>
        )}
        {isActive && (
          <span
            className="text-xs font-medium text-amber-400"
            dir="ltr"
          >
            {isSolving
              ? "..."
              : solvedDisplayValue
                ? `→ ${solvedDisplayValue}`
                : ""}
          </span>
        )}
      </div>
    </div>
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
      <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
        <span className="flex items-center gap-1">
          {label}
          {tooltip && (
            <span className="group relative">
              <Info
                size={13}
                className="text-[var(--text-muted)] cursor-help"
              />
              <span className="absolute z-10 hidden group-hover:block w-64 p-2 text-xs text-[var(--text-primary)] bg-[var(--surface)] border border-[var(--surface-light)] rounded-lg shadow-lg -top-2 start-6">
                {tooltip}
              </span>
            </span>
          )}
        </span>
      </label>
      <div className="relative">
        <input
          type="number"
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          min={min}
          max={max}
          step={step}
          disabled={disabled}
          className="w-full px-3 py-2 bg-[var(--surface)] border border-[var(--surface-light)] rounded-lg text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--primary)] disabled:opacity-50 disabled:cursor-not-allowed [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
          dir="ltr"
        />
        {suffix && (
          <span className="absolute inset-inline-end-3 top-1/2 -translate-y-1/2 text-sm text-[var(--text-muted)]">
            {suffix}
          </span>
        )}
      </div>
    </div>
  );
}
