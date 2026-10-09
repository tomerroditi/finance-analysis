import axios from "axios";
import { readOrCreateDemoSessionId, readStoredDemoMode } from "./demoMode";
import type { Transaction } from "../types/transaction";

const api = axios.create({
  baseURL: "/api",
  headers: {
    "Content-Type": "application/json",
  },
});

// Remote-access API token. When the backend is exposed beyond localhost
// (./start.sh prod's tailnet share, or BIND_HOST set), non-local clients must send
// `Authorization: Bearer <token>` on /api requests. The token is handed
// over once via a `?apiToken=` URL parameter, persisted to localStorage,
// and stripped from the URL so it doesn't linger in the address bar or
// browser history. Local (loopback) clients never need it — the backend
// trusts same-machine connections.
const API_TOKEN_STORAGE_KEY = "fad_api_token";

export function captureApiTokenFromUrl(): void {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  const token = url.searchParams.get("apiToken");
  if (!token) return;
  localStorage.setItem(API_TOKEN_STORAGE_KEY, token);
  url.searchParams.delete("apiToken");
  window.history.replaceState(null, "", url.toString());
}

captureApiTokenFromUrl();

api.interceptors.request.use((config) => {
  const token =
    typeof window !== "undefined"
      ? localStorage.getItem(API_TOKEN_STORAGE_KEY)
      : null;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  // Demo Mode is per-client and declared per request. Without this header
  // the backend serves the real database, which is the correct default for
  // curl, the desktop app, and Playwright's request context.
  if (readStoredDemoMode()) {
    config.headers["X-FAD-Demo"] = "1";
  }
  // Sent unconditionally rather than only in Demo Mode: on the shared
  // Vercel deployment the mode is forced server-side, so the stored flag is
  // off there even though every request is a demo request. The backend
  // ignores the id unless it serves per-visitor sandboxes.
  const demoSessionId = readOrCreateDemoSessionId();
  if (demoSessionId) {
    config.headers["X-FAD-Demo-Session"] = demoSessionId;
  }
  return config;
});

// Response interceptor: log only safe metadata about failures so raw server
// payloads (which may include stack traces, SQL fragments, or file paths)
// never land in the browser console where browser extensions or screenshots
// could exfiltrate them. When the request never reached the server (no
// `response`), also dispatches an `api-network-failed` window event so the
// global NetworkStatusToast can surface a single transient toast.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const safeError = {
      method: error.config?.method,
      url: error.config?.url,
      status: error.response?.status,
      statusText: error.response?.statusText,
      message: error.message,
    };
    console.error("API Error:", safeError);
    if (typeof window !== "undefined" && !error.response) {
      window.dispatchEvent(
        new CustomEvent("api-network-failed", { detail: safeError }),
      );
    }
    return Promise.reject(error);
  },
);

