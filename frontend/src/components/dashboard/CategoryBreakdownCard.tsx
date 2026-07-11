import { useQuery } from "@tanstack/react-query";
import { TrendingDown, Tag } from "lucide-react";
import { analyticsApi, taggingApi } from "../../services/api";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { useTranslation } from "react-i18next";
import { formatCurrency } from "../../utils/numberFormatting";

/** Category breakdown dashboard card (expenses + refunds, sorted, with share %). */
export function CategoryBreakdownCard() {
  const { t } = useTranslation();
  const qk = useQueryKeys();

  const { data: categoryData } = useQuery({
    queryKey: qk.analytics.byCategory(),
    queryFn: async () => (await analyticsApi.getByCategory()).data,
  });
  const { data: categoryIcons } = useQuery({
    queryKey: qk.tagging.icons(),
    queryFn: async () => (await taggingApi.getIcons()).data,
  });

  const expenses = categoryData?.expenses
    ?.slice()
    .sort((a: { amount: number }, b: { amount: number }) => b.amount - a.amount) || [];
  const refunds = categoryData?.refunds
    ?.slice()
    .sort((a: { amount: number }, b: { amount: number }) => b.amount - a.amount) || [];
  const totalExpenses = expenses.reduce((s: number, d: { amount: number }) => s + d.amount, 0);
  const totalRefunds = refunds.reduce((s: number, d: { amount: number }) => s + d.amount, 0);
  const topCategory = expenses[0];
  const maxExpense = topCategory?.amount || 1;
  const maxRefund = refunds[0]?.amount || 1;

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] overflow-hidden flex flex-col">
      <div className="px-3 md:px-6 pt-4 md:pt-5">
        <h2 className="text-sm md:text-base font-bold">{t("dashboard.categories")}</h2>
      </div>
      <div className="px-3 md:px-6 pb-4 md:pb-6 pt-4 min-h-[400px] md:h-[600px] overflow-y-auto flex flex-col">
        <div className="flex flex-col flex-1 min-h-0 space-y-5">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 md:gap-4">
            <div className="bg-[var(--surface-light)] rounded-xl px-3 md:px-4 py-2.5 md:py-3 flex items-center gap-3">
              <div className="p-2 rounded-lg bg-rose-500/20 text-rose-400">
                <TrendingDown size={18} />
              </div>
              <div>
                <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">{t("dashboard.totalExpenses")}</p>
                <p className="text-lg font-bold text-rose-400">{formatCurrency(totalExpenses)}</p>
              </div>
            </div>
            <div className="bg-[var(--surface-light)] rounded-xl px-3 md:px-4 py-2.5 md:py-3 flex items-center gap-3">
              <div className="p-2 rounded-lg bg-amber-500/20 text-amber-400 text-lg">
                {topCategory ? (categoryIcons?.[topCategory.category] || "📊") : "—"}
              </div>
              <div className="min-w-0">
                <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">{t("dashboard.topCategory")}</p>
                <p className="text-sm font-bold truncate" dir="auto">{topCategory?.category || "—"}</p>
              </div>
            </div>
            <div className="bg-[var(--surface-light)] rounded-xl px-3 md:px-4 py-2.5 md:py-3 flex items-center gap-3">
              <div className="p-2 rounded-lg bg-blue-500/20 text-blue-400">
                <Tag size={18} />
              </div>
              <div>
                <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">{t("dashboard.categories")}</p>
                <p className="text-lg font-bold">{expenses.length}</p>
              </div>
            </div>
          </div>

          <div>
            <p className="text-sm font-bold text-rose-400 uppercase tracking-wider mb-3">{t("dashboard.expenses")}</p>
            <div className="space-y-1.5 max-h-[350px] overflow-y-auto pe-1">
              {expenses.map((d: { category: string; amount: number }, i: number) => {
                const pct = totalExpenses > 0 ? (d.amount / totalExpenses) * 100 : 0;
                const barWidth = (d.amount / maxExpense) * 100;
                const icon = categoryIcons?.[d.category] ?? "";
                return (
                  <div key={d.category} className="group flex items-center gap-2 py-1.5 px-2 rounded-lg hover:bg-[var(--surface-light)] transition-colors">
                    <span className="text-base w-6 text-center shrink-0">{icon || (d.category === "Uncategorized" ? "❓" : `${i + 1}.`)}</span>
                    <span className="text-xs md:text-sm font-medium w-20 md:w-28 truncate shrink-0" title={d.category} dir="auto">{d.category}</span>
                    <div className="flex-1 h-5 bg-[var(--surface-light)] rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-rose-600 to-rose-400 transition-all duration-500"
                        style={{ width: `${barWidth}%` }}
                      />
                    </div>
                    <span className="text-xs md:text-sm font-bold tabular-nums w-16 md:w-24 text-end shrink-0">{formatCurrency(d.amount)}</span>
                    <span className="text-[10px] md:text-xs text-[var(--text-muted)] w-10 md:w-12 text-end shrink-0">{pct.toFixed(1)}%</span>
                  </div>
                );
              })}
              {expenses.length === 0 && (
                <p className="text-[var(--text-muted)] text-sm py-4 text-center">{t("dashboard.noExpenseData")}</p>
              )}
            </div>
          </div>

          {refunds.length > 0 && (
            <div>
              <p className="text-sm font-bold text-emerald-400 uppercase tracking-wider mb-3">{t("dashboard.refunds")}</p>
              <div className="space-y-1.5 max-h-[200px] overflow-y-auto pe-1">
                {refunds.map((d: { category: string; amount: number }, i: number) => {
                  const pct = totalRefunds > 0 ? (d.amount / totalRefunds) * 100 : 0;
                  const barWidth = (d.amount / maxRefund) * 100;
                  const icon = categoryIcons?.[d.category] ?? "";
                  return (
                    <div key={d.category} className="group flex items-center gap-2 py-1.5 px-2 rounded-lg hover:bg-[var(--surface-light)] transition-colors">
                      <span className="text-base w-6 text-center shrink-0">{icon || `${i + 1}.`}</span>
                      <span className="text-xs md:text-sm font-medium w-20 md:w-28 truncate shrink-0" title={d.category} dir="auto">{d.category}</span>
                      <div className="flex-1 h-5 bg-[var(--surface-light)] rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-emerald-600 to-emerald-400 transition-all duration-500"
                          style={{ width: `${barWidth}%` }}
                        />
                      </div>
                      <span className="text-xs md:text-sm font-bold tabular-nums w-16 md:w-24 text-end shrink-0">{formatCurrency(d.amount)}</span>
                      <span className="text-[10px] md:text-xs text-[var(--text-muted)] w-10 md:w-12 text-end shrink-0">{pct.toFixed(1)}%</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
