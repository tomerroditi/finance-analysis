import { useState } from "react";
import {
  useQuery,
  useMutation,
  useQueryClient,
  useIsMutating,
} from "@tanstack/react-query";
import type { AxiosResponse } from "axios";
import { useTranslation } from "react-i18next";
import {
  Target,
  Plus,
  Minus,
  Pencil,
  Trash2,
  Check,
  X,
  ChevronUp,
  ChevronDown,
  Lock,
  LockOpen,
  Wallet,
  Undo2,
  HandCoins,
} from "lucide-react";
import {
  savingsGoalsApi,
  type SavingsGoal,
  type SavingsGoalEntry,
  type SavingsGoalFreeCash,
} from "../../services/api";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { useScrollCap } from "../../hooks/useScrollCap";
import { usePendingRows } from "../../hooks/usePendingRows";
import { qkPrefix } from "../../services/queryKeys";
import { useConfirm, useNotify } from "../../context/DialogContext";
import { Skeleton } from "../common/Skeleton";
import { YearlySavingsSection } from "./YearlySavingsSection";
import { GoalsHistoryPanel } from "./GoalsHistoryPanel";
import { GoalEditorModal } from "./GoalEditorModal";
import { formatChange, formatCurrency } from "../../utils/numberFormatting";
import { formatDate } from "../../utils/dateFormatting";

/** How tall the goal list may stand before it scrolls in place (26rem, px). */
const LIST_CAP_PX = 416;

/** A goal row, roughly — the least overflow worth capping for (see the hook). */
const LIST_CAP_SLACK_PX = 120;

/** How many entries a goal lists before "show all". */
const ENTRIES_SHOWN = 5;

/**
 * Every reorder shares this key and scope. The scope makes the server calls
 * run one after another, so rapid clicks cannot land out of order; the key
 * lets the card hold its list query while any reorder is still in flight.
 */
const REORDER_KEY = ["savings-goals", "reorder"] as const;

/** Whether an amount survives rounding to whole shekels — "0 ₪" is noise. */
function showsShekels(amount: number): boolean {
  return amount >= 0.5;
}

/**
 * Dashboard savings-goals panel.
 *
 * A goal holds what the user puts into it: "Add money" and "Take out" write
 * dated entries, each listed under the goal and undoable. Spending linked to a
 * goal draws it down and income matching its saved-into rule fills it, on
 * their own. A goal with a monthly amount offers to fund it ("Fund ₪X"), and
 * "Fund all" funds every suggestion in priority order.
 *
 * Under the goals sits free cash: bank and cash less what the goals hold. It
 * goes negative when more is set aside than there is, and "Cover it" then
 * offers a plan that takes money back from the lowest-priority goals first —
 * nothing moves until the user confirms it.
 */
