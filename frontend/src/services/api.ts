import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  headers: {
    "Content-Type": "application/json",
  },
});

// Request interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error("API Error:", error.response?.data || error.message);
    return Promise.reject(error);
  },
);

// Transactions API
export const transactionsApi = {
  getAll: (service?: string, includeSplitParents = false) =>
    api.get("/transactions/", {
      params: { service, include_split_parents: includeSplitParents },
    }),
  getById: (id: number) => api.get(`/transactions/${id}`),
  create: (data: Record<string, unknown>) => api.post("/transactions/", data),
  update: (uniqueId: string, data: Record<string, unknown>) =>
    api.put(`/transactions/${uniqueId}`, data),
  delete: (uniqueId: string, source: string) =>
    api.delete(`/transactions/${uniqueId}`, { params: { source } }),
  updateTag: (id: string, category: string, tag: string, service: string) =>
    api.put(`/transactions/${id}/tag`, null, {
      params: { category, tag, service },
    }),
  bulkTag: (data: {
    transaction_ids: (string | number)[];
    source: string;
    category?: string;
    tag?: string;
    description?: string;
    account_name?: string;
    date?: string;
    amount?: number;
  }) => api.post("/transactions/bulk-tag", data),
  split: (
    id: number,
    data: {
      source: string;
      splits: { amount: number; category: string; tag: string }[];
    },
  ) => api.post(`/transactions/${id}/split`, data),
  revertSplit: (id: number, source: string) =>
    api.delete(`/transactions/${id}/split`, { params: { source } }),
};

// Budget API
export const budgetApi = {
  getRules: () => api.get("/budget/rules"),
  getRulesByMonth: (year: number, month: number) =>
    api.get(`/budget/rules/${year}/${month}`),
  createRule: (rule: object) => api.post("/budget/rules", rule),
  updateRule: (id: number, rule: object) =>
    api.put(`/budget/rules/${id}`, rule),
  deleteRule: (id: number) => api.delete(`/budget/rules/${id}`),
  copyRules: (year: number, month: number) =>
    api.post(`/budget/rules/${year}/${month}/copy`),
  getAnalysis: (year: number, month: number, includeSplitParents = false) =>
    api.get(`/budget/analysis/${year}/${month}`, {
      params: { include_split_parents: includeSplitParents },
    }),
  getProjects: () => api.get("/budget/projects"),
  getAvailableProjects: () => api.get("/budget/projects/available"),
  createProject: (project: { category: string; total_budget: number }) =>
    api.post("/budget/projects", project),
  updateProject: (name: string, data: { total_budget: number }) =>
    api.put(`/budget/projects/${name}`, data),
  getProjectDetails: (name: string, includeSplitParents = false) =>
    api.get(`/budget/projects/${name}`, {
      params: { include_split_parents: includeSplitParents },
    }),
  deleteProject: (name: string) => api.delete(`/budget/projects/${name}`),
};

// Tagging API
export type Operator =
  | "contains"
  | "equals"
  | "starts_with"
  | "ends_with"
  | "gt"
  | "lt"
  | "gte"
  | "lte"
  | "between";

export type ConditionType = "AND" | "OR" | "CONDITION";

export interface ConditionNode {
  type: ConditionType;
  subconditions?: ConditionNode[];
  field?: string;
  operator?: Operator;
  value?: string | number | boolean | null | (string | number)[];
}

export interface TaggingRule {
  id: number;
  name: string;
  conditions: ConditionNode;
  category: string;
  tag: string;
}

