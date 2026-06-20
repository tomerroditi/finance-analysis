import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  analyticsApi,
  cashBalancesApi,
  bankBalancesApi,
  investmentsApi,
  transactionsApi,
  taggingApi,
  type BankBalance,
} from "../services/api";
import { BudgetSpendingGauge } from "../components/dashboard/BudgetSection";
import { RecentTransactionsFeed } from "../components/dashboard/RecentTransactionsSection";
import { CashFlowForecastSection } from "../components/dashboard/CashFlowForecastCard";
import { InsightsStrip } from "../components/dashboard/InsightsStrip";
import { RecurringSection } from "../components/dashboard/RecurringSection";
import { GoalsSection } from "../components/dashboard/GoalsSection";
import { SpendingHeatmap } from "../components/dashboard/SpendingHeatmap";
import { IncomeBySourceCard } from "../components/dashboard/IncomeBySourceCard";
import { DashboardChartsPanel } from "../components/dashboard/DashboardChartsPanel";
import { Skeleton } from "../components/common/Skeleton";
import { EmptyState } from "../components/common/EmptyState";
import { DemoModeConfirmPopover } from "../components/common/DemoModeConfirmPopover";
import { useDemoMode } from "../context/DemoModeContext";
import { useTranslation } from "react-i18next";
import { formatCurrency, formatChange, formatPercentChange } from "../utils/numberFormatting";
import { useDashboardLayout, cardSize, type DashboardCardId } from "../hooks/useDashboardLayout";


/* ------------------------------------------------------------------ */
/*  Helper sub-components (extracted to avoid creating during render)  */
/* ------------------------------------------------------------------ */

function MomBadge({ mom }: { mom: { delta: number; percent: number | null } | null }) {
  if (!mom) return null;
  const { delta, percent } = mom;
  const color = delta >= 0 ? "text-emerald-400" : "text-rose-400";
  return (
    <span dir="ltr" className={`text-[10px] font-semibold ${color}`}>
      {formatChange(delta)} {percent !== null && `(${formatPercentChange(percent)})`}
    </span>
  );
}

