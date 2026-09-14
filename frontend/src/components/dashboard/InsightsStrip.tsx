import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Info, Sparkles, Lightbulb, X, Undo2 } from "lucide-react";
import { analyticsApi, type Insight } from "../../services/api";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { useDashboardLayout, type DashboardCardId } from "../../hooks/useDashboardLayout";
import { formatCurrency } from "../../utils/numberFormatting";

const SEVERITY_STYLES: Record<Insight["severity"], { box: string; icon: typeof Info }> = {
  warning: { box: "bg-amber-500/10 border-amber-500/25 text-amber-300", icon: AlertTriangle },
  info: { box: "bg-blue-500/10 border-blue-500/25 text-blue-300", icon: Info },
  positive: { box: "bg-emerald-500/10 border-emerald-500/25 text-emerald-300", icon: Sparkles },
};

/**
 * Insight codes that only restate what a full dashboard card already shows:
 * the "This Month" hero *is* the pace projection, and the Subscriptions panel
 * already carries the review queue and each item's new / price-changed badge.
 *
 * Which cards are on screen is a browser-local layout preference, so the
 * backend can't make this call — it ships every insight it finds and the strip
 * drops the ones the user is already reading elsewhere. Hide the sibling card
 * and its insight comes back, which is the point: the strip fills the gap
 * rather than duplicating the page.
 */
const RESTATED_BY: Partial<Record<string, DashboardCardId>> = {
  overspendPace: "forecast",
  onTrack: "forecast",
  recurringToReview: "recurring",
  newRecurring: "recurring",
  priceIncrease: "recurring",
  priceDecrease: "recurring",
};

/**
 * Build the human-readable message for an insight by mapping its ``code`` to a
 * translated, interpolated string. Currency/labels are formatted client-side so
 * copy stays bilingual without backend string formatting.
 */
function useInsightMessage() {
  const { t } = useTranslation();
  return (insight: Insight): string => {
    const d = insight.data;
    const money = (v: unknown) => formatCurrency(typeof v === "number" ? v : Number(v) || 0);
    switch (insight.code) {
      case "categorySpike":
        return t("dashboard.insights.categorySpike", {
          percent: d.percent, category: d.category, amount: money(d.amount),
        });
      case "overspendPace":
        return t("dashboard.insights.overspendPace", { amount: money(d.amount) });
      case "onTrack":
        return t("dashboard.insights.onTrack", { amount: money(d.amount) });
      case "newRecurring":
        return t("dashboard.insights.newRecurring", {
          label: d.label, amount: money(d.amount),
          cadence: t(`dashboard.recurring.cadence.${d.cadence}`),
        });
      case "priceIncrease":
        return t("dashboard.insights.priceIncrease", { label: d.label, delta: money(d.delta) });
      case "priceDecrease":
        return t("dashboard.insights.priceDecrease", { label: d.label, delta: money(d.delta) });
      case "largeTransaction":
        return t("dashboard.insights.largeTransaction", { label: d.label, amount: money(d.amount) });
      case "recurringToReview":
        return t("dashboard.insights.recurringToReview", {
          count: Number(d.count) || 0, amount: money(d.amount),
        });
      default:
        return "";
    }
  };
}

/** Horizontal strip of rule-based insight cards from ``/analytics/insights``. */
export function InsightsStrip() {
  const { t } = useTranslation();
  const qk = useQueryKeys();
  const queryClient = useQueryClient();
  const message = useInsightMessage();
  const { layout } = useDashboardLayout();
  // The key of the card just dismissed, so a misclick has a way back. Kept in
  // component state rather than derived: it is about this interaction, not
  // about what the server knows.
  const [undoKey, setUndoKey] = useState<string | null>(null);

  const { data } = useQuery({
    queryKey: qk.analytics.insights(),
    queryFn: async () => {
      const res = await analyticsApi.getInsights();
      return res.data;
    },
    // This is the one card whose contents the user edits, by dismissing. The
    // persisted IndexedDB snapshot hydrates instantly on reload and would
    // otherwise count as fresh for the global five minutes — long enough to
    // show a card the user has already waved away, because the snapshot is
    // throttled and can predate the dismissal. Revalidate on every mount.
    staleTime: 0,
  });

  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: qk.analytics.insights() });

  const dismiss = useMutation({
    mutationFn: (key: string) => analyticsApi.dismissInsight(key),
    // Drop the card from the cache before the round trip: a card that lingers
    // until the refetch lands reads as a click that did not register. The
    // refetch still follows, because dismissing frees a slot the backend may
    // fill with the runner-up it was holding back.
    onMutate: async (key) => {
      await queryClient.cancelQueries({ queryKey: qk.analytics.insights() });
      const previous = queryClient.getQueryData<Insight[]>(qk.analytics.insights());
      queryClient.setQueryData<Insight[]>(qk.analytics.insights(), (old) =>
        (old ?? []).filter((insight) => insight.key !== key),
      );
      return { previous };
    },
    onError: (_error, _key, context) => {
      if (context?.previous) {
        queryClient.setQueryData(qk.analytics.insights(), context.previous);
      }
    },
    onSuccess: (_res, key) => setUndoKey(key),
    onSettled: refresh,
  });

  const restore = useMutation({
    mutationFn: (key: string) => analyticsApi.restoreInsight(key),
    onSuccess: () => {
      setUndoKey(null);
      refresh();
    },
  });

  const visible = (data ?? [])
    .filter((insight) => {
      const restatedBy = RESTATED_BY[insight.code];
      return !restatedBy || layout.hidden.includes(restatedBy);
    })
    // A code this build has no copy for renders as an empty card — better to
    // show nothing than a coloured box with an icon and no sentence.
    .map((insight) => ({ insight, text: message(insight) }))
    .filter(({ text }) => text !== "");

  if (visible.length === 0 && !undoKey) return null;

  return (
    <div>
      <div className="flex items-center gap-2 mb-2 text-[var(--text-muted)]">
        <Lightbulb size={14} />
        <p className="text-xs font-bold uppercase tracking-wider">{t("dashboard.insights.title")}</p>
        {!!undoKey && (
          <button
            type="button"
            onClick={() => restore.mutate(undoKey)}
            disabled={restore.isPending}
            className="ms-auto flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
          >
            <Undo2 size={12} />
            {t("dashboard.insights.undo")}
          </button>
        )}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 md:gap-3">
        {visible.map(({ insight, text }) => {
          const style = SEVERITY_STYLES[insight.severity];
          const Icon = style.icon;
          return (
            <div
              key={insight.key}
              data-testid="insight-card"
              data-insight-key={insight.key}
              className={`flex items-start gap-2 rounded-xl border px-3 py-2.5 ${style.box}`}
            >
              <Icon size={16} className="shrink-0 mt-0.5" />
              <p className="text-xs md:text-sm leading-snug text-[var(--text-primary)]" dir="auto">
                {text}
              </p>
              <button
                type="button"
                aria-label={t("dashboard.insights.dismiss")}
                title={t("dashboard.insights.dismiss")}
                data-testid="insight-dismiss"
                onClick={() => dismiss.mutate(insight.key)}
                disabled={dismiss.isPending}
                className="ms-auto shrink-0 -me-1 -mt-0.5 p-1 rounded-md text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-light)] transition-colors"
              >
                <X size={14} />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