export const taggingApi = {
  // Category & Tag Management (Legislated in routes/tagging.py)
  getCategories: () => api.get("/tagging/categories"),
  createCategory: (name: string, tags?: string[]) =>
    api.post("/tagging/categories", { name, tags }),
  deleteCategory: (name: string) => api.delete(`/tagging/categories/${name}`),
  createTag: (category: string, name: string) =>
    api.post("/tagging/tags", { category, name }),
  deleteTag: (category: string, name: string) =>
    api.delete(`/tagging/tags/${category}/${name}`),
  renameCategory: (name: string, newName: string) =>
    api.put(`/tagging/categories/${encodeURIComponent(name)}`, { new_name: newName }),
  renameTag: (category: string, name: string, newName: string) =>
    api.put(`/tagging/tags/${encodeURIComponent(category)}/${encodeURIComponent(name)}`, { new_name: newName }),
  relocateTag: (oldCategory: string, newCategory: string, tag: string) =>
    api.post("/tagging/tags/relocate", {
      old_category: oldCategory,
      new_category: newCategory,
      tag,
    }),
  getIcons: () => api.get("/tagging/icons"),
  updateIcon: (category: string, icon: string) =>
    api.put(`/tagging/icons/${category}`, null, { params: { icon } }),

  // Rules Management (New routes/tagging_rules.py)
  getRules: () =>
    api.get<TaggingRule[]>("/tagging-rules/rules"),
  createRule: (rule: Omit<TaggingRule, "id">) =>
    api.post("/tagging-rules/rules", rule),
  updateRule: (id: number, rule: Partial<TaggingRule>) =>
    api.put(`/tagging-rules/rules/${id}`, rule),
  deleteRule: (id: number) => api.delete(`/tagging-rules/rules/${id}`),
  applyRules: (overwrite = false) =>
    api.post("/tagging-rules/rules/apply", null, { params: { overwrite } }),
  applyRule: (id: number, overwrite = false) =>
    api.post(`/tagging-rules/rules/${id}/apply`, null, {
      params: { overwrite },
    }),
  testRule: (conditions: ConditionNode[]) =>
    api.post("/tagging-rules/rules/test", conditions),
  checkConflicts: (conditions: ConditionNode, category: string, tag: string, ruleId?: number) =>
    api.post("/tagging-rules/rules/validate", {
      conditions,
      category,
      tag,
      rule_id: ruleId
    }),
  previewRule: (conditions: ConditionNode, limit = 100) =>
    api.post<{ matches: Record<string, unknown>[]; count: number }>("/tagging-rules/rules/preview", {
      conditions,
      limit
    }),
};

// Credentials API
export const credentialsApi = {
  getAll: () => api.get("/credentials"),
  getAccounts: () => api.get("/credentials/accounts"),
  getProviders: () => api.get("/credentials/providers"),
  getFields: (provider: string) => api.get(`/credentials/fields/${provider}`),
  create: (data: {
    service: string;
    provider: string;
    account_name: string;
    credentials: Record<string, string>;
  }) => api.post("/credentials", data),
  getAccountDetails: (service: string, provider: string, accountName: string) =>
    api.get(`/credentials/${service}/${provider}/${accountName}`),
  delete: (service: string, provider: string, account_name: string) =>
    api.delete(`/credentials/${service}/${provider}/${account_name}`),
};

// Scraping API
export const scrapingApi = {
  getStatus: (processId: number) =>
    api.get("/scraping/status", { params: { scraping_process_id: processId } }),
  start: (payload: {
    service: string;
    provider: string;
    account: string;
    scraping_period_days?: number;
  }) => {
    return api.post("/scraping/start", payload);
  },
  submit2fa: (
    service: string,
    provider: string,
    account: string,
    code: string,
  ) => api.post("/scraping/2fa", { service, provider, account, code }),
  abort: (processId: number) =>
    api.post("/scraping/abort", { process_id: processId }),
  getLastScrapes: () =>
    api.get<
      {
        service: string;
        provider: string;
        account_name: string;
        last_scrape_date: string | null;
      }[]
    >("/scraping/last-scrapes"),
};

// Insurance Accounts API
export interface InsuranceAccount {
  id: number;
  provider: string;
  policy_id: string;
  policy_type: string;
  pension_type: string | null;
  account_name: string;
  balance: number | null;
  balance_date: string | null;
  investment_tracks: string | null;
  commission_deposits_pct: number | null;
  commission_savings_pct: number | null;
  insurance_covers: string | null;
  insurance_costs: string | null;
  liquidity_date: string | null;
}

