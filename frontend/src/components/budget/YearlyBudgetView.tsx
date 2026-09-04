import React, { useState, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, X, PenSquare, Trash2, Plus } from "lucide-react";
import { budgetApi, type YearlyAnalysis } from "../../services/api";
import { YearlyRuleModal } from "../modals/YearlyRuleModal";
import { useConfirm } from "../../context/DialogContext";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { BudgetCommandBar, PeriodNav } from "./BudgetCommandBar";
import { BudgetStatusBand, type BandStat } from "./BudgetStatusBand";
import { BudgetNoticeLine } from "./BudgetNoticeLine";
import { BudgetLedgerRow } from "./BudgetLedgerRow";
import { RuleSparkline } from "./RuleSparkline";
import { isAllTagsRule } from "../../utils/budgetRules";
import { formatCurrency } from "../../utils/numberFormatting";
import { formatMonthCompact } from "../../utils/dateFormatting";
import {
  bucketByMonth,
  monthKeysOfYear,
  type TrendTransaction,
} from "../../utils/budgetTrends";

const MONTHS_IN_YEAR = 12;

interface YearlyBudgetViewProps {
  tabs: React.ReactNode;
}

export const YearlyBudgetView: React.FC<YearlyBudgetViewProps> = ({ tabs }) => {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const queryClient = useQueryClient();
  const qk = useQueryKeys();
  const currentYear = new Date().getFullYear();
  const [year, setYear] = useState(currentYear);
  const [modalOpen, setModalOpen] = useState(false);
  const [editRule, setEditRule] = useState<YearlyAnalysis["rules"][number]["rule"] | null>(null);
  const [alertDismissed, setAlertDismissed] = useState(false);
  const [expandedRuleId, setExpandedRuleId] = useState<number | null>(null);

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

  // Memoised because `?? []` mints a new array on every render, which would
  // re-bucket every rule's burn series for nothing.
  const rules = useMemo(() => data?.rules ?? [], [data?.rules]);
  const summary = data?.summary;

  // Months elapsed in the viewed year — the whole year once it is in the past.
  const now = new Date();
  const elapsedMonths =
    year < currentYear
      ? MONTHS_IN_YEAR
      : year > currentYear
        ? 0
        : now.getMonth() + 1;
  const paceRatio = elapsedMonths / MONTHS_IN_YEAR;

  const monthKeys = useMemo(() => monthKeysOfYear(year), [year]);
  const monthLabels = useMemo(
    () => monthKeys.map((key) => formatMonthCompact(`${key}-01`)),
    [monthKeys],
  );

  // A yearly envelope has no per-period endpoint, so its burn series is
  // bucketed from the transactions the analysis already returns per rule.
  // `current_amount` arrives spend-positive (the service already negates the
  // transaction sum), so it is passed through as the series' reference total.
  const seriesByRule = useMemo(() => {
    const map = new Map<number, number[]>();
    for (const entry of rules) {
      map.set(
        entry.rule.id,
        bucketByMonth(
          entry.data as TrendTransaction[],
          monthKeys,
          entry.current_amount,
        ),
      );
    }
    return map;
  }, [rules, monthKeys]);

  const stats: BandStat[] = summary
    ? [
        {
          key: "spent",
          label: t("budget.yearly.spentYtd"),
          value: (
            <span className="text-lg md:text-xl font-bold" dir="ltr">
              {formatCurrency(summary.total_spent)}
            </span>
          ),
        },
        {
          key: "health",
          label: t("budget.yearly.health"),
          value: (
            <span className="flex items-baseline gap-1 flex-wrap">
              <span className="text-lg md:text-xl font-bold text-emerald-400">
                {summary.on_track}
              </span>
              <span className="text-[10px] sm:text-xs text-[var(--text-muted)]">
                {t("budget.onTrackLabel")}
              </span>
              {summary.over > 0 && (
                <>
                  <span className="text-[10px] sm:text-xs text-[var(--text-muted)]">·</span>
                  <span className="text-lg md:text-xl font-bold text-rose-400">
                    {summary.over}
                  </span>
                  <span className="text-[10px] sm:text-xs text-[var(--text-muted)]">
                    {t("budget.overBudgetLabel")}
                  </span>
                </>
              )}
            </span>
          ),
        },
        {
          key: "pace",
          label: t("budget.yearly.pace"),
          value: (
            <span className="block">
              <span className="text-lg md:text-xl font-bold" dir="ltr">
                {Math.round(paceRatio * 100)}%
              </span>
              <span className="block text-[10px] sm:text-xs text-[var(--text-muted)] truncate">
                {t("budget.yearly.monthsElapsed", {
                  elapsed: elapsedMonths,
                  total: MONTHS_IN_YEAR,
                })}
              </span>
            </span>
          ),
        },
      ]
    : [];

  return (
    <div className="space-y-3 md:space-y-4">
      <BudgetCommandBar
        tabs={tabs}
        actions={
          <button
            onClick={() => {
              setEditRule(null);
              setModalOpen(true);
            }}
            className="inline-flex items-center justify-center gap-2 px-3 md:px-4 py-2 text-xs md:text-sm bg-[var(--primary)] text-white rounded-lg hover:bg-[var(--primary-dark)] transition-colors shadow-sm font-medium whitespace-nowrap"
          >
            <Plus size={18} className="shrink-0" />
            {t("budget.yearly.addRule")}
          </button>
        }
      >
        <PeriodNav
          label={year}
          isCurrent={year === currentYear}
          onPrev={() => setYear((y) => y - 1)}
          onNext={() => setYear((y) => y + 1)}
          onToday={() => setYear(currentYear)}
          todayTitle={t("budget.yearly.currentYear")}
          ltr
          widthClass="w-20 md:w-24"
        />
      </BudgetCommandBar>

      <BudgetNoticeLine />

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

      {/* No rules means nothing is allocated — an empty 0 / 0 gauge is noise,
          the empty-state line below says it better. */}
      {summary && rules.length > 0 && (
        <BudgetStatusBand
          label={t("budget.yearly.allocated")}
          spent={summary.total_spent}
          total={summary.total_allocated}
          stats={stats}
        />
      )}

      {isLoading ? (
        <p className="text-[var(--text-muted)] text-sm py-8 text-center">{t("common.loading")}</p>
      ) : rules.length === 0 ? (
        <p className="text-[var(--text-muted)] text-sm py-8 text-center">{t("budget.yearly.empty")}</p>
      ) : (
        <div className="w-full space-y-2">
            {rules.map((entry) => {
              const rule = entry.rule;
              const tagList = Array.isArray(rule.tags) ? rule.tags : [];
              const subLabel = `${rule.category} · ${isAllTagsRule(rule) ? t("budget.yearly.allTags") : tagList.join("; ")}`;
              return (
                <BudgetLedgerRow
                  key={rule.id}
                  label={rule.name}
                  subLabel={subLabel}
                  current={entry.current_amount}
                  total={rule.amount}
                  isExpanded={expandedRuleId === rule.id}
                  onToggleExpand={() =>
                    setExpandedRuleId((prev) => (prev === rule.id ? null : rule.id))
                  }
                  trend={
                    <RuleSparkline
                      variant="burn"
                      series={seriesByRule.get(rule.id) ?? []}
                      labels={monthLabels}
                      budget={rule.amount}
                      totalPeriods={MONTHS_IN_YEAR}
                      showPace
                    />
                  }
                  actions={
                    <>
                      {entry.allow_edit && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setEditRule(rule);
                            setModalOpen(true);
                          }}
                          className="p-1.5 text-[var(--text-muted)] hover:text-blue-500 hover:bg-blue-500/10 rounded-lg transition-all"
                          title={t("budget.editRule")}
                          aria-label={t("budget.editRule")}
                        >
                          <PenSquare size={16} />
                        </button>
                      )}
                      {entry.allow_delete && (
                        <button
                          onClick={async (e) => {
                            e.stopPropagation();
                            const ok = await confirm({
                              title: t("budget.deleteRule"),
                              message: t("budget.yearly.confirmDelete", { name: rule.name }),
                              confirmLabel: t("common.delete"),
                              isDestructive: true,
                            });
                            if (ok) deleteMutation.mutate(rule.id);
                          }}
                          className="p-1.5 text-[var(--text-muted)] hover:text-red-500 hover:bg-red-500/10 rounded-lg transition-all"
                          title={t("budget.deleteRule")}
                          aria-label={t("budget.deleteRule")}
                        >
                          <Trash2 size={16} />
                        </button>
                      )}
                    </>
                  }
                >
                  <div className="px-3 pb-3 text-xs text-[var(--text-muted)]" dir="auto">
                    {t("budget.yearly.spentOfAllocation", {
                      spent: formatCurrency(entry.current_amount),
                      total: formatCurrency(rule.amount),
                    })}
                  </div>
                </BudgetLedgerRow>
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
