import React, { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { BudgetLedgerRow, LedgerRowAction } from "./BudgetLedgerRow";
import { TransactionCollapsibleList } from "./TransactionCollapsibleList";
import { RuleSparkline } from "./RuleSparkline";
import type { PendingRefund } from "../../services/api";
import type { Transaction } from "../../types/transaction";
import { bucketByMonth, type TrendTransaction } from "../../utils/budgetTrends";
import { isAllTagsRule } from "../../utils/budgetRules";
import { formatMonthCompact } from "../../utils/dateFormatting";

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
  /** Month keys the project spans, oldest first (see ProjectBudgetView). */
  monthKeys: string[];
  expandedRuleId: string | null;
  toggleExpand: (id: string) => void;
  pendingRefundsMap: Map<string, PendingRefund>;
  includeSplitParents: boolean;
  onIncludeSplitParentsChange: (value: boolean) => void;
  onEditTagRule: (rule: ProjectBudgetRule) => void;
  onTransactionUpdated: () => void;
}

/**
 * Per-tag ledger for the selected project.
 *
 * The project's own total is no longer a row here — it is the status band at
 * the top of the page, which shows the same figure the "all tags" rule
 * carried. What is left is one line per tag envelope plus the uncategorized
 * catch-all.
 */
export const ProjectBudgetList: React.FC<ProjectBudgetListProps> = ({
  projectDetails,
  monthKeys,
  expandedRuleId,
  toggleExpand,
  pendingRefundsMap,
  includeSplitParents,
  onIncludeSplitParentsChange,
  onEditTagRule,
  onTransactionUpdated,
}) => {
  const { t } = useTranslation();

  const projectTotalRule = projectDetails.rules.find((r) => isAllTagsRule(r.rule));
  const tagRules = projectDetails.rules.filter((r) => r !== projectTotalRule);

  const monthLabels = useMemo(
    () => monthKeys.map((key) => formatMonthCompact(`${key}-01`)),
    [monthKeys],
  );

  const otherTransactions = useMemo(() => {
    const allTransactions = projectTotalRule?.data || [];
    const coveredIds = new Set<string | number | undefined>();
    tagRules.forEach((rule) => {
      rule.data.forEach((tx) => coveredIds.add(tx.unique_id || tx.id));
    });
    return allTransactions.filter((tx) => !coveredIds.has(tx.unique_id || tx.id));
  }, [projectTotalRule, tagRules]);

  const otherTotal = otherTransactions.reduce(
    (acc, tx) => acc + Math.abs(tx.amount || 0),
    0,
  );

  return (
    <div className="space-y-2">
      {/* No sub-label: a project rule always covers exactly one tag, so the
          tag line only ever repeated the rule name back at the reader. */}
      {tagRules.map((item) => {
        return (
          <BudgetLedgerRow
            key={item.rule.id}
            label={item.rule.name}
            current={item.current_amount}
            total={item.rule.amount}
            isExpanded={expandedRuleId === String(item.rule.id)}
            onToggleExpand={() => toggleExpand(String(item.rule.id))}
            trend={
              <RuleSparkline
                variant="burn"
                series={bucketByMonth(
                  item.data as TrendTransaction[],
                  monthKeys,
                  item.current_amount,
                )}
                labels={monthLabels}
                budget={item.rule.amount}
                totalPeriods={monthKeys.length}
              />
            }
            actions={
              <LedgerRowAction
                kind="edit"
                label={t("budget.editRule")}
                onClick={
                  item.allow_edit ? () => onEditTagRule(item.rule) : undefined
                }
              />
            }
          >
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
          </BudgetLedgerRow>
        );
      })}

      {otherTransactions.length > 0 && (
        <BudgetLedgerRow
          label={t("budget.uncategorizedSpending")}
          subLabel={t("budget.uncategorizedSubLabel")}
          current={otherTotal}
          total={0}
          isExpanded={expandedRuleId === "other_project_txs"}
          onToggleExpand={() => toggleExpand("other_project_txs")}
          actions={<LedgerRowAction kind="edit" label={t("budget.editRule")} />}
          trend={
            <RuleSparkline
              variant="burn"
              series={bucketByMonth(
                otherTransactions as TrendTransaction[],
                monthKeys,
                otherTotal,
              )}
              labels={monthLabels}
              budget={0}
              totalPeriods={monthKeys.length}
            />
          }
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
        </BudgetLedgerRow>
      )}

      {projectDetails.rules.length === 0 && (
        <div className="text-center text-[var(--text-muted)] py-8">
          {t("budget.noRulesForProject")}
        </div>
      )}
    </div>
  );
};
