import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { DollarSign } from "lucide-react";
import {
  analyticsApi,
  cashBalancesApi,
  bankBalancesApi,
  investmentsApi,
  transactionsApi,
  taggingApi,
  scrapingApi,
  type BankBalance,
} from "../services/api";
import { UpdateBankBalanceModal } from "../components/modals/UpdateBankBalanceModal";
import { BudgetSpendingGauge } from "../components/dashboard/BudgetSection";
import { RecentTransactionsFeed } from "../components/dashboard/RecentTransactionsSection";
import { CashFlowForecastSection } from "../components/dashboard/CashFlowForecastCard";
import { InsightsStrip } from "../components/dashboard/InsightsStrip";
import { RecurringSection } from "../components/dashboard/RecurringSection";
import { GoalsSection } from "../components/dashboard/GoalsSection";
import { SpendingHeatmap } from "../components/dashboard/SpendingHeatmap";
import { IncomeBySourceCard } from "../components/dashboard/IncomeBySourceCard";
import { IncomeExpensesCard } from "../components/dashboard/IncomeExpensesCard";
import { NetWorthCard } from "../components/dashboard/NetWorthCard";
import { CashFlowCard } from "../components/dashboard/CashFlowCard";
import { CategoryBreakdownCard } from "../components/dashboard/CategoryBreakdownCard";
import { Skeleton } from "../components/common/Skeleton";
import { DeferUntilVisible } from "../components/common/DeferUntilVisible";
import { EmptyState } from "../components/common/EmptyState";
import { DemoModeConfirmPopover } from "../components/common/DemoModeConfirmPopover";
import { useDemoMode } from "../context/DemoModeContext";
import { useTranslation } from "react-i18next";
import { formatCurrency, formatChange, formatPercentChange } from "../utils/numberFormatting";
import { formatMonthCompact } from "../utils/dateFormatting";
import { useDashboardLayout, cardSize, type DashboardCardId } from "../hooks/useDashboardLayout";


/* How many leading cards render eagerly on first paint. The rest defer until
 * scrolled near the viewport. Four covers the two half-card rows that sit above
 * the fold in the default layout, so the visible dashboard is never gated on a
 * skeleton while the heavier chart cards below load lazily. */
const EAGER_CARD_COUNT = 4;

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