export const insuranceAccountsApi = {
  getAll: () => api.get<InsuranceAccount[]>("/insurance-accounts/"),
};

// Investments API
export const investmentsApi = {
  getAll: (includeClosed = false) =>
    api.get("/investments", { params: { include_closed: includeClosed } }),
  getById: (id: number) => api.get(`/investments/${id}`),
  create: (investment: object) => api.post("/investments", investment),
  update: (id: number, investment: object) =>
    api.put(`/investments/${id}`, investment),
  close: (id: number, closedDate: string) =>
    api.post(`/investments/${id}/close`, null, {
      params: { closed_date: closedDate },
    }),
  reopen: (id: number) => api.post(`/investments/${id}/reopen`),
  delete: (id: number) => api.delete(`/investments/${id}`),
  getPortfolioAnalysis: () => api.get("/investments/analysis/portfolio"),
  getPortfolioBalanceHistory: (includeClosed?: boolean) =>
    api.get("/investments/analysis/balance-history", {
      params: { include_closed: includeClosed },
    }),
  getInvestmentAnalysis: (id: number, startDate?: string, endDate?: string) =>
    api.get(`/investments/${id}/analysis`, {
      params: { start_date: startDate, end_date: endDate },
    }),
  // Balance snapshots
  getBalanceSnapshots: (id: number) =>
    api.get(`/investments/${id}/balances`),
  createBalanceSnapshot: (id: number, data: { date: string; balance: number }) =>
    api.post(`/investments/${id}/balances`, data),
  updateBalanceSnapshot: (investmentId: number, snapshotId: number, data: { date?: string; balance?: number }) =>
    api.put(`/investments/${investmentId}/balances/${snapshotId}`, data),
  deleteBalanceSnapshot: (investmentId: number, snapshotId: number) =>
    api.delete(`/investments/${investmentId}/balances/${snapshotId}`),
  calculateFixedRateSnapshots: (id: number, endDate?: string) =>
    api.post(`/investments/${id}/balances/calculate`, null, {
      params: endDate ? { end_date: endDate } : {},
    }),
};

// Liabilities API
export const liabilitiesApi = {
  getAll: (includePaidOff = false) =>
    api.get("/liabilities/", { params: { include_paid_off: includePaidOff } }),
  getById: (id: number) => api.get(`/liabilities/${id}`),
  getDebtOverTime: () => api.get("/liabilities/debt-over-time"),
  create: (liability: object) => api.post("/liabilities/", liability),
  update: (id: number, liability: object) =>
    api.put(`/liabilities/${id}`, liability),
  payOff: (id: number, paidOffDate: string) =>
    api.post(`/liabilities/${id}/pay-off`, {
      paid_off_date: paidOffDate,
    }),
  reopen: (id: number) => api.post(`/liabilities/${id}/reopen`),
  delete: (id: number) => api.delete(`/liabilities/${id}`),
  getAnalysis: (id: number) => api.get(`/liabilities/${id}/analysis`),
  getTransactions: (id: number) => api.get(`/liabilities/${id}/transactions`),
  detectTransactions: (tag: string) =>
    api.get("/liabilities/detect-transactions", { params: { tag } }),
  generateTransactions: (id: number) =>
    api.post(`/liabilities/${id}/generate-transactions`),
};

