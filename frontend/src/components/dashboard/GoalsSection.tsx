import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Target, Plus, Pencil, Trash2, Check } from "lucide-react";
import {
  savingsGoalsApi,
  type SavingsGoal,
  type SavingsGoalInput,
} from "../../services/api";
import { useDemoMode } from "../../context/DemoModeContext";
import { Modal } from "../common/Modal";
import { Skeleton } from "../common/Skeleton";
import { formatCurrency } from "../../utils/numberFormatting";

/** Dashboard savings-goals panel: progress tracking + CRUD via a modal editor. */
export function GoalsSection() {
  const { t } = useTranslation();
  const { isDemoMode } = useDemoMode();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<SavingsGoal | "new" | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["savings-goals", isDemoMode],
    queryFn: async () => {
      const res = await savingsGoalsApi.getAll();
      return res.data;
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => savingsGoalsApi.delete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["savings-goals"] }),
  });

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] p-4 md:p-6">
      <div className="flex items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-[var(--primary)]/15 text-[var(--primary)]">
            <Target size={16} />
          </div>
          <p className="text-sm md:text-base font-bold">{t("dashboard.goals.title")}</p>
        </div>
        <button
          onClick={() => setEditing("new")}
          className="flex items-center gap-1 text-xs md:text-sm font-medium text-[var(--primary)] hover:opacity-80 transition-opacity"
        >
          <Plus size={15} />
          {t("dashboard.goals.add")}
        </button>
      </div>

      {isLoading ? (
        <Skeleton variant="card" className="h-32" />
      ) : !data || data.length === 0 ? (
        <p className="text-[var(--text-muted)] text-sm py-6 text-center">{t("dashboard.goals.empty")}</p>
      ) : (
        <div className="space-y-3">
          {data.map((goal) => (
            <GoalRow
              key={goal.id}
              goal={goal}
              onEdit={() => setEditing(goal)}
              onDelete={() => {
                if (window.confirm(t("dashboard.goals.confirmDelete", { name: goal.name }))) {
                  deleteMutation.mutate(goal.id);
                }
              }}
            />
          ))}
        </div>
      )}

      {editing !== null && (
        <GoalEditorModal
          goal={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}

function GoalRow({
  goal,
  onEdit,
  onDelete,
}: {
  goal: SavingsGoal;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation();
  const barColor = goal.is_achieved
    ? "from-emerald-500 to-emerald-400"
    : "from-[var(--primary)] to-blue-400";

  return (
    <div className="group border border-[var(--surface-light)] rounded-xl p-3 hover:bg-[var(--surface-light)]/30 transition-colors">
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-1.5 min-w-0">
          {!!goal.is_achieved && <Check size={14} className="text-emerald-400 shrink-0" />}
          <p className="font-semibold text-sm truncate" dir="auto" title={goal.name}>{goal.name}</p>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <span dir="ltr" className="text-xs md:text-sm font-bold tabular-nums">
            {formatCurrency(goal.current_amount)}
            <span className="text-[var(--text-muted)] font-normal"> / {formatCurrency(goal.target_amount)}</span>
          </span>
          <button onClick={onEdit} aria-label={t("common.edit")} className="p-1.5 rounded-lg text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-light)] transition-colors">
            <Pencil size={14} />
          </button>
          <button onClick={onDelete} aria-label={t("common.delete")} className="p-1.5 rounded-lg text-[var(--text-muted)] hover:text-rose-400 hover:bg-[var(--surface-light)] transition-colors">
            <Trash2 size={14} />
          </button>
        </div>
      </div>
      <div className="w-full bg-[var(--surface-light)] rounded-full h-2 overflow-hidden">
        <div className={`h-2 rounded-full bg-gradient-to-r ${barColor} transition-all duration-500`} style={{ width: `${goal.progress_pct}%` }} />
      </div>
      <div className="flex justify-between items-center mt-1.5 text-[10px] md:text-xs text-[var(--text-muted)]">
        <span dir="ltr">{goal.progress_pct}%</span>
        {goal.is_achieved ? (
          <span className="text-emerald-400 font-medium">{t("dashboard.goals.achieved")}</span>
        ) : goal.monthly_needed != null && goal.months_remaining != null ? (
          <span>
            {t("dashboard.goals.monthlyNeeded", {
              amount: formatCurrency(goal.monthly_needed),
              count: goal.months_remaining,
            })}
          </span>
        ) : (
          <span>{t("dashboard.goals.remaining", { amount: formatCurrency(goal.remaining) })}</span>
        )}
      </div>
    </div>
  );
}

function GoalEditorModal({ goal, onClose }: { goal: SavingsGoal | null; onClose: () => void }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [name, setName] = useState(goal?.name ?? "");
  const [targetAmount, setTargetAmount] = useState(goal ? String(goal.target_amount) : "");
  const [currentAmount, setCurrentAmount] = useState(goal ? String(goal.current_amount) : "0");
  const [targetDate, setTargetDate] = useState(goal?.target_date ?? "");

  const save = useMutation({
    mutationFn: (payload: SavingsGoalInput) =>
      goal ? savingsGoalsApi.update(goal.id, payload) : savingsGoalsApi.create(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["savings-goals"] });
      onClose();
    },
  });

  const canSave = name.trim().length > 0 && Number(targetAmount) > 0;

  const handleSubmit = () => {
    if (!canSave) return;
    save.mutate({
      name: name.trim(),
      target_amount: Number(targetAmount),
      current_amount: Number(currentAmount) || 0,
      target_date: targetDate || null,
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
          <label className="block text-xs font-medium text-[var(--text-muted)] mb-1">{t("dashboard.goals.nameLabel")}</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t("dashboard.goals.namePlaceholder")}
            className="w-full bg-[var(--surface-light)] border border-[var(--surface-light)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[var(--primary)]"
            dir="auto"
          />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-[var(--text-muted)] mb-1">{t("dashboard.goals.targetLabel")}</label>
            <input
              type="number" inputMode="decimal" value={targetAmount}
              onChange={(e) => setTargetAmount(e.target.value)}
              className="w-full bg-[var(--surface-light)] border border-[var(--surface-light)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[var(--primary)]"
              dir="ltr"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-[var(--text-muted)] mb-1">{t("dashboard.goals.savedLabel")}</label>
            <input
              type="number" inputMode="decimal" value={currentAmount}
              onChange={(e) => setCurrentAmount(e.target.value)}
              className="w-full bg-[var(--surface-light)] border border-[var(--surface-light)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[var(--primary)]"
              dir="ltr"
            />
          </div>
        </div>
        <div>
          <label className="block text-xs font-medium text-[var(--text-muted)] mb-1">{t("dashboard.goals.dateLabel")}</label>
          <input
            type="date" value={targetDate ?? ""}
            onChange={(e) => setTargetDate(e.target.value)}
            className="w-full bg-[var(--surface-light)] border border-[var(--surface-light)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[var(--primary)]"
            dir="ltr"
          />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm font-medium text-[var(--text-muted)] hover:bg-[var(--surface-light)] transition-colors">
            {t("common.cancel")}
          </button>
          <button
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
