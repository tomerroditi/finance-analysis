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
  create: (data: any) => api.post("/transactions/", data),
  update: (uniqueId: string, data: any) =>
    api.put(`/transactions/${uniqueId}`, data),
  delete: (uniqueId: string, source: string) =>
    api.delete(`/transactions/${uniqueId}`, { params: { source } }),
  updateTag: (id: string, category: string, tag: string, service: string) =>
    api.put(`/transactions/${id}/tag`, null, {
      params: { category, tag, service },
    }),
  bulkTag: (data: {
    transaction_ids: number[];
    source: string;
    category?: string;
    tag?: string;
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
  value?: any;
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
  testRule: (conditions: any[]) =>
    api.post("/tagging-rules/rules/test", conditions),
  checkConflicts: (conditions: ConditionNode, category: string, tag: string, ruleId?: number) =>
    api.post("/tagging-rules/rules/validate", {
      conditions,
      category,
      tag,
      rule_id: ruleId
    }),
  previewRule: (conditions: ConditionNode, limit = 100) =>
    api.post<{ matches: any[]; count: number }>("/tagging-rules/rules/preview", {
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
  start: (payload: { service: string; provider: string; account: string }) => {
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
  getInvestmentAnalysis: (id: number, startDate?: string, endDate?: string) =>
    api.get(`/investments/${id}/analysis`, {
      params: { start_date: startDate, end_date: endDate },
    }),
};

// Analytics API
export const analyticsApi = {
  getOverview: () =>
    api.get<{
      latest_data_date: string | null;
      total_transactions: number;
      total_income: number;
      total_expenses: number;
      net_balance_change: number;
    }>("/analytics/overview"),
  getNetBalanceOverTime: () =>
    api.get<{ month: string; net_change: number; cumulative_balance: number }[]>(
      "/analytics/net-balance-over-time"
    ),
  getIncomeExpensesOverTime: () =>
    api.get<{ month: string; income: number; expenses: number }[]>(
      "/analytics/income-expenses-over-time"
    ),
  getByCategory: () => api.get("/analytics/by-category"),
  getSankeyData: () => api.get("/analytics/sankey"),
  getNetWorthOverTime: () =>
    api.get<{ month: string; bank_balance: number; investment_value: number; net_worth: number }[]>(
      "/analytics/net-worth-over-time"
    ),
  getIncomeBySourceOverTime: () =>
    api.get<{ month: string; sources: Record<string, number>; total: number }[]>(
      "/analytics/income-by-source-over-time"
    ),
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

// Pending Refunds API
export interface PendingRefund {
  id: number;
  source_type: "transaction" | "split";
  source_id: number;
  source_table: string;
  expected_amount: number;
  status: "pending" | "resolved" | "partial";
  notes?: string;
  total_refunded?: number;
  remaining?: number;
  links?: RefundLink[];
  // Enriched fields
  date?: string;
  description?: string;
  account_name?: string;
  provider?: string;
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
    source_id: number;
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
      refund_transaction_id: number;
      refund_source: string;
      amount: number;
    },
  ) => api.post(`/pending-refunds/${pendingId}/link`, data),
  unlinkRefund: (linkId: number) =>
    api.delete(`/pending-refunds/links/${linkId}`),
};

export const testingApi = {
  toggleTestMode: (enabled: boolean) =>
    api.post<{ status: string; test_mode: boolean }>(
      "/testing/toggle_test_mode",
      { enabled },
    ),
  getTestModeStatus: () =>
    api.get<{ test_mode: boolean }>("/testing/test_mode_status"),
};

export default api;
