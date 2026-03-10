# Income Breakdown Over Time — Design

## Goal

Add a stacked bar chart to the Dashboard showing income broken down by source (category+tag) per month. Enables seeing both composition (what % comes from each source) and trends (how sources change over time).

## Visualization

**Chart type:** Stacked bar chart (Plotly, inline in Dashboard — same as existing charts).

**Placement:** After the existing "Monthly Income vs Expenses" chart, in a full-width container.

Each month is one bar. Each colored segment represents an income source. Hover shows source name, amount, and percentage of that month's total.

## Data Model

### API Endpoint

`GET /analytics/income-by-source-over-time?start_date=&end_date=`

### Response Shape

```json
[
  {
    "month": "2024-01",
    "sources": {
      "Salary": 8000,
      "Other Income / Freelance": 1500,
      "Liabilities (Loans)": 3000
    },
    "total": 12500
  }
]
```

### Income Source Identification

Reuses existing `_get_income_mask()` logic:
- Transactions where `category` is in `IncomeCategories` (Salary, Other Income)
- Transactions where `category` is in `LiabilitiesCategories` AND `amount > 0` (loan disbursements)
- Credit card transactions are always excluded

### Source Naming Convention

| Scenario | Label |
|----------|-------|
| Category with single/no tag | Category name (e.g., "Salary") |
| Category with multiple tags | "Category / Tag" (e.g., "Other Income / Freelance") |
| Positive liabilities | "Loans" |
| Prior Wealth tag | **Excluded** (one-time baseline, shown in net worth chart) |

## Implementation Scope

| Layer | File | Change |
|-------|------|--------|
| Service | `backend/services/analysis_service.py` | New `get_income_by_source_over_time()` method |
| Route | `backend/routes/analytics.py` | New `GET /analytics/income-by-source-over-time` endpoint |
| Frontend API | `frontend/src/services/api.ts` | New `getIncomeBySourceOverTime()` on `analyticsApi` |
| Dashboard | `frontend/src/pages/Dashboard.tsx` | New query + stacked bar chart section |
| Tests | `tests/backend/unit/services/test_analysis_service.py` | Unit tests for new method |
| Tests | `tests/backend/routes/test_analytics_routes.py` | Route tests for new endpoint |

No new components, no new dependencies.

## Edge Cases

- **Months with no income:** Zero-height bar (natural Plotly behavior)
- **Sources appearing in some months only:** Included with zero value (Plotly handles automatically)
- **Prior Wealth:** Excluded — not recurring income
- **Empty dataset:** Return empty list, chart shows nothing

## Color Palette

Green-toned sequential palette for consistency with income = green convention across the dashboard. Plotly's default color sequence provides sufficient contrast between segments.
