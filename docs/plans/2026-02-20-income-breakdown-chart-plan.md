# Income Breakdown Over Time — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a stacked bar chart to the Dashboard showing income broken down by source (category+tag) per month.

**Architecture:** New backend service method groups income transactions by month and category+tag label. New API endpoint exposes it. Frontend renders a Plotly stacked bar chart in the Dashboard, placed after "Monthly Income vs Expenses".

**Tech Stack:** Python/Pandas (backend), FastAPI route, TypeScript/React/Plotly (frontend)

---

### Task 1: Backend Service — `get_income_by_source_over_time()`

**Files:**
- Test: `tests/backend/unit/services/test_analysis_service.py`
- Modify: `backend/services/analysis_service.py`

**Step 1: Write the failing tests**

Add to `tests/backend/unit/services/test_analysis_service.py`:

```python
class TestAnalysisServiceIncomeBySource:
    """Tests for income breakdown by source over time."""

    def test_get_income_by_source_over_time(self, db_session, seed_base_transactions):
        """Verify monthly income is broken down by category+tag source."""
        service = AnalysisService(db_session)
        result = service.get_income_by_source_over_time()

        assert len(result) == 3
        months = [r["month"] for r in result]
        assert months == ["2024-01", "2024-02", "2024-03"]

        # January: only Salary 8000
        jan = result[0]
        assert jan["sources"] == {"Salary": 8000.0}
        assert jan["total"] == 8000.0

        # February: Salary 8500 + Other Income 3500
        feb = result[1]
        assert feb["sources"] == {"Salary": 8500.0, "Other Income": 3500.0}
        assert feb["total"] == 12000.0

        # March: only Salary 8200
        mar = result[2]
        assert mar["sources"] == {"Salary": 8200.0}
        assert mar["total"] == 8200.0

    def test_get_income_by_source_over_time_with_date_filter(
        self, db_session, seed_base_transactions
    ):
        """Verify date filtering narrows results to specified range."""
        service = AnalysisService(db_session)
        result = service.get_income_by_source_over_time(
            start_date="2024-02-01", end_date="2024-02-28"
        )

        assert len(result) == 1
        assert result[0]["month"] == "2024-02"
        assert result[0]["sources"]["Salary"] == 8500.0
        assert result[0]["sources"]["Other Income"] == 3500.0

    def test_get_income_by_source_over_time_with_tags(self, db_session):
        """Verify category/tag combo labels when tags exist on income transactions."""
        from backend.models.transaction import BankTransaction

        records = [
            BankTransaction(
                id="bank_tag_1", date="2024-04-01", provider="hapoalim",
                account_name="Checking", description="Salary April",
                amount=8000.0, category="Salary", tag=None,
                source="bank_transactions", type="normal", status="completed",
            ),
            BankTransaction(
                id="bank_tag_2", date="2024-04-10", provider="leumi",
                account_name="Business", description="Freelance Project A",
                amount=2000.0, category="Other Income", tag="Freelance",
                source="bank_transactions", type="normal", status="completed",
            ),
            BankTransaction(
                id="bank_tag_3", date="2024-04-15", provider="leumi",
                account_name="Business", description="Dividend Payment",
                amount=500.0, category="Other Income", tag="Dividends",
                source="bank_transactions", type="normal", status="completed",
            ),
            BankTransaction(
                id="bank_tag_4", date="2024-04-20", provider="leumi",
                account_name="Business", description="Misc Income",
                amount=300.0, category="Other Income", tag=None,
                source="bank_transactions", type="normal", status="completed",
            ),
        ]
        db_session.add_all(records)
        db_session.commit()

        service = AnalysisService(db_session)
        result = service.get_income_by_source_over_time()

        assert len(result) == 1
        sources = result[0]["sources"]
        # Salary has no tag variants -> just "Salary"
        assert sources["Salary"] == 8000.0
        # Other Income with tags -> "Other Income / Tag"
        assert sources["Other Income / Freelance"] == 2000.0
        assert sources["Other Income / Dividends"] == 500.0
        # Other Income with no tag -> just "Other Income"
        assert sources["Other Income"] == 300.0
        assert result[0]["total"] == 10800.0

    def test_get_income_by_source_over_time_includes_positive_liabilities(self, db_session):
        """Verify positive Liabilities (loans received) counted as income source."""
        from backend.models.transaction import BankTransaction

        records = [
            BankTransaction(
                id="bank_loan_inc", date="2024-05-01", provider="hapoalim",
                account_name="Checking", description="Loan Disbursement",
                amount=50000.0, category="Liabilities", tag="Mortgage",
                source="bank_transactions", type="normal", status="completed",
            ),
            BankTransaction(
                id="bank_sal_inc", date="2024-05-01", provider="hapoalim",
                account_name="Checking", description="Salary May",
                amount=8000.0, category="Salary", tag=None,
                source="bank_transactions", type="normal", status="completed",
            ),
        ]
        db_session.add_all(records)
        db_session.commit()

        service = AnalysisService(db_session)
        result = service.get_income_by_source_over_time()

        assert len(result) == 1
        sources = result[0]["sources"]
        assert sources["Loans"] == 50000.0
        assert sources["Salary"] == 8000.0

    def test_get_income_by_source_over_time_excludes_prior_wealth(
        self, db_session, seed_base_transactions, seed_prior_wealth_transactions
    ):
        """Verify Prior Wealth tagged transactions are excluded from income sources."""
        service = AnalysisService(db_session)
        result = service.get_income_by_source_over_time()

        # Prior Wealth should not appear as a source label
        for month_data in result:
            for source_label in month_data["sources"]:
                assert "Prior Wealth" not in source_label

    def test_get_income_by_source_over_time_empty(self, db_session):
        """Verify empty database returns empty list."""
        service = AnalysisService(db_session)
        result = service.get_income_by_source_over_time()
        assert result == []

    def test_get_income_by_source_over_time_excludes_cc(
        self, db_session, seed_base_transactions
    ):
        """Verify credit card transactions are excluded from income calculation."""
        service = AnalysisService(db_session)
        result = service.get_income_by_source_over_time()

        # All income should come from bank/cash sources only
        # CC transactions have no income categories in seed data, but verify
        # the method filters them out by checking totals match expected
        total_income = sum(r["total"] for r in result)
        assert total_income == 8000.0 + 12000.0 + 8200.0  # 28200
```

**Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/backend/unit/services/test_analysis_service.py::TestAnalysisServiceIncomeBySource -v`
Expected: FAIL — `AttributeError: 'AnalysisService' object has no attribute 'get_income_by_source_over_time'`

**Step 3: Write the implementation**

Add to `backend/services/analysis_service.py`, in the `AnalysisService` class:

```python
def get_income_by_source_over_time(
    self, start_date: Optional[str] = None, end_date: Optional[str] = None
) -> list[dict]:
    """
    Get monthly income broken down by source (category+tag combination).

    Parameters
    ----------
    start_date : str, optional
        ISO date string (YYYY-MM-DD) for the start of the range.
    end_date : str, optional
        ISO date string (YYYY-MM-DD) for the end of the range.

    Returns
    -------
    list[dict]
        List of ``{month, sources: {label: amount}, total}`` records
        ordered chronologically. Prior Wealth transactions are excluded.
    """
    df = self.repo.get_table()

    if df.empty:
        return []

    # Exclude credit card transactions (same as other income methods)
    df = df[df["source"] != "credit_card_transactions"]

    if start_date:
        df = df[df["date"] >= start_date]
    if end_date:
        df = df[df["date"] <= end_date]

    if df.empty:
        return []

    # Filter to income rows only
    income_mask = self._get_income_mask(df)
    income_df = df[income_mask].copy()

    # Exclude Prior Wealth transactions
    income_df = income_df[income_df["tag"] != PRIOR_WEALTH_TAG]

    if income_df.empty:
        return []

    # Build source labels
    income_df["source_label"] = income_df.apply(self._income_source_label, axis=1)

    income_df["month"] = pd.to_datetime(income_df["date"]).dt.strftime("%Y-%m")

    result = []
    for month in sorted(income_df["month"].unique()):
        month_df = income_df[income_df["month"] == month]
        sources = {}
        for label, group in month_df.groupby("source_label"):
            sources[label] = round(float(group["amount"].sum()), 2)
        total = round(sum(sources.values()), 2)
        result.append({"month": month, "sources": sources, "total": total})

    return result

