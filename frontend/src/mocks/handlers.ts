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

export const mockRetirementGoal = {
  id: 1,
  current_age: 35,
  gender: "male",
  target_retirement_age: 55,
  life_expectancy: 90,
  monthly_expenses_in_retirement: 12000,
  inflation_rate: 2.5,
  expected_return_rate: 7,
  withdrawal_rate: 4,
  pension_monthly_payout_estimate: 3000,
  keren_hishtalmut_balance: 100000,
  keren_hishtalmut_monthly_contribution: 2500,
  bituach_leumi_eligible: true,
  bituach_leumi_monthly_estimate: 4000,
  other_passive_income: 0,
};

export const mockRetirementStatus = {
  net_worth: 500000,
  avg_monthly_expenses: 10000,
  avg_monthly_income: 15000,
  savings_rate: 33.3,
  total_investments: 35000,
  monthly_savings: 5000,
};

export const mockRetirementProjections = {
  fire_number: 3600000,
  years_to_fire: 18,
  fire_age: 53,
  earliest_possible_retirement_age: 50,
  monthly_savings_needed: 8000,
  progress_pct: 13.9,
  readiness: "off_track" as const,
  portfolio_depleted_age: 85,
  target_retirement_age: 55,
  net_worth_projection: [
    { age: 35, net_worth_optimistic: 500000, net_worth_baseline: 500000, net_worth_conservative: 500000 },
    { age: 45, net_worth_optimistic: 1500000, net_worth_baseline: 1200000, net_worth_conservative: 900000 },
    { age: 55, net_worth_optimistic: 4000000, net_worth_baseline: 3000000, net_worth_conservative: 2000000 },
  ],
  income_projection: [
    { age: 55, salary_savings: 0, portfolio_withdrawal: 10000, pension: 3000, bituach_leumi: 4000, passive_income: 0, total_income: 17000, expenses: 12000 },
  ],
};

export const mockRetirementSuggestions = {
  target_retirement_age: 58,
  monthly_expenses_in_retirement: 10000,
  expected_return_rate: 8,
  life_expectancy: 85,
};

// ── Handlers ────────────────────────────────────────────────────────

export const handlers = [
  // ── Tagging API ──
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
  http.get("/api/transactions/:id", () =>
    HttpResponse.json(mockTransactions[0]),
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
  http.get("/api/budget/projects", () => HttpResponse.json([])),
  http.get("/api/budget/projects/available", () =>
    HttpResponse.json([]),
  ),
  http.post("/api/budget/projects", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.put("/api/budget/projects/:name", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.delete("/api/budget/projects/:name", () =>
    HttpResponse.json({ status: "ok" }),
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
  http.get("/api/analytics/by-category", () =>
    HttpResponse.json({
      expenses: [
        { category: "Food", amount: -1200 },
        { category: "Transport", amount: -300 },
      ],
      refunds: [],
    }),
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
      investments: [
        {
          id: 1,
          name: "S&P 500 ETF",
          data: [
            { date: "2026-01-01", balance: 20000 },
            { date: "2026-02-01", balance: 22000 },
            { date: "2026-03-01", balance: 25000 },
          ],
        },
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
      insurances: ["hafenix"],
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
  http.post("/api/pending-refunds/", () =>
    HttpResponse.json({ id: 1, status: "ok" }),
  ),

  // ── Retirement API ──
  http.get("/api/retirement/goal", () =>
    HttpResponse.json(mockRetirementGoal),
  ),
  http.put("/api/retirement/goal", () =>
    HttpResponse.json(mockRetirementGoal),
  ),
  http.get("/api/retirement/status", () =>
    HttpResponse.json(mockRetirementStatus),
  ),
  http.get("/api/retirement/projections", () =>
    HttpResponse.json(mockRetirementProjections),
  ),
  http.post("/api/retirement/projections", () =>
    HttpResponse.json(mockRetirementProjections),
  ),
  http.get("/api/retirement/suggestions", () =>
    HttpResponse.json(mockRetirementSuggestions),
  ),
  http.post("/api/retirement/suggestions", () =>
    HttpResponse.json(mockRetirementSuggestions),
  ),
  http.get("/api/retirement/keren-hishtalmut-balance", () =>
    HttpResponse.json({ balance: 100000 }),
  ),

  // ── Insurance Accounts API ──
  http.get("/api/insurance-accounts/", () => HttpResponse.json([])),

  // ── Backups API ──
  http.get("/api/backups/", () => HttpResponse.json([])),

  // ── Testing/Demo Mode API ──
  http.get("/api/testing/demo_mode_status", () =>
    HttpResponse.json({ demo_mode: false }),
  ),
  http.post("/api/testing/toggle_demo_mode", () =>
    HttpResponse.json({ status: "ok", demo_mode: true }),
  ),
];
