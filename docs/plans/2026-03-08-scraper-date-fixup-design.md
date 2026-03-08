# Scraper Date Fixup — Design

## Problem

The old Node.js scraper (israeli-bank-scrapers) had a bug where **onezero** (bank) and **isracard** (credit card) transactions were recorded with dates **1 day earlier** than the real transaction date.

After switching to the new Python scraper framework on **2026-03-04**, correct dates are now scraped. Because the dedup key is `[id, provider, date, amount]`, the correctly-dated transactions were inserted as new rows — creating duplicates.

## Goal

1. Fix the dates on old transactions (shift +1 day)
2. Remove duplicate rows that now match, keeping the old row (preserves user's category/tag edits)
3. Re-link any split transactions that referenced deleted duplicate rows

## Scope

| Provider | Table | Fix |
|----------|-------|-----|
| `onezero` | `bank_transactions` | date +1 day |
| `isracard` | `credit_card_transactions` | date +1 day |

## Identification Strategy

- **Old transactions:** `provider in ("onezero", "isracard")` AND `created_at < 2026-03-04`
- **New transactions:** same providers AND `created_at >= 2026-03-04`
- **Duplicates:** after date fix, rows matching on `[id, provider, date, amount]`

## Algorithm

```
1. Back up database to ~/.finance-analysis/data.db.bak-YYYYMMDD
2. For each affected table (bank_transactions, credit_card_transactions):
   a. SELECT old transactions (provider match + created_at < cutoff)
   b. Compute corrected date = date + 1 day for each
   c. SELECT new transactions (provider match + created_at >= cutoff)
   d. Find duplicates: old rows (with corrected date) that match new rows on [id, provider, date, amount]
   e. For duplicates:
      - Keep the OLD row (update its date to corrected date)
      - Delete the NEW row
      - If the new row has splits in split_transactions (via transaction_id = unique_id),
        re-point them to the old row's unique_id
   f. For non-duplicate old rows:
      - Just update the date to corrected date
3. Print summary of changes
```

## Script Interface

```bash
# Dry run (default) — shows what would change
python scripts/fix_scraper_dates.py

# Apply changes
python scripts/fix_scraper_dates.py --apply
```

## Output

Dry-run prints:
- Count of old transactions per provider/table
- Count of duplicates found
- Count of split transactions that need re-linking
- Sample rows (first 5) for each category

## Safety

- Database backup before any writes
- Dry-run by default
- Single SQLite transaction — rollback on any error
- No ORM — direct SQL for simplicity and atomicity
