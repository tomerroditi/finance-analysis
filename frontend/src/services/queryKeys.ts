/**
 * Single source of truth for React Query keys.
 *
 * Every server-data key is produced here so identical data always shares one
 * cache entry (the old ad-hoc keys had the same endpoint cached under 2–3
 * divergent keys). The demo-mode flag is uniformly the LAST segment: demo and
 * real data never share entries, and prefix-based invalidation (which matches
 * from the start of the key) is unaffected by it.
 *
 * Invalidate with `qkPrefix.*` — mode-agnostic prefixes that hit both modes.
 * Read keys via the `useQueryKeys()` hook (binds the current demo mode), or
 * `makeQueryKeys(isDemoMode)` outside React (route prefetch).
 *
 * PWA note: the heads "last-scrapes", "providers" and "credentials-*" are
 * load-bearing — queryClient.ts excludes them from IndexedDB persistence by
 * key head. Don't rename them without updating NON_PERSISTABLE_KEY_PREFIXES
 * and bumping PERSIST_BUSTER.
 */

export const qkPrefix = {
  transactions: ["transactions"] as const,
  // Matches only transaction LIST entries (["transactions","list",...]) —
  // setQueriesData patches assume Transaction[] data and must NOT match
  // sibling entries like ["transactions","uncategorized-count",...].
  transactionsList: ["transactions", "list"] as const,
  pendingRefunds: ["pending-refunds"] as const,
  budget: ["budget"] as const,
  // Narrower than `budget` — matches only the monthly-analysis family
  // (["budget","analysis",year,month,...]), not projects/alerts/overrides.
  // Used where a predicate assumes the analysis key shape (sibling-month
  // refetch in MonthlyBudgetView).
  budgetAnalysis: ["budget", "analysis"] as const,
  analytics: ["analytics"] as const,
  investments: ["investments"] as const,
  liabilities: ["liabilities"] as const,
  categories: ["categories"] as const,
  categoryIcons: ["category-icons"] as const,
  taggingRules: ["tagging-rules"] as const,
  bankBalances: ["bank-balances"] as const,
  cashBalances: ["cash-balances"] as const,
  savingsGoals: ["savings-goals"] as const,
  insuranceAccounts: ["insurance-accounts"] as const,
  lastScrapes: ["last-scrapes"] as const,
  // PWA note: excluded from IndexedDB persistence (queryClient.ts) — the
  // backup list is cheap to refetch and stale entries are misleading.
  backups: ["backups"] as const,
  credentialsAccounts: ["credentials-accounts"] as const,
  providers: ["providers"] as const,
  retirement: ["retirement"] as const,
} as const;

export function makeQueryKeys(demo: boolean) {
  return {
    transactions: {
      list: (service: string | undefined, includeSplitParents: boolean) =>
        ["transactions", "list", service ?? "all", includeSplitParents, demo] as const,
      uncategorizedCount: () => ["transactions", "uncategorized-count", demo] as const,
    },
    pendingRefunds: {
      all: () => ["pending-refunds", demo] as const,
    },
    budget: {
      analysis: (year: number, month: number, includeSplitParents: boolean) =>
        ["budget", "analysis", year, month, includeSplitParents, demo] as const,
      projects: () => ["budget", "projects", demo] as const,
      projectDetails: (name: string, includeSplitParents: boolean) =>
        ["budget", "project-details", name, includeSplitParents, demo] as const,
      availableProjects: () => ["budget", "available-projects", demo] as const,
      alertsCurrent: (threshold: number) =>
        ["budget", "alerts", "current", threshold, demo] as const,
      alertsMonth: (year: number, month: number, threshold: number) =>
        ["budget", "alerts", year, month, threshold, demo] as const,
      monthOverrides: () => ["budget", "month-overrides", demo] as const,
      yearly: (year: number) => ["budget", "yearly", year, demo] as const,
      categoryConflicts: () => ["budget", "category-conflicts", demo] as const,
    },
    tagging: {
      categories: () => ["categories", demo] as const,
      icons: () => ["category-icons", demo] as const,
      rules: () => ["tagging-rules", demo] as const,
      // Head "rule-preview" is load-bearing: queryClient.ts excludes it from
      // IndexedDB persistence by key head.
      rulePreview: (conditions: unknown) =>
        ["rule-preview", conditions, demo] as const,
    },
    retirement: {
      goal: () => ["retirement", "goal", demo] as const,
      status: () => ["retirement", "status", demo] as const,
      projections: () => ["retirement", "projections", demo] as const,
      suggestions: () => ["retirement", "suggestions", demo] as const,
      scrapedDefaults: () => ["retirement", "scraped-defaults", demo] as const,
    },
    balances: {
      bank: () => ["bank-balances", demo] as const,
      cash: () => ["cash-balances", demo] as const,
    },
    scraping: {
      lastScrapes: () => ["last-scrapes", demo] as const,
    },
    backups: {
      list: () => ["backups", demo] as const,
    },
    credentials: {
      accounts: () => ["credentials-accounts", demo] as const,
      providers: () => ["providers", demo] as const,
    },
    investments: {
      list: (includeClosed: boolean) => ["investments", "list", includeClosed, demo] as const,
      portfolio: () => ["investments", "portfolio", demo] as const,
      balanceHistory: (includeClosed: boolean) =>
        ["investments", "balance-history", includeClosed, demo] as const,
      analysis: (id: number) => ["investments", "analysis", id, demo] as const,
      snapshots: (id: number) => ["investments", "snapshots", id, demo] as const,
    },
    liabilities: {
      list: (includePaidOff: boolean) => ["liabilities", "list", includePaidOff, demo] as const,
      analysis: (id: number) => ["liabilities", "analysis", id, demo] as const,
      debtOverTime: () => ["liabilities", "debt-over-time", demo] as const,
    },
    insurance: {
      accounts: () => ["insurance-accounts", demo] as const,
    },
    savingsGoals: {
      all: () => ["savings-goals", demo] as const,
    },
    analytics: {
      overview: () => ["analytics", "overview", demo] as const,
      netWorthOverTime: () => ["analytics", "net-worth-over-time", demo] as const,
      debtPayments: () => ["analytics", "debt-payments-over-time", demo] as const,
      byCategory: () => ["analytics", "by-category", demo] as const,
      sankey: () => ["analytics", "sankey", demo] as const,
      incomeExpensesOverTime: (includeProjects: boolean, excludeRefunds: boolean) =>
        ["analytics", "income-expenses-over-time", includeProjects, excludeRefunds, demo] as const,
      expensesByCategoryOverTime: () =>
        ["analytics", "expenses-by-category-over-time", demo] as const,
      incomeBySourceOverTime: () =>
        ["analytics", "income-by-source-over-time", demo] as const,
      incomeBySource: (start: string | undefined, end: string | undefined) =>
        ["analytics", "income-by-source", start ?? "all", end ?? "all", demo] as const,
      monthlyExpenses: (excludePendingRefunds: boolean, includeProjects: boolean) =>
        ["analytics", "monthly-expenses", excludePendingRefunds, includeProjects, demo] as const,
      recurring: () => ["analytics", "recurring", demo] as const,
      insights: () => ["analytics", "insights", demo] as const,
      cashFlowForecast: () => ["analytics", "cash-flow-forecast", demo] as const,
    },
  };
}

export type QueryKeys = ReturnType<typeof makeQueryKeys>;
