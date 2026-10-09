import { http, HttpResponse } from "msw";

// ── Shared mock data factories ──────────────────────────────────────

export const mockCategories: Record<string, string[]> = {
  Food: ["Groceries", "Restaurants"],
  Transport: ["Fuel", "Public Transport"],
  Housing: ["Rent", "Utilities"],
  Salary: [],
  "Other Income": [],
  Investments: [],
  Liabilities: [],
  Ignore: [],
  "Credit Cards": [],
};

export const mockTransactions = [
  {
    id: 1,
    unique_id: "bank_tx_1",
    source: "bank_transactions",
    description: "Supermarket Purchase",
    amount: -250,
    date: "2026-03-15",
    category: "Food",
    tag: "Groceries",
    provider: "hapoalim",
    account_name: "Main Account",
  },
  {
    id: 2,
    unique_id: "bank_tx_2",
    source: "bank_transactions",
    description: "Monthly Salary",
    amount: 15000,
    date: "2026-03-01",
    category: "Salary",
    tag: null,
    provider: "hapoalim",
    account_name: "Main Account",
  },
  {
    id: 3,
    unique_id: "cc_tx_1",
    source: "credit_card_transactions",
    description: "Gas Station",
    amount: -180,
    date: "2026-03-10",
    category: "Transport",
    tag: "Fuel",
    provider: "max",
    account_name: "Max Card",
  },
  {
    id: 4,
    unique_id: "cash_tx_1",
    source: "cash_transactions",
    description: "Coffee",
    amount: -15,
    date: "2026-03-12",
    category: null,
    tag: null,
    provider: "cash",
    account_name: "Wallet",
  },
];

export const mockBankBalances = [
  {
    id: 1,
    provider: "hapoalim",
    account_name: "Main Account",
    balance: 50000,
    prior_wealth_amount: 30000,
    last_manual_update: "2026-03-01",
    last_scrape_update: "2026-03-15",
  },
];

export const mockCashBalances = [
  {
    id: 1,
    account_name: "Wallet",
    balance: 500,
    prior_wealth_amount: 0,
    last_manual_update: "2026-03-01",
  },
];

export const mockInvestments = [
  {
    id: 1,
    name: "S&P 500 ETF",
    type: "stocks",
    category: "Investments",
    tag: null,
    is_closed: 0,
    closed_date: null,
    interest_rate: null,
    interest_rate_type: null,
    notes: null,
    current_balance: 25000,
    total_deposits: 20000,
    total_withdrawals: 0,
    profit_loss: 5000,
    roi: 25,
  },
  {
    id: 2,
    name: "Government Bonds",
    type: "bonds",
    category: "Investments",
    tag: null,
    is_closed: 0,
    closed_date: null,
    interest_rate: 4.5,
    interest_rate_type: "fixed",
    notes: "5-year term",
    current_balance: 10000,
    total_deposits: 10000,
    total_withdrawals: 0,
    profit_loss: 0,
    roi: 0,
  },
  {
    id: 3,
    name: "Migdal 007-916-407357",
    type: "hishtalmut",
    category: "Investments",
    tag: null,
    is_closed: 0,
    closed_date: null,
    interest_rate: null,
    interest_rate_type: null,
    notes: null,
    insurance_policy_id: "007-916-407357",
    liquidity_date: "2030-01-01",
    commission_deposit: 1.5,
    commission_management: 0.4,
    current_balance: 15000,
    total_deposits: 14000,
    total_withdrawals: 0,
    profit_loss: 1000,
    roi: 7.14,
  },
];

export const mockLiabilities = [
  {
    id: 1,
    name: "Home Mortgage",
    lender: "Bank Hapoalim",
    principal: 500000,
    interest_rate: 3.5,
    interest_rate_type: "fixed",
    term_months: 240,
    start_date: "2024-01-01",
    category: "Liabilities",
    tag: "Mortgage",
    is_paid_off: 0,
    paid_off_date: null,
    notes: null,
    remaining_balance: 480000,
    monthly_payment: 2900,
    total_interest_cost: 196000,
    payments_made: 27,
    percent_paid: 4,
  },
];

export const mockPortfolioAnalysis = {
  total_value: 35000,
  total_profit: 5000,
  portfolio_roi: 16.67,
  allocation: [
    {
      id: 1,
      name: "S&P 500 ETF",
      type: "stocks",
      balance: 25000,
      profit_loss: 5000,
      roi: 25,
    },
    {
      id: 2,
      name: "Government Bonds",
      type: "bonds",
      balance: 10000,
      profit_loss: 0,
      roi: 0,
    },
  ],
};