// Analytics API
export const analyticsApi = {
  getOverview: () =>
    api.get<{
      latest_data_date: string | null;
      total_income: number;
      total_expenses: number;
      total_investments: number;
      net_balance_change: number;
    }>("/analytics/overview"),
  getNetBalanceOverTime: () =>
    api.get<{ month: string; net_change: number; cumulative_balance: number }[]>(
      "/analytics/net-balance-over-time"
    ),
  getIncomeExpensesOverTime: (excludeProjects = false, excludeLiabilities = false, excludeRefunds = false) =>
    api.get<{ month: string; income: number; expenses: number }[]>(
      "/analytics/income-expenses-over-time",
      { params: { exclude_projects: excludeProjects, exclude_liabilities: excludeLiabilities, exclude_refunds: excludeRefunds } }
    ),
  getDebtPaymentsOverTime: () =>
    api.get<{ month: string; amount: number; tags: Record<string, number> }[]>(
      "/analytics/debt-payments-over-time"
    ),
  getByCategory: () => api.get("/analytics/by-category"),
  getExpensesByCategoryOverTime: () =>
    api.get<{ month: string; categories: Record<string, number> }[]>(
      "/analytics/expenses-by-category-over-time"
    ),
  getSankeyData: () => api.get("/analytics/sankey"),
  getNetWorthOverTime: () =>
    api.get<{ month: string; bank_balance: number; investment_value: number; cash: number; net_worth: number }[]>(
      "/analytics/net-worth-over-time"
    ),
  getIncomeBySourceOverTime: () =>
    api.get<{ month: string; sources: Record<string, number>; total: number }[]>(
      "/analytics/income-by-source-over-time"
    ),
  getMonthlyExpenses: (excludePendingRefunds = true, includeProjects = false) =>
    api.get<{
      months: { month: string; expenses: number; project_expenses?: number }[];
      avg_3_months: number;
      avg_6_months: number;
      avg_12_months: number;
    }>("/analytics/monthly-expenses", {
      params: { exclude_pending_refunds: excludePendingRefunds, include_projects: includeProjects },
    }),
};

// Bank Balances API
export interface BankBalance {
  id: number;
  provider: string;
  account_name: string;
  balance: number;
  prior_wealth_amount: number;
  last_manual_update: string | null;
  last_scrape_update: string | null;
}

export const bankBalancesApi = {
  getAll: () => api.get<BankBalance[]>("/bank-balances/"),
  setBalance: (data: {
    provider: string;
    account_name: string;
    balance: number;
  }) => api.post<BankBalance>("/bank-balances/", data),
};

// Cash Balances API
export interface CashBalance {
  id: number;
  account_name: string;
  balance: number;
  prior_wealth_amount: number;
  last_manual_update: string | null;
}

export const cashBalancesApi = {
  getAll: () => api.get<CashBalance[]>("/cash-balances/"),
  setBalance: (data: { account_name: string; balance: number }) =>
    api.post<CashBalance>("/cash-balances/", data),
  delete: (accountName: string) =>
    api.delete(`/cash-balances/${accountName}`),
  migrate: () => api.post<CashBalance[]>("/cash-balances/migrate"),
};

// Pending Refunds API
export interface PendingRefund {
  id: number;
  source_type: "transaction" | "split";
  source_id: string | number;
  source_table: string;
  expected_amount: number;
  status: "pending" | "resolved" | "partial" | "closed";
  notes?: string;
  total_refunded?: number;
  remaining?: number;
  links?: RefundLink[];
  // Enriched fields
  date?: string;
  description?: string;
  account_name?: string;
  provider?: string;
  category?: string;
  tag?: string;
}

export interface RefundLink {
  id: number;
  pending_refund_id: number;
  refund_transaction_id: number;
  refund_source: string;
  amount: number;
  // Enriched fields
  date?: string;
  description?: string;
}

export const pendingRefundsApi = {
  create: (data: {
    source_type: "transaction" | "split";
    source_id: string | number;
    source_table: string;
    expected_amount: number;
    notes?: string;
  }) => api.post<PendingRefund>("/pending-refunds/", data),
  getAll: (status?: string) =>
    api.get<PendingRefund[]>("/pending-refunds/", { params: { status } }),
  getById: (id: number) => api.get<PendingRefund>(`/pending-refunds/${id}`),
  cancel: (id: number) => api.delete(`/pending-refunds/${id}`),
  linkRefund: (
    pendingId: number,
    data: {
      refund_transaction_id: string | number;
      refund_source: string;
      amount: number;
    },
  ) => api.post(`/pending-refunds/${pendingId}/link`, data),
  unlinkRefund: (linkId: number) =>
    api.delete(`/pending-refunds/links/${linkId}`),
  close: (id: number) => api.post(`/pending-refunds/${id}/close`),
};

