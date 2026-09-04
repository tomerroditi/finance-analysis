import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Target } from "lucide-react";
import {
  savingsGoalsApi,
  type SavingsGoalLinkType,
} from "../../services/api";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { qkPrefix } from "../../services/queryKeys";
import { Modal } from "../common/Modal";
import type { Transaction } from "../../types/transaction";

/**
 * Row action for attaching one transaction to a savings goal.
 *
 * Two roles, and the sign of the transaction decides which one is offered by
 * default: money going out can either be *set aside* for a goal (a
 * contribution, which consumes that month's surplus before the waterfall runs)
 * or *spent out of* one (a utilization, which draws the goal down without ever
 * moving its target).
 *
 * The button hides itself when the user keeps no goals, so the actions column
 * stays uncluttered for everyone who does not use the feature.
 */
export function GoalLinkAction({ transaction }: { transaction: Transaction }) {
  const { t } = useTranslation();
  const qk = useQueryKeys();
  const queryClient = useQueryClient();
  const [isOpen, setIsOpen] = useState(false);

  const { data: goals } = useQuery({
    queryKey: qk.savingsGoals.all(),
    queryFn: async () => {
      const res = await savingsGoalsApi.getAll();
      return res.data;
    },
  });

  const { data: links } = useQuery({
    queryKey: qk.savingsGoals.links(),
    queryFn: async () => {
      const res = await savingsGoalsApi.getLinks();
      return res.data;
    },
  });

  const sourceTable = transaction.source ?? "";
  const sourceId = Number(transaction.unique_id ?? transaction.id ?? NaN);

  const existing = links?.find(
    (link) =>
      link.source_table === sourceTable &&
      String(link.source_id) === String(sourceId),
  );

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: qkPrefix.savingsGoals });
  };

  const linkMutation = useMutation({
    mutationFn: ({
      goalId,
      linkType,
    }: {
      goalId: number;
      linkType: SavingsGoalLinkType;
    }) =>
      savingsGoalsApi.link(goalId, {
        source_type: "transaction",
        source_id: sourceId,
        source_table: sourceTable,
        link_type: linkType,
      }),
    onSuccess: () => {
      invalidate();
      setIsOpen(false);
    },
  });

  const unlinkMutation = useMutation({
    mutationFn: (linkId: number) => savingsGoalsApi.unlink(linkId),
    onSuccess: () => {
      invalidate();
      setIsOpen(false);
    },
  });

  const openGoals = (goals ?? []).filter((goal) => !goal.is_closed);
  // Without a goal to attach to, or without a resolvable transaction key, the
  // action can't do anything useful.
  if (openGoals.length === 0 || !sourceTable || Number.isNaN(sourceId)) return null;

  const linkedGoal = existing
    ? goals?.find((goal) => goal.id === existing.goal_id)
    : undefined;

  return (
    <>
      <button
        className={`p-1.5 rounded-md hover:bg-[var(--surface-light)] transition-colors ${
          existing
            ? "text-[var(--primary)]"
            : "text-[var(--text-muted)] hover:text-white"
        }`}
        title={
          linkedGoal
            ? t("transactions.goalLink.linkedTo", { name: linkedGoal.name })
            : t("transactions.goalLink.action")
        }
        aria-label={t("transactions.goalLink.action")}
        onClick={() => setIsOpen(true)}
      >
        <Target size={14} />
      </button>

      {isOpen && (
        <Modal
          isOpen
          onClose={() => setIsOpen(false)}
          title={t("transactions.goalLink.title")}
          titleIcon={<Target size={18} />}
          maxWidth="sm"
        >
          <div className="space-y-3 p-4 md:p-6">
            <p className="text-xs text-[var(--text-muted)]">
              {t("transactions.goalLink.explainer")}
            </p>

            {openGoals.map((goal) => (
              <div
                key={goal.id}
                className="flex items-center justify-between gap-2 border border-[var(--surface-light)] rounded-lg px-3 py-2"
              >
                <span className="text-sm truncate" dir="auto" title={goal.name}>
                  {goal.name}
                </span>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() =>
                      linkMutation.mutate({
                        goalId: goal.id,
                        linkType: "contribution",
                      })
                    }
                    disabled={linkMutation.isPending}
                    className="px-2 py-1 rounded-md text-xs font-medium bg-[var(--surface-light)] hover:bg-[var(--primary)]/20 disabled:opacity-50 transition-colors"
                  >
                    {t("transactions.goalLink.asContribution")}
                  </button>
                  <button
                    onClick={() =>
                      linkMutation.mutate({
                        goalId: goal.id,
                        linkType: "utilization",
                      })
                    }
                    disabled={linkMutation.isPending}
                    className="px-2 py-1 rounded-md text-xs font-medium bg-[var(--surface-light)] hover:bg-[var(--primary)]/20 disabled:opacity-50 transition-colors"
                  >
                    {t("transactions.goalLink.asUtilization")}
                  </button>
                </div>
              </div>
            ))}

            <div className="flex justify-between items-center gap-2 pt-2">
              {existing ? (
                <button
                  onClick={() => unlinkMutation.mutate(existing.id)}
                  disabled={unlinkMutation.isPending}
                  className="px-3 py-2 rounded-lg text-sm font-medium text-rose-400 hover:bg-[var(--surface-light)] disabled:opacity-50 transition-colors"
                >
                  {t("transactions.goalLink.unlink")}
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