// Transactions API
export const transactionsApi = {
  getAll: (service?: string, includeSplitParents = false) =>
    api.get("/transactions/", {
      params: { service, include_split_parents: includeSplitParents },
    }),
  getUncategorizedCount: () =>
    api.get<{ count: number }>("/transactions/uncategorized-count"),
  create: (data: Record<string, unknown>) => api.post("/transactions/", data),
  update: (uniqueId: string, data: Record<string, unknown>) =>
    api.put(`/transactions/${encodeURIComponent(uniqueId)}`, data),
  delete: (uniqueId: string, source: string) =>
    api.delete(`/transactions/${encodeURIComponent(uniqueId)}`, { params: { source } }),
  updateTag: (id: string, category: string, tag: string, service: string) =>
    api.put(`/transactions/${encodeURIComponent(id)}/tag`, null, {
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
    uniqueId: string | number,
    data: {
      source: string;
      splits: { amount: number; category: string; tag: string }[];
    },
  ) => api.post(`/transactions/${encodeURIComponent(String(uniqueId))}/split`, data),
  revertSplit: (uniqueId: string | number, source: string) =>
    api.delete(`/transactions/${encodeURIComponent(String(uniqueId))}/split`, { params: { source } }),
};

// Budget API
export const budgetApi = {
  getRules: () => api.get("/budget/rules"),
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
  getTrend: (
    year: number,
    month: number,
    months = 12,
    includeSplitParents = false,
  ) =>
    api.get<BudgetTrendPointResponse[]>(`/budget/trend/${year}/${month}`, {
      params: { months, include_split_parents: includeSplitParents },
    }),
  getProjects: () => api.get("/budget/projects"),
  getProjectsStatus: () =>
    api.get<ProjectStatus[]>("/budget/projects/status"),
  getAvailableProjects: () => api.get("/budget/projects/available"),
  createProject: (project: { category: string; total_budget: number }) =>
    api.post("/budget/projects", project),
  updateProject: (name: string, data: { total_budget: number }) =>
    api.put(`/budget/projects/${encodeURIComponent(name)}`, data),
  getProjectDetails: (name: string, includeSplitParents = false) =>
    api.get(`/budget/projects/${encodeURIComponent(name)}`, {
      params: { include_split_parents: includeSplitParents },
    }),
  deleteProject: (name: string) =>
    api.delete(`/budget/projects/${encodeURIComponent(name)}`),
  setProjectClosed: (name: string, closed: boolean) =>
    api.put(`/budget/projects/${encodeURIComponent(name)}/closed`, { closed }),
  getCurrentAlerts: (threshold?: number) =>
    api.get("/budget/alerts", {
      params: threshold !== undefined ? { threshold } : undefined,
    }),
  getMonthAlerts: (year: number, month: number, threshold?: number) =>
    api.get(`/budget/alerts/${year}/${month}`, {
      params: threshold !== undefined ? { threshold } : undefined,
    }),
  getYearlyAnalysis: (year: number, includeSplitParents = false) =>
    api.get(`/budget/yearly/${year}/analysis`, {
      params: { include_split_parents: includeSplitParents },
    }),
  createYearlyRule: (rule: {
    name: string;
    amount: number;
    category: string;
    tags: string[];
    year: number;
  }) => api.post("/budget/yearly/rules", rule),
  updateYearlyRule: (id: number, rule: object) =>
    api.put(`/budget/yearly/rules/${id}`, rule),
  deleteYearlyRule: (id: number) => api.delete(`/budget/yearly/rules/${id}`),
  setYearlyRuleClosed: (id: number, closed: boolean) =>
    api.put(`/budget/yearly/rules/${id}/closed`, { closed }),
  copyYearlyRules: (year: number) => api.post(`/budget/yearly/${year}/copy`),
  getCategoryConflicts: () => api.get("/budget/category-conflicts"),
  getOverview: (year: number, month: number, includeSplitParents = false) =>
    api.get<BudgetOverview>(`/budget/overview/${year}/${month}`, {
      params: { include_split_parents: includeSplitParents },
    }),
};

/** One recurring charge the month still owes. */
/** One month of `GET /budget/trend/{year}/{month}`. */
export interface BudgetTrendPointResponse {
  year: number;
  month: number;
  /** The month's "Total Budget" cap. */
  budget: number;
  /** That row's spend, already sign-normalised by the backend. */
  actual: number;
  /** Spend per rule name — names, not ids, because an auto-filled month
   *  creates fresh rows for the same rule. */
  rules: Record<string, number>;
  /** The cap each rule carried *that* month, keyed the same way. A rule
   *  missing from the map had no rule that month. */
  limits: Record<string, number>;
}

export interface BudgetChargeDue {
  label: string;
  amount: number;
  expected_date: string;
}

/**
 * A project budget and whether it has been closed.
 *
 * A closed project is finished, not deleted: it keeps its rules, its history
 * and its own tab, and only drops out of the budget Overview.
 */
export interface ProjectStatus {
  name: string;
  closed: boolean;
}

/**
 * A yearly or project rule: what the viewed month put in, and where the
 * rule stands overall. The two are never interchangeable — ``spent`` always
 * describes today, whichever month is being viewed.
 */
export interface BudgetLongRule {
  name: string;
  kind: "yearly" | "project";
  category: string;
  month_contribution: number;
  spent: number;
  budget: number;
}

/** Cross-kind roll-up of one month — see ``GET /budget/overview``. */
export interface BudgetOverview {
  year: number;
  month: number;
  is_current_month: boolean;
  days_in_month: number;
  days_elapsed: number;
  days_left: number;
  monthly_budget: number;
  monthly_spent: number;
  fixed_spent: number;
  /** Transactions on the fixed side. Not ``charges_due.length``, which is what is still owed. */
  fixed_charge_count: number;
  variable_spent: number;
  committed_remaining: number;
  free_to_spend: number;
  variable_per_day: number;
  /** ``null`` once the month is settled — then there is a final figure, not a projection. */
  projected: number | null;
  charges_due: BudgetChargeDue[];
  projects_month_spent: number;
  yearly_month_spent: number;
  total_out: number;
  long_envelopes: BudgetLongRule[];
}

export interface CategoryConflict {
  category: string;
  kinds: ("monthly" | "yearly")[];
}

export interface BudgetAlert {
  rule_id: number;
  name: string;
  category: string;
  tags: string[];
  amount: number;
  spent: number;
  percentage: number;
  severity: "warning" | "critical";
}

export interface BudgetAlertsResponse {
  year: number;
  month: number;
  alerts: BudgetAlert[];
}

export interface YearlyRollup {
  total_allocated: number;
  total_spent: number;
  remaining: number;
  on_track: number;
  over: number;
  /** Rules the user has marked settled — counted apart from the health above. */
  closed: number;
  biggest_overspend: { name: string; percentage: number } | null;
}

export interface YearlyAnalysis {
  rules: {
    rule: {
      id: number;
      name: string;
      amount: number;
      category: string;
      tags: string[];
      year: number;
    };
    current_amount: number;
    /** The year's transactions behind this rule — what the row expands to show. */
    data: Transaction[];
    allow_edit: boolean;
    allow_delete: boolean;
    /**
     * Whether the rule has been closed.
     *
     * A closed yearly rule is settled, not deleted: it keeps its allocation,
     * its spend and its row here, and it still claims its tags against the
     * monthly budget. It only stops appearing in the budget Overview.
     */
    closed: boolean;
  }[];
  summary: YearlyRollup;
  alerts: BudgetAlert[];
  carried_from: number | null;
  skipped_conflicts: string[];
}

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
  getCategoryUsage: () => api.get("/tagging/categories/usage"),
  createCategory: (name: string, tags?: string[]) =>
    api.post("/tagging/categories", { name, tags }),
  deleteCategory: (name: string) =>
    api.delete(`/tagging/categories/${encodeURIComponent(name)}`),
  createTag: (category: string, name: string) =>
    api.post("/tagging/tags", { category, name }),
  deleteTag: (category: string, name: string) =>
    api.delete(
      `/tagging/tags/${encodeURIComponent(category)}/${encodeURIComponent(name)}`,
    ),
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
    api.put(`/tagging/icons/${encodeURIComponent(category)}`, null, {
      params: { icon },
    }),

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
  previewRule: (conditions: ConditionNode, limit?: number) =>
    api.post<{ matches: Record<string, unknown>[]; count: number }>("/tagging-rules/rules/preview", {
      conditions,
      ...(limit !== undefined ? { limit } : {})
    }),
};

