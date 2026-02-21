# Investment Balance Snapshots Design

## Problem

Investment "current balance" is calculated as `-(sum of all transactions)`, reflecting only deposits minus withdrawals. It has no awareness of actual market value, making profit/loss, ROI, and CAGR meaningless for open investments.

## Solution

Add a `investment_balance_snapshots` table to store timestamped market-value snapshots per investment. Snapshots can be entered manually, auto-calculated for fixed-rate investments, or populated by scraping in the future.

## Data Model

### New Table: `investment_balance_snapshots`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | INTEGER | PK, auto-increment |
| `investment_id` | INTEGER | FK -> `investments.id`, NOT NULL |
| `date` | TEXT (YYYY-MM-DD) | NOT NULL |
| `balance` | REAL | NOT NULL |
| `source` | TEXT | NOT NULL: `"manual"`, `"scraped"`, or `"calculated"` |

- Unique constraint: `(investment_id, date)` -- upsert semantics, one snapshot per investment per day.
- Index on `(investment_id, date)` for efficient "latest snapshot on or before X" queries.

## Balance Resolution Logic

To determine the balance of investment X on date Y:

1. Find the latest snapshot with `date <= Y` for that investment.
2. If no snapshot exists, fall back to transaction-based: `-(sum of transactions up to Y)`.
3. If a snapshot exists, use it directly -- it represents total market value (not an adjustment on top of transactions).

Snapshots represent **total market value**. If you deposited 10,000 and the investment grew to 12,000, the snapshot is `12000`.

## Fixed-Rate Auto-Calculation

For investments with `interest_rate_type = "fixed"` and a non-null `interest_rate`, the system generates `source="calculated"` snapshots by replaying the transaction timeline with daily compounding:

```
daily_rate = (1 + annual_rate) ^ (1/365) - 1

For each day from first deposit to target date:
  - Start with previous day's balance
  - Apply daily interest: balance *= (1 + daily_rate)
  - Apply any transactions on this day (deposits add, withdrawals subtract)
```

This handles:
- **Partial withdrawals** -- withdrawn money stops compounding immediately.
- **Intra-month precision** -- daily granularity gives correct pro-rata interest.

Manual/scraped snapshots always take precedence over calculated ones for the same date.

## Updated KPI Calculations

### Per-Investment Analysis (Snapshot-Aware)

| KPI | Formula |
|-----|---------|
| Current Balance | Latest snapshot balance (fallback: txn-based if no snapshots) |
| Profit/Loss | `current_balance - net_invested` |
| ROI | `((current_balance + total_withdrawals) / total_deposits - 1) * 100` |
| CAGR | Compound annual growth rate using snapshot-based final value |
| Balance History | Interpolate between snapshots; fall back to txn-based for periods without snapshots |

### Portfolio Overview

Sum of snapshot-based current balances across open investments. Same cascade: snapshot if available, transaction-based fallback.

### Dashboard / Net Worth

No changes -- stays transaction-based. Future opt-in enhancement.

### Closed Investments

When closing, prompt for a final balance snapshot (actual payout). If provided, profit/loss reflects reality. If not, falls back to transaction-based.

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/investments/{id}/balances` | List all snapshots |
| `POST` | `/investments/{id}/balances` | Add/upsert snapshot `{date, balance}` |
| `PUT` | `/investments/{id}/balances/{snapshot_id}` | Update snapshot |
| `DELETE` | `/investments/{id}/balances/{snapshot_id}` | Delete snapshot |
| `POST` | `/investments/{id}/balances/calculate` | Trigger fixed-rate auto-calculation |

## UI Changes

1. **Balance History chart** -- switches from transaction-based to snapshot-based. Snapshot points shown as dots with interpolation between them. Source shown on hover.
2. **"Update Balance" button** on each InvestmentCard -- quick form: date (default today), balance amount.
3. **Snapshots table** in analysis modal -- below chart, lists all snapshots with date, balance, source, delete action. Inline editing.
4. **Fixed-rate "Calculate" button** -- for fixed-rate investments, triggers auto-calculation. Calculated vs manual snapshots displayed differently on chart.
5. **Staleness indicator** -- "Last updated: X days ago" on investment card if latest snapshot > 30 days old.

## Migration & Backward Compatibility

- **No data migration needed.** New table starts empty.
- **No breaking changes.** Balance resolution falls back to transaction-based when no snapshots exist.
- **Gradual adoption.** Users add snapshots at their own pace. Existing investments continue working unchanged.
- **Closed investments.** Keep transaction-based profit/loss. Users can retroactively add a final snapshot to correct numbers.
