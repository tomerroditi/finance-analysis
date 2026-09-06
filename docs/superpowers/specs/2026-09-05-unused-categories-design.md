# Unused Categories on the Categories Page

**Date:** 2026-09-05
**Status:** Approved design, pending implementation

## Problem

`frontend/src/pages/Categories.tsx` renders every category in one flat grid.
The grid only grows: a category added for a one-off trip or a closed account
stays at full visual weight forever, so the page gets steadily harder to scan.

This feature demotes categories that have gone quiet into a collapsed section.
It is **display-only** — no category is deleted, hidden from any dropdown, or
excluded from any calculation. Every other consumer of the categories map is
untouched.

## Definition of "unused"

A category is unused when **all** of these hold:

1. It has no transaction dated within the last `UNUSED_CATEGORY_MONTHS` (6) months.
2. It was created more than 6 months ago (`Category.created_at < cutoff`).
3. It is not in `PROTECTED_CATEGORIES`.

One constant governs both the transaction window and the creation grace, so the
rule reads as a single sentence: *nothing has happened here in six months, and
it has been around at least that long to prove it.*

### Deliberately not exempt

Categories referenced by a budget rule or a tagging rule are **not** exempt.

This is a considered trade-off, recorded so it is not re-litigated by accident.
A project budget created 8 months ago that has not spent yet will appear in the
unused section while its rule is live. The created-at grace covers the common
case (a rule and its category are usually created together), and the section is
non-destructive, so the cost of the false positive is one extra click. Revisit
if it proves annoying in practice.

### Scope of "has a transaction"

Usage is measured over the **merged view**: the four non-insurance transaction
tables (bank, credit card, cash, manual investments), with `split_parent` rows
excluded and split children counted via their parent's date. Insurance
transactions are excluded, matching `count_uncategorized` and
`get_table(exclude_services=["insurances"])`.

## Architecture

The 6-month rule lives **entirely in the backend**. The frontend receives a
boolean and splits an array by it.

Rejected alternatives:

- *Backend returns dates only, frontend computes `unused`.* Requires a second
  copy of `PROTECTED_CATEGORIES` and the cutoff in TypeScript. It would drift.
- *Extend `GET /tagging/categories`.* That response is `Record<string, string[]>`
  and is consumed by `useCategories` in roughly ten places. Changing its shape
  touches the whole app for a one-page feature.

## Backend

### `TransactionsRepository.get_category_last_used() -> dict[str, str]`

Pure SQL, mirroring the cross-table pattern in `count_uncategorized`
(`backend/repositories/transactions/core.py:401`). No DataFrame load.

For each of the four non-insurance repos:

```sql
SELECT category, MAX(date)
FROM <table>
WHERE category IS NOT NULL
  AND (type IS NULL OR type != 'split_parent')
GROUP BY category
```

`date` is stored as a `YYYY-MM-DD` string, so lexicographic `MAX` is
chronologically correct. The existing `ix_{table}_category_tag` index covers
the grouping.

Split children carry a `category` but **no `date`** — the date lives on the
parent row. So per table, additionally:

```sql
SELECT s.category, MAX(p.date)
FROM split_transactions s
JOIN <parent_table> p ON p.unique_id = s.transaction_id
WHERE s.source = '<parent_table>' AND s.category IS NOT NULL
GROUP BY s.category
```

The inner join drops orphaned splits, matching what the merged pandas view does
silently. `s.source` must be paired with the parent table because `unique_id` is
a per-table auto-increment.

Results merge in Python by `max()`. Returns `{category_name: "YYYY-MM-DD"}`,
omitting categories with no transactions at all.

### `CategoriesTagsService.get_category_usage() -> dict[str, dict]`

Combines:

- every category name from `get_categories_and_tags()`
- the last-used map above
- `Category.created_at`, via a new `TaggingRepository.get_categories_created_at()`
- `PROTECTED_CATEGORIES`

```python
cutoff = (
    pd.Timestamp.today().normalize()
    - pd.DateOffset(months=UNUSED_CATEGORY_MONTHS)
).date()
unused = (
    name not in PROTECTED_CATEGORIES
    and created_at.date() < cutoff
    and (last_used is None or date.fromisoformat(last_used) < cutoff)
)
```

Month arithmetic uses `pd.DateOffset`, matching
`tagging_rules_service.py:758`. The project has no `dateutil` dependency, so
`relativedelta` is not available.

Returns `{name: {"last_used": str | None, "unused": bool}}` for **every**
category — a dict keyed by name, because the frontend does per-category lookups
while iterating the existing categories map.

`UNUSED_CATEGORY_MONTHS = 6` is a new constant in
`backend/constants/categories.py`.

### Route

`GET /tagging/categories/usage` in `backend/routes/tagging.py`.