// Credentials API
export interface CredentialAccount {
  service: string;
  provider: string;
  account_name: string;
  /** Stored details are unreadable on this machine or the keyring has no
   * password — the account cannot scrape until they are re-entered. */
  needs_reentry?: boolean;
}

export interface CredentialDeleteResult {
  status: string;
  /** 0 when the caller kept the account's data. */
  transactions_deleted: number;
}

export const credentialsApi = {
  getAll: () => api.get("/credentials/"),
  getAccounts: () => api.get<CredentialAccount[]>("/credentials/accounts"),
  getProviders: () => api.get<Record<string, string[]>>("/credentials/providers"),
  getFields: (provider: string) =>
    api.get<{ fields: string[] }>(`/credentials/fields/${encodeURIComponent(provider)}`),
  create: (data: {
    service: string;
    provider: string;
    account_name: string;
    credentials: Record<string, string>;
  }) => api.post("/credentials/", data),
  getAccountDetails: (service: string, provider: string, accountName: string) =>
    api.get(
      `/credentials/${encodeURIComponent(service)}/${encodeURIComponent(provider)}/${encodeURIComponent(accountName)}`,
    ),
  /**
   * Remove a connection.
   *
   * `deleteData` defaults to `false`: only the credential row and its saved
   * password go away, so the account's transactions, bank balance (and the
   * prior wealth derived from it) and scrape history survive and a
   * reconnection resumes where it left off. Pass `true` to additionally wipe
   * the account's transactions and everything referencing them — that is
   * irreversible and makes a reconnection start a fresh one-year backfill.
   */
  delete: (
    service: string,
    provider: string,
    account_name: string,
    options?: { deleteData?: boolean },
  ) =>
    api.delete<CredentialDeleteResult>(
      `/credentials/${encodeURIComponent(service)}/${encodeURIComponent(provider)}/${encodeURIComponent(account_name)}`,
      { params: { delete_data: options?.deleteData ?? false } },
    ),
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
    force_2fa?: boolean;
  }) => {
    return api.post("/scraping/start", payload);
  },
  submit2fa: (
    service: string,
    provider: string,
    account: string,
    code: string,
  ) => api.post("/scraping/2fa", { service, provider, account, code }),
  resend2fa: (service: string, provider: string, account: string) =>
    api.post<{ status: "resent" | "restarted"; process_id: number }>(
      "/scraping/resend-2fa",
      { service, provider, account },
    ),
  abort: (processId: number) =>
    api.post("/scraping/abort", { process_id: processId }),
  /**
   * Scrapes still in flight on the backend for this client.
   *
   * Lets `useScraping` re-hydrate after its component unmounts (navigating
   * away from Data Sources and back, a reload, a second tab) instead of
   * losing track of a running scrape.
   */
  getActive: () =>
    api.get<
      {
        process_id: number;
        service: string;
        provider: string;
        account_name: string;
        status: string;
      }[]
    >("/scraping/active"),
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
  custom_name: string | null;
  balance: number | null;
  balance_date: string | null;
  investment_tracks: string | null;
  commission_deposits_pct: number | null;
  commission_savings_pct: number | null;
  insurance_covers: string | null;
  /** Provider's year-to-date movement statement, not a cost list — read only via `utils/insuranceStatement.ts`. */
  insurance_costs: string | null;
  liquidity_date: string | null;
  /** JSON object of provider facts (forecasts, profit, agent, loans) — read via `utils/policyDetails.ts`. */
  details: string | null;
}

