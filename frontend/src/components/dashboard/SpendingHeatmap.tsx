import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { CalendarDays } from "lucide-react";
import type { Transaction } from "../../types/transaction";
import { formatCurrency } from "../../utils/numberFormatting";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import type { DashboardCardSize } from "../../hooks/useDashboardLayout";

// Categories that are not discretionary spending.
const NON_EXPENSE = new Set([
  "Ignore", "Salary", "Other Income", "Investments", "Liabilities", "Credit Cards",
]);

type Cell = { day: number; spend: number } | null;

interface MonthData {
  year: number;
  month: number; // 0-11
  weeks: Cell[][];
  total: number;
}

/** Build the calendar grid + spending total for a single month. */
function buildMonth(transactions: Transaction[] | undefined, year: number, month: number): MonthData {
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const firstWeekday = new Date(year, month, 1).getDay(); // 0 = Sunday

  const perDay: Record<number, number> = {};
  for (const tx of transactions ?? []) {
    const amount = tx.amount ?? 0;
    if (amount >= 0) continue;
    if (tx.category && NON_EXPENSE.has(tx.category)) continue;
    const d = new Date(tx.date ?? "");
    if (d.getFullYear() !== year || d.getMonth() !== month) continue;
    perDay[d.getDate()] = (perDay[d.getDate()] ?? 0) + Math.abs(amount);
  }

  const cells: Cell[] = [];
  for (let i = 0; i < firstWeekday; i++) cells.push(null);
  for (let day = 1; day <= daysInMonth; day++) cells.push({ day, spend: perDay[day] ?? 0 });
  while (cells.length % 7 !== 0) cells.push(null);

  const weeks: Cell[][] = [];
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));

  return {
    year,
    month,
    weeks,
    total: Object.values(perDay).reduce((s, v) => s + v, 0),
  };
}

/**
 * Spending heatmap — a calendar grid where each day's cell is shaded by how much
 * was spent that day. Reuses the dashboard's already-fetched transactions, so no
 * extra request.
 *
 * When the card sits at half-row width on wide screens it shows the previous and
 * current month stacked vertically (shared colour scale so the shading is comparable).
 * A full-width card, or any narrow (mobile) render, shows the current month only.
 *
 * Cells use a fixed h-8 height (not aspect-square) so both one and two month views
 * stay within the dashboard card's 39rem height cap.
 */
export function SpendingHeatmap({
  transactions,
  size = "half",
}: {
  transactions: Transaction[] | undefined;
  size?: DashboardCardSize;
}) {
  const { t, i18n } = useTranslation();
  // Two months only when the card occupies half a row (>=lg). A full-width card
  // or the single-column mobile layout shows one month.
  const isWide = useMediaQuery("(min-width: 1024px)");
  const twoMonths = size === "half" && isWide;

  const months = useMemo(() => {
    const now = new Date();
    const list: MonthData[] = [];
    if (twoMonths) {
      const prev = new Date(now.getFullYear(), now.getMonth() - 1, 1);
      list.push(buildMonth(transactions, prev.getFullYear(), prev.getMonth()));
    }
    list.push(buildMonth(transactions, now.getFullYear(), now.getMonth()));
    return list;
  }, [transactions, twoMonths]);

  // Shared scale across the shown months so intensities are comparable.
  const maxSpend = useMemo(() => {
    let max = 0;
    for (const mo of months)
      for (const week of mo.weeks)
        for (const cell of week) if (cell && cell.spend > max) max = cell.spend;
    return max;
  }, [months]);

  const weekdayLabels =
    i18n.language === "he"
      ? ["א", "ב", "ג", "ד", "ה", "ו", "ש"]
      : ["S", "M", "T", "W", "T", "F", "S"];

  const monthLabel = (mo: MonthData) =>
    new Date(mo.year, mo.month, 1).toLocaleDateString(
      i18n.language === "he" ? "he-IL" : "en-US",
      { month: "long" },
    );

  const current = months[months.length - 1];

  return (
    <div className={`bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] ${twoMonths ? "p-3 md:p-4" : "p-4 md:p-6"}`}>
      <div className={`flex items-center justify-between gap-2 ${twoMonths ? "mb-2" : "mb-4"}`}>
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-[var(--primary)]/15 text-[var(--primary)]">
            <CalendarDays size={16} />
          </div>
          <p className="text-sm md:text-base font-bold">{t("dashboard.heatmap.title")}</p>
        </div>
        {!twoMonths && (
          <div className="text-end">
            <p className="text-[10px] md:text-xs text-[var(--text-muted)]">{t("dashboard.heatmap.monthTotal")}</p>
            <p dir="ltr" className="text-sm md:text-base font-bold text-start">{formatCurrency(current.total)}</p>
          </div>
        )}
      </div>

      <div className={twoMonths ? "space-y-3" : ""}>
        {months.map((mo) => (
          <MonthCalendar
            key={`${mo.year}-${mo.month}`}
            data={mo}
            maxSpend={maxSpend}
            weekdayLabels={weekdayLabels}
            label={twoMonths ? monthLabel(mo) : undefined}
          />
        ))}
      </div>
    </div>
  );
}

function MonthCalendar({
  data,
  maxSpend,
  weekdayLabels,
  label,
}: {
  data: MonthData;
  maxSpend: number;
  weekdayLabels: string[];
  /** When set, render a per-month header (name + total) above the grid. */
  label?: string;
}) {
  const cellColor = (spend: number): string => {
    if (spend <= 0) return "bg-[var(--surface-light)]";
    const intensity = maxSpend > 0 ? spend / maxSpend : 0;
    if (intensity > 0.75) return "bg-rose-500";
    if (intensity > 0.5) return "bg-rose-500/70";
    if (intensity > 0.25) return "bg-rose-500/45";
    return "bg-rose-500/25";
  };

  return (
    <div className="min-w-0">
      {label && (
        <div className="flex items-center justify-between gap-2 mb-1">
          <p className="text-[11px] md:text-xs font-semibold text-[var(--text-muted)]" dir="auto">{label}</p>
          <p dir="ltr" className="text-[11px] md:text-xs font-bold">{formatCurrency(data.total)}</p>
        </div>
      )}
      <div className="grid grid-cols-7 gap-1 mb-1">
        {weekdayLabels.map((l, i) => (
          <div key={i} className="text-center text-[9px] md:text-[10px] text-[var(--text-muted)] font-medium">{l}</div>
        ))}
      </div>
      <div className="space-y-1">
        {data.weeks.map((week, wi) => (
          <div key={wi} className="grid grid-cols-7 gap-1">
            {week.map((cell, ci) =>
              cell === null ? (
                <div key={ci} className="h-8" />
              ) : (
                <div
                  key={ci}
                  title={`${cell.day}: ${formatCurrency(cell.spend)}`}
                  className={`h-8 rounded-md flex items-center justify-center ${cellColor(cell.spend)}`}
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
