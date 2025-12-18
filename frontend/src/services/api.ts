import axios from 'axios';

const api = axios.create({
    baseURL: '/api',
    headers: {
        'Content-Type': 'application/json',
    },
});

// Request interceptor for error handling
api.interceptors.response.use(
    (response) => response,
    (error) => {
        console.error('API Error:', error.response?.data || error.message);
        return Promise.reject(error);
    }
);

// Transactions API
export const transactionsApi = {
    getAll: (service?: string) =>
        api.get('/transactions', { params: { service } }),
    getById: (id: number) =>
        api.get(`/transactions/${id}`),
    updateTag: (id: string, category: string, tag: string, service: string) =>
        api.put(`/transactions/${id}/tag`, null, { params: { category, tag, service } }),
};

// Budget API
export const budgetApi = {
    getRules: () => api.get('/budget/rules'),
    getRulesByMonth: (year: number, month: number) =>
        api.get(`/budget/rules/${year}/${month}`),
    createRule: (rule: object) => api.post('/budget/rules', rule),
    updateRule: (id: number, rule: object) => api.put(`/budget/rules/${id}`, rule),
    deleteRule: (id: number) => api.delete(`/budget/rules/${id}`),
};

// Tagging API
export const taggingApi = {
    getCategories: () => api.get('/tagging/categories'),
    createCategory: (name: string, tags?: string[]) =>
        api.post('/tagging/categories', { name, tags }),
    createTag: (category: string, name: string) =>
        api.post('/tagging/tags', { category, name }),
    getRules: (activeOnly = true) =>
        api.get('/tagging/rules', { params: { active_only: activeOnly } }),
};

// Credentials API
export const credentialsApi = {
    getAll: () => api.get('/credentials'),
    getAccounts: () => api.get('/credentials/accounts'),
    delete: (service: string, provider: string, account: string) =>
        api.delete(`/credentials/${service}/${provider}/${account}`),
};

// Scraping API
export const scrapingApi = {
    getHistory: () => api.get('/scraping/history'),
    getTodaySummary: () => api.get('/scraping/today'),
    start: () => api.post('/scraping/start'),
    submit2fa: (scraperName: string, code: string) =>
        api.post('/scraping/2fa', { scraper_name: scraperName, code }),
};

// Investments API
export const investmentsApi = {
    getAll: (includeClosed = false) =>
        api.get('/investments', { params: { include_closed: includeClosed } }),
    getById: (id: number) => api.get(`/investments/${id}`),
    create: (investment: object) => api.post('/investments', investment),
    update: (id: number, investment: object) => api.put(`/investments/${id}`, investment),
    close: (id: number, closedDate: string) =>
        api.post(`/investments/${id}/close`, null, { params: { closed_date: closedDate } }),
    reopen: (id: number) => api.post(`/investments/${id}/reopen`),
    delete: (id: number) => api.delete(`/investments/${id}`),
};

// Analytics API
export const analyticsApi = {
    getOverview: () => api.get('/analytics/overview'),
    getIncomeOutcome: (year?: number, month?: number) =>
        api.get('/analytics/income-outcome', { params: { year, month } }),
    getByCategory: () => api.get('/analytics/by-category'),
};

export default api;
