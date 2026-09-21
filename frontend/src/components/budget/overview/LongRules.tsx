import React from "react";
import { useTranslation } from "react-i18next";
import { CalendarRange, Layers } from "lucide-react";
import type { BudgetLongRule } from "../../../services/api";
import { formatAmount, formatCurrency } from "../../../utils/numberFormatting";
import { ruleColor, ruleTextColor, percentOf, rankRules } from "./ruleMath";

function KindTag({ kind }: { kind: BudgetLongRule["kind"] }) {
  const { t } = useTranslation();
  const Icon = kind === "project" ? Layers : CalendarRange;
  return (
    <span className="inline-flex items-center gap-1 text-[10px] tracking-wide uppercase text-[var(--text-muted)] whitespace-nowrap">
      <Icon size={11} className="shrink-0" />
      {kind === "project" ? t("budget.project") : t("budget.yearly.tab")}
    </span>
  );
}

interface LongRulesProps {
  rules: BudgetLongRule[];
  /** Month label for the contribution column, e.g. "September". */
  monthLabel: string;
  /** A settled month: the standing column describes today, not that month. */
  isPast: boolean;
}

/**
 * Yearly and project rules, each showing two figures that must never be
 * mistaken for one another.
 *
 * A yearly or project rule has no monthly limit, so it has no percentage
 * that belongs to the month being viewed — the backend filters yearly spend by
 * year alone and project spend not at all, so a percentage here always
 * describes today. Only the contribution is scoped to the month. Showing one
 * without the other is what made the old by-kind card misleading: on the live
 * month it showed the lifetime figure, and on a past month the contribution,
 * under headings that looked identical.
 *
 * Hence two columns with their own headings, and on a settled month the
 * standing column says so out loud.
 */
export const LongRules: React.FC<LongRulesProps> = ({
  rules,
  monthLabel,
  isPast,
}) => {
  const { t } = useTranslation();
  if (rules.length === 0) return null;

  const ranked = rankRules(rules);
  const columns =
    "grid-cols-[minmax(0,1.4fr)_96px_minmax(0,1fr)_120px_168px_44px]";

  return (
    <div
      data-testid="budget-long-rules"
      className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] shadow-sm p-4 md:p-5 flex flex-col gap-3"
    >
      <div className="flex items-center justify-between gap-2">
        <p className="font-bold text-sm md:text-base">
          {t("budget.overview.longRules")}
        </p>
        <span className="text-xs text-[var(--text-muted)]">
          {t("budget.overview.longRulesCount", { count: rules.length })}
        </span>
      </div>

      {/* Column headings exist so neither figure can be read as the other. */}
      <div className={`hidden md:grid ${columns} gap-3 px-3`}>
        <span />
        <span />
        <span />
        <span className="text-end text-[10px] uppercase tracking-wide text-[var(--text-muted)]">
          {t("budget.overview.inMonth", { month: monthLabel })}
        </span>
        <span className="text-end text-[10px] uppercase tracking-wide text-[var(--text-muted)]">
          {isPast ? t("budget.overview.overallNow") : t("budget.overview.overall")}
        </span>
        <span />
      </div>

      <div className="flex flex-col gap-1.5">
        {ranked.map((rule) => {
          const percent = percentOf(rule);
          return (
            <div
              key={`${rule.kind}-${rule.name}`}
              data-testid="long-rule-row"
              className="rounded-xl border border-[var(--surface-light)] bg-[var(--surface)] px-3 py-2.5"
            >
              {/* Desktop: one line, both figures under their headings. */}
              <div className={`hidden md:grid ${columns} gap-3 items-center`}>
                <span className="font-semibold text-sm truncate" dir="auto">
                  {rule.name}
                </span>
                <KindTag kind={rule.kind} />
                <span className="relative block h-1.5 w-full rounded-full bg-[var(--surface-light)] overflow-hidden">
                  <span
                    className={`absolute inset-y-0 start-0 rounded-full ${ruleColor(percent)}`}
                    style={{ width: `${Math.min(percent, 100)}%` }}
                  />
                </span>
                <span
                  dir="ltr"
                  data-testid="long-rule-contribution"
                  className="text-end text-xs font-mono font-bold whitespace-nowrap"
                >
                  {rule.month_contribution
                    ? formatCurrency(rule.month_contribution)
                    : "—"}
                </span>
                <span
                  dir="ltr"
                  data-testid="long-rule-standing"
                  className="text-end text-xs font-mono whitespace-nowrap"
                >
                  {/* One ₪ on the pair, carried by the ceiling — unless the
                      rule has none, where the spend keeps its own. */}
                  <span className="font-bold">
                    {rule.budget > 0
                      ? formatAmount(rule.spent)
                      : formatCurrency(rule.spent)}
                  </span>
                  <span className="text-[var(--text-muted)] font-normal">
                    {" / "}
                    {rule.budget > 0 ? formatCurrency(rule.budget) : "—"}
                  </span>
                </span>
                <span
                  dir="ltr"
                  className={`text-end text-xs font-mono font-bold ${ruleTextColor(percent)}`}
                >
                  {rule.budget > 0 ? `${percent}%` : "—"}
                </span>
              </div>

              {/* Mobile: the two figures stack, each still labelled. */}
              <div className="md:hidden flex flex-col gap-1.5">
                <span className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2 min-w-0">
                    <span className="font-semibold text-sm truncate" dir="auto">
                      {rule.name}
                    </span>
                    <KindTag kind={rule.kind} />
                  </span>
                  <span
                    dir="ltr"
                    className={`text-xs font-mono font-bold shrink-0 ${ruleTextColor(percent)}`}
                  >
                    {rule.budget > 0 ? `${percent}%` : "—"}
                  </span>
                </span>
                <span className="flex items-center justify-between gap-2 text-[11px] text-[var(--text-muted)]">
                  <span>
                    {t("budget.overview.inMonth", { month: monthLabel })}:{" "}
                    <span dir="ltr" className="font-mono text-[var(--text-default)]">
                      {rule.month_contribution
                        ? formatCurrency(rule.month_contribution)
                        : "—"}
                    </span>
                  </span>
                  <span>
                    {isPast
                      ? t("budget.overview.overallNow")
                      : t("budget.overview.overall")}
                    :{" "}
                    <span dir="ltr" className="font-mono text-[var(--text-default)]">
                      {formatCurrency(rule.spent)}
                    </span>
                  </span>
                </span>
              </div>
            </div>
          );
        })}
      </div>

      <p className="text-[11px] text-[var(--text-muted)] text-pretty">
        {isPast
          ? t("budget.overview.longNotePast", { month: monthLabel })
          : t("budget.overview.longNoteLive", { month: monthLabel })}
      </p>
    </div>
  );
};