@staticmethod
def _income_source_label(row: pd.Series) -> str:
    """
    Build a human-readable label for an income source.

    Parameters
    ----------
    row : pd.Series
        A transaction row with 'category', 'tag', and 'amount' fields.

    Returns
    -------
    str
        Label like "Salary", "Other Income / Freelance", or "Loans".
    """
    category = row["category"]

    # Positive liabilities = loans
    if category == LiabilitiesCategories.LIABILITIES.value:
        return "Loans"

    tag = row.get("tag")
    if pd.isna(tag) or tag is None or tag == "":
        return category
    return f"{category} / {tag}"
```

**Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/backend/unit/services/test_analysis_service.py::TestAnalysisServiceIncomeBySource -v`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add backend/services/analysis_service.py tests/backend/unit/services/test_analysis_service.py
git commit -m "feat: add get_income_by_source_over_time to AnalysisService"
```

---

### Task 2: Backend Route — `/analytics/income-by-source-over-time`

**Files:**
- Test: `tests/backend/routes/test_analytics_routes.py`
- Modify: `backend/routes/analytics.py`

**Step 1: Write the failing tests**

Add to `tests/backend/routes/test_analytics_routes.py`, inside `TestAnalyticsRoutes`:

```python
def test_get_income_by_source_over_time(self, test_client, seed_base_transactions):
    """GET /api/analytics/income-by-source-over-time returns income breakdown."""
    response = test_client.get("/api/analytics/income-by-source-over-time")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    entry = data[0]
    assert "month" in entry
    assert "sources" in entry
    assert "total" in entry
    assert isinstance(entry["sources"], dict)
    assert entry["total"] > 0

