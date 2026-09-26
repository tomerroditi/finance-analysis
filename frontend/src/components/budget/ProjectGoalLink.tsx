import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Target } from "lucide-react";
import { savingsGoalsApi } from "../../services/api";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { qkPrefix } from "../../services/queryKeys";
import { useNotify } from "../../context/DialogContext";
import { Modal } from "../common/Modal";
import { BAR_CONTROL } from "./BudgetCommandBar";

/**
 * Command-bar action that pays for a whole project budget out of one savings
 * goal.
 *
 * Linking is a single write on the goal (`funding_project`): every purchase in
 * the project's category from the goal's start month on — the ones already on
 * record and every one that lands later — is spent out of the goal, so the
 * user never links the project's transactions one at a time.
 *
 * The button hides itself when the user keeps no goals.
 */
export function ProjectGoalLink({ project }: { project: string }) {
  const { t } = useTranslation();
  const qk = useQueryKeys();
  const queryClient = useQueryClient();
  const notify = useNotify();
  const [isOpen, setIsOpen] = useState(false);

  const { data: goals } = useQuery({
    queryKey: qk.savingsGoals.all(),
    queryFn: () => savingsGoalsApi.getAll().then((res) => res.data),
  });

  const fundingGoal = goals?.find((goal) => goal.funding_project === project);

  const mutation = useMutation({
    mutationFn: ({ goalId, target }: { goalId: number; target: string | null }) =>
      savingsGoalsApi.setFundingProject(goalId, target),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.savingsGoals });
      // The monthly budget view carries each goal's allocations.
      queryClient.invalidateQueries({ queryKey: qkPrefix.budget });
      setIsOpen(false);
    },
    onError: () => notify.error(t("budget.projectGoal.failed")),
  });

  // A closed goal keeps the project it already funds, but nothing new can be
  // pointed at it: its history is frozen.
  const openGoals = (goals ?? []).filter(
    (goal) => !goal.is_closed || goal.id === fundingGoal?.id,
  );
  if (openGoals.length === 0) return null;

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        data-testid="project-goal-link"
        title={
          fundingGoal
            ? t("budget.projectGoal.fundedBy", { name: fundingGoal.name })
            : t("budget.projectGoal.action")
        }
        className={`inline-flex items-center gap-2 px-3 md:px-4 text-xs md:text-sm bg-[var(--surface-light)] border border-[var(--surface-light)] rounded-lg hover:bg-[var(--surface)] transition-colors shadow-sm font-medium whitespace-nowrap min-w-0 max-w-full ${BAR_CONTROL} ${
          fundingGoal ? "text-[var(--primary)]" : ""
        }`}
      >
        <Target size={18} className="shrink-0" />
        <span className="truncate" dir="auto">
          {fundingGoal ? fundingGoal.name : t("budget.projectGoal.short")}
        </span>
      </button>

      {isOpen && (
        <Modal
          isOpen
          onClose={() => setIsOpen(false)}
          title={t("budget.projectGoal.title", { name: project })}
          titleIcon={<Target size={18} />}
          maxWidth="sm"
        >
          <div className="space-y-3 p-4 md:p-6" data-testid="project-goal-modal">
            <p className="text-xs text-[var(--text-muted)]">
              {t("budget.projectGoal.explainer")}
            </p>

            {openGoals.map((goal) => {
              const isFunding = goal.id === fundingGoal?.id;
              return (
                <button
                  key={goal.id}
                  onClick={() => mutation.mutate({ goalId: goal.id, target: project })}
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
                      {t("budget.projectGoal.linked")}
                    </span>
                  ) : (
                    goal.funding_project && (
                      <span
                        className="text-xs text-[var(--text-muted)] truncate shrink min-w-0"
                        dir="auto"
                      >
                        {t("budget.projectGoal.fundsOther", {
                          name: goal.funding_project,
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
                  onClick={() =>
                    mutation.mutate({ goalId: fundingGoal.id, target: null })
                  }
                  disabled={mutation.isPending}
                  className="px-3 py-2 rounded-lg text-sm font-medium text-rose-400 hover:bg-[var(--surface-light)] disabled:opacity-50 transition-colors"
                >
                  {t("budget.projectGoal.unlink")}
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
