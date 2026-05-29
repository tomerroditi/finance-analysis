import React, { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { PenSquare } from "lucide-react";
import { BudgetProgressBar } from "../BudgetProgressBar";
import { BudgetRuleRow } from "./BudgetRuleRow";
import { TransactionCollapsibleList } from "./TransactionCollapsibleList";
import { ProjectSpendChart } from "./ProjectSpendChart";
import type { PendingRefund } from "../../services/api";
import type { Transaction } from "../../types/transaction";

interface ProjectBudgetRule {
  id: number;
  name: string;
  category: string;
  amount: number;
  tags?: string | string[];
}

interface ProjectRuleItem {
  rule: ProjectBudgetRule;
  current_amount: number;
  data: Transaction[];
  allow_edit: boolean;
  allow_delete: boolean;
}

interface ProjectDetails {
  name: string;
  rules: ProjectRuleItem[];
  total_spent: number;
}

interface ProjectBudgetListProps {
  projectDetails: ProjectDetails;
  expandedRuleId: string | null;
  toggleExpand: (id: string) => void;
  pendingRefundsMap: Map<string, PendingRefund>;
  includeSplitParents: boolean;
  onIncludeSplitParentsChange: (value: boolean) => void;
  onEditTotalBudget: () => void;
  onEditTagRule: (rule: ProjectBudgetRule) => void;
  onTransactionUpdated: () => void;
}

function isAllTagsRule(rule: ProjectBudgetRule): boolean {
  return (
    rule.tags?.includes("ALL_TAGS") === true ||
    rule.tags === "ALL_TAGS" ||
    (Array.isArray(rule.tags) && rule.tags[0] === "ALL_TAGS")
  );
}

/** Per-tag budget bars + Total Project Budget anchor + uncategorized spend. */
export const ProjectBudgetList: React.FC<ProjectBudgetListProps> = ({
  projectDetails,
  expandedRuleId,
  toggleExpand,
  pendingRefundsMap,
  includeSplitParents,
  onIncludeSplitParentsChange,
  onEditTotalBudget,
  onEditTagRule,
  onTransactionUpdated,
}) => {
  const { t } = useTranslation();

  const projectTotalRule = projectDetails.rules.find((r) =>
    isAllTagsRule(r.rule),
  );

  const otherTransactions = useMemo(() => {
    const allTransactions = projectTotalRule?.data || [];
    const specificRules = projectDetails.rules.filter(
      (r) => r !== projectTotalRule,
    );
    const coveredIds = new Set<string | number | undefined>();
    specificRules.forEach((rule) => {
      rule.data.forEach((tx) => coveredIds.add(tx.unique_id || tx.id));
    });
    return allTransactions.filter(
      (tx) => !coveredIds.has(tx.unique_id || tx.id),
    );
  }, [projectDetails, projectTotalRule]);

  // Deduped union of every transaction belonging to the project, used to plot
  // per-month spend regardless of how the project's rules are shaped.
  const allTransactions = useMemo(() => {
    const seen = new Set<string | number>();
    const out: Transaction[] = [];
    for (const rule of projectDetails.rules) {
      for (const tx of rule.data) {
        const key = tx.unique_id ?? tx.id;
        if (key !== undefined) {
          if (seen.has(key)) continue;
          seen.add(key);
        }
        out.push(tx);
      }
    }
    return out;
  }, [projectDetails]);

  return (
    <div className="space-y-3">
      <ProjectSpendChart transactions={allTransactions} />

      {projectDetails.rules.map((item) => {
        const isTotalRule = isAllTagsRule(item.rule);
        const subLabel = Array.isArray(item.rule.tags)
          ? item.rule.tags.join(", ")
          : item.rule.tags;
        const editAction = item.allow_edit ? (
          <button
            onClick={(e) => {
              e.stopPropagation();
              if (isTotalRule) {
                onEditTotalBudget();
              } else {
                onEditTagRule(item.rule);
              }
            }}
            className="p-1.5 text-[var(--text-muted)] hover:text-blue-500 hover:bg-blue-500/10 rounded-lg transition-all"
            title={t("budget.editRule")}
          >
            <PenSquare size={16} />
          </button>
        ) : undefined;

        const txList = (
          <TransactionCollapsibleList
            transactions={item.data}
            isOpen={expandedRuleId === String(item.rule.id)}
            showActions
            onTransactionUpdated={onTransactionUpdated}
            pendingRefundsMap={pendingRefundsMap}
            showSplitParentsFilter
            includeSplitParents={includeSplitParents}
            onIncludeSplitParentsChange={onIncludeSplitParentsChange}
          />
        );

        if (isTotalRule) {
          return (
            <BudgetProgressBar
              key={item.rule.id}
              label={t("budget.totalProjectBudget")}
              subLabel={t("budget.overallAllocation")}
              current={item.current_amount}
              total={item.rule.amount}
              onToggleExpand={() => toggleExpand(String(item.rule.id))}
              isExpanded={expandedRuleId === String(item.rule.id)}
              actions={editAction}
            >
              {txList}
            </BudgetProgressBar>
          );
        }

        return (
          <BudgetRuleRow
            key={item.rule.id}
            label={item.rule.name}
            subLabel={subLabel}
            current={item.current_amount}
            total={item.rule.amount}
            isExpanded={expandedRuleId === String(item.rule.id)}
            onToggleExpand={() => toggleExpand(String(item.rule.id))}
            actions={editAction}
          >
            {txList}
          </BudgetRuleRow>
        );
      })}

      {otherTransactions.length > 0 && (
        <div className="pt-4 border-t border-[var(--surface-light)] mt-4 md:mt-6">
          <h3 className="text-xs font-bold text-[var(--text-muted)] mb-3 uppercase tracking-wider">
            {t("budget.otherProjectTransactions")}
          </h3>
          <BudgetRuleRow
            label={t("budget.uncategorizedSpending")}
            subLabel={t("budget.uncategorizedSubLabel")}
            current={otherTransactions.reduce(
              (acc, tx) => acc + Math.abs(tx.amount || 0),
              0,
            )}
            total={0}
            isExpanded={expandedRuleId === "other_project_txs"}
            onToggleExpand={() => toggleExpand("other_project_txs")}
          >
            <TransactionCollapsibleList
              transactions={otherTransactions}
              isOpen={expandedRuleId === "other_project_txs"}
              showActions
              onTransactionUpdated={onTransactionUpdated}
              pendingRefundsMap={pendingRefundsMap}
              showSplitParentsFilter
              includeSplitParents={includeSplitParents}
              onIncludeSplitParentsChange={onIncludeSplitParentsChange}
            />
          </BudgetRuleRow>
        </div>
      )}

      {projectDetails.rules.length === 0 && (
        <div className="text-center text-[var(--text-muted)] py-8">
          {t("budget.noRulesForProject")}
        </div>
      )}
    </div>
  );
};