export const mockOverview = {
  latest_data_date: "2026-03-15",
  total_income: 15000,
  total_expenses: 5000,
  total_investments: 30000,
  net_balance_change: 10000,
};

export const mockBudgetRules = [
  {
    id: 1,
    category: "Food",
    tag: null,
    amount: 2000,
    year: 2026,
    month: 3,
    is_project: false,
  },
  {
    id: 2,
    category: "Transport",
    tag: null,
    amount: 500,
    year: 2026,
    month: 3,
    is_project: false,
  },
];

export const mockBudgetAnalysis = {
  rules: [
    {
      rule: { id: 1, name: "Food", category: "Food", tags: null, amount: 2000 },
      current_amount: 1200,
    },
    {
      rule: { id: 2, name: "Transport", category: "Transport", tags: null, amount: 500 },
      current_amount: 300,
    },
  ],
  total_budgeted: 2500,
  total_spent: 1500,
};

export const mockCredentials = [
  {
    service: "banks",
    provider: "hapoalim",
    account_name: "Main Account",
  },
  {
    service: "credit_cards",
    provider: "max",
    account_name: "Max Card",
  },
];

/** A saved plan following one tracked portfolio and the cash balance. */
export const mockFirePlan = {
  saved: true,
  fields: {
    dateOfBirth: "1990-01-01",
    gender: "male",
    base_problem: "retire_asap",
    base_problem_max_age: "60",
    balance: "50000",
    num_expense_fields: "1",
    expenseSum1: "12000",
    num_income_fields: "1",
    incomeSum1: "20000",
    num_portfolio_fields: "1",
    portfolioBalance1: "300000",
    portfolioDescription1: "Index fund",
    portfolioSource1: "investment:1",
    num_keren_fields: "0",
    num_loan_fields: "0",
    num_realestate_fields: "0",
  },
  linked: ["balance"],
  tracked: {
    scalars: { balance: "50000" },
    rows: {
      portfolio: [
        {
          source: "investment:1",
          label: "Index fund",
          fields: { portfolioBalance: "300000" },
          seed: { portfolioDescription: "Index fund" },
        },
        {
          source: "investment:2",
          label: "Bonds",
          fields: { portfolioBalance: "80000" },
          seed: { portfolioDescription: "Bonds" },
        },
      ],
    },
  },
};

/** The saved plan's projection: retire at 52.5, two goals met. */
export const mockFireProjection = {
  status: "success" as const,
  retire_index: 200,
  retire_age: 52.5,
  retire_year: 2042,
  retire_month: 7,
  search_limit_months: 300,
  inferred: false,
  goals: [
    { key: "living_expenses", label: "", met: true, shortfall: 0 },
    { key: "bequest", label: "", met: true, shortfall: 0 },
  ],
  months: [
    { index: 0, year: 2026, month: 10, age: 36.75, net_worth: 350000, cash: 50000, assets: {}, incomes: {}, expenses: {}, liabilities: 0 },
    { index: 12, year: 2027, month: 10, age: 37.75, net_worth: 420000, cash: 50000, assets: {}, incomes: {}, expenses: {}, liabilities: 0 },
  ],
  recommendation: null,
  annuities: [],
  withdrawal_plan: [],
  snapshots: [
    { label: "now", year: 2026, month: 10, net_worth: 350000, breakdown: {}, shortfall_capital: 0 },
    { label: "retirement", year: 2042, month: 7, net_worth: 2400000, breakdown: {}, shortfall_capital: 0 },
  ],
  pension_income: [{ owner: "", age: 67, monthly: 6500 }],
};

// ── Handlers ────────────────────────────────────────────────────────

