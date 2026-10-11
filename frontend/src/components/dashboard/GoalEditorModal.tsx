import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Target } from "lucide-react";
import {
  savingsGoalsApi,
  type SavingsGoal,
  type SavingsGoalInput,
} from "../../services/api";
import { qkPrefix } from "../../services/queryKeys";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { Modal } from "../common/Modal";
import { GoalAutoLinkField } from "./GoalAutoLinkField";
import { joinRuleTags, splitRuleTags } from "../../utils/goalRuleTags";

const FIELD =
  "w-full bg-[var(--surface-light)] border border-[var(--surface-light)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[var(--primary)]";
const LABEL = "block text-xs font-medium text-[var(--text-muted)] mb-1";

/**
 * Create or edit a savings goal.
 *
 * Nothing here moves money except the starting amount, which only a new goal
 * offers: it becomes the goal's first entry, and later changes go through the
 * row's "Add money" / "Take out" so each one is a visible, undoable entry.
 * The monthly amount is a suggestion the card offers to fund, never a
 * standing order.
 */
export function GoalEditorModal({
  goal,
  onClose,
}: {
  goal: SavingsGoal | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const qk = useQueryKeys();
  const queryClient = useQueryClient();
  const [name, setName] = useState(goal?.name ?? "");
  const [targetAmount, setTargetAmount] = useState(goal ? String(goal.target_amount) : "");
  const [initialAmount, setInitialAmount] = useState("");
  const [monthlyAmount, setMonthlyAmount] = useState(
    goal?.monthly_amount != null ? String(goal.monthly_amount) : "",
  );
  const [startMonth, setStartMonth] = useState(goal?.start_month ?? "");
  const [targetDate, setTargetDate] = useState(goal?.target_date ?? "");
  const [spendRule, setSpendRule] = useState({
    category: goal?.utilization_category ?? "",
    tags: splitRuleTags(goal?.utilization_tags),
  });
  const [saveRule, setSaveRule] = useState({
    category: goal?.contribution_category ?? "",
    tags: splitRuleTags(goal?.contribution_tags),
  });

  const save = useMutation({
    mutationFn: async (payload: SavingsGoalInput) =>
      goal
        ? await savingsGoalsApi.update(goal.id, payload)
        : await savingsGoalsApi.create(payload),
    onSuccess: (res) => {
      queryClient.setQueryData(qk.savingsGoals.all(), res.data);
      queryClient.invalidateQueries({ queryKey: qkPrefix.savingsGoals });
      onClose();
    },
  });

  const initial = Number(initialAmount) || 0;
  const monthly = monthlyAmount.trim() === "" ? null : Number(monthlyAmount);
  const canSave =
    name.trim().length > 0 &&
    Number(targetAmount) > 0 &&
    initial >= 0 &&
    (monthly === null || monthly >= 0);

  const handleSubmit = () => {
    if (!canSave) return;
    save.mutate({
      name: name.trim(),
      target_amount: Number(targetAmount),
      monthly_amount: monthly || null,
      start_month: startMonth || null,
      target_date: targetDate || null,
      utilization_category: spendRule.category || null,
      utilization_tags: joinRuleTags(spendRule.category ? spendRule.tags : null),
      contribution_category: saveRule.category || null,
      contribution_tags: joinRuleTags(saveRule.category ? saveRule.tags : null),
      ...(goal || initial <= 0 ? {} : { initial_amount: initial }),
    });
  };

  return (
    <Modal
      isOpen
      onClose={onClose}
      title={goal ? t("dashboard.goals.editTitle") : t("dashboard.goals.addTitle")}
      titleIcon={<Target size={18} />}
      maxWidth="md"
    >
      <div className="space-y-4 p-4 md:p-6">
        <div>
          <label className={LABEL} htmlFor="goal-name">{t("dashboard.goals.nameLabel")}</label>
          <input
            id="goal-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t("dashboard.goals.namePlaceholder")}
            className={FIELD}
            dir="auto"
          />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className={LABEL} htmlFor="goal-target">{t("dashboard.goals.targetLabel")}</label>
            <input
              id="goal-target"
              type="number"
              inputMode="decimal"
              min={0}
              value={targetAmount}
              onChange={(e) => setTargetAmount(e.target.value)}
              className={FIELD}
              dir="ltr"
            />
          </div>
          <div>
            <label className={LABEL} htmlFor="goal-monthly">{t("dashboard.goals.monthlyLabel")}</label>
            <input
              id="goal-monthly"
              type="number"
              inputMode="decimal"
              min={0}
              value={monthlyAmount}
              onChange={(e) => setMonthlyAmount(e.target.value)}
              placeholder={t("dashboard.goals.monthlyPlaceholder")}
              className={FIELD}
              dir="ltr"
            />
            <p className="text-[10px] text-[var(--text-muted)] mt-1">
              {t("dashboard.goals.monthlyHint")}
            </p>
          </div>
        </div>
        {!goal && (
          <div>
            <label className={LABEL} htmlFor="goal-initial">{t("dashboard.goals.initialLabel")}</label>
            <input
              id="goal-initial"
              type="number"
              inputMode="decimal"
              min={0}
              value={initialAmount}
              onChange={(e) => setInitialAmount(e.target.value)}
              placeholder="0"
              className={FIELD}
              dir="ltr"
            />
            <p className="text-[10px] text-[var(--text-muted)] mt-1">
              {t("dashboard.goals.initialHint")}
            </p>
          </div>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className={LABEL} htmlFor="goal-start">{t("dashboard.goals.startMonthLabel")}</label>
            <input
              id="goal-start"
              // The same calendar as the target date. Goals count whole
              // months, so whichever day is picked, the goal starts with the
              // month it falls in — shown back as that month's first day.
              type="date"
              value={startMonth ? `${startMonth.slice(0, 7)}-01` : ""}
              onChange={(e) => setStartMonth(e.target.value.slice(0, 7))}
              className={FIELD}
              dir="ltr"
            />
            <p className="text-[10px] text-[var(--text-muted)] mt-1">
              {t("dashboard.goals.startMonthHint")}
            </p>
          </div>
          <div>
            <label className={LABEL} htmlFor="goal-date">{t("dashboard.goals.dateLabel")}</label>
            <input
              id="goal-date"
              type="date"
              value={targetDate ?? ""}
              onChange={(e) => setTargetDate(e.target.value)}
              className={FIELD}
              dir="ltr"
            />
          </div>
        </div>
        <fieldset className="space-y-3 border-t border-[var(--surface-light)] pt-3">
          <legend className="text-xs font-semibold text-[var(--text-muted)] pe-2">
            {t("dashboard.goals.autoLinkTitle")}
          </legend>
          <GoalAutoLinkField
            testId="goal-auto-link-spend"
            label={t("dashboard.goals.autoLinkSpendLabel")}
            hint={t("dashboard.goals.autoLinkSpendHint")}
            category={spendRule.category}
            tags={spendRule.tags}
            onChange={(category, tags) => setSpendRule({ category, tags })}
          />
          <GoalAutoLinkField
            testId="goal-auto-link-save"
            label={t("dashboard.goals.autoLinkSaveLabel")}
            hint={t("dashboard.goals.autoLinkSaveHint")}
            category={saveRule.category}
            tags={saveRule.tags}
            onChange={(category, tags) => setSaveRule({ category, tags })}
          />
        </fieldset>
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm font-medium text-[var(--text-muted)] hover:bg-[var(--surface-light)] transition-colors"
          >
            {t("common.cancel")}
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!canSave || save.isPending}
            className="px-4 py-2 rounded-lg text-sm font-bold bg-[var(--primary)] text-white disabled:opacity-50 hover:opacity-90 transition-opacity"
          >
            {t("common.save")}
          </button>
        </div>
      </div>
    </Modal>
  );
}
