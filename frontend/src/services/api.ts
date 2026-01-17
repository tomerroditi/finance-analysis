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
  getAnalysis: (year: number, month: number) =>
    api.get(`/budget/analysis/${year}/${month}`),
  getProjects: () => api.get("/budget/projects"),
  getAvailableProjects: () => api.get("/budget/projects/available"),
  createProject: (project: { category: string; total_budget: number }) =>
    api.post("/budget/projects", project),
  updateProject: (name: string, data: { total_budget: number }) =>
    api.put(`/budget/projects/${name}`, data),
  getProjectDetails: (name: string) => api.get(`/budget/projects/${name}`),
  deleteProject: (name: string) => api.delete(`/budget/projects/${name}`),
};

// Tagging API
export const taggingApi = {
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
  getRules: (activeOnly = true) =>
    api.get("/tagging/rules", { params: { active_only: activeOnly } }),
  createRule: (rule: any) => api.post("/tagging/rules", rule),
  updateRule: (id: number, rule: any) => api.put(`/tagging/rules/${id}`, rule),
  deleteRule: (id: number) => api.delete(`/tagging/rules/${id}`),
  applyRules: () => api.post("/tagging/rules/apply"),
  testRule: (conditions: any[]) => api.post("/tagging/rules/test", conditions),
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
  getOverview: (startDate?: string, endDate?: string) =>
    api.get("/analytics/overview", {
      params: { start_date: startDate, end_date: endDate },
    }),
  getIncomeOutcome: (startDate?: string, endDate?: string) =>
    api.get("/analytics/income-outcome", {
      params: { start_date: startDate, end_date: endDate },
    }),
  getByCategory: (startDate?: string, endDate?: string) =>
    api.get("/analytics/by-category", {
      params: { start_date: startDate, end_date: endDate },
    }),
  getMonthlyTrend: (startDate?: string, endDate?: string) =>
    api.get("/analytics/monthly-trend", {
      params: { start_date: startDate, end_date: endDate },
    }),
  getSankeyData: (startDate?: string, endDate?: string) =>
    api.get("/analytics/sankey", {
      params: { start_date: startDate, end_date: endDate },
    }),
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