function BreakdownList({ items }: { items: { name: string; amount: number }[] }) {
  return (
    <div className="mt-2 pt-2 border-t border-[var(--surface-light)] space-y-1">
      {items.map((item) => (
        <div key={item.name} className="flex justify-between text-xs">
          <span className="text-[var(--text-muted)] truncate me-2" dir="auto">{item.name}</span>
          <span className="tabular-nums font-medium shrink-0" dir="ltr">{formatCurrency(item.amount)}</span>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Section 1 — Financial Health Header (pinned, not customizable)    */
/* ------------------------------------------------------------------ */

function FinancialHealthHeader({
  netWorthData,
  cashBalances,
  bankBalances,
  portfolioAllocation,
  isLoading,
}: {
  netWorthData:
    | { month: string; bank_balance: number; investment_value: number; cash: number; net_worth: number }[]
    | undefined;
  cashBalances: { account_name: string; balance: number }[] | undefined;
  bankBalances: BankBalance[] | undefined;
  portfolioAllocation: { name: string; balance: number }[] | undefined;
  isLoading: boolean;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);

  const latestNetWorth = netWorthData?.length ? netWorthData[netWorthData.length - 1] : null;
  const previousNetWorth =
    netWorthData && netWorthData.length >= 2 ? netWorthData[netWorthData.length - 2] : null;

  const calcMom = (current: number | undefined, previous: number | undefined) => {
    if (current == null || previous == null) return null;
    const delta = current - previous;
    const percent = previous !== 0 ? (delta / Math.abs(previous)) * 100 : null;
    return { delta, percent };
  };

  const netWorthMom = calcMom(latestNetWorth?.net_worth, previousNetWorth?.net_worth);
  const bankMom = calcMom(latestNetWorth?.bank_balance, previousNetWorth?.bank_balance);
  const investmentMom = calcMom(latestNetWorth?.investment_value, previousNetWorth?.investment_value);
  const cashMom = calcMom(latestNetWorth?.cash, previousNetWorth?.cash);

  const totalCash = cashBalances?.reduce((sum, c) => sum + c.balance, 0) ?? 0;
  const openInvestments = portfolioAllocation?.filter((i) => i.balance > 0);

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} variant="card" className="h-16" />
        ))}
      </div>
    );
  }

  return (
    <div
      className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-3 cursor-pointer"
      onClick={() => setExpanded((v) => !v)}
    >
      {/* Net Worth */}
      <div className="bg-[var(--surface)] rounded-xl px-3 sm:px-4 py-2.5 sm:py-3 border border-[var(--surface-light)] overflow-hidden">
        <p className="text-[10px] sm:text-xs text-[var(--text-muted)] truncate">{t("dashboard.netWorth")}</p>
        <p dir="ltr" className="text-base sm:text-lg font-bold mt-0.5 truncate">
          {latestNetWorth ? formatCurrency(latestNetWorth.net_worth) : "--"}
        </p>
        <MomBadge mom={netWorthMom} />
      </div>

      {/* Bank Balance */}
      <div className="bg-[var(--surface)] rounded-xl px-3 sm:px-4 py-2.5 sm:py-3 border border-[var(--surface-light)] overflow-hidden">
        <p className="text-[10px] sm:text-xs text-[var(--text-muted)] truncate">{t("dashboard.bankBalance")}</p>
        <p dir="ltr" className="text-base sm:text-lg font-bold mt-0.5 truncate">
          {latestNetWorth ? formatCurrency(latestNetWorth.bank_balance) : "--"}
        </p>
        <MomBadge mom={bankMom} />
        {expanded && bankBalances && bankBalances.length > 0 && (
          <BreakdownList
            items={bankBalances.map((b) => ({ name: b.account_name, amount: b.balance }))}
          />
        )}
      </div>

      {/* Investments */}
      <div className="bg-[var(--surface)] rounded-xl px-3 sm:px-4 py-2.5 sm:py-3 border border-[var(--surface-light)] overflow-hidden">
        <p className="text-[10px] sm:text-xs text-[var(--text-muted)] truncate">{t("dashboard.investmentValue")}</p>
        <p dir="ltr" className="text-base sm:text-lg font-bold mt-0.5 truncate">
          {latestNetWorth ? formatCurrency(latestNetWorth.investment_value) : "--"}
        </p>
        <MomBadge mom={investmentMom} />
        {expanded && openInvestments && openInvestments.length > 0 && (
          <BreakdownList
            items={openInvestments.map((i) => ({ name: i.name, amount: i.balance }))}
          />
        )}
      </div>

      {/* Cash */}
      <div className="bg-[var(--surface)] rounded-xl px-3 sm:px-4 py-2.5 sm:py-3 border border-[var(--surface-light)] overflow-hidden">
        <p className="text-[10px] sm:text-xs text-[var(--text-muted)] truncate">{t("dashboard.cashBalance")}</p>
        <p dir="ltr" className="text-base sm:text-lg font-bold mt-0.5 truncate">{formatCurrency(totalCash)}</p>
        <MomBadge mom={cashMom} />
        {expanded && cashBalances && cashBalances.length > 0 && (
          <BreakdownList
            items={cashBalances.map((c) => ({ name: c.account_name, amount: c.balance }))}
          />
        )}
      </div>

    </div>
  );
}

/* ================================================================== */
/*  Main Dashboard Component                                          */
/* ================================================================== */

