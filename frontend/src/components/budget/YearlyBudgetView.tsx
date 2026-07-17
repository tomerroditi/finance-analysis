import React, { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, X, PenSquare, Trash2 } from "lucide-react";
import { budgetApi, type YearlyAnalysis } from "../../services/api";
import { BudgetProgressBar } from "../BudgetProgressBar";
import { YearHeader } from "./YearHeader";
import { YearlySummaryStrip } from "./YearlySummaryStrip";
import { YearlyRuleModal } from "../modals/YearlyRuleModal";
import { useConfirm } from "../../context/DialogContext";
import { useQueryKeys } from "../../hooks/useQueryKeys";

export const YearlyBudgetView: React.FC = () => {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const queryClient = useQueryClient();
  const qk = useQueryKeys();
  const currentYear = new Date().getFullYear();
  const [year, setYear] = useState(currentYear);
  const [modalOpen, setModalOpen] = useState(false);
  const [editRule, setEditRule] = useState<YearlyAnalysis["rules"][number]["rule"] | null>(null);
  const [alertDismissed, setAlertDismissed] = useState(false);

  useEffect(() => {
    // Reset the dismissed-alert flag when the selected year changes so a
    // carry-forward/conflict alert dismissed for one year doesn't stay
    // hidden after navigating to another. `year` is the only dep and is
    // stable between renders (no loop) — matches the SelectDropdown
    // precedent for resetting local UI state on a prop/param change.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setAlertDismissed(false);
  }, [year]);

  const { data, isLoading } = useQuery({
    queryKey: qk.budget.yearly(year),
    queryFn: () => budgetApi.getYearlyAnalysis(year).then((r) => r.data as YearlyAnalysis),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => budgetApi.deleteYearlyRule(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.budget.yearly(year) }),
  });

  const rules = data?.rules ?? [];

  return (
    <div className="space-y-4">
      <YearHeader
        year={year}
        isCurrentYear={year === currentYear}
        onPrev={() => setYear((y) => y - 1)}
        onNext={() => setYear((y) => y + 1)}
        onToday={() => setYear(currentYear)}
        onAddRule={() => {
          setEditRule(null);
          setModalOpen(true);
        }}
      />

      {!alertDismissed && data?.carried_from != null && (
        <div className="flex gap-2.5 items-start bg-amber-500/10 border border-amber-500/40 rounded-xl px-3.5 py-3 text-sm">
          <AlertTriangle size={16} className="text-amber-400 mt-0.5 shrink-0" />
          <div dir="auto">
            {data.skipped_conflicts.length > 0
              ? t("budget.yearly.carriedWithSkips", {
                  fromYear: data.carried_from,
                  tags: data.skipped_conflicts.join(", "),
                })
              : t("budget.yearly.carried", { fromYear: data.carried_from })}
          </div>
          <button
            onClick={() => setAlertDismissed(true)}
            aria-label={t("common.dismiss")}
            className="ms-auto text-[var(--text-muted)] hover:text-[var(--text-default)]"
          >
            <X size={16} />
          </button>
        </div>
      )}

      {data?.summary && <YearlySummaryStrip summary={data.summary} />}

      {isLoading ? (
        <p className="text-[var(--text-muted)] text-sm py-8 text-center">{t("common.loading")}</p>
      ) : rules.length === 0 ? (
        <p className="text-[var(--text-muted)] text-sm py-8 text-center">{t("budget.yearly.empty")}</p>
      ) : (
        <div>
          {rules.map((entry) => {
            const r = entry.rule;
            const tagList = Array.isArray(r.tags) ? r.tags : [];
            const isAllTags = tagList.length === 1 && tagList[0].toLowerCase() === "all_tags";
            const subLabel = `${r.category} · ${isAllTags ? t("budget.yearly.allTags") : tagList.join("; ")}`;
            return (
              <BudgetProgressBar
                key={r.id}
                current={-entry.current_amount}
                total={r.amount}
                label={r.name}
                subLabel={subLabel}
                actions={
                  <>
                    {entry.allow_edit && (
                      <button
                        onClick={() => {
                          setEditRule(r);
                          setModalOpen(true);
                        }}
                        className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50/50 rounded-lg transition-all"
                        title={t("budget.editRule")}
                        aria-label={t("budget.editRule")}
                      >
                        <PenSquare size={16} />
                      </button>
                    )}
                    {entry.allow_delete && (
                      <button
                        onClick={async () => {
                          const ok = await confirm({
                            title: t("budget.deleteRule"),
                            message: t("budget.yearly.confirmDelete", { name: r.name }),
                            confirmLabel: t("common.delete"),
                            isDestructive: true,
                          });
                          if (ok) deleteMutation.mutate(r.id);
                        }}
                        className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50/50 rounded-lg transition-all"
                        title={t("budget.deleteRule")}
                        aria-label={t("budget.deleteRule")}
                      >
                        <Trash2 size={16} />
                      </button>
                    )}
                  </>
                }
              />
            );
          })}
        </div>
      )}

      <YearlyRuleModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        year={year}
        editRule={editRule}
      />
    </div>
  );
};