export function GoalsSection() {
  const { t } = useTranslation();
  const qk = useQueryKeys();
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const notify = useNotify();
  const [editing, setEditing] = useState<SavingsGoal | "new" | null>(null);

  const reordering = useIsMutating({ mutationKey: REORDER_KEY }) > 0;

  const { data, isLoading } = useQuery({
    queryKey: qk.savingsGoals.all(),
    queryFn: async () => (await savingsGoalsApi.getAll()).data,
    // Held while reorders are queued: a refetch in between answers with an
    // order the user has already moved past and snaps the rows back. A
    // disabled query keeps its data and refetches once re-enabled.
    enabled: !reordering,
  });

  const { data: pool } = useQuery({
    queryKey: qk.savingsGoals.freeCash(),
    queryFn: async () => (await savingsGoalsApi.getFreeCash()).data,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: qkPrefix.savingsGoals });

  /** Every goal write answers with the whole list; show it, then refresh the rest. */
  const applyGoals = (res: AxiosResponse<SavingsGoal[]>) => {
    if (Array.isArray(res.data)) {
      queryClient.setQueryData(qk.savingsGoals.all(), res.data);
    }
    return invalidate();
  };
  const failed = () => notify.error(t("dashboard.goals.writeFailed"));

  // One mutation serves every row, so each row is gated on its own write.
  const pending = usePendingRows<string>();

  const deleteMutation = useMutation({
    mutationFn: (id: number) => savingsGoalsApi.delete(id),
    onSuccess: invalidate,
    onError: failed,
  });

  const entryMutation = useMutation({
    mutationFn: ({ goalId, amount, note }: { goalId: number; amount: number; note: string | null }) =>
      savingsGoalsApi.addEntry(goalId, amount, note),
    onMutate: ({ goalId }) => pending.begin(`goal:${goalId}`),
    onSettled: (_data, _error, { goalId }) => pending.end(`goal:${goalId}`),
    onSuccess: applyGoals,
    onError: failed,
  });

  const undoMutation = useMutation({
    mutationFn: (entryId: number) => savingsGoalsApi.deleteEntry(entryId),
    onMutate: (entryId) => pending.begin(`entry:${entryId}`),
    onSettled: (_data, _error, entryId) => pending.end(`entry:${entryId}`),
    onSuccess: applyGoals,
    onError: failed,
  });

  const fundOneMutation = useMutation({
    mutationFn: (goalId: number) => savingsGoalsApi.fund([goalId]),
    onMutate: (goalId) => pending.begin(`goal:${goalId}`),
    onSettled: (_data, _error, goalId) => pending.end(`goal:${goalId}`),
    onSuccess: applyGoals,
    onError: failed,
  });

  const fundAllMutation = useMutation({
    mutationFn: () => savingsGoalsApi.fund(null),
    onSuccess: applyGoals,
    onError: failed,
  });

  const closeMutation = useMutation({
    mutationFn: ({ goalId, close }: { goalId: number; close: boolean }) =>
      close ? savingsGoalsApi.close(goalId) : savingsGoalsApi.reopen(goalId),
    onMutate: ({ goalId }) => pending.begin(`goal:${goalId}`),
    onSettled: (_data, _error, { goalId }) => pending.end(`goal:${goalId}`),
    onSuccess: applyGoals,
    onError: failed,
  });

  const coverMutation = useMutation({
    mutationFn: () => savingsGoalsApi.cover(),
    onSuccess: applyGoals,
    onError: failed,
  });

  const reorderMutation = useMutation({
    mutationKey: REORDER_KEY,
    scope: { id: REORDER_KEY.join(":") },
    mutationFn: (goalIds: number[]) => savingsGoalsApi.reorder(goalIds),
    // Runs at click time even while an earlier reorder is still queued, so
    // the rows move immediately and each click builds on the last one.
    onMutate: async (goalIds: number[]) => {
      const key = qk.savingsGoals.all();
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<SavingsGoal[]>(key);
      if (previous) {
        const byId = new Map(previous.map((g) => [g.id, g]));
        queryClient.setQueryData<SavingsGoal[]>(
          key,
          goalIds.flatMap((id, priority) => {
            const goal = byId.get(id);
            return goal ? [{ ...goal, priority }] : [];
          }),
        );
      }
      return { previous };
    },
    // Only the last reorder in the queue may write: an earlier one's answer
    // is for an order the user has already moved past.
    onSuccess: (res) => {
      if (queryClient.isMutating({ mutationKey: REORDER_KEY }) <= 1) {
        queryClient.setQueryData(qk.savingsGoals.all(), res.data);
      }
    },
    onError: (_err, _ids, context) => {
      if (context?.previous && queryClient.isMutating({ mutationKey: REORDER_KEY }) <= 1) {
        queryClient.setQueryData(qk.savingsGoals.all(), context.previous);
      }
    },
    onSettled: () => invalidate(),
  });

  const goals = data ?? [];
  const canFundAll = goals.some(
    (goal) => !goal.is_closed && showsShekels(goal.suggested_this_month),
  );

  // Measured rather than counted: rows differ in height (an open entry form or
  // entry list runs far taller than a plain row). `data`, not `goals`: the
  // query's array is stable between renders, the `?? []` fallback is not.
  const [listRef, capped] = useScrollCap(LIST_CAP_PX, data, LIST_CAP_SLACK_PX);

  /** Swap a goal with its neighbour and persist the new order. */
  const move = (index: number, direction: -1 | 1) => {
    const next = index + direction;
    if (next < 0 || next >= goals.length) return;
    const ids = goals.map((g) => g.id);
    [ids[index], ids[next]] = [ids[next], ids[index]];
    reorderMutation.mutate(ids);
  };

  const cover = async (plan: SavingsGoalFreeCash) => {
    const steps = plan.cover_plan
      .map((step) =>
        t("dashboard.goals.coverStep", { name: step.name, amount: formatCurrency(step.amount) }),
      )
      .join("\n");
    const ok = await confirm({
      title: t("dashboard.goals.coverTitle"),
      message: `${t("dashboard.goals.coverConfirm", { amount: formatCurrency(plan.shortfall) })}\n\n${steps}`,
      confirmLabel: t("dashboard.goals.coverIt"),
    });
    if (ok) coverMutation.mutate();
  };

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] p-4 md:p-6">
      <div className="flex items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-2 min-w-0">
          <div className="p-1.5 rounded-lg bg-[var(--primary)]/15 text-[var(--primary)]">
            <Target size={16} />
          </div>
          <p className="text-sm md:text-base font-bold truncate">{t("dashboard.goals.title")}</p>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {canFundAll && (
            <button
              type="button"
              onClick={() => fundAllMutation.mutate()}
              disabled={fundAllMutation.isPending}
              title={t("dashboard.goals.fundAllHint")}
              className="flex items-center gap-1 text-xs md:text-sm font-medium text-emerald-400 hover:opacity-80 disabled:opacity-50 transition-opacity"
            >
              <HandCoins size={15} />
              {t("dashboard.goals.fundAll")}
            </button>
          )}
          <button
            type="button"
            onClick={() => setEditing("new")}
            className="flex items-center gap-1 text-xs md:text-sm font-medium text-[var(--primary)] hover:opacity-80 transition-opacity"
          >
            <Plus size={15} />
            {t("dashboard.goals.add")}
          </button>
        </div>
      </div>

      <YearlySavingsSection />

      {isLoading ? (
        <Skeleton variant="card" className="h-32" />
      ) : goals.length === 0 ? (
        <p className="text-[var(--text-muted)] text-sm py-6 text-center">{t("dashboard.goals.empty")}</p>
      ) : (
        /* The list scrolls in place past a few goals, so a dozen of them do
           not carry free cash and the history panel off the screen — but only
           once a cap would hide something worth scrolling to; until then it is
           a plain block, so a drag across it scrolls the page. */
        <div
          ref={listRef}
          className={`space-y-3 ${capped ? "max-h-[26rem] overflow-y-auto pe-1" : ""}`}
          data-testid="goals-list"
        >
          {goals.map((goal, index) => (
            <GoalRow
              key={goal.id}
              goal={goal}
              rank={index + 1}
              busy={pending.isPending(`goal:${goal.id}`)}
              isUndoing={(entryId) => pending.isPending(`entry:${entryId}`)}
              canMoveUp={index > 0}
              canMoveDown={index < goals.length - 1}
              onMoveUp={() => move(index, -1)}
              onMoveDown={() => move(index, 1)}
              onEdit={() => setEditing(goal)}
              onEntry={(amount, note, done) =>
                entryMutation.mutate({ goalId: goal.id, amount, note }, { onSuccess: done })
              }
              onUndo={(entryId) => undoMutation.mutate(entryId)}
              onFund={() => fundOneMutation.mutate(goal.id)}
              onToggleClosed={async () => {
                if (goal.is_closed) {
                  closeMutation.mutate({ goalId: goal.id, close: false });
                  return;
                }
                const ok = await confirm({
                  title: t("dashboard.goals.closeTitle"),
                  message: t("dashboard.goals.confirmClose", {
                    name: goal.name,
                    amount: formatCurrency(goal.available),
                  }),
                  confirmLabel: t("dashboard.goals.close"),
                });
                if (ok) closeMutation.mutate({ goalId: goal.id, close: true });
              }}
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

      {!!pool?.has_goals && (
        <FreeCashRow
          pool={pool}
          covering={coverMutation.isPending}
          onCover={() => cover(pool)}
        />
      )}

      {goals.length > 0 && <GoalsHistoryPanel />}

      {editing !== null && (
        <GoalEditorModal
          goal={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}

/**
 * Bank and cash less what the goals hold — the money nothing is set aside for.
 *
 * Below zero it says so in red: more has been set aside than there is, and
 * "Cover it" offers to take the difference back from the lowest-priority
 * goals first.
 */
function FreeCashRow({
  pool,
  covering,
  onCover,
}: {
  pool: SavingsGoalFreeCash;
  covering: boolean;
  onCover: () => void;
}) {
  const { t } = useTranslation();
  const short = showsShekels(pool.shortfall);

  return (
    <div
      className={`mt-3 border border-dashed rounded-xl p-3 ${short ? "border-red-400/50" : "border-[var(--surface-light)]"}`}
      data-testid="goals-free-cash"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className="p-1.5 rounded-lg bg-[var(--surface-light)] text-[var(--text-muted)]">
            <Wallet size={14} />
          </div>
          <div className="min-w-0">
            <p className="text-xs md:text-sm font-medium truncate">
              {t("dashboard.goals.freeCash")}
            </p>
            <p className="text-[10px] md:text-xs text-[var(--text-muted)]">
              {t("dashboard.goals.freeCashHint", {
                liquid: formatCurrency(pool.liquid),
                earmarked: formatCurrency(pool.earmarked),
              })}
            </p>
          </div>
        </div>
        <span
          className={`text-sm md:text-base font-bold shrink-0 ${pool.free_cash < -0.5 ? "text-red-400" : ""}`}
          data-testid="goals-free-cash-amount"
        >
          {formatCurrency(pool.free_cash)}
        </span>
      </div>
      {short && (
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <p className="text-[10px] md:text-xs text-red-400">
            {t("dashboard.goals.shortfall", { amount: formatCurrency(pool.shortfall) })}
          </p>
          {pool.cover_plan.length > 0 && (
            <button
              type="button"
              onClick={onCover}
              disabled={covering}
              className="px-2.5 py-1 rounded-lg text-xs font-bold bg-red-500/15 text-red-400 hover:bg-red-500/25 disabled:opacity-50 transition-colors"
            >
              {t("dashboard.goals.coverIt")}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

const ICON_BUTTON =
  "p-1.5 rounded-lg text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-light)] disabled:opacity-30 disabled:hover:bg-transparent transition-colors";
const CHIP =
  "flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] md:text-xs font-medium bg-[var(--surface-light)] hover:bg-[var(--primary)]/20 disabled:opacity-40 disabled:hover:bg-[var(--surface-light)] transition-colors";

function GoalRow({
  goal,
  rank,
  busy,
  isUndoing,
  canMoveUp,
  canMoveDown,
  onMoveUp,
  onMoveDown,
  onEdit,
  onEntry,
  onUndo,
  onFund,
  onToggleClosed,
  onDelete,
}: {
  goal: SavingsGoal;
  rank: number;
  /** A write on this goal is in flight. */
  busy: boolean;
  isUndoing: (entryId: number) => boolean;
  canMoveUp: boolean;
  canMoveDown: boolean;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onEdit: () => void;
  /** Signed amount; `done` runs once the entry is saved. */
  onEntry: (amount: number, note: string | null, done: () => void) => void;
  onUndo: (entryId: number) => void;
  onFund: () => void;
  onToggleClosed: () => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation();
  const [form, setForm] = useState<"add" | "take" | null>(null);
  const [showEntries, setShowEntries] = useState(false);
  const closed = !!goal.is_closed;
  const barColor = closed
    ? "from-[var(--text-muted)] to-[var(--text-muted)]"
    : goal.is_achieved
      ? "from-emerald-500 to-emerald-400"
      : "from-[var(--primary)] to-blue-400";
  const canTakeOut = showsShekels(goal.available);
  // Once a goal pays for something, the headline is what it gathered and
  // the bar splits into what is spent and what is left of it.
  const hasSpent = showsShekels(goal.spent);
  const toPercent = (amount: number) =>
    goal.target_amount > 0 ? Math.min(100, Math.max(0, (amount / goal.target_amount) * 100)) : 0;
  const filledPct = Math.min(100, Math.max(0, goal.progress_pct));
  const spentPct = hasSpent ? Math.min(filledPct, toPercent(Math.min(goal.spent, goal.saved))) : 0;

  return (
    <div className="group border border-[var(--surface-light)] rounded-xl p-3 hover:bg-[var(--surface-light)]/30 transition-colors">
      {/* The name owns its own line: sharing one with the figures and the
          action buttons left it about eight characters wide on a phone. */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-1.5 min-w-0 flex-1">
          <span
            className="text-[10px] font-bold text-[var(--text-muted)] tabular-nums shrink-0"
            title={t("dashboard.goals.priorityHint")}
            dir="ltr"
          >
            #{rank}
          </span>
          {closed && <Lock size={13} className="text-[var(--text-muted)] shrink-0" />}
          {!closed && !!goal.is_achieved && (
            <Check size={14} className="text-emerald-400 shrink-0" />
          )}
          <p className="font-semibold text-sm truncate" dir="auto" title={goal.name}>{goal.name}</p>
        </div>
        <div className="flex items-center gap-0.5 shrink-0">
          <button
            type="button"
            onClick={onMoveUp}
            disabled={!canMoveUp}
            aria-label={t("dashboard.goals.moveUp")}
            className={ICON_BUTTON}
          >
            <ChevronUp size={14} />
          </button>
          <button
            type="button"
            onClick={onMoveDown}
            disabled={!canMoveDown}
            aria-label={t("dashboard.goals.moveDown")}
            className={ICON_BUTTON}
          >
            <ChevronDown size={14} />
          </button>
          <button type="button" onClick={onEdit} aria-label={t("common.edit")} className={ICON_BUTTON}>
            <Pencil size={14} />
          </button>
          <button
            type="button"
            onClick={onToggleClosed}
            disabled={busy}
            aria-label={t(closed ? "dashboard.goals.reopen" : "dashboard.goals.close")}
            title={t(closed ? "dashboard.goals.reopen" : "dashboard.goals.close")}
            className={ICON_BUTTON}
          >
            {closed ? <LockOpen size={14} /> : <Lock size={14} />}
          </button>
          <button
            type="button"
            onClick={onDelete}
            aria-label={t("common.delete")}
            className={`${ICON_BUTTON} hover:text-rose-400`}
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      <div data-testid="goal-figures">
        <div className="flex items-baseline justify-between gap-2 mb-1.5">
          <span dir="ltr" className="text-sm md:text-base font-bold tabular-nums" data-testid="goal-balance">
            {formatCurrency(hasSpent ? goal.saved : goal.available)}
            <span className="text-[var(--text-muted)] text-xs md:text-sm font-normal">
              {" / "}
              {formatCurrency(goal.target_amount)}
            </span>
            {hasSpent && (
              <span
                className="text-[var(--text-muted)] text-[10px] md:text-xs font-normal"
                data-testid="goal-left-to-spend"
              >
                {" · "}
                {t("dashboard.goals.leftToSpend", { amount: formatCurrency(goal.available) })}
              </span>
            )}
          </span>
          <span dir="ltr" className="text-[10px] md:text-xs text-[var(--text-muted)] tabular-nums shrink-0">
            {goal.progress_pct}%
          </span>
        </div>
        <div className="flex w-full bg-[var(--surface-light)] rounded-full h-2 overflow-hidden">
          {spentPct > 0 && (
            <div
              className="h-2 bg-slate-400 transition-all duration-500"
              style={{ width: `${spentPct}%` }}
              data-testid="goal-bar-spent"
            />
          )}
          <div
            className={`h-2 bg-gradient-to-r ${barColor} transition-all duration-500 ${spentPct > 0 ? "" : "rounded-full"}`}
            style={{ width: `${filledPct - spentPct}%` }}
          />
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1.5 text-[10px] md:text-xs text-[var(--text-muted)]">
          <GoalStatusLine goal={goal} />
        </div>
        {(showsShekels(goal.added_this_month) ||
          showsShekels(goal.spent) ||
          showsShekels(goal.owed)) && (
          <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1.5 text-[10px] md:text-xs text-[var(--text-muted)]">
            {showsShekels(goal.added_this_month) && (
              <span>
                {t("dashboard.goals.addedThisMonth", {
                  amount: formatCurrency(goal.added_this_month),
                })}
              </span>
            )}
            {showsShekels(goal.spent) && (
              <span className="flex items-center gap-1">
                <span className="inline-block h-2 w-2 rounded-full bg-slate-400" aria-hidden />
                {t("dashboard.goals.spentAmount", { amount: formatCurrency(goal.spent) })}
              </span>
            )}
            {showsShekels(goal.owed) && (
              <span className="text-amber-400">
                {t("dashboard.goals.owed", { amount: formatCurrency(goal.owed) })}
              </span>
            )}
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-1.5 mt-2">
        {!closed && (
          <>
            <button
              type="button"
              onClick={() => setForm(form === "add" ? null : "add")}
              aria-pressed={form === "add"}
              disabled={busy}
              className={CHIP}
            >
              <Plus size={12} />
              {t("dashboard.goals.addMoney")}
            </button>
            <button
              type="button"
              onClick={() => setForm(form === "take" ? null : "take")}
              aria-pressed={form === "take"}
              disabled={busy || !canTakeOut}
              className={CHIP}
            >
              <Minus size={12} />
              {t("dashboard.goals.takeOut")}
            </button>
            {showsShekels(goal.suggested_this_month) && (
              <button
                type="button"
                onClick={onFund}
                disabled={busy}
                title={t("dashboard.goals.fundHint")}
                className={`${CHIP} text-emerald-400`}
              >
                <HandCoins size={12} />
                {t("dashboard.goals.fund", {
                  amount: formatCurrency(goal.suggested_this_month),
                })}
              </button>
            )}
          </>
        )}
        {goal.entries.length > 0 && (
          <button
            type="button"
            onClick={() => setShowEntries((shown) => !shown)}
            aria-expanded={showEntries}
            className="ms-auto flex items-center gap-1 text-[10px] md:text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
          >
            {showEntries ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            {t("dashboard.goals.entries", { count: goal.entries.length })}
          </button>
        )}
      </div>

      {form && !closed && (
        <EntryForm
          key={form}
          mode={form}
          goal={goal}
          busy={busy}
          onCancel={() => setForm(null)}
          onSubmit={(amount, note) => onEntry(amount, note, () => setForm(null))}
        />
      )}

      {showEntries && goal.entries.length > 0 && (
        <EntryList
          entries={goal.entries}
          canUndo={!closed}
          isUndoing={isUndoing}
          onUndo={onUndo}
        />
      )}
    </div>
  );
}

/** The inline amount form behind "Add money" / "Take out". */
function EntryForm({
  mode,
  goal,
  busy,
  onCancel,
  onSubmit,
}: {
  mode: "add" | "take";
  goal: SavingsGoal;
  busy: boolean;
  onCancel: () => void;
  /** Signed: taking out submits a negative amount. */
  onSubmit: (amount: number, note: string | null) => void;
}) {
  const { t } = useTranslation();
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const value = Number(amount);
  // Half an agora of slack, so taking out everything the card shows works.
  const tooMuch = mode === "take" && value > goal.available + 0.005;
  const valid = value > 0 && !tooMuch;

  return (
    <form
      className="mt-2 space-y-1.5"
      data-testid="goal-entry-form"
      onSubmit={(event) => {
        event.preventDefault();
        if (!valid) return;
        onSubmit(mode === "take" ? -value : value, note.trim() || null);
      }}
    >
      <div className="flex items-center gap-2">
        <input
          type="number"
          inputMode="decimal"
          min={0}
          step="any"
          value={amount}
          onChange={(event) => setAmount(event.target.value)}
          aria-label={t(
            mode === "add" ? "dashboard.goals.addAmountLabel" : "dashboard.goals.takeAmountLabel",
            { name: goal.name },
          )}
          placeholder={t("dashboard.goals.amountPlaceholder")}
          className="w-28 shrink-0 rounded-lg bg-[var(--surface-light)] px-3 py-1.5 text-sm"
          dir="ltr"
        />
        <input
          type="text"
          value={note}
          onChange={(event) => setNote(event.target.value)}
          aria-label={t("dashboard.goals.noteLabel")}
          placeholder={t("dashboard.goals.notePlaceholder")}
          className="min-w-0 flex-1 rounded-lg bg-[var(--surface-light)] px-3 py-1.5 text-sm"
          dir="auto"
        />
        <button
          type="submit"
          disabled={!valid || busy}
          aria-label={t("common.save")}
          className="p-2 rounded-lg text-emerald-400 hover:bg-[var(--surface-light)] disabled:opacity-50"
        >
          <Check size={16} />
        </button>
        <button
          type="button"
          onClick={onCancel}
          aria-label={t("common.cancel")}
          className="p-2 rounded-lg text-[var(--text-muted)] hover:bg-[var(--surface-light)]"
        >
          <X size={16} />
        </button>
      </div>
      {mode === "take" && (
        <p className={`text-[10px] md:text-xs ${tooMuch ? "text-amber-400" : "text-[var(--text-muted)]"}`}>
          {t("dashboard.goals.takeAvailable", { amount: formatCurrency(goal.available) })}
        </p>
      )}
    </form>
  );
}

/** A goal's entries, newest first, each with an undo. */
function EntryList({
  entries,
  canUndo,
  isUndoing,
  onUndo,
}: {
  entries: SavingsGoalEntry[];
  /** A closed goal's entries are history: reopen it to change them. */
  canUndo: boolean;
  isUndoing: (entryId: number) => boolean;
  onUndo: (entryId: number) => void;
}) {
  const { t } = useTranslation();
  const [showAll, setShowAll] = useState(false);
  const shown = showAll ? entries : entries.slice(0, ENTRIES_SHOWN);

  /** What the entry was, in words: its note, or where it came from. */
  const describe = (entry: SavingsGoalEntry): string => {
    if (entry.note) return entry.note;
    switch (entry.source) {
      case "cover":
        return t("dashboard.goals.entrySource.cover");
      case "migrated":
        return t("dashboard.goals.entrySource.migrated");
      case "close":
        return t("dashboard.goals.entrySource.close");
      default:
        return t(
          entry.amount >= 0
            ? "dashboard.goals.entrySource.added"
            : "dashboard.goals.entrySource.takenOut",
        );
    }
  };

  return (
    <div className="mt-2 border-t border-[var(--surface-light)] pt-2" data-testid="goal-entries">
      <ul className="space-y-1">
        {shown.map((entry) => (
          <li
            key={entry.id}
            className="flex items-center gap-2 text-[10px] md:text-xs"
            data-testid="goal-entry"
          >
            <span className="text-[var(--text-muted)] tabular-nums shrink-0" dir="ltr">
              {formatDate(entry.date)}
            </span>
            <span className="min-w-0 flex-1 truncate" dir="auto" title={describe(entry)}>
              {describe(entry)}
            </span>
            <span
              className={`font-semibold tabular-nums shrink-0 ${entry.amount < 0 ? "text-amber-400" : "text-emerald-400"}`}
            >
              {formatChange(entry.amount, { compact: false })}
            </span>
            {canUndo && entry.source !== "close" ? (
              <button
                type="button"
                onClick={() => onUndo(entry.id)}
                disabled={isUndoing(entry.id)}
                aria-label={t("dashboard.goals.undoEntry")}
                title={t("dashboard.goals.undoEntry")}
                className="p-1 rounded-md text-[var(--text-muted)] hover:text-rose-400 hover:bg-[var(--surface-light)] disabled:opacity-40 transition-colors shrink-0"
              >
                <Undo2 size={12} />
              </button>
            ) : (
              <span className="w-5 shrink-0" />
            )}
          </li>
        ))}
      </ul>
      {entries.length > ENTRIES_SHOWN && (
        <button
          type="button"
          onClick={() => setShowAll((all) => !all)}
          className="mt-1 text-[10px] md:text-xs text-[var(--primary)] hover:opacity-80"
        >
          {showAll
            ? t("dashboard.goals.showFewerEntries")
            : t("dashboard.goals.showAllEntries", { count: entries.length })}
        </button>
      )}
    </div>
  );
}

/** The status line: closed, achieved, past due, on-schedule, or plain remainder. */
function GoalStatusLine({ goal }: { goal: SavingsGoal }) {
  const { t } = useTranslation();

  if (goal.is_closed) {
    return <span className="font-medium">{t("dashboard.goals.closed")}</span>;
  }
  if (goal.is_achieved) {
    return <span className="text-emerald-400 font-medium">{t("dashboard.goals.achieved")}</span>;
  }
  if (goal.is_past_due) {
    return (
      <span className="text-amber-400">
        {t("dashboard.goals.pastDue", { amount: formatCurrency(goal.remaining) })}
      </span>
    );
  }
  if (goal.monthly_needed != null && goal.months_remaining === 0) {
    return <span>{t("dashboard.goals.dueThisMonth", { amount: formatCurrency(goal.monthly_needed) })}</span>;
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
