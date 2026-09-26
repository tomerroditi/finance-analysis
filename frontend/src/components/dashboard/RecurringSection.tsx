import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Check, Eye, EyeOff, Repeat, RotateCcw, X } from "lucide-react";
import {
  analyticsApi,
  type RecurringDecisionInput,
  type RecurringItem,
  type RecurringSummary,
} from "../../services/api";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { useScrollCap } from "../../hooks/useScrollCap";
import { applyDecisions } from "./recurringOptimistic";
import { qkPrefix } from "../../services/queryKeys";
import { Skeleton } from "../common/Skeleton";
import { formatCurrency } from "../../utils/numberFormatting";
import { formatDate } from "../../utils/dateFormatting";

const STATUS_STYLES: Record<RecurringItem["status"], string> = {
  active: "bg-[var(--surface-light)] text-[var(--text-muted)]",
  new: "bg-blue-500/15 text-blue-300",
  price_changed: "bg-amber-500/15 text-amber-300",
  ended: "bg-rose-500/15 text-rose-300",
};

/**
 * Dashboard subscriptions / recurring-charges panel from ``/analytics/recurring``.
 *
 * Detection is a heuristic, so nothing it finds is treated as a real
 * commitment until the user says so: candidates land in a "needs review"
 * block at the top and only move into the list — and into the monthly total,
 * the budget Overview's committed spend and the forecast — once confirmed.
 */