export const handlers = [
  // ── Tagging API ──
  http.get("/api/tagging/categories/usage", () =>
    HttpResponse.json(
      Object.fromEntries(
        Object.keys(mockCategories).map((name) => [
          name,
          { last_used: "2026-08-01", unused: false },
        ]),
      ),
    ),
  ),
  http.get("/api/tagging/categories", () =>
    HttpResponse.json(mockCategories),
  ),
  http.post("/api/tagging/categories", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.delete("/api/tagging/categories/:name", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.post("/api/tagging/tags", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.delete("/api/tagging/tags/:category/:name", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.put("/api/tagging/categories/:name", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.put("/api/tagging/tags/:category/:name", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.post("/api/tagging/tags/relocate", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.get("/api/tagging/icons", () =>
    HttpResponse.json({ Food: "🍔", Transport: "🚗", Housing: "🏠" }),
  ),
  http.put("/api/tagging/icons/:category", () =>
    HttpResponse.json({ status: "ok" }),
  ),

  // ── Tagging Rules API ──
  http.get("/api/tagging-rules/rules", () => HttpResponse.json([])),
  http.post("/api/tagging-rules/rules", () =>
    HttpResponse.json({ id: 1, status: "ok" }),
  ),

  // ── Transactions API ──
  http.get("/api/transactions/", () =>
    HttpResponse.json(mockTransactions),
  ),
  http.post("/api/transactions/", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.put("/api/transactions/:id", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.delete("/api/transactions/:id", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.post("/api/transactions/bulk-tag", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.post("/api/transactions/:id/split", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.put("/api/transactions/:id/tag", () =>
    HttpResponse.json({ status: "ok" }),
  ),

  // ── Budget API ──
  http.get("/api/budget/rules", () =>
    HttpResponse.json(mockBudgetRules),
  ),
  http.get("/api/budget/rules/:year/:month", () =>
    HttpResponse.json(mockBudgetRules),
  ),
  http.post("/api/budget/rules", () =>
    HttpResponse.json({ id: 3, status: "ok" }),
  ),
  http.put("/api/budget/rules/:id", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.delete("/api/budget/rules/:id", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.post("/api/budget/rules/:year/:month/copy", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.get("/api/budget/analysis/:year/:month", () =>
    HttpResponse.json(mockBudgetAnalysis),
  ),
  // The budget page fires these on mount. Unhandled, MSW passes them to the
  // real network, they fail, and the axios interceptor `console.error`s — a
  // log that can land after the test file's worker has closed its RPC, which
  // fails the whole vitest run with an EnvironmentTeardownError.
  http.get("/api/savings-goals/", () => HttpResponse.json([])),
  http.get("/api/savings-goals/links", () => HttpResponse.json([])),
  http.get("/api/savings-goals/free-cash", () =>
    HttpResponse.json({
      free_cash: 0,
      earmarked: 0,
      liquid: 0,
      clawed_back_this_month: 0,
      has_goals: false,
    }),
  ),
  http.get("/api/budget/category-conflicts", () =>
    HttpResponse.json({ conflicts: [] }),
  ),
  http.get("/api/budget-month-overrides/", () => HttpResponse.json([])),
  http.get("/api/budget/projects", () => HttpResponse.json([])),
  http.get("/api/budget/projects/available", () =>
    HttpResponse.json([]),
  ),
  // Ahead of the "/:name" handler below, which would otherwise swallow the
  // literal path and answer a project-details object where a list is expected.
  http.get("/api/budget/projects/status", () => HttpResponse.json([])),
  http.post("/api/budget/projects", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.put("/api/budget/projects/:name", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.delete("/api/budget/projects/:name", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.put("/api/budget/projects/:name/closed", () =>
    HttpResponse.json({ status: "success", name: "Test", closed: true }),
  ),
  http.get("/api/budget/projects/:name", () =>
    HttpResponse.json({ name: "Test", rules: [], transactions: [] }),
  ),

  // ── Analytics API ──
  http.get("/api/analytics/overview", () =>
    HttpResponse.json(mockOverview),
  ),
  http.get("/api/analytics/income-expenses-over-time", () =>
    HttpResponse.json([
      { month: "2026-01", income: 15000, expenses: 5000 },
      { month: "2026-02", income: 15000, expenses: 6000 },
      { month: "2026-03", income: 15000, expenses: 4500 },
    ]),
  ),
  http.get("/api/analytics/debt-payments-over-time", () =>
    HttpResponse.json([
      { month: "2026-01", amount: 2900, tags: { Mortgage: 2900 } },
      { month: "2026-02", amount: 2900, tags: { Mortgage: 2900 } },
    ]),
  ),
  http.get("/api/analytics/expenses-by-category-over-time", () =>
    HttpResponse.json([
      { month: "2026-03", categories: { Food: 1200, Transport: 300 } },
    ]),
  ),
  http.get("/api/analytics/sankey", () =>
    HttpResponse.json({
      nodes: [],
      links: [],
    }),
  ),
  http.get("/api/analytics/net-worth-over-time", () =>
    HttpResponse.json([
      { month: "2026-01", bank_balance: 45000, investment_value: 30000, cash: 500, net_worth: 75500 },
      { month: "2026-02", bank_balance: 48000, investment_value: 32000, cash: 500, net_worth: 80500 },
      { month: "2026-03", bank_balance: 50000, investment_value: 35000, cash: 500, net_worth: 85500 },
    ]),
  ),
  http.get("/api/analytics/income-by-source-over-time", () =>
    HttpResponse.json([
      { month: "2026-03", sources: { Salary: 15000 }, total: 15000 },
    ]),
  ),
  http.get("/api/analytics/monthly-expenses", () =>
    HttpResponse.json({
      months: [
        { month: "2026-01", expenses: 5000 },
        { month: "2026-02", expenses: 6000 },
        { month: "2026-03", expenses: 4500 },
      ],
      avg_3_months: 5167,
      avg_6_months: 5167,
      avg_12_months: 5167,
    }),
  ),
  http.get("/api/analytics/net-balance-over-time", () =>
    HttpResponse.json([
      { month: "2026-03", net_change: 10000, cumulative_balance: 50000 },
    ]),
  ),

  // ── Bank Balances API ──
  http.get("/api/bank-balances/", () =>
    HttpResponse.json(mockBankBalances),
  ),
  http.post("/api/bank-balances/", () =>
    HttpResponse.json(mockBankBalances[0]),
  ),

  // ── Cash Balances API ──
  http.get("/api/cash-balances/", () =>
    HttpResponse.json(mockCashBalances),
  ),
  http.post("/api/cash-balances/", () =>
    HttpResponse.json(mockCashBalances[0]),
  ),
  http.post("/api/cash-balances/migrate", () =>
    HttpResponse.json(mockCashBalances),
  ),
  http.delete("/api/cash-balances/:name", () =>
    HttpResponse.json({ status: "ok" }),
  ),

  // ── Investments API ──
  http.get("/api/investments", () =>
    HttpResponse.json(mockInvestments),
  ),
  http.get("/api/investments/:id", () =>
    HttpResponse.json(mockInvestments[0]),
  ),
  http.post("/api/investments", () =>
    HttpResponse.json({ id: 3, status: "ok" }),
  ),
  http.put("/api/investments/:id", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.delete("/api/investments/:id", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.post("/api/investments/:id/close", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.post("/api/investments/:id/reopen", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.get("/api/investments/analysis/portfolio", () =>
    HttpResponse.json(mockPortfolioAnalysis),
  ),
  http.get("/api/investments/analysis/balance-history", () =>
    HttpResponse.json({
      series: [
        {
          id: 1,
          name: "S&P 500 ETF",
          tag: "Stocks",
          data: [
            { date: "2026-01-01", balance: 20000 },
            { date: "2026-02-01", balance: 22000 },
            { date: "2026-03-01", balance: 25000 },
          ],
        },
      ],
      total: [
        { date: "2026-01-01", balance: 20000 },
        { date: "2026-02-01", balance: 22000 },
        { date: "2026-03-01", balance: 25000 },
      ],
    }),
  ),
  http.get("/api/investments/:id/analysis", () =>
    HttpResponse.json({
      total_deposits: 20000,
      total_withdrawals: 0,
      net_invested: 20000,
      current_balance: 25000,
      profit_loss: 5000,
      roi: 25,
      cagr: 12.5,
    }),
  ),
  http.get("/api/investments/:id/balances", () =>
    HttpResponse.json([
      { id: 1, date: "2026-03-01", balance: 25000, source: "manual" },
    ]),
  ),
  http.post("/api/investments/:id/balances", () =>
    HttpResponse.json({ id: 2, status: "ok" }),
  ),

  // ── Liabilities API ──
  http.get("/api/liabilities/", () =>
    HttpResponse.json(mockLiabilities),
  ),
  http.get("/api/liabilities/:id", () =>
    HttpResponse.json(mockLiabilities[0]),
  ),
  http.post("/api/liabilities/", () =>
    HttpResponse.json({ id: 2, status: "ok" }),
  ),
  http.put("/api/liabilities/:id", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.delete("/api/liabilities/:id", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.post("/api/liabilities/:id/pay-off", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.post("/api/liabilities/:id/reopen", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.get("/api/liabilities/:id/analysis", () =>
    HttpResponse.json({
      amortization_schedule: [],
      payment_history: [],
      actual_vs_expected: [],
      total_interest_paid: 5000,
      total_interest_remaining: 191000,
      monthly_payment: 2900,
      percent_paid: 4,
      payments_made: 27,
    }),
  ),
  http.get("/api/liabilities/:id/transactions", () =>
    HttpResponse.json([]),
  ),
  http.get("/api/liabilities/debt-over-time", () =>
    HttpResponse.json([
      { month: "2026-01", liabilities: { "Home Mortgage": 485000 } },
      { month: "2026-02", liabilities: { "Home Mortgage": 482000 } },
      { month: "2026-03", liabilities: { "Home Mortgage": 480000 } },
    ]),
  ),
  http.get("/api/liabilities/detect-transactions", () =>
    HttpResponse.json({ receipt: null, payments: [] }),
  ),

  // ── Credentials API ──
  http.get("/api/credentials", () =>
    HttpResponse.json(mockCredentials),
  ),
  http.get("/api/credentials/accounts", () =>
    HttpResponse.json(mockCredentials),
  ),
  http.get("/api/credentials/providers", () =>
    HttpResponse.json({
      banks: ["hapoalim", "leumi", "discount"],
      credit_cards: ["max", "visa_cal", "isracard"],
      insurances: ["mislaka"],
    }),
  ),
  http.get("/api/credentials/fields/:provider", () =>
    HttpResponse.json([
      { name: "username", type: "text", label: "Username" },
      { name: "password", type: "password", label: "Password" },
    ]),
  ),
  http.post("/api/credentials", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.delete("/api/credentials/:service/:provider/:account", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.get("/api/credentials/:service/:provider/:account", () =>
    HttpResponse.json({ username: "testuser" }),
  ),

  // ── Scraping API ──
  http.get("/api/scraping/status", () =>
    HttpResponse.json({ status: "done" }),
  ),
  http.post("/api/scraping/start", () =>
    HttpResponse.json({ process_id: 1, status: "running" }),
  ),
  http.post("/api/scraping/abort", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.get("/api/scraping/active", () => HttpResponse.json([])),
  http.get("/api/scraping/last-scrapes", () =>
    HttpResponse.json([
      {
        service: "banks",
        provider: "hapoalim",
        account_name: "Main Account",
        last_scrape_date: "2026-03-15",
      },
    ]),
  ),

  // ── Pending Refunds API ──
  http.get("/api/pending-refunds/", () => HttpResponse.json([])),
  http.get("/api/pending-refunds/budget-adjustment", () =>
    HttpResponse.json({ total: 0 }),
  ),
  http.get("/api/pending-refunds/refund-sources", () =>
    HttpResponse.json([]),
  ),
  http.post("/api/pending-refunds/", () =>
    HttpResponse.json({ id: 1, status: "ok" }),
  ),

  // ── Early-retirement plan API ──
  http.get("/api/fire/plan", () => HttpResponse.json(mockFirePlan)),
  http.put("/api/fire/plan", () => HttpResponse.json(mockFirePlan)),
  http.delete("/api/fire/plan", () =>
    HttpResponse.json({ ...mockFirePlan, saved: false }),
  ),
  http.get("/api/fire/plan/projection", () =>
    HttpResponse.json(mockFireProjection),
  ),
  http.post("/api/fire/calculate", () => HttpResponse.json(mockFireProjection)),

  // ── Insurance Accounts API ──
  http.get("/api/insurance-accounts/", () => HttpResponse.json([])),
  http.get("/api/insurance-accounts/clearing-house-reports", () =>
    HttpResponse.json([]),
  ),

  // ── Backups API ──
  http.get("/api/backups/", () => HttpResponse.json([])),

  // ── Testing/Demo Mode API ──
  http.get("/api/testing/demo_mode_status", () =>
    HttpResponse.json({
      demo_mode: false,
      forced: false,
      sandboxed: false,
      durable: false,
      blob_configured: false,
    }),
  ),
  http.post("/api/testing/demo/prepare", () =>
    HttpResponse.json({ status: "success", created: false }),
  ),
  http.post("/api/testing/demo/reset", () =>
    HttpResponse.json({ status: "success" }),
  ),
];