/** One monthly household summary from the pension clearing house. */
export interface ClearingHouseReport {
  provider: string;
  account_name: string;
  calc_date: string;
  total_savings: number | null;
  forecast_total_balance: number | null;
  forecast_monthly_pension: number | null;
  forecast_lump_sum: number | null;
  disability_monthly: number | null;
  survivor_spouse_monthly: number | null;
  survivor_child_monthly: number | null;
  death_lump_sum: number | null;
  report_number: number | null;
  report_count: number | null;
  subscription_expires: string | null;
  subscription_months_left: number | null;
  license_holder: string | null;
}

export const insuranceAccountsApi = {
  getAll: () => api.get<InsuranceAccount[]>("/insurance-accounts/"),
  getClearingHouseReports: () =>
    api.get<ClearingHouseReport[]>("/insurance-accounts/clearing-house-reports"),
  rename: (policyId: string, customName: string | null) =>
    api.patch<InsuranceAccount>(
      `/insurance-accounts/${encodeURIComponent(policyId)}/rename`,
      { custom_name: customName },
    ),
};

// Investments API
export interface Investment {
  id: number;
  name: string;
  category: string;
  tag: string;
  type: string;
  is_closed: boolean;
  closed_date?: string;
  interest_rate?: number;
  interest_rate_type?: string;
  rate_spread?: number | null;
  notes?: string;
  insurance_policy_id?: string | null;
  liquidity_date?: string | null;
  commission_deposit?: number | null;
  commission_management?: number | null;
  latest_snapshot_date?: string;
  latest_snapshot_balance?: number;
  current_balance?: number;
  sparkline?: number[];
  first_transaction_date?: string;
  created_date?: string;
}

