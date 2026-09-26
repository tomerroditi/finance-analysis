import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ArrowUpRight, Landmark, Percent, Receipt, TrendingUp } from "lucide-react";
import { formatDate } from "../../utils/dateFormatting";
import { formatCurrency } from "../../utils/numberFormatting";
import type { PensionKpis } from "../../utils/pensionKpis";

function fmtPct(value: number): string {
  return `${value.toFixed(2)}%`;
}

function Tile({
  label,
  value,
  sub,
  icon: Icon,
  iconClass,
  valueClass = "text-white",
  className = "",
  testId,
}: {
  label: string;
  value: string;
  sub?: ReactNode;
  icon: React.ComponentType<{ size: number; className?: string }>;
  iconClass: string;
  valueClass?: string;
  className?: string;
  testId: string;
}) {
  return (
    <div
      data-testid={testId}
      className={`bg-[var(--surface)] rounded-xl border border-[var(--surface-light)] p-3 md:p-4 min-w-0 ${className}`}
    >
      <p className="flex items-center gap-1.5 text-[var(--text-muted)] text-[10px] uppercase tracking-widest font-bold">
        <Icon size={12} className={`shrink-0 ${iconClass}`} />
        <span className="truncate">{label}</span>
      </p>
      <p className={`text-lg md:text-xl font-black mt-1.5 whitespace-nowrap ${valueClass}`}>{value}</p>
      {sub && <p className="text-[var(--text-muted)] text-[11px] mt-0.5 leading-snug">{sub}</p>}
    </div>
  );
}

/**
 * Where the household's pension savings stand today: balance, what goes in,
 * what the funds earned and what they cost. The forward-looking figures live
 * in the retirement-outlook card above it.
 */
export function PensionKpiStrip({ kpis }: { kpis: PensionKpis }) {
  const { t } = useTranslation();
  const hasProfit = kpis.ytdProfit != null;
  const tileCount = hasProfit ? 5 : 4;
  // Two columns on a phone: an odd count lets the lead tile take a full row
  // instead of leaving a hole at the end.
  const leadSpan = tileCount % 2 === 1 ? "col-span-2 lg:col-span-1" : "";

  return (
    <div
      data-testid="pension-kpi-strip"
      className={`grid grid-cols-2 gap-1.5 ${hasProfit ? "lg:grid-cols-5" : "lg:grid-cols-4"}`}
    >
      <Tile
        testId="pension-kpi-balance"
        className={leadSpan}
        label={t("insurance.kpis.totalSavings")}
        value={formatCurrency(kpis.totalBalance)}
        sub={
          kpis.balanceAsOf
            ? t("insurance.kpis.fundsAsOf", {
                count: kpis.fundCount,
                date: formatDate(new Date(kpis.balanceAsOf)),
              })
            : t("insurance.kpis.funds", { count: kpis.fundCount })
        }
        icon={Landmark}
        iconClass="text-blue-400"
      />
      <Tile
        testId="pension-kpi-deposits"
        label={t("insurance.kpis.recentDeposits")}
        value={formatCurrency(kpis.recentDeposits)}
        sub={
          kpis.monthlyDepositAvg != null
            ? t("insurance.kpis.monthlyAvg", { amount: formatCurrency(kpis.monthlyDepositAvg) })
            : t("insurance.kpis.noRecentDeposits")
        }
        icon={ArrowUpRight}
        iconClass="text-emerald-400"
      />
      {hasProfit && (
        <Tile
          testId="pension-kpi-profit"
          label={t("insurance.kpis.ytdProfit")}
          value={formatCurrency(kpis.ytdProfit ?? 0)}
          valueClass={(kpis.ytdProfit ?? 0) < 0 ? "text-rose-400" : "text-emerald-400"}
          sub={t("insurance.kpis.sinceJanuary")}
          icon={TrendingUp}
          iconClass="text-emerald-400"
        />
      )}
      <Tile
        testId="pension-kpi-costs"
        label={t("insurance.kpis.costsThisYear")}
        value={formatCurrency(kpis.costsThisYear)}
        sub={t("insurance.kpis.costsBreakdown", {
          risk: formatCurrency(kpis.riskCost),
          fee: formatCurrency(kpis.managementFee),
        })}
        icon={Receipt}
        iconClass="text-rose-400"
      />
      <Tile
        testId="pension-kpi-fee"
        label={t("insurance.kpis.feeOnSavings")}
        value={kpis.feeOnSavingsPct != null ? fmtPct(kpis.feeOnSavingsPct) : "—"}
        sub={
          kpis.feeOnDepositsPct != null
            ? t("insurance.kpis.feeOnDeposits", { pct: fmtPct(kpis.feeOnDepositsPct) })
            : undefined
        }
        icon={Percent}
        iconClass="text-amber-400"
      />
    </div>
  );
}