function MonthlyChangeList({
  items,
}: {
  items: { month: string; label: string; change: number; percent: number | null }[];
}) {
  return (
    <div className="mt-2 pt-2 border-t border-[var(--surface-light)] space-y-1">
      {items.map((item) => (
        <div key={item.month} className="flex justify-between text-xs">
          <span className="text-[var(--text-muted)] truncate me-2" dir="auto">{item.label}</span>
          <span
            dir="ltr"
            className={`tabular-nums font-medium shrink-0 ${item.change >= 0 ? "text-emerald-400" : "text-rose-400"}`}
          >
            {formatChange(item.change)}
            {item.percent !== null && ` (${formatPercentChange(item.percent)})`}
          </span>
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
  lastScrapes,
  isLoading,
}: {
  netWorthData:
    | { month: string; bank_balance: number; investment_value: number; cash: number; net_worth: number }[]
    | undefined;
  cashBalances: { account_name: string; balance: number }[] | undefined;
  bankBalances: BankBalance[] | undefined;
  portfolioAllocation: { name: string; balance: number }[] | undefined;
  lastScrapes:
    | { service: string; provider: string; account_name: string; last_scrape_date: string | null }[]
    | undefined;
  isLoading: boolean;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const [balanceModalAccount, setBalanceModalAccount] = useState<
    { provider: string; account_name: string; balance: number } | null
  >(null);

  const isScrapedToday = (provider: string, accountName: string): boolean => {
    const scrape = lastScrapes?.find(
      (s) => s.provider === provider && s.account_name === accountName,
    );
    if (!scrape?.last_scrape_date) return false;
    const d = new Date(scrape.last_scrape_date);
    const now = new Date();
    return (
      d.getFullYear() === now.getFullYear() &&
      d.getMonth() === now.getMonth() &&
      d.getDate() === now.getDate()
    );
  };

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

  // Net worth change per month for the last 3 months (most recent first).
  // Each change is the month-over-month delta of net_worth, with its percent
  // relative to the prior month; the series already carries every month, so no
  // extra API call is needed.
  const netWorthMonthlyChanges =
    netWorthData && netWorthData.length >= 2
      ? netWorthData
          .slice(1)
          .map((entry, i) => {
            const prev = netWorthData[i].net_worth;
            const change = entry.net_worth - prev;
            return {
              month: entry.month,
              label: formatMonthCompact(entry.month),
              change,
              percent: prev !== 0 ? (change / Math.abs(prev)) * 100 : null,
            };
          })
          .slice(-3)
          .reverse()
      : [];

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
    <>
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
        {expanded && netWorthMonthlyChanges.length > 0 && (
          <MonthlyChangeList items={netWorthMonthlyChanges} />
        )}
      </div>

      {/* Bank Balance */}
      <div className="bg-[var(--surface)] rounded-xl px-3 sm:px-4 py-2.5 sm:py-3 border border-[var(--surface-light)] overflow-hidden">
        <p className="text-[10px] sm:text-xs text-[var(--text-muted)] truncate">{t("dashboard.bankBalance")}</p>
        <p dir="ltr" className="text-base sm:text-lg font-bold mt-0.5 truncate">
          {latestNetWorth ? formatCurrency(latestNetWorth.bank_balance) : "--"}
        </p>
        <MomBadge mom={bankMom} />
        {expanded && bankBalances && bankBalances.length > 0 && (
          <div className="mt-2 pt-2 border-t border-[var(--surface-light)] space-y-1">
            {bankBalances.map((b) => {
              const canUpdate = isScrapedToday(b.provider, b.account_name);
              return (
                <div
                  key={`${b.provider}|${b.account_name}`}
                  className="flex items-center justify-between text-xs gap-2"
                >
                  <span className="text-[var(--text-muted)] truncate me-1" dir="auto">
                    {b.account_name}
                  </span>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className="tabular-nums font-medium">{formatCurrency(b.balance)}</span>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (canUpdate) {
                          setBalanceModalAccount({
                            provider: b.provider,
                            account_name: b.account_name,
                            balance: b.balance,
                          });
                        }
                      }}
                      disabled={!canUpdate}
                      aria-label={
                        canUpdate
                          ? t("dataSources.setBalance")
                          : t("dataSources.scrapeFirstToSetBalance")
                      }
                      title={
                        canUpdate
                          ? t("dataSources.setBalance")
                          : t("dataSources.scrapeFirstToSetBalance")
                      }
                      className={`p-1 rounded-md transition-all ${
                        canUpdate
                          ? "bg-amber-500/10 text-amber-400 hover:bg-amber-500/20"
                          : "bg-[var(--surface-light)] text-[var(--text-muted)] cursor-not-allowed opacity-50"
                      }`}
                    >
                      <DollarSign size={12} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
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
    <UpdateBankBalanceModal
      isOpen={balanceModalAccount !== null}
      onClose={() => setBalanceModalAccount(null)}
      provider={balanceModalAccount?.provider ?? ""}
      accountName={balanceModalAccount?.account_name ?? ""}
      currentBalance={balanceModalAccount?.balance ?? null}
      isScrapedToday={
        balanceModalAccount
          ? isScrapedToday(balanceModalAccount.provider, balanceModalAccount.account_name)
          : false
      }
    />
    </>
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

  const { data: lastScrapes } = useQuery({
    queryKey: ["last-scrapes", isDemoMode],
    queryFn: () => scrapingApi.getLastScrapes().then((res) => res.data),
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
    heatmap: () => <SpendingHeatmap transactions={allTransactions} size={cardSize("heatmap")} />,
    income_by_source: () => <IncomeBySourceCard />,
    income_expenses: () => <IncomeExpensesCard />,
    net_worth: () => <NetWorthCard />,
    cash_flow: () => <CashFlowCard />,
    category: () => <CategoryBreakdownCard />,
  };

  return (
    <div className="space-y-4 md:space-y-8 animate-in fade-in duration-500">
      {/* Pinned: Financial Health Header (KPI cards) */}
      <FinancialHealthHeader
        netWorthData={netWorthData}
        cashBalances={cashBalances}
        bankBalances={bankBalances}
        portfolioAllocation={portfolioData?.allocation}
        lastScrapes={lastScrapes}
        isLoading={netWorthLoading}
      />

      {/* Customizable region: 2-column grid on wide screens (>=lg). Full-size
          cards span both columns; half-size cards take one. Native
          grid-auto-flow: row (no `dense`) fills top->bottom, start->end and
          honors document.dir for RTL automatically — a half card with no half
          neighbour before a full card leaves an empty gap, and the stored order
          is preserved exactly.

          Rows size to their content on >=lg (`grid-auto-rows: auto`), so a card
          alone on a row is exactly as tall as it needs to be — no empty gap
          below short cards. The card height is capped at `--dash-card-h`
          (`lg:[&>*]:max-h-[var(--dash-card-h)]`): content taller than the cap
          scrolls inside the card (`[&>*]:overflow-y-auto`) instead of growing
          the row. When two half cards share a row, the default
          `align-items: stretch` plus `[&>*]:h-full` makes both as tall as the
          taller card (still capped). On mobile the grid is a single column with
          natural, uncapped heights. */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-8 [--dash-card-h:39rem]">
        {layout.order.map((id, index) => (
          <div
            key={id}
            data-card-id={id}
            data-card-size={cardSize(id)}
            className={`min-w-0 [&>*]:h-full [&>*]:overflow-y-auto ${
              id !== "recent" ? "lg:[&>*]:max-h-[var(--dash-card-h)]" : ""
            } ${cardSize(id) === "full" ? "lg:col-span-2" : ""}`}
          >
            {/* The first cards render eagerly (above the fold on any viewport);
                the rest wait until scrolled near, so their analytics requests
                don't compete with the header + top cards on first paint. The
                placeholder reserves the card's capped height so lower cards
                stay below the fold and the layout doesn't jump on mount. */}
            <DeferUntilVisible
              eager={index < EAGER_CARD_COUNT}
              reserveClassName={cardSize(id) === "full" ? "min-h-[39rem]" : "min-h-[20rem]"}
            >
              {cardRenderers[id]()}
            </DeferUntilVisible>
          </div>
        ))}
      </div>
    </div>
  );
}
