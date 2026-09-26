import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Target } from "lucide-react";
import { savingsGoalsApi, type SavingsGoal } from "../../services/api";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { qkPrefix } from "../../services/queryKeys";
import { useNotify } from "../../context/DialogContext";
import { Modal } from "../common/Modal";
import { BAR_CONTROL } from "./BudgetCommandBar";
import { joinRuleTags } from "../../utils/goalRuleTags";

/** Whether `goal` pays for exactly the spending `(category, tags)` names. */
function goalCovers(goal: SavingsGoal, category: string, tags: string | null): boolean {
  return (
    goal.utilization_category === category && (goal.utilization_tags ?? null) === tags
  );
}

/**
 * Budget action that pays for a whole budget out of one savings goal: a
 * project (its category) from the project tab's command bar, or a yearly
 * envelope (its category and tags) from the envelope's row.
 *
 * Linking is a single write on the goal (`utilization_category` + tags): every
 * matching purchase from the goal's start month on — the ones already on
 * record and every one that lands later — is spent out of the goal, so the
 * user never links the budget's transactions one at a time.
 *
 * Hides itself when the user keeps no goals.
 */
export function BudgetGoalLink({
  category,
  tags,
  name,
  variant = "bar",
}: {
  category: string;
  /** Omit (or pass `["all_tags"]`) to cover the whole category. */
  tags?: string[] | null;
  /** What the modal title calls the budget — a project or envelope name. */
  name: string;
  /** `bar` — labelled command-bar button; `icon` — ledger-row action. */
  variant?: "bar" | "icon";
}) {
  const { t } = useTranslation();
  const qk = useQueryKeys();
  const queryClient = useQueryClient();
  const notify = useNotify();
  const [isOpen, setIsOpen] = useState(false);
  const ruleTags = joinRuleTags(tags);

  const { data: goals } = useQuery({
    queryKey: qk.savingsGoals.all(),
    queryFn: () => savingsGoalsApi.getAll().then((res) => res.data),
  });

  const fundingGoal = goals?.find((goal) => goalCovers(goal, category, ruleTags));

  const mutation = useMutation({
    mutationFn: ({ goalId, link }: { goalId: number; link: boolean }) =>
      link
        ? savingsGoalsApi.setSpendingLink(goalId, category, tags ?? null)
        : savingsGoalsApi.setSpendingLink(goalId, null),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.savingsGoals });
      // The monthly budget view carries each goal's allocations.
      queryClient.invalidateQueries({ queryKey: qkPrefix.budget });
      setIsOpen(false);
    },
    onError: () => notify.error(t("budget.goalLink.failed")),
  });

  // A closed goal keeps what it already pays for, but nothing new can be
  // pointed at it: its history is frozen.
  const openGoals = (goals ?? []).filter(
    (goal) => !goal.is_closed || goal.id === fundingGoal?.id,
  );
  if (openGoals.length === 0) return null;

  const title = fundingGoal
    ? t("budget.goalLink.fundedBy", { name: fundingGoal.name })
    : t("budget.goalLink.action");

  return (
    <>
      {variant === "bar" ? (
        <button
          onClick={() => setIsOpen(true)}
          data-testid="budget-goal-link"
          title={title}
          className={`inline-flex items-center gap-2 px-3 md:px-4 text-xs md:text-sm bg-[var(--surface-light)] border border-[var(--surface-light)] rounded-lg hover:bg-[var(--surface)] transition-colors shadow-sm font-medium whitespace-nowrap min-w-0 max-w-full ${BAR_CONTROL} ${
            fundingGoal ? "text-[var(--primary)]" : ""
          }`}
        >
          <Target size={18} className="shrink-0" />
          <span className="truncate" dir="auto">
            {fundingGoal ? fundingGoal.name : t("budget.goalLink.short")}
          </span>
        </button>
      ) : (
        <button
          type="button"
          data-testid="budget-goal-link"
          onClick={(e) => {
            e.stopPropagation();
            setIsOpen(true);
          }}
          title={title}
          aria-label={title}
          className={`p-1.5 rounded-lg transition-all hover:bg-blue-500/10 ${
            fundingGoal
              ? "text-[var(--primary)]"
              : "text-[var(--text-muted)] hover:text-blue-500"
          }`}
        >
          <Target size={16} />
        </button>
      )}

      {isOpen && (
        <Modal
          isOpen
          onClose={() => setIsOpen(false)}
          title={t("budget.goalLink.title", { name })}
          titleIcon={<Target size={18} />}
          maxWidth="sm"
        >
          <div className="space-y-3 p-4 md:p-6" data-testid="budget-goal-modal">
            <p className="text-xs text-[var(--text-muted)]">
              {t("budget.goalLink.explainer")}
            </p>

            {openGoals.map((goal) => {
              const isFunding = goal.id === fundingGoal?.id;
              return (
                <button
                  key={goal.id}
                  onClick={() => mutation.mutate({ goalId: goal.id, link: true })}
                  disabled={mutation.isPending || isFunding}
                  aria-pressed={isFunding}
                  className={`w-full flex items-center justify-between gap-2 border rounded-lg px-3 py-2 text-start transition-colors disabled:cursor-default ${
                    isFunding
                      ? "border-[var(--primary)] bg-[var(--primary)]/10"
                      : "border-[var(--surface-light)] hover:bg-[var(--surface-light)] disabled:opacity-50"
                  }`}
                >
                  <span className="text-sm truncate" dir="auto" title={goal.name}>
                    {goal.name}
                  </span>
                  {isFunding ? (
                    <span className="text-xs font-medium text-[var(--primary)] shrink-0">
                      {t("budget.goalLink.linked")}
                    </span>
                  ) : (
                    goal.utilization_category && (
                      // Linking replaces whatever the goal paid for before.
                      <span
                        className="text-xs text-[var(--text-muted)] truncate shrink min-w-0"
                        dir="auto"
                      >
                        {t("budget.goalLink.fundsOther", {
                          name: goal.utilization_tags
                            ? `${goal.utilization_category} · ${goal.utilization_tags.split(";").join(", ")}`
                            : goal.utilization_category,
                        })}
                      </span>
                    )
                  )}
                </button>
              );
            })}

            <div className="flex justify-between items-center gap-2 pt-2">
              {fundingGoal ? (
                <button
                  onClick={() => mutation.mutate({ goalId: fundingGoal.id, link: false })}
                  disabled={mutation.isPending}
                  className="px-3 py-2 rounded-lg text-sm font-medium text-rose-400 hover:bg-[var(--surface-light)] disabled:opacity-50 transition-colors"
                >
                  {t("budget.goalLink.unlink")}
                </button>
              ) : (
                <span />
              )}
              <button
                onClick={() => setIsOpen(false)}
                className="px-4 py-2 rounded-lg text-sm font-medium text-[var(--text-muted)] hover:bg-[var(--surface-light)] transition-colors"
              >
                {t("common.cancel")}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