export function RecurringSection() {
  const { t } = useTranslation();
  const qk = useQueryKeys();
  const queryClient = useQueryClient();
  const [showDismissed, setShowDismissed] = useState(false);
  const [showEnded, setShowEnded] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: qk.analytics.recurring(showDismissed),
    queryFn: async () => {
      const res = await analyticsApi.getRecurring(showDismissed);
      return res.data;
    },
  });

  const decide = useMutation({
    mutationFn: (decisions: RecurringDecisionInput[]) =>
      analyticsApi.setRecurringDecisions(decisions),
    // Show the verdict at once. The write itself is quick, but it invalidates
    // every derived read on the dashboard, so waiting for the sweep that
    // follows left the item sitting in "needs review" long enough to look
    // ignored. Both cached variants are patched — the dismissed-inclusive
    // list is the same data under a second key, and leaving it stale would
    // make the "show dismissed" toggle contradict the list above it.
    onMutate: async (decisions) => {
      const filter = { queryKey: qkPrefix.recurring };
      await queryClient.cancelQueries(filter);
      const snapshot = queryClient.getQueriesData<RecurringSummary>(filter);

      snapshot.forEach(([key, summary]) => {
        if (!summary) return;
        // The key is ["analytics", "recurring", includeDismissed, demo].
        queryClient.setQueryData<RecurringSummary>(
          key,
          applyDecisions(summary, decisions, key[2] === true),
        );
      });
      return { snapshot };
    },
    onError: (_error, _decisions, context) => {
      context?.snapshot.forEach(([key, summary]) =>
        queryClient.setQueryData(key, summary),
      );
    },
    // No invalidation here on purpose. A verdict moves money between
    // "committed" and "free to spend", so the budget Overview and every
    // analytics figure built on recurring charges do have to be refetched —
    // but the shared `MutationCache.onSuccess` in `queryClient.ts` already
    // sweeps them 200 ms after the last mutation settles. Sweeping again
    // from here just ran every one of those queries twice per click (and
    // un-debounced), which is overhead on exactly the path that felt slow.
    // On failure the rollback above restores the server's own last answer,
    // so there is nothing to refetch either.
  });

  const items = data?.items ?? [];
  // A charge whose last sighting is long past is over, and an ended one is
  // never in the monthly total, never in committed spend and has no next
  // date — so it is history, not a commitment, and listing it alongside the
  // live ones only pads the card. It stays one click away rather than gone:
  // a cancellation that turns out to be a billing gap comes straight back.
  const ended = items.filter((item) => item.status === "ended");
  const live = showEnded ? items : items.filter((item) => item.status !== "ended");
  // Detection is a heuristic, so the review list leads with the candidates it
  // is most sure about — the reviewer works down from the obvious ones rather
  // than meeting a marginal guess first.
  const pending = live
    .filter((item) => item.confirmation === "pending")
    .sort((a, b) => b.confidence - a.confidence);
  const confirmed = live.filter((item) => item.confirmation === "confirmed");
  // Both lists cap themselves, and only once a cap would hide a row — see
  // `useScrollCap`: a list that scrolls by a hair swallows the drag meant for
  // the page.
  const [pendingListRef, pendingCapped] = useScrollCap(220, pending.length);
  const [confirmedListRef, confirmedCapped] = useScrollCap(360, confirmed.length);
  // Deliberately off `items`, not `live`: "show dismissed" is an explicit
  // request to see everything that was ruled out, and its count comes from
  // the backend over every candidate. Filtering it by `showEnded` too would
  // let the toggle promise two and reveal one.
  const dismissed = items.filter((item) => item.confirmation === "dismissed");
  // "Nothing detected", not "nothing on screen". Dismissed candidates are
  // absent from `items` in this view but still real, and the empty state
  // carries no toggles — so counting this as empty would strand them with no
  // way back. Ended ones are in `items` already, just filtered out of `live`.
  const isEmpty = items.length === 0 && (data?.dismissed_count ?? 0) === 0;

  // Deliberately not gated on `decide.isPending`. Disabling every verdict
  // button while one request is in flight locked the whole card for as long
  // as the write took — seconds on a real database — and a click landing in
  // that window was silently dropped, which reads as the approval not having
  // been accepted. The row moves optimistically the moment it is clicked, so
  // the disabled state communicated nothing the list was not already showing,
  // and a repeated verdict is idempotent.
  // The label, amount and cadence ride along because the row already has
  // them: they are stored beside the verdict for audit, and the backend
  // would otherwise have to run a full detection pass per verdict to
  // recover what is on screen here.
  const verdict = (
    item: RecurringItem,
    decision: RecurringDecisionInput["decision"],
  ): RecurringDecisionInput => ({
    normalized: item.normalized,
    decision,
    label: item.label,
    amount: item.amount,
    cadence: item.cadence,
  });

  const decideOne = (item: RecurringItem, decision: RecurringDecisionInput["decision"]) =>
    decide.mutate([verdict(item, decision)]);

  const decideAll = (
    group: RecurringItem[],
    decision: RecurringDecisionInput["decision"],
  ) => decide.mutate(group.map((item) => verdict(item, decision)));

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] p-4 md:p-6">
      <div className="flex items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-[var(--primary)]/15 text-[var(--primary)]">
            <Repeat size={16} />
          </div>
          <p className="text-sm md:text-base font-bold">{t("dashboard.recurring.title")}</p>
        </div>
        {!!data && confirmed.length > 0 && (
          <div className="text-end">
            <p className="text-[10px] md:text-xs text-[var(--text-muted)]">{t("dashboard.recurring.totalMonthly")}</p>
            <p dir="ltr" data-testid="recurring-total" className="text-sm md:text-base font-bold text-start">{formatCurrency(data.total_monthly)}</p>
          </div>
        )}
      </div>

      {isLoading ? (
        <Skeleton variant="card" className="h-40" />
      ) : isEmpty ? (
        <p className="text-[var(--text-muted)] text-sm py-6 text-center">{t("dashboard.recurring.empty")}</p>
      ) : (
        <div className="space-y-4">
          {pending.length > 0 && (
            <section
              aria-label={t("dashboard.recurring.review.title")}
              className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-2.5"
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <div className="min-w-0">
                  <p className="text-xs md:text-sm font-bold text-amber-300">
                    {t("dashboard.recurring.review.title")}
                  </p>
                  <p className="text-[10px] md:text-xs text-[var(--text-muted)]">
                    {t("dashboard.recurring.review.subtitle", {
                      count: pending.length,
                      amount: formatCurrency(data?.pending_monthly ?? 0),
                    })}
                  </p>
                </div>
                <button
                  type="button"
                  disabled={pending.length === 0}
                  onClick={() => decideAll(pending, "confirmed")}
                  className="shrink-0 text-[10px] md:text-xs px-2 py-1 rounded-lg bg-[var(--primary)]/15 text-[var(--primary)] hover:bg-[var(--primary)]/25 disabled:opacity-50 transition-colors"
                >
                  {t("dashboard.recurring.review.confirmAll")}
                </button>
              </div>

              {/* Capped so a long backlog of candidates cannot push the
                  confirmed charges out of the card's own scroll view — but
                  only once the cap hides a row, so a short list still lets a
                  drag across it scroll the page. */}
              <div
                ref={pendingListRef}
                className={`space-y-1.5 ${pendingCapped ? "max-h-[220px] overflow-y-auto pe-1" : ""}`}
              >
                {pending.map((item) => (
                  <div
                    key={item.normalized}
                    data-testid="recurring-pending-item"
                    className="flex items-center gap-2 py-2 px-2.5 rounded-lg bg-[var(--surface)]"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-xs md:text-sm font-medium truncate" dir="auto" title={item.label}>
                        {item.label}
                      </p>
                      <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                        <span className="text-[9px] md:text-[10px] text-[var(--text-muted)]">
                          {t(
                            item.amount_kind === "metered"
                              ? "dashboard.recurring.review.evidenceMetered"
                              : "dashboard.recurring.review.evidence",
                            {
                              cadence: t(
                                `dashboard.recurring.cadence.${item.cadence}`,
                              ),
                              count: item.occurrences,
                              amount: formatCurrency(item.amount),
                            },
                          )}
                        </span>
                        <span
                          className={`text-[9px] md:text-[10px] px-1.5 py-0.5 rounded ${
                            item.confidence >= 0.85
                              ? "bg-emerald-500/15 text-emerald-300"
                              : "bg-[var(--surface-light)] text-[var(--text-muted)]"
                          }`}
                        >
                          {t("dashboard.recurring.review.confidence", {
                            percent: Math.round(item.confidence * 100),
                          })}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        type="button"
                        aria-label={t("dashboard.recurring.review.confirm", { label: item.label })}
                        title={t("dashboard.recurring.review.confirm", { label: item.label })}
                        onClick={() => decideOne(item, "confirmed")}
                        className="p-2 rounded-lg bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25 transition-colors"
                      >
                        <Check size={16} />
                      </button>
                      <button
                        type="button"
                        aria-label={t("dashboard.recurring.review.dismiss", { label: item.label })}
                        title={t("dashboard.recurring.review.dismiss", { label: item.label })}
                        onClick={() => decideOne(item, "dismissed")}
                        className="p-2 rounded-lg bg-rose-500/15 text-rose-300 hover:bg-rose-500/25 transition-colors"
                      >
                        <X size={16} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {confirmed.length === 0 ? (
            <p className="text-[var(--text-muted)] text-xs py-2 text-center">
              {t(
                pending.length > 0
                  ? "dashboard.recurring.noneConfirmed"
                  : "dashboard.recurring.noneRunning",
              )}
            </p>
          ) : (
            <div
              ref={confirmedListRef}
              className={`space-y-1.5 ${confirmedCapped ? "max-h-[360px] overflow-y-auto pe-1" : ""}`}
            >
              {confirmed.map((item) => (
                <div
                  key={item.normalized}
                  data-testid="recurring-confirmed-item"
                  className={`group flex items-center gap-2 py-2 px-2.5 rounded-lg hover:bg-[var(--surface-light)]/40 transition-colors ${
                    item.status === "ended" ? "opacity-60" : ""
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <p className="text-xs md:text-sm font-medium truncate" dir="auto" title={item.label}>{item.label}</p>
                    <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                      <span className="text-[9px] md:text-[10px] px-1.5 py-0.5 rounded bg-[var(--surface-light)] text-[var(--text-muted)]">
                        {t(`dashboard.recurring.cadence.${item.cadence}`)}
                      </span>
                      {item.status !== "active" && (
                        <span className={`text-[9px] md:text-[10px] px-1.5 py-0.5 rounded ${STATUS_STYLES[item.status]}`}>
                          {t(`dashboard.recurring.status.${item.status}`)}
                        </span>
                      )}
                      {item.status !== "ended" && (
                        <span className="text-[9px] md:text-[10px] text-[var(--text-muted)]">
                          {t("dashboard.recurring.next", { date: formatDate(item.next_expected_date) })}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="text-end shrink-0">
                    <p dir="ltr" className="text-xs md:text-sm font-bold tabular-nums">{formatCurrency(item.amount)}</p>
                    <p className="text-[9px] md:text-[10px] text-[var(--text-muted)]">
                      {t("dashboard.recurring.perMonth", { amount: formatCurrency(item.monthly_equivalent) })}
                    </p>
                  </div>
                  {/* Two different retractions: send it back to review when
                      the verdict was premature, or drop it for good when it
                      was never a subscription. Hidden until hover on a
                      pointer device, always present on touch. */}
                  <div className="flex items-center gap-1 shrink-0 md:opacity-0 md:group-hover:opacity-100 md:focus-within:opacity-100 transition-opacity">
                    <button
                      type="button"
                      aria-label={t("dashboard.recurring.review.unconfirm", { label: item.label })}
                      title={t("dashboard.recurring.review.unconfirm", { label: item.label })}
                      onClick={() => decideOne(item, "pending")}
                      className="p-2 rounded-lg text-[var(--text-muted)] hover:bg-[var(--surface-light)] transition-colors"
                    >
                      <RotateCcw size={16} />
                    </button>
                    <button
                      type="button"
                      data-testid="recurring-remove"
                      aria-label={t("dashboard.recurring.review.remove", { label: item.label })}
                      title={t("dashboard.recurring.review.remove", { label: item.label })}
                      onClick={() => decideOne(item, "dismissed")}
                      className="p-2 rounded-lg text-[var(--text-muted)] hover:bg-rose-500/15 hover:text-rose-300 transition-colors"
                    >
                      <X size={16} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {showDismissed && dismissed.length > 0 && (
            <div className="space-y-1.5 border-t border-[var(--surface-light)] pt-2">
              {dismissed.map((item) => (
                <div
                  key={item.normalized}
                  data-testid="recurring-dismissed-item"
                  className="flex items-center gap-2 py-2 px-2.5 rounded-lg opacity-60"
                >
                  {/* What it cost and how often it billed, because that is
                      what tells the user whether ruling it out was a
                      mistake — a bare merchant label does not. */}
                  <div className="min-w-0 flex-1">
                    <p className="text-xs md:text-sm font-medium truncate" dir="auto" title={item.label}>
                      {item.label}
                    </p>
                    <p className="text-[9px] md:text-[10px] text-[var(--text-muted)]">
                      {t("dashboard.recurring.review.evidence", {
                        cadence: t(`dashboard.recurring.cadence.${item.cadence}`),
                        count: item.occurrences,
                        amount: formatCurrency(item.amount),
                      })}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => decideOne(item, "pending")}
                    className="shrink-0 text-[10px] md:text-xs px-2 py-1 rounded-lg bg-[var(--surface-light)] hover:bg-[var(--surface-light)]/70 transition-colors"
                  >
                    {t("dashboard.recurring.review.restore")}
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="flex items-center gap-3 flex-wrap">
            {(showDismissed || (data?.dismissed_count ?? 0) > 0) && (
              <button
                type="button"
                onClick={() => setShowDismissed((shown) => !shown)}
                className="flex items-center gap-1.5 text-[10px] md:text-xs text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
              >
                {showDismissed ? <EyeOff size={12} /> : <Eye size={12} />}
                {showDismissed
                  ? t("dashboard.recurring.review.hideDismissed")
                  : t("dashboard.recurring.review.showDismissed", {
                      count: data?.dismissed_count ?? 0,
                    })}
              </button>
            )}
            {/* Counted off the unfiltered list, so the toggle still offers
                the way back when every charge on the card has ended. */}
            {(showEnded || ended.length > 0) && (
              <button
                type="button"
                data-testid="recurring-toggle-ended"
                onClick={() => setShowEnded((shown) => !shown)}
                className="flex items-center gap-1.5 text-[10px] md:text-xs text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
              >
                {showEnded ? <EyeOff size={12} /> : <Eye size={12} />}
                {showEnded
                  ? t("dashboard.recurring.review.hideEnded")
                  : t("dashboard.recurring.review.showEnded", {
                      count: ended.length,
                    })}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