export const investmentsApi = {
  getAll: (includeClosed = false) =>
    api.get<Investment[]>("/investments/", { params: { include_closed: includeClosed } }),
  getById: (id: number) => api.get(`/investments/${id}`),
  create: (investment: object) => api.post("/investments/", investment),
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
export type LoanType = "fixed_unlinked" | "prime_linked" | "variable_unlinked";
export type AmortizationMethod = "shpitzer" | "equal_principal" | "balloon";

export interface Liability {
  id: number;
  name: string;
  lender?: string;
  category: string;
  tag: string;
  principal_amount: number;
  interest_rate: number;
  loan_type: LoanType;
  amortization_method: AmortizationMethod;
  rate_spread?: number | null;
  rate_reset_months?: number | null;
  term_months: number;
  start_date: string;
  is_paid_off: number;
  paid_off_date?: string;
  notes?: string;
  created_date: string;
  monthly_payment: number;
  total_interest: number;
  remaining_balance: number;
  total_paid: number;
  percent_paid: number;
  payments_made: number;
  current_rate: number;
  /** Set when the liability mirrors a loan against a pension/KH policy. */
  insurance_loan_key?: string | null;
}

export const liabilitiesApi = {
  getAll: (includePaidOff = false) =>
    api.get<Liability[]>("/liabilities/", { params: { include_paid_off: includePaidOff } }),
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

// Interest rates API
export interface CurrentRates {
  boi_rate: number | null;
  prime: number | null;
  as_of: string | null;
}

export const ratesApi = {
  getCurrent: () => api.get<CurrentRates>("/rates/current"),
  getHistory: (series: "boi_rate" | "prime" = "boi_rate") =>
    api.get<{ date: string; value: number }[]>("/rates/history", {
      params: { series },
    }),
  refresh: () => api.post("/rates/refresh"),
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
  getDebtPaymentsOverTime: () =>
    api.get<{ month: string; amount: number; tags: Record<string, number> }[]>(
      "/analytics/debt-payments-over-time"
    ),
  getExpensesByCategoryOverTime: (
    excludePendingRefunds = true,
    excludeProjects = false,
    excludeLiabilities = false,
  ) =>
    api.get<{ month: string; categories: Record<string, number> }[]>(
      "/analytics/expenses-by-category-over-time",
      {
        params: {
          exclude_pending_refunds: excludePendingRefunds,
          exclude_projects: excludeProjects,
          exclude_liabilities: excludeLiabilities,
        },
      }
    ),
  getSankeyData: () => api.get("/analytics/sankey"),
  getNetWorthOverTime: () =>
    api.get<{ month: string; bank_balance: number; investment_value: number; cash: number; net_worth: number }[]>(
      "/analytics/net-worth-over-time"
    ),
  getIncomeBySourceOverTime: (excludePendingRefunds = true, excludeLiabilities = false) =>
    api.get<{ month: string; sources: Record<string, number>; total: number }[]>(
      "/analytics/income-by-source-over-time",
      {
        params: {
          exclude_pending_refunds: excludePendingRefunds,
          exclude_liabilities: excludeLiabilities,
        },
      }
    ),
  getCashFlowForecast: () =>
    api.get<CashFlowForecast>("/analytics/cash-flow-forecast"),
  getRecurring: (includeDismissed = false) =>
    api.get<RecurringSummary>("/analytics/recurring", {
      params: { include_dismissed: includeDismissed },
    }),
  setRecurringDecisions: (decisions: RecurringDecisionInput[]) =>
    api.post<{ updated: RecurringDecisionInput[] }>(
      "/analytics/recurring/decisions",
      { decisions },
    ),
  getInsights: () => api.get<Insight[]>("/analytics/insights"),
  dismissInsight: (key: string) =>
    api.post<InsightDismissal>("/analytics/insights/dismiss", { key }),
  restoreInsight: (key: string) =>
    api.post<InsightDismissal>("/analytics/insights/restore", { key }),
};

export interface RecurringItem {
  label: string;
  normalized: string;
  amount: number;
  last_amount: number;
  cadence: RecurringCadence;
  period_days: number;
  monthly_equivalent: number;
  occurrences: number;
  category: string | null;
  first_date: string;
  last_date: string;
  next_expected_date: string;
  status: "active" | "new" | "price_changed" | "ended";
  price_change: number;
  confirmation: RecurringConfirmation;
  /** How much evidence backs the detection, 0..1. */
  confidence: number;
  /** ``fixed`` for a flat subscription, ``metered`` for a consumption bill. */
  amount_kind: "fixed" | "metered";
}

export type RecurringCadence =
  | "monthly"
  | "bimonthly"
  | "quarterly"
  | "semiannual"
  | "annual";

/** Where a detected candidate stands with the user. */
export type RecurringConfirmation = "confirmed" | "pending" | "dismissed";

/** One verdict to store; ``pending`` undoes a previous one. */
export interface RecurringDecisionInput {
  normalized: string;
  decision: RecurringConfirmation;
  /**
   * What the candidate read as on screen when the user ruled. Stored beside
   * the verdict for audit and read by nothing — sent because the card
   * already has it, where deriving it server-side would cost a full
   * detection pass per verdict.
   */
  label?: string;
  amount?: number;
  cadence?: RecurringCadence;
}

export interface RecurringSummary {
  items: RecurringItem[];
  /** Monthly equivalent of confirmed, still-running charges only. */
  total_monthly: number;
  /** The same sum over candidates still awaiting a verdict. */
  pending_monthly: number;
  pending_count: number;
  confirmed_count: number;
  dismissed_count: number;
}

export interface Insight {
  code: string;
  /** Stable identity of this card — what a dismissal is keyed by. */
  key: string;
  severity: "positive" | "info" | "warning";
  data: Record<string, string | number>;
}

export interface InsightDismissal {
  key: string;
  dismissed: boolean;
}

export interface RecurringIncomeDue {
  label: string;
  normalized: string;
  amount: number;
  cadence: string;
  expected_date: string;
}

export interface CashFlowForecast {
  month: string;
  days_in_month: number;
  day_of_month: number;
  days_remaining: number;
  observed_through: string | null;
  actual_income: number;
  actual_expenses: number;
  expected_income: number;
  expected_expenses: number;
  projected_net: number;
  income_basis: "recurring" | "trend";
  recurring_income_due: number;
  recurring_income_items: RecurringIncomeDue[];
  current_bank_balance: number;
  projected_end_balance: number;
  safe_to_spend: number;
  safe_to_spend_daily: number;
  avg_monthly_income: number;
  avg_monthly_expenses: number;
  committed_remaining: number;
  daily: { date: string; actual_balance: number | null; projected_balance: number | null }[];
}

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
    api.delete(`/cash-balances/${encodeURIComponent(accountName)}`),
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
  account_name?: string;
  provider?: string;
  transaction_amount?: number;
}

export interface RefundSourceAllocation {
  link_id: number;
  pending_refund_id: number;
  amount: number;
  pending_description?: string;
  pending_status: PendingRefund["status"];
  pending_date?: string;
  expected_amount: number;
}

export interface RefundSource {
  refund_source: string;
  refund_transaction_id: number;
  description?: string;
  date?: string;
  account_name?: string;
  provider?: string;
  transaction_amount: number | null;
  total_allocated: number;
  available: number | null;
  note?: string | null;
  allocations: RefundSourceAllocation[];
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
  getRefundSources: () =>
    api.get<RefundSource[]>("/pending-refunds/refund-sources"),
  updateNotes: (id: number, notes: string) =>
    api.patch<{ id: number; notes: string | null }>(`/pending-refunds/${id}`, {
      notes,
    }),
  setSourceNote: (data: {
    refund_source: string;
    refund_transaction_id: number;
    note: string;
  }) =>
    api.put<{ refund_source: string; refund_transaction_id: number; note: string | null }>(
      "/pending-refunds/refund-sources/note",
      data,
    ),
};

export interface BudgetMonthOverride {
  id: number;
  source_type: "transaction" | "split";
  source_id: string | number;
  source_table: string;
  override_year: number;
  override_month: number;
}

export const budgetMonthOverridesApi = {
  getAll: () =>
    api.get<BudgetMonthOverride[]>("/budget-month-overrides/"),
  set: (data: {
    source_type: "transaction" | "split";
    source_id: string | number;
    source_table: string;
    override_year: number;
    override_month: number;
  }) => api.post("/budget-month-overrides/", data),
  remove: (id: number) => api.delete(`/budget-month-overrides/${id}`),
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
  monthly_income: number | null;
  net_worth_override: number | null;
  monthly_expenses_override: number | null;
  total_investments_override: number | null;
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
  avg_monthly_salary: number | null;
}

/** Monthly pension estimated from the funds' own published forecasts. */
export interface PensionForecast {
  estimate: number | null;
  with_deposits: number;
  no_deposits: number;
  as_of: string | null;
  funds: number;
}

export interface RetirementProjections {
  fire_number: number;
  years_to_fire: number;
  fire_age: number;
  earliest_possible_retirement_age: number;
  monthly_savings_needed: number;
  progress_pct: number;
  // "funded" = never reaches the FIRE number in the target window, but the
  // portfolio never depletes either (pension / Bituach Leumi carry it).
  readiness: "on_track" | "close" | "funded" | "off_track";
  portfolio_depleted_age: number | null;
  target_retirement_age: number;
  full_pension_age: number;
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
  getScrapedDefaults: () =>
    api.get<ScrapedDefaults>("/retirement/scraped-defaults"),
  getPensionForecast: (currentAge: number, targetRetirementAge: number) =>
    api.get<PensionForecast>("/retirement/pension-forecast", {
      params: { current_age: currentAge, target_retirement_age: targetRetirementAge },
    }),
  getSuggestions: () =>
    api.get<RetirementSuggestions>("/retirement/suggestions"),
  previewSuggestions: (data: Omit<RetirementGoal, "id">) =>
    api.post<RetirementSuggestions>("/retirement/suggestions", data),
};

/** Where an entry came from: by hand, a "cover it" plan, the move to manual goals, or closing the goal. */
export type SavingsGoalEntrySource = "manual" | "cover" | "migrated" | "close";

/** One dated movement of money into (+) or out of (-) a goal. */
export interface SavingsGoalEntry {
  id: number;
  goal_id: number;
  /** `YYYY-MM-DD` */
  date: string;
  /** Signed: positive was added, negative was taken out. */
  amount: number;
  source: SavingsGoalEntrySource;
  note: string | null;
}

export interface SavingsGoal {
  id: number;
  name: string;
  target_amount: number;
  priority: number;
  /** Suggested monthly funding — never moves money on its own. */
  monthly_amount: number | null;
  start_month: string | null;
  target_date: string | null;
  contribution_category: string | null;
  contribution_tags: string | null;
  /** Category whose spending is drawn from the goal automatically. */
  utilization_category: string | null;
  /** Semicolon-separated tags narrowing `utilization_category`; `null` = every tag. */
  utilization_tags: string | null;
  status: "active" | "closed";
  closed_month: string | null;
  notes: string | null;
  /** Net money put in by hand (the sum of its entries). */
  added: number;
  /** Income its saved-into rule or links brought in. */
  income: number;
  /** Money spent out of it (linked spending, refunds netted). */
  spent: number;
  /** added + income — progress toward the target. */
  saved: number;
  /** saved - spent; negative only for a goal that spent ahead of its income. */
  balance: number;
  /** max(0, balance) — what it holds now. */
  available: number;
  /** max(0, -balance) — spent ahead of its income, repaid as that income arrives. */
  owed: number;
  remaining: number;
  progress_pct: number;
  is_achieved: boolean;
  is_closed: boolean;
  months_remaining: number | null;
  monthly_needed: number | null;
  /** The target date has passed and the goal is still short. */
  is_past_due: boolean;
  added_this_month: number;
  /** What to put in this month; 0 when there is nothing to suggest. */
  suggested_this_month: number;
  /** Newest first. */
  entries: SavingsGoalEntry[];
}

/** Create payload; an update takes a `Partial` and ignores `initial_amount`. */
export interface SavingsGoalInput {
  name: string;
  target_amount: number;
  priority?: number | null;
  monthly_amount?: number | null;
  start_month?: string | null;
  target_date?: string | null;
  contribution_category?: string | null;
  contribution_tags?: string | null;
  utilization_category?: string | null;
  utilization_tags?: string | null;
  notes?: string | null;
  /** Create only, >= 0: becomes the goal's first entry. */
  initial_amount?: number;
}

/** One goal's movement in a single month. */
export interface SavingsGoalMonthRow {
  goal_id: number;
  name: string;
  priority: number;
  status: string;
  added: number;
  income: number;
  spent: number;
  /** added + income - spent */
  change: number;
}

/** A month of goal movement — also the budget month analysis' `savings_goals`. */
export interface SavingsGoalMonth {
  year: number;
  month: number;
  /** Only goals with any movement that month. */
  goals: SavingsGoalMonthRow[];
  total_added: number;
  total_change: number;
}

/** One goal at the end of a month in the timeline. */
export interface SavingsGoalTimelineGoal {
  goal_id: number;
  /** What it held at month end. */
  balance: number;
  /** How much that moved during the month. */
  change: number;
}

export interface SavingsGoalTimelineMonth {
  month: string;
  /** Free cash at month end; may be negative. */
  free_cash: number;
  goals: SavingsGoalTimelineGoal[];
}

/** One calendar year's savings: income minus spending, against its target. */
export interface YearlySavingsYear {
  year: number;
  saved: number;
  /** `null` until a target is set for the year. */
  target: number | null;
  is_current: boolean;
  /** Every month on record that year, oldest first. */
  months: { month: string; saved: number }[];
}

/** Where an even pace toward this year's target stands today. */
export interface YearlySavingsPace {
  expected_by_today: number;
  /** Negative when behind. */
  ahead_by: number;
  needed_per_month: number;
  months_left: number;
}

export interface YearlySavings {
  current_year: number;
  /** Oldest first; always includes the current year. */
  years: YearlySavingsYear[];
  /** `null` while the current year has no target. */
  pace: YearlySavingsPace | null;
}

export interface SavingsGoalTimeline {
  has_goals: boolean;
  /** Full history length, so the UI offers "all time" only when it adds months. */
  total_months: number;
  /** Oldest first. */
  months: SavingsGoalTimelineMonth[];
  goals: {
    id: number;
    name: string;
    priority: number;
    status: string;
    is_closed: boolean;
  }[];
}

/** One step of the plan that takes money back from goals to cover a shortfall. */
export interface SavingsGoalCoverStep {
  goal_id: number;
  name: string;
  amount: number;
}

/** Bank and cash, less what the goals hold. */
export interface SavingsGoalFreeCash {
  /** May be negative: more set aside than there is. */
  free_cash: number;
  /** What the goals hold (the sum of their `available`). */
  earmarked: number;
  /** Bank + cash. */
  liquid: number;
  has_goals: boolean;
  /** max(0, -free_cash) */
  shortfall: number;
  /** Lowest priority first; empty unless there is a shortfall. */
  cover_plan: SavingsGoalCoverStep[];
}

export type SavingsGoalLinkType = "contribution" | "utilization";

export interface SavingsGoalLink {
  id: number;
  goal_id: number;
  source_type: string;
  source_id: number;
  source_table: string;
  link_type: SavingsGoalLinkType;
}

export const savingsGoalsApi = {
  getAll: () => api.get<SavingsGoal[]>("/savings-goals/"),
  create: (data: SavingsGoalInput) => api.post<SavingsGoal[]>("/savings-goals/", data),
  update: (id: number, data: Partial<SavingsGoalInput>) =>
    api.put<SavingsGoal[]>(`/savings-goals/${id}`, data),
  delete: (id: number) => api.delete(`/savings-goals/${id}`),
  reorder: (goalIds: number[]) =>
    api.post<SavingsGoal[]>("/savings-goals/reorder", { goal_ids: goalIds }),
  close: (id: number) => api.post<SavingsGoal[]>(`/savings-goals/${id}/close`),
  reopen: (id: number) => api.post<SavingsGoal[]>(`/savings-goals/${id}/reopen`),
  /** Put money in (positive) or take it out (negative). */
  addEntry: (goalId: number, amount: number, note?: string | null) =>
    api.post<SavingsGoal[]>(`/savings-goals/${goalId}/entries`, {
      amount,
      note: note ?? null,
    }),
  deleteEntry: (entryId: number) =>
    api.delete<SavingsGoal[]>(`/savings-goals/entries/${entryId}`),
  /** Fund this month's suggestions; `null` funds every goal that has one. */
  fund: (goalIds: number[] | null) =>
    api.post<SavingsGoal[]>("/savings-goals/fund", { goal_ids: goalIds }),
  getFreeCash: () => api.get<SavingsGoalFreeCash>("/savings-goals/free-cash"),
  /** Applies the current `cover_plan`. */
  cover: () => api.post<SavingsGoal[]>("/savings-goals/free-cash/cover"),
  getMonth: (year: number, month: number) =>
    api.get<SavingsGoalMonth>(`/savings-goals/month/${year}/${month}`),
  getYearly: () => api.get<YearlySavings>("/savings-goals/yearly"),
  /** `null` clears the year's target. */
  setYearlyTarget: (year: number, targetAmount: number | null) =>
    api.put<YearlySavings>(`/savings-goals/yearly/${year}/target`, {
      target_amount: targetAmount,
    }),
  /** Month-end balances and changes. `months: 0` asks for the whole timeline. */
  getTimeline: (months: number) =>
    api.get<SavingsGoalTimeline>("/savings-goals/timeline", {
      params: { months },
    }),
  getLinks: (goalId?: number) =>
    api.get<SavingsGoalLink[]>("/savings-goals/links", {
      params: goalId ? { goal_id: goalId } : undefined,
    }),
  link: (
    goalId: number,
    payload: {
      source_type: string;
      source_id: number;
      source_table: string;
      link_type: SavingsGoalLinkType;
    },
  ) => api.post<SavingsGoal[]>(`/savings-goals/${goalId}/links`, payload),
  unlink: (linkId: number) => api.delete(`/savings-goals/links/${linkId}`),
  /**
   * Spend a category (optionally narrowed to tags) out of a goal — a project
   * budget or a yearly envelope in one link. `category: null` clears it.
   */
  setSpendingLink: (
    goalId: number,
    category: string | null,
    tags: string[] | null = null,
  ) =>
    api.put<SavingsGoal[]>(`/savings-goals/${goalId}/spending-link`, {
      category,
      tags,
    }),
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
  prepareDemo: () =>
    api.post<{ status: string; created: boolean }>("/testing/demo/prepare"),
  resetDemo: () => api.post<{ status: string }>("/testing/demo/reset"),
  getDemoModeStatus: () =>
    api.get<{
      demo_mode: boolean;
      forced: boolean;
      sandboxed: boolean;
      durable: boolean;
      blob_configured: boolean;
    }>(
      "/testing/demo_mode_status",
    ),
};

export interface OnboardingStatus {
  has_credentials: boolean;
  has_transactions: boolean;
  has_budgets: boolean;
  has_investments: boolean;
  is_first_run: boolean;
}

export const onboardingApi = {
  getStatus: () => api.get<OnboardingStatus>("/onboarding/status"),
};

export interface VersionInfo {
  version: string;
  platform: string;
}

export const versionApi = {
  get: () => api.get<VersionInfo>("/version"),
};

export interface UpdateInfo {
  current: string;
  latest: string | null;
  is_outdated: boolean;
  asset_url: string | null;
  html_url: string | null;
  checked_at: string | null;
  error: string | null;
}

export const updatesApi = {
  check: () => api.get<UpdateInfo>("/updates/check"),
  refresh: () => api.post<UpdateInfo>("/updates/check"),
};

export interface UninstallResult {
  status: string;
  keyring_entries_deleted: number;
  user_dir_will_be_removed: boolean;
}

export const uninstallApi = {
  uninstall: (wipe_data: boolean) =>
    api.post<UninstallResult>("/uninstall", { wipe_data }),
};

export default api;
