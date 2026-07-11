import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Info, Sparkles, Lightbulb } from "lucide-react";
import { analyticsApi, type Insight } from "../../services/api";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { formatCurrency } from "../../utils/numberFormatting";

const SEVERITY_STYLES: Record<Insight["severity"], { box: string; icon: typeof Info }> = {
  warning: { box: "bg-amber-500/10 border-amber-500/25 text-amber-300", icon: AlertTriangle },
  info: { box: "bg-blue-500/10 border-blue-500/25 text-blue-300", icon: Info },
  positive: { box: "bg-emerald-500/10 border-emerald-500/25 text-emerald-300", icon: Sparkles },
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
      default:
        return "";
    }
  };
}

/** Horizontal strip of rule-based insight cards from ``/analytics/insights``. */
export function InsightsStrip() {
  const { t } = useTranslation();
  const qk = useQueryKeys();
  const message = useInsightMessage();

  const { data } = useQuery({
    queryKey: qk.analytics.insights(),
    queryFn: async () => {
      const res = await analyticsApi.getInsights();
      return res.data;
    },
  });

  if (!data || data.length === 0) return null;

  return (
    <div>
      <div className="flex items-center gap-2 mb-2 text-[var(--text-muted)]">
        <Lightbulb size={14} />
        <p className="text-xs font-bold uppercase tracking-wider">{t("dashboard.insights.title")}</p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 md:gap-3">
        {data.map((insight, i) => {
          const style = SEVERITY_STYLES[insight.severity];
          const Icon = style.icon;
          return (
            <div
              key={`${insight.code}-${i}`}
              className={`flex items-start gap-2 rounded-xl border px-3 py-2.5 ${style.box}`}
            >
              <Icon size={16} className="shrink-0 mt-0.5" />
              <p className="text-xs md:text-sm leading-snug text-[var(--text-primary)]" dir="auto">
                {message(insight)}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
