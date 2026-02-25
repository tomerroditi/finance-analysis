import { http, HttpResponse } from "msw";

export const handlers = [
  // Tagging API
  http.get("/api/tagging/categories", () =>
    HttpResponse.json({
      categories: {
        Food: ["Groceries", "Restaurants"],
        Transport: ["Fuel", "Public Transport"],
      },
    }),
  ),
  http.post("/api/tagging/categories", () =>
    HttpResponse.json({ status: "ok" }),
  ),
  http.post("/api/tagging/tags", () =>
    HttpResponse.json({ status: "ok" }),
  ),

  // Transactions API
  http.get("/api/transactions/", () => HttpResponse.json([])),
  http.post("/api/transactions/bulk-tag", () =>
    HttpResponse.json({ status: "ok" }),
  ),

  // Testing API
  http.get("/api/testing/demo_mode_status", () =>
    HttpResponse.json({ demo_mode: false }),
  ),
  http.post("/api/testing/toggle_demo_mode", () =>
    HttpResponse.json({ status: "ok", demo_mode: true }),
  ),

  // Analytics API
  http.get("/api/analytics/overview", () =>
    HttpResponse.json({
      latest_data_date: null,
      total_income: 0,
      total_expenses: 0,
      total_investments: 0,
      net_balance_change: 0,
    }),
  ),
];