export function Dashboard() {
  const { t } = useTranslation();
  const { isDemoMode } = useDemoMode();
  const navigate = useNavigate();
  const [showDemoConfirm, setShowDemoConfirm] = useState(false);
  const { layout } = useDashboardLayout();

  // ---- Queries used by the page shell + the customizable cards ----

  const { data: cashBalances } = useQuery({
    queryKey: ["cash-balances", isDemoMode],
    queryFn: () => cashBalancesApi.getAll().then((res) => res.data),
  });

  const { data: bankBalances } = useQuery({
    queryKey: ["bank-balances", isDemoMode],
    queryFn: () => bankBalancesApi.getAll().then((res) => res.data),
  });

  const { data: portfolioData } = useQuery({
    queryKey: ["portfolio-analysis", isDemoMode],
    queryFn: () => investmentsApi.getPortfolioAnalysis().then((res) => res.data),
  });

  const { data: netWorthData, isLoading: netWorthLoading } = useQuery({
    queryKey: ["net-worth-over-time", isDemoMode],
    queryFn: async () => {
      const res = await analyticsApi.getNetWorthOverTime();
      return res.data;
    },
  });

  const { data: allTransactions, isLoading: transactionsLoading } = useQuery({
    queryKey: ["all-transactions", isDemoMode],
    queryFn: async () => {
      const res = await transactionsApi.getAll(undefined, false);
      return res.data;
    },
  });

  const { data: categoryIcons } = useQuery({
    queryKey: ["category-icons", isDemoMode],
    queryFn: async () => {
      const res = await taggingApi.getIcons();
      return res.data;
    },
  });

  // ---- Render ----

  const isDbEmpty =
    !transactionsLoading && (allTransactions?.length ?? 0) === 0;

  if (isDbEmpty) {
    return (
      <EmptyState
        title={t("emptyStates.dashboard.title")}
        description={t("emptyStates.dashboard.description")}
        steps={[
          {
            title: t("emptyStates.connectStep.title"),
            description: t("emptyStates.connectStep.description"),
          },
          {
            title: t("emptyStates.scrapeStep.title"),
            description: t("emptyStates.scrapeStep.description"),
          },
          {
            title: t("emptyStates.analyseStep.title"),
            description: t("emptyStates.analyseStep.description"),
          },
        ]}
        cta={{
          label: t("emptyStates.connectAccounts"),
          onClick: () => navigate("/data-sources"),
        }}
        secondary={{
          label: t("emptyStates.tryDemoMode"),
          onClick: () => setShowDemoConfirm(true),
        }}
        footer={
          showDemoConfirm ? (
            <DemoModeConfirmPopover onClose={() => setShowDemoConfirm(false)} />
          ) : undefined
        }
      />
    );
  }

  // Each customizable card maps its id to a renderer. The page renders only the
  // cards in `layout.order` (hidden ones are excluded), in stored order.
  const cardRenderers: Record<DashboardCardId, () => ReactNode> = {
    forecast: () => <CashFlowForecastSection />,
    insights: () => <InsightsStrip />,
    budget: () => <BudgetSpendingGauge categoryIcons={categoryIcons} />,
    recent: () => (
      <RecentTransactionsFeed
        transactions={allTransactions}
        categoryIcons={categoryIcons}
        isLoading={transactionsLoading}
      />
    ),
    recurring: () => <RecurringSection />,
    goals: () => <GoalsSection />,
    heatmap: () => <SpendingHeatmap transactions={allTransactions} />,
    income_by_source: () => <IncomeBySourceCard />,
    charts: () => <DashboardChartsPanel />,
  };

  return (
    <div className="space-y-4 md:space-y-8 animate-in fade-in duration-500">
      {/* Pinned: Financial Health Header (KPI cards) */}
      <FinancialHealthHeader
        netWorthData={netWorthData}
        cashBalances={cashBalances}
        bankBalances={bankBalances}
        portfolioAllocation={portfolioData?.allocation}
        isLoading={netWorthLoading}
      />

      {/* Customizable region: 2-column grid on wide screens (>=lg). Full-size
          cards span both columns; half-size cards take one. Native
          grid-auto-flow: row (no `dense`) fills top->bottom, start->end and
          honors document.dir for RTL automatically — a half card with no half
          neighbour before a full card leaves an empty gap, and the stored order
          is preserved exactly.

          Every cell is a fixed height on >=lg (`lg:auto-rows-[var(--dash-card-h)]`)
          so all blocks are the same size regardless of content. Each card fills
          its cell (`[&>*]:h-full`) and scrolls its own overflow
          (`[&>*]:overflow-y-auto`) instead of stretching the row. On mobile the
          grid is a single column with natural heights. */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-8 lg:auto-rows-[var(--dash-card-h)] [--dash-card-h:32rem]">
        {layout.order.map((id) => (
          <div
            key={id}
            data-card-id={id}
            data-card-size={cardSize(id)}
            className={`min-w-0 [&>*]:h-full [&>*]:overflow-y-auto ${
              cardSize(id) === "full" ? "lg:col-span-2" : ""
            }`}
          >
            {cardRenderers[id]()}
          </div>
        ))}
      </div>
    </div>
  );
}