def test_get_income_by_source_over_time_date_filter(self, test_client, seed_base_transactions):
    """GET /api/analytics/income-by-source-over-time with date filter narrows results."""
    response = test_client.get(
        "/api/analytics/income-by-source-over-time"
        "?start_date=2024-02-01&end_date=2024-02-28"
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["month"] == "2024-02"

def test_get_income_by_source_over_time_empty(self, test_client):
    """GET /api/analytics/income-by-source-over-time with no data returns empty list."""
    response = test_client.get("/api/analytics/income-by-source-over-time")
    assert response.status_code == 200
    assert response.json() == []
```

**Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/backend/routes/test_analytics_routes.py::TestAnalyticsRoutes::test_get_income_by_source_over_time -v`
Expected: FAIL — 404 (endpoint doesn't exist yet)

**Step 3: Write the route**

Add to `backend/routes/analytics.py`:

```python
@router.get("/income-by-source-over-time")
async def get_income_by_source_over_time(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_database),
):
    """Return monthly income broken down by source (category+tag).

    Parameters
    ----------
    start_date : str, optional
        ISO date string (YYYY-MM-DD) for the start of the range.
    end_date : str, optional
        ISO date string (YYYY-MM-DD) for the end of the range.

    Returns
    -------
    list[dict]
        List of ``{month, sources: {label: amount}, total}`` records
        ordered chronologically. Prior Wealth is excluded.
    """
    service = AnalysisService(db)
    return service.get_income_by_source_over_time(start_date, end_date)
```

**Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/backend/routes/test_analytics_routes.py::TestAnalyticsRoutes::test_get_income_by_source_over_time tests/backend/routes/test_analytics_routes.py::TestAnalyticsRoutes::test_get_income_by_source_over_time_date_filter tests/backend/routes/test_analytics_routes.py::TestAnalyticsRoutes::test_get_income_by_source_over_time_empty -v`
Expected: All 3 PASS

**Step 5: Run full test suite to check for regressions**

Run: `poetry run pytest -x -q`
Expected: All tests pass

**Step 6: Commit**

```bash
git add backend/routes/analytics.py tests/backend/routes/test_analytics_routes.py
git commit -m "feat: add /analytics/income-by-source-over-time endpoint"
```

---

### Task 3: Frontend API Method

**Files:**
- Modify: `frontend/src/services/api.ts`

**Step 1: Add the API method**

Add to the `analyticsApi` object in `frontend/src/services/api.ts`, after `getNetWorthOverTime`:

```typescript
getIncomeBySourceOverTime: (startDate?: string, endDate?: string) =>
  api.get<{ month: string; sources: Record<string, number>; total: number }[]>(
    "/analytics/income-by-source-over-time",
    { params: { start_date: startDate, end_date: endDate } }
  ),
```

**Step 2: Commit**

```bash
git add frontend/src/services/api.ts
git commit -m "feat: add getIncomeBySourceOverTime to frontend analyticsApi"
```

---

### Task 4: Frontend Dashboard Chart

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

**Step 1: Add the query**

Add a new `useQuery` hook in the `Dashboard` component, after the existing `netWorthData` query (around line 154):

```typescript
const { data: incomeBySourceData } = useQuery({
  queryKey: ["income-by-source", dateRange.start, dateRange.end, isTestMode],
  queryFn: async () => {
    const start = dateRange.start
      ? format(dateRange.start, "yyyy-MM-dd")
      : undefined;
    const end = dateRange.end
      ? format(dateRange.end, "yyyy-MM-dd")
      : undefined;
    const res = await analyticsApi.getIncomeBySourceOverTime(start, end);
    return res.data;
  },
  enabled:
    (dateRange.start === null && dateRange.end === null) ||
    (!!dateRange.start && !!dateRange.end),
});
```

**Step 2: Add the stacked bar chart section**

Add the chart JSX after the existing "Monthly Income vs Expenses" chart section (after the closing `</div>` at line ~404, before the `{/* Category Breakdown Charts */}` section). Place it as a full-width section:

```tsx
{/* Income Breakdown by Source */}
{incomeBySourceData && incomeBySourceData.length > 0 && (() => {
  // Collect all unique source labels across all months
  const allSources = Array.from(
    new Set(incomeBySourceData.flatMap((d) => Object.keys(d.sources)))
  );

  // Green-toned palette for income sources
  const colors = [
    "#059669", "#10b981", "#34d399", "#6ee7b7",
    "#a7f3d0", "#047857", "#065f46", "#064e3b",
  ];

  return (
    <div className="bg-[var(--surface)] rounded-2xl p-6 border border-[var(--surface-light)] shadow-xl overflow-hidden">
      <h3 className="text-lg font-bold mb-4">Income by Source</h3>
      <div className="h-[350px]">
        <Plot
          data={allSources.map((source, i) => ({
            x: incomeBySourceData.map((d) => d.month),
            y: incomeBySourceData.map((d) => d.sources[source] || 0),
            name: source,
            type: "bar" as const,
            marker: { color: colors[i % colors.length] },
          }))}
          layout={{
            ...chartTheme,
            barmode: "stack",
            autosize: true,
            height: 350,
            yaxis: {
              title: { text: "Amount (ILS)", font: { color: "#94a3b8" } },
              tickfont: { color: "#94a3b8" },
            },
            legend: {
              orientation: "h",
              y: -0.15,
              x: 0.5,
              xanchor: "center",
            },
          }}
          style={{ width: "100%", height: "100%" }}
          config={{ displayModeBar: false, responsive: true }}
        />
      </div>
    </div>
  );
})()}
```

**Step 3: Manual verification**

Run both servers: `python .claude/scripts/with_server.py -- echo "servers started"`
Open `http://localhost:5173` and verify:
- The "Income by Source" chart appears below "Monthly Income vs Expenses"
- Bars are stacked with distinct green segments per income source
- Hovering shows source name and amount
- Date range picker filters the chart correctly
- Chart is empty/hidden when no data exists

**Step 4: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat: add income by source stacked bar chart to Dashboard"
```

---

### Task 5: Final Verification

**Step 1: Run full backend test suite**

Run: `poetry run pytest -x -q`
Expected: All tests pass, no regressions

**Step 2: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no TypeScript errors

**Step 3: Run frontend lint**

Run: `cd frontend && npm run lint`
Expected: No lint errors