No path conflict: `/categories/{name}` only has `DELETE` and `PUT`, no `GET`.

### No migration

`Category` already inherits `created_at` from `TimestampMixin`
(`backend/models/base.py:11`). Nothing schema-level is needed.

### No PWA changes

The response is neither sensitive nor real-time, so the service worker URL
filter in `frontend/vite.config.ts` and the `shouldDehydrateQuery` rule in
`frontend/src/queryClient.ts` both stay as they are. Recorded explicitly
because the project rule is to consider both lists whenever an endpoint is
added.

## Frontend

### Data

- `useCategoryUsage()` in `frontend/src/hooks/useCategories.ts`, alongside
  `useCategories`.
- Query key `qk.tagging.categoryUsage()` added to
  `frontend/src/services/queryKeys.ts`.
- `taggingApi.getCategoryUsage()` in `frontend/src/services/api.ts`. The path
  must match the route exactly.

### Components

**`frontend/src/components/categories/CategoryCard.tsx`** (new)

The grid button is currently ~25 lines of inline JSX in `Categories.tsx` and
would otherwise be duplicated across two grids. Extract it, with a `subtitle`
prop so the active grid can pass the tag count and the unused grid can pass
"Last used …".

**`frontend/src/components/categories/UnusedCategoriesSection.tsx`** (new)

A chevron disclosure `<button>` reading *"Unused categories (7)"* plus a
one-line hint, expanding into the same card grid. Collapsed by default.
Expansion state is local `useState` — a per-visit affordance, not persisted.
Renders `null` when the count is zero.

**`Categories.tsx`** (modified)

Splits `filteredEntries` into `activeEntries` and `unusedEntries` using the
usage map. While the usage query is in flight, every category renders in the
active grid — the page degrades to today's behaviour rather than flashing
categories in and out of a collapsed section.

### Search

A search query filters **both** buckets. If the unused bucket has matches, the
section auto-expands. Nothing the user types can be silently unfindable — this
is the property that keeps the collapse from being a bug.

### Card content

An unused card shows **"Last used Mar 2026"**, or **"Never used"** when
`last_used` is `null`, in place of the tag count. That is the fact justifying
the demotion, and it is what the user needs in order to decide whether to
delete.

Month formatting goes through the existing locale-aware date util so it is
correct in Hebrew.

### Detail panel

Clicking an unused card opens the existing `CategoryDetailPanel`, which already
has delete. The section becomes the natural cleanup surface with no new
delete UI.

### i18n

New keys in **both** `en.json` and `he.json`:

- `categories.unusedSection` — "Unused categories"
- `categories.unusedHint` — explains the 6-month rule
- `categories.lastUsed` — "Last used {{date}}"
- `categories.neverUsed` — "Never used"

## Testing

### Backend

`tests/backend/unit/` — repository tests for `get_category_last_used`:

- max date picked across two different tables for the same category
- `split_parent` rows excluded
- a split child's parent date counts as usage
- an orphaned split (parent row gone) is ignored
- a category with no transactions is absent from the map

`tests/backend/unit/services/test_categories_tags_service.py` — a new test class
for `get_category_usage`:

- stale category → `unused: True`
- category with a transaction inside the window → `unused: False`
- protected category with no transactions → `unused: False`
- category created inside the window with no transactions → `unused: False`
- `last_used` is returned for both used and unused categories

### Frontend unit

`frontend/src/pages/Categories.test.tsx`:

- section absent when no category is unused
- unused categories are not in the main grid
- a search matching an unused category auto-expands the section

### e2e

A **separate `test()`** in `frontend/e2e/categories.spec.ts`, not a block
appended to the existing journey test.

This departs from the project's default rule (new read-only coverage joins the
page's single-load journey) for a reason discovered during planning. The frozen
demo DB stamps every category with `created_at = 2026-07-29`, and `_shift_dates`
in `backend/demo_setup.py` shifts only the transaction-bearing tables —
`categories` is not in its list. So in Demo Mode every category sits inside the
creation grace and the unused section never renders today, while it *would*
begin rendering once wall-clock time passes six months from that stamp.
Asserting against demo data either way produces a test that is vacuous now and
flips later.

A `page.route()` stub on `GET /api/tagging/categories/usage` makes the assertion
deterministic, and a route stub installed before page boot is exactly the
documented reason to open a separate `test()`. The stub intercepts a GET only,
so the spec performs no backend writes and stays eligible for
`READ_ONLY_SPECS`, where it is listed at `frontend/playwright.config.ts:74`.

## Out of scope

- Bulk-deleting unused categories.
- Persisting the expanded/collapsed state.
- Making the 6-month window user-configurable.
- Any equivalent treatment for unused *tags* within a category.
