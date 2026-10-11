import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Check, Pencil, X } from "lucide-react";
import { savingsGoalsApi } from "../../services/api";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { qkPrefix } from "../../services/queryKeys";
import { formatCurrency } from "../../utils/numberFormatting";
import { Skeleton } from "../common/Skeleton";

/** How many past years the summary line names. */
const PAST_YEARS_SHOWN = 3;

/**
 * This year's savings against the target set for it.
 *
 * Saving is measured, not earmarked: what each month earned less what it
 * spent, with investing counted as saved and a goal's own income (and the
 * bills it pays) left out — see `backend/services/savings_goals/yearly.py`.
 * It sits above the goals because it answers the question they are for: how
 * much is being put aside at all.
 */
export function YearlySavingsSection() {
  const { t } = useTranslation();
  const qk = useQueryKeys();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: qk.savingsGoals.yearly(),
    queryFn: async () => (await savingsGoalsApi.getYearly()).data,
  });

  const save = useMutation({
    mutationFn: ({ year, target }: { year: number; target: number | null }) =>
      savingsGoalsApi.setYearlyTarget(year, target),
    onSuccess: (res) => {
      queryClient.setQueryData(qk.savingsGoals.yearly(), res.data);
      queryClient.invalidateQueries({ queryKey: qkPrefix.savingsGoals });
      setEditing(false);
    },
  });

  if (isLoading || !data) {
    return <Skeleton variant="card" className="h-28 mb-4" />;
  }

  const thisYear = data.years.find((row) => row.is_current);
  if (!thisYear) return null;
  const { pace } = data;
  const target = thisYear.target;
  const negative = thisYear.saved < 0;
  const percent = target ? (thisYear.saved / target) * 100 : 0;
  const past = data.years
    .filter((row) => !row.is_current && row.months.length > 0)
    .slice(-PAST_YEARS_SHOWN)
    .reverse();

  const startEditing = () => {
    setDraft(target ? String(target) : "");
    setEditing(true);
  };
  const submit = () => {
    const amount = Number(draft);
    save.mutate({ year: thisYear.year, target: draft.trim() && amount > 0 ? amount : null });
  };

  return (
    <div
      className="mb-4 rounded-xl border border-[var(--surface-light)] p-3"
      data-testid="yearly-savings"
    >
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs md:text-sm font-bold">
          {t("dashboard.goals.yearly.title", { year: thisYear.year })}
        </p>
        {!editing && (
          <button
            type="button"
            onClick={startEditing}
            className="flex items-center gap-1 text-[10px] md:text-xs text-[var(--text-muted)] hover:text-[var(--primary)] transition-colors"
          >
            <Pencil size={12} />
            {t(target ? "dashboard.goals.yearly.editTarget" : "dashboard.goals.yearly.setTarget")}
          </button>
        )}
      </div>

      {editing && (
        <form
          className="mt-2 flex items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          <input
            type="number"
            inputMode="decimal"
            min={0}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            aria-label={t("dashboard.goals.yearly.targetLabel", { year: thisYear.year })}
            placeholder={t("dashboard.goals.yearly.targetPlaceholder")}
            className="w-full rounded-lg bg-[var(--surface-light)] px-3 py-1.5 text-sm"
            dir="ltr"
          />
          <button
            type="submit"
            disabled={save.isPending}
            aria-label={t("common.save")}
            className="p-2 rounded-lg text-emerald-400 hover:bg-[var(--surface-light)] disabled:opacity-50"
          >
            <Check size={16} />
          </button>
          <button
            type="button"
            onClick={() => setEditing(false)}
            aria-label={t("common.cancel")}
            className="p-2 rounded-lg text-[var(--text-muted)] hover:bg-[var(--surface-light)]"
          >
            <X size={16} />
          </button>
        </form>
      )}

      <div className="mt-2 flex items-baseline justify-between gap-2">
        <p className="text-base md:text-lg font-bold" data-testid="yearly-saved">
          <span className={negative ? "text-red-400" : ""}>{formatCurrency(thisYear.saved)}</span>
          {target ? (
            <span className="text-xs md:text-sm font-normal text-[var(--text-muted)]">
              {" / "}
              {formatCurrency(target)}
            </span>
          ) : null}
        </p>
        {!!target && (
          <span className="text-[10px] md:text-xs text-[var(--text-muted)]" dir="ltr">
            {Math.round(percent)}%
          </span>
        )}
      </div>

      {!!target && (
        <div className="mt-1.5 h-2 rounded-full bg-[var(--surface-light)] overflow-hidden">
          <div
            className="h-2 rounded-full bg-gradient-to-r from-emerald-500 to-emerald-400 transition-all duration-500"
            style={{ width: `${Math.max(0, Math.min(100, percent))}%` }}
          />
        </div>
      )}

      {pace && (
        <div className="mt-1.5 space-y-0.5 text-[10px] md:text-xs text-[var(--text-muted)]">
          <p>
            {t("dashboard.goals.yearly.expected", { amount: formatCurrency(pace.expected_by_today) })}
            {" · "}
            <span className={pace.ahead_by >= 0 ? "text-emerald-400" : "text-amber-400"}>
              {t(
                pace.ahead_by >= 0 ? "dashboard.goals.yearly.ahead" : "dashboard.goals.yearly.behind",
                { amount: formatCurrency(Math.abs(pace.ahead_by)) },
              )}
            </span>
          </p>
          <p>
            {pace.needed_per_month > 0
              ? t("dashboard.goals.yearly.needed", {
                  amount: formatCurrency(pace.needed_per_month),
                  count: pace.months_left,
                })
              : t("dashboard.goals.yearly.reached")}
          </p>
        </div>
      )}

      {past.length > 0 && (
        <p className="mt-2 text-[10px] md:text-xs text-[var(--text-muted)]" data-testid="yearly-past">
          {past.map((row, index) => (
            <span key={row.year}>
              {index > 0 && " · "}
              <span className="font-semibold">{row.year}</span>{" "}
              <span className={row.saved < 0 ? "text-red-400" : ""}>{formatCurrency(row.saved)}</span>
              {row.target ? ` / ${formatCurrency(row.target)}` : ""}
            </span>
          ))}
        </p>
      )}
    </div>
  );
}