// Retirement API
export interface RetirementGoal {
  id: number;
  current_age: number;
  gender: string;
  target_retirement_age: number;
  life_expectancy: number;
  monthly_expenses_in_retirement: number;
  inflation_rate: number;
  expected_return_rate: number;
  withdrawal_rate: number;
  pension_monthly_payout_estimate: number;
  keren_hishtalmut_balance: number;
  keren_hishtalmut_monthly_contribution: number;
  bituach_leumi_eligible: boolean;
  bituach_leumi_monthly_estimate: number;
  other_passive_income: number;
}

export interface RetirementStatus {
  net_worth: number;
  avg_monthly_expenses: number;
  avg_monthly_income: number;
  savings_rate: number;
  total_investments: number;
  monthly_savings: number;
}

export interface RetirementSuggestions {
  target_retirement_age: number;
  monthly_expenses_in_retirement: number;
  expected_return_rate: number;
  life_expectancy: number;
}

export interface ScrapedDefaults {
  keren_hishtalmut_balance: number | null;
  keren_hishtalmut_monthly_contribution: number | null;
  pension_monthly_deposit: number | null;
}

export interface RetirementProjections {
  fire_number: number;
  years_to_fire: number;
  fire_age: number;
  earliest_possible_retirement_age: number;
  monthly_savings_needed: number;
  progress_pct: number;
  readiness: "on_track" | "close" | "off_track";
  portfolio_depleted_age: number | null;
  target_retirement_age: number;
  net_worth_projection: {
    age: number;
    net_worth_optimistic: number;
    net_worth_baseline: number;
    net_worth_conservative: number;
  }[];
  income_projection: {
    age: number;
    salary_savings: number;
    portfolio_withdrawal: number;
    pension: number;
    bituach_leumi: number;
    passive_income: number;
    total_income: number;
    expenses: number;
  }[];
}

export const retirementApi = {
  getGoal: () => api.get<RetirementGoal | null>("/retirement/goal"),
  upsertGoal: (data: Omit<RetirementGoal, "id">) =>
    api.put<RetirementGoal>("/retirement/goal", data),
  getStatus: () => api.get<RetirementStatus>("/retirement/status"),
  getProjections: () =>
    api.get<RetirementProjections>("/retirement/projections"),
  previewProjections: (data: Omit<RetirementGoal, "id">) =>
    api.post<RetirementProjections>("/retirement/projections", data),
  getKerenHishtalmutBalance: () =>
    api.get<{ balance: number | null }>("/retirement/keren-hishtalmut-balance"),
  getScrapedDefaults: () =>
    api.get<ScrapedDefaults>("/retirement/scraped-defaults"),
  getSuggestions: () =>
    api.get<RetirementSuggestions>("/retirement/suggestions"),
  previewSuggestions: (data: Omit<RetirementGoal, "id">) =>
    api.post<RetirementSuggestions>("/retirement/suggestions", data),
  solveForField: (field: string) =>
    api.get<{ field: string; value: number; unit: string }>(
      `/retirement/solve/${field}`,
    ),
};

export const backupApi = {
  list: () =>
    api.get<
      { filename: string; created_at: string; size_bytes: number }[]
    >("/backups/"),
  create: () =>
    api.post<{ filename: string; created_at: string; size_bytes: number }>(
      "/backups/",
    ),
  restore: (filename: string) =>
    api.post<{ status: string; filename: string }>("/backups/restore", {
      filename,
    }),
};

export const testingApi = {
  toggleDemoMode: (enabled: boolean) =>
    api.post<{ status: string; demo_mode: boolean }>(
      "/testing/toggle_demo_mode",
      { enabled },
    ),
  getDemoModeStatus: () =>
    api.get<{ demo_mode: boolean }>("/testing/demo_mode_status"),
};

export default api;
