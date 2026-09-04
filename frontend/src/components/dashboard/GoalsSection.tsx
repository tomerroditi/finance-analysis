import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  Target,
  Plus,
  Pencil,
  Trash2,
  Check,
  ChevronUp,
  ChevronDown,
  History,
  Lock,
  RotateCcw,
} from "lucide-react";
import {
  savingsGoalsApi,
  type SavingsGoal,
  type SavingsGoalInput,
  type SavingsGoalRebuildChange,
} from "../../services/api";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { qkPrefix } from "../../services/queryKeys";
import { useConfirm } from "../../context/DialogContext";
import { Modal } from "../common/Modal";
import { Skeleton } from "../common/Skeleton";
import { formatCurrency } from "../../utils/numberFormatting";

/**
 * Dashboard savings-goals panel.
 *
 * Goals fill themselves from each month's surplus in priority order, so the
 * list is a waterfall: the top goal is funded first and spills what it cannot
 * take (its target, or its monthly cap) down to the next one. Reordering
 * applies to future months only — restating history is the explicit
 * "redistribute" action, which previews the diff before committing.
 */
export function GoalsSection() {
  const { t } = useTranslation();
  const qk = useQueryKeys();
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const [editing, setEditing] = useState<SavingsGoal | "new" | null>(null);
  const [redistributing, setRedistributing] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: qk.savingsGoals.all(),
    queryFn: async () => {
      const res = await savingsGoalsApi.getAll();
      return res.data;
    },
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: qkPrefix.savingsGoals });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => savingsGoalsApi.delete(id),
    onSuccess: invalidate,
  });

  const reorderMutation = useMutation({
    mutationFn: (goalIds: number[]) => savingsGoalsApi.reorder(goalIds),
    onSuccess: invalidate,
  });

  const goals = data ?? [];

  /** Swap a goal with its neighbour and persist the new waterfall order. */
  const move = (index: number, direction: -1 | 1) => {
    const next = index + direction;
    if (next < 0 || next >= goals.length) return;
    const ids = goals.map((g) => g.id);
    [ids[index], ids[next]] = [ids[next], ids[index]];
    reorderMutation.mutate(ids);
  };

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] p-4 md:p-6">
      <div className="flex items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-[var(--primary)]/15 text-[var(--primary)]">
            <Target size={16} />
          </div>
          <p className="text-sm md:text-base font-bold">{t("dashboard.goals.title")}</p>
        </div>
        <div className="flex items-center gap-3">
          {goals.length > 1 && (
            <button
              onClick={() => setRedistributing(true)}
              className="flex items-center gap-1 text-xs md:text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
              title={t("dashboard.goals.redistributeHint")}
            >
              <History size={14} />
              {t("dashboard.goals.redistribute")}
            </button>
          )}
          <button
            onClick={() => setEditing("new")}
            className="flex items-center gap-1 text-xs md:text-sm font-medium text-[var(--primary)] hover:opacity-80 transition-opacity"
          >
            <Plus size={15} />
            {t("dashboard.goals.add")}
          </button>
        </div>
      </div>

      {isLoading ? (
        <Skeleton variant="card" className="h-32" />
      ) : goals.length === 0 ? (
        <p className="text-[var(--text-muted)] text-sm py-6 text-center">{t("dashboard.goals.empty")}</p>
      ) : (
        <div className="space-y-3">
          {goals.map((goal, index) => (
            <GoalRow
              key={goal.id}
              goal={goal}
              rank={index + 1}
              canMoveUp={index > 0}
              canMoveDown={index < goals.length - 1}
              onMoveUp={() => move(index, -1)}
              onMoveDown={() => move(index, 1)}
              onEdit={() => setEditing(goal)}
              onDelete={async () => {
                const ok = await confirm({
                  title: t("common.deleteTitle"),
                  message: t("dashboard.goals.confirmDelete", { name: goal.name }),
                  confirmLabel: t("common.delete"),
                  isDestructive: true,
                });
                if (ok) deleteMutation.mutate(goal.id);
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

      {redistributing && (
        <RedistributeModal onClose={() => setRedistributing(false)} />
      )}
    </div>
  );
}

function GoalRow({
  goal,
  rank,
  canMoveUp,
  canMoveDown,
  onMoveUp,
  onMoveDown,
  onEdit,
  onDelete,
}: {
  goal: SavingsGoal;
  rank: number;
  canMoveUp: boolean;
  canMoveDown: boolean;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation();
  const barColor = goal.is_closed
    ? "from-[var(--text-muted)] to-[var(--text-muted)]"
    : goal.is_achieved
      ? "from-emerald-500 to-emerald-400"
      : "from-[var(--primary)] to-blue-400";

  return (
    <div className="group border border-[var(--surface-light)] rounded-xl p-3 hover:bg-[var(--surface-light)]/30 transition-colors">
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <span
            className="text-[10px] font-bold text-[var(--text-muted)] tabular-nums shrink-0"
            title={t("dashboard.goals.priorityHint")}
            dir="ltr"
          >
            #{rank}
          </span>
          {!!goal.is_closed && <Lock size={13} className="text-[var(--text-muted)] shrink-0" />}
          {!goal.is_closed && !!goal.is_achieved && (
            <Check size={14} className="text-emerald-400 shrink-0" />
          )}
          <p className="font-semibold text-sm truncate" dir="auto" title={goal.name}>{goal.name}</p>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <span dir="ltr" className="text-xs md:text-sm font-bold tabular-nums">
            {formatCurrency(goal.funded)}
            <span className="text-[var(--text-muted)] font-normal"> / {formatCurrency(goal.target_amount)}</span>
          </span>
          <button
            onClick={onMoveUp}
            disabled={!canMoveUp}
            aria-label={t("dashboard.goals.moveUp")}
            className="p-1 rounded-lg text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-light)] disabled:opacity-30 disabled:hover:bg-transparent transition-colors"
          >
            <ChevronUp size={14} />
          </button>
          <button
            onClick={onMoveDown}
            disabled={!canMoveDown}
            aria-label={t("dashboard.goals.moveDown")}
            className="p-1 rounded-lg text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-light)] disabled:opacity-30 disabled:hover:bg-transparent transition-colors"
          >
            <ChevronDown size={14} />
          </button>
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
      <div className="flex justify-between items-center gap-2 mt-1.5 text-[10px] md:text-xs text-[var(--text-muted)]">
        <span dir="ltr">{goal.progress_pct}%</span>
        <GoalStatusLine goal={goal} />
      </div>
      {(goal.this_month_allocation > 0 || goal.utilized > 0) && (
        <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1.5 text-[10px] md:text-xs text-[var(--text-muted)]">
          {goal.this_month_allocation > 0 && (
            <span>
              {t("dashboard.goals.thisMonth", {
                amount: formatCurrency(goal.this_month_allocation),
              })}
            </span>
          )}
          {goal.utilized > 0 && (
            <span>
              {t("dashboard.goals.utilized", {
                spent: formatCurrency(goal.utilized),
                available: formatCurrency(goal.available),
              })}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

/** The right-hand status line: closed, achieved, on-schedule, or plain remainder. */
function GoalStatusLine({ goal }: { goal: SavingsGoal }) {
  const { t } = useTranslation();

  if (goal.is_closed) {
    return <span className="font-medium">{t("dashboard.goals.closed")}</span>;
  }
  if (goal.is_achieved) {
    return <span className="text-emerald-400 font-medium">{t("dashboard.goals.achieved")}</span>;
  }
  if (goal.monthly_needed != null && goal.months_remaining != null) {
    return (
      <span>
        {t("dashboard.goals.monthlyNeeded", {
          amount: formatCurrency(goal.monthly_needed),
          count: goal.months_remaining,
        })}
      </span>
    );
  }
  return <span>{t("dashboard.goals.remaining", { amount: formatCurrency(goal.remaining) })}</span>;
}

/**
 * Preview-then-commit for restating allocation history.
 *
 * A dry run is fetched first so the user sees exactly which goal gains and
 * which loses before anything is written. Closed goals never appear — their
 * allocations are frozen and cannot be reclaimed.
 */
function RedistributeModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [changes, setChanges] = useState<SavingsGoalRebuildChange[] | null>(null);

  // The preview is a POST that changes nothing, but it must NOT be a query:
  // its key would sit under the `savings-goals` prefix, so every goal mutation
  // would re-trigger it (three round-trips per modal open, measured), and the
  // IndexedDB persister would cache a read-only POST — the exact anti-pattern
  // `.claude/rules/frontend_pwa.md` warns about. As a mutation it runs once,
  // on open, and leaves no cache entry to invalidate or exclude.
  const preview = useMutation({
    mutationFn: () => savingsGoalsApi.rebuild(null, true),
    onSuccess: (res) => setChanges(res.data.changes),
  });
  const { mutate: loadPreview } = preview;

  useEffect(() => {
    loadPreview();
  }, [loadPreview]);

  const commit = useMutation({
    mutationFn: () => savingsGoalsApi.rebuild(null, false),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.savingsGoals });
      onClose();
    },
  });

  const moved = (changes ?? []).filter((c) => c.delta !== 0);

  return (
    <Modal
      isOpen
      onClose={onClose}
      title={t("dashboard.goals.redistributeTitle")}
      titleIcon={<RotateCcw size={18} />}
      maxWidth="md"
    >
      <div className="space-y-4 p-4 md:p-6">
        <p className="text-xs text-[var(--text-muted)]">
          {t("dashboard.goals.redistributeExplainer")}
        </p>

        {preview.isPending ? (
          <Skeleton variant="card" className="h-24" />
        ) : moved.length === 0 ? (
          <p className="text-sm text-[var(--text-muted)] py-4 text-center">
            {t("dashboard.goals.redistributeNoChange")}
          </p>
        ) : (
          <div className="space-y-2">
            {moved.map((change) => (
              <div
                key={change.goal_id}
                className="flex items-center justify-between gap-2 text-sm border border-[var(--surface-light)] rounded-lg px-3 py-2"
              >
                <span className="truncate" dir="auto">{change.name}</span>
                <span dir="ltr" className="tabular-nums shrink-0">
                  <span className="text-[var(--text-muted)]">{formatCurrency(change.before)}</span>
                  {" → "}
                  <span className="font-semibold">{formatCurrency(change.after)}</span>
                  <span className={change.delta > 0 ? "text-emerald-400 ms-2" : "text-rose-400 ms-2"}>
                    {change.delta > 0 ? "+" : ""}
                    {formatCurrency(change.delta)}
                  </span>
                </span>
              </div>
            ))}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm font-medium text-[var(--text-muted)] hover:bg-[var(--surface-light)] transition-colors">
            {t("common.cancel")}
          </button>
          <button
            onClick={() => commit.mutate()}
            disabled={moved.length === 0 || commit.isPending}
            className="px-4 py-2 rounded-lg text-sm font-bold bg-[var(--primary)] text-white disabled:opacity-50 hover:opacity-90 transition-opacity"
          >
            {t("dashboard.goals.redistributeConfirm")}
          </button>
        </div>
      </div>
    </Modal>
  );
}

function GoalEditorModal({ goal, onClose }: { goal: SavingsGoal | null; onClose: () => void }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [name, setName] = useState(goal?.name ?? "");
  const [targetAmount, setTargetAmount] = useState(goal ? String(goal.target_amount) : "");
  const [openingBalance, setOpeningBalance] = useState(goal ? String(goal.opening_balance) : "0");
  const [monthlyCap, setMonthlyCap] = useState(goal?.monthly_cap != null ? String(goal.monthly_cap) : "");
  const [startMonth, setStartMonth] = useState(goal?.start_month ?? "");
  const [targetDate, setTargetDate] = useState(goal?.target_date ?? "");

  const save = useMutation({
    mutationFn: (payload: SavingsGoalInput) =>
      goal ? savingsGoalsApi.update(goal.id, payload) : savingsGoalsApi.create(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.savingsGoals });
      onClose();
    },
  });

  const canSave = name.trim().length > 0 && Number(targetAmount) > 0;

  const handleSubmit = () => {
    if (!canSave) return;
    save.mutate({
      name: name.trim(),
      target_amount: Number(targetAmount),
      opening_balance: Number(openingBalance) || 0,
      // An empty cap field means uncapped, so the goal can fill in one month.
      monthly_cap: monthlyCap.trim() === "" ? null : Number(monthlyCap),
      start_month: startMonth || null,
      target_date: targetDate || null,
    });
  };

  const field =
    "w-full bg-[var(--surface-light)] border border-[var(--surface-light)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[var(--primary)]";
  const label = "block text-xs font-medium text-[var(--text-muted)] mb-1";

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
          <label className={label} htmlFor="goal-name">{t("dashboard.goals.nameLabel")}</label>
          <input
            id="goal-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t("dashboard.goals.namePlaceholder")}
            className={field}
            dir="auto"
          />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className={label} htmlFor="goal-target">{t("dashboard.goals.targetLabel")}</label>
            <input
              id="goal-target"
              type="number" inputMode="decimal" value={targetAmount}
              onChange={(e) => setTargetAmount(e.target.value)}
              className={field}
              dir="ltr"
            />
          </div>
          <div>
            <label className={label} htmlFor="goal-opening">{t("dashboard.goals.openingLabel")}</label>
            <input
              id="goal-opening"
              type="number" inputMode="decimal" value={openingBalance}
              onChange={(e) => setOpeningBalance(e.target.value)}
              className={field}
              dir="ltr"
            />
            <p className="text-[10px] text-[var(--text-muted)] mt-1">
              {t("dashboard.goals.openingHint")}
            </p>
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className={label} htmlFor="goal-cap">{t("dashboard.goals.capLabel")}</label>
            <input
              id="goal-cap"
              type="number" inputMode="decimal" value={monthlyCap}
              onChange={(e) => setMonthlyCap(e.target.value)}
              placeholder={t("dashboard.goals.capPlaceholder")}
              className={field}
              dir="ltr"
            />
            <p className="text-[10px] text-[var(--text-muted)] mt-1">
              {t("dashboard.goals.capHint")}
            </p>
          </div>
          <div>
            <label className={label} htmlFor="goal-start">{t("dashboard.goals.startMonthLabel")}</label>
            <input
              id="goal-start"
              type="month" value={startMonth ?? ""}
              onChange={(e) => setStartMonth(e.target.value)}
              className={field}
              dir="ltr"
            />
            <p className="text-[10px] text-[var(--text-muted)] mt-1">
              {t("dashboard.goals.startMonthHint")}
            </p>
          </div>
        </div>
        <div>
          <label className={label} htmlFor="goal-date">{t("dashboard.goals.dateLabel")}</label>
          <input
            id="goal-date"
            type="date" value={targetDate ?? ""}
            onChange={(e) => setTargetDate(e.target.value)}
            className={field}
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
