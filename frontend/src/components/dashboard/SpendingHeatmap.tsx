import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { CalendarDays } from "lucide-react";
import type { Transaction } from "../../types/transaction";
import { formatCurrency } from "../../utils/numberFormatting";

// Categories that are not discretionary spending.
const NON_EXPENSE = new Set([
  "Ignore", "Salary", "Other Income", "Investments", "Liabilities", "Credit Cards",
]);

/**
 * Current-month spending heatmap — a calendar grid where each day's cell is
 * shaded by how much was spent that day. Reuses the dashboard's already-fetched
 * transactions, so no extra request.
 */
export function SpendingHeatmap({ transactions }: { transactions: Transaction[] | undefined }) {
  const { t, i18n } = useTranslation();

  const { weeks, maxSpend, total } = useMemo(() => {
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const firstWeekday = new Date(year, month, 1).getDay(); // 0 = Sunday

    const perDay: Record<number, number> = {};
    for (const tx of transactions ?? []) {
      const dateStr = tx.date ?? "";
      const amount = tx.amount ?? 0;
      if (amount >= 0) continue;
      if (tx.category && NON_EXPENSE.has(tx.category)) continue;
      const d = new Date(dateStr);
      if (d.getFullYear() !== year || d.getMonth() !== month) continue;
      perDay[d.getDate()] = (perDay[d.getDate()] ?? 0) + Math.abs(amount);
    }

    const cells: ({ day: number; spend: number } | null)[] = [];
    for (let i = 0; i < firstWeekday; i++) cells.push(null);
    for (let day = 1; day <= daysInMonth; day++) {
      cells.push({ day, spend: perDay[day] ?? 0 });
    }
    while (cells.length % 7 !== 0) cells.push(null);

    const grid: (typeof cells)[] = [];
    for (let i = 0; i < cells.length; i += 7) grid.push(cells.slice(i, i + 7));

    const spends = Object.values(perDay);
    return {
      weeks: grid,
      maxSpend: spends.length ? Math.max(...spends) : 0,
      total: spends.reduce((s, v) => s + v, 0),
    };
  }, [transactions]);

  const weekdayLabels =
    i18n.language === "he"
      ? ["א", "ב", "ג", "ד", "ה", "ו", "ש"]
      : ["S", "M", "T", "W", "T", "F", "S"];

  const cellColor = (spend: number): string => {
    if (spend <= 0) return "bg-[var(--surface-light)]";
    const intensity = maxSpend > 0 ? spend / maxSpend : 0;
    if (intensity > 0.75) return "bg-rose-500";
    if (intensity > 0.5) return "bg-rose-500/70";
    if (intensity > 0.25) return "bg-rose-500/45";
    return "bg-rose-500/25";
  };

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] p-4 md:p-6">
      <div className="flex items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-[var(--primary)]/15 text-[var(--primary)]">
            <CalendarDays size={16} />
          </div>
          <p className="text-sm md:text-base font-bold">{t("dashboard.heatmap.title")}</p>
        </div>
        <div className="text-end">
          <p className="text-[10px] md:text-xs text-[var(--text-muted)]">{t("dashboard.heatmap.monthTotal")}</p>
          <p dir="ltr" className="text-sm md:text-base font-bold text-start">{formatCurrency(total)}</p>
        </div>
      </div>

      <div className="grid grid-cols-7 gap-1.5 mb-1.5">
        {weekdayLabels.map((label, i) => (
          <div key={i} className="text-center text-[9px] md:text-[10px] text-[var(--text-muted)] font-medium">{label}</div>
        ))}
      </div>
      <div className="space-y-1.5">
        {weeks.map((week, wi) => (
          <div key={wi} className="grid grid-cols-7 gap-1.5">
            {week.map((cell, ci) =>
              cell === null ? (
                <div key={ci} className="aspect-square" />
              ) : (
                <div
                  key={ci}
                  title={`${cell.day}: ${formatCurrency(cell.spend)}`}
                  className={`aspect-square rounded-md flex items-center justify-center ${cellColor(cell.spend)}`}
                >
                  <span className="text-[8px] md:text-[10px] text-[var(--text-primary)]/70">{cell.day}</span>
                </div>
              ),
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
