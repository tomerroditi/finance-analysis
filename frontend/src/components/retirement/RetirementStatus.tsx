import { useTranslation } from "react-i18next";
import {
  TrendingUp,
  Wallet,
  PiggyBank,
  ArrowUpDown,
  DollarSign,
  Percent,
} from "lucide-react";
import type { RetirementStatus as StatusType } from "../../services/api";

interface Props {
  status: StatusType;
}

const formatCurrency = (value: number) =>
  new Intl.NumberFormat("he-IL", {
    style: "currency",
    currency: "ILS",
    maximumFractionDigits: 0,
  }).format(value);

export function RetirementStatus({ status }: Props) {
  const { t } = useTranslation();

  const cards = [
    {
      key: "netWorth",
      icon: TrendingUp,
      value: formatCurrency(status.net_worth),
      color: "text-emerald-400",
    },
    {
      key: "avgMonthlyIncome",
      icon: DollarSign,
      value: formatCurrency(status.avg_monthly_income),
      color: "text-blue-400",
    },
    {
      key: "avgMonthlyExpenses",
      icon: Wallet,
      value: formatCurrency(status.avg_monthly_expenses),
      color: "text-rose-400",
    },
    {
      key: "monthlySavings",
      icon: PiggyBank,
      value: formatCurrency(status.monthly_savings),
      color: status.monthly_savings >= 0 ? "text-emerald-400" : "text-rose-400",
    },
    {
      key: "savingsRate",
      icon: Percent,
      value: `${status.savings_rate}%`,
      color:
        status.savings_rate >= 50
          ? "text-emerald-400"
          : status.savings_rate >= 20
            ? "text-amber-400"
            : "text-rose-400",
    },
    {
      key: "totalInvestments",
      icon: ArrowUpDown,
      value: formatCurrency(status.total_investments),
      color: "text-purple-400",
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
      {cards.map((card) => (
        <div
          key={card.key}
          className="p-4 rounded-xl bg-[var(--surface)] border border-[var(--surface-light)]"
        >
          <div className="flex items-center gap-2 mb-2">
            <card.icon size={16} className={card.color} />
            <span className="text-xs text-[var(--text-muted)] truncate">
              {t(`earlyRetirement.status.${card.key}`)}
            </span>
          </div>
          <div className={`text-lg font-bold ${card.color}`} dir="ltr">
            {card.value}
          </div>
        </div>
      ))}
    </div>
  );
}
