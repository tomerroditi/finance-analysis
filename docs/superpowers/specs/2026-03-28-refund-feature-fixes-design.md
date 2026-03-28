# Refund Feature Fixes - Design Spec

**Date:** 2026-03-28
**Scope:** Fix disconnect, partial refund handling, close-as-partial, auto-split, and full RefundsView management

---

## Status Model

| Status | Meaning | Budget exclusion |
|--------|---------|-----------------|
| `pending` | No links yet | Exclude full `expected_amount` |
| `partial` | Some linked, still tracking | Exclude `remaining` (expected - total_refunded) |
| `resolved` | Fully refunded | No exclusion |
| `closed` | User accepted partial, stop tracking | No exclusion (unrefunded remainder counts as expense) |

Status transitions:
- `pending` -> `partial` (first link added, total < expected)
- `pending` -> `resolved` (link covers full amount)
- `partial` -> `resolved` (additional links cover remaining)
- `partial` -> `closed` (user closes manually)
- `pending` -> `closed` (user closes with no links)
- `resolved` -> `partial` (link removed, total drops below expected)
- `partial` -> `pending` (all links removed)

---

## Backend Changes

### 1. Fix `unlink_refund` in service

`PendingRefundsService.unlink_refund(link_id)`:
1. Find the link to get `pending_refund_id`
2. Delete the link via repo
3. Recalculate total_refunded from remaining links
4. Update status: 0 refunded -> `pending`, < expected -> `partial`, >= expected -> `resolved`

### 2. New `close_pending_refund` endpoint

- `POST /pending-refunds/{pending_id}/close`
- Allowed when status is `pending` or `partial`
- Sets status to `closed`
- Record and its links remain for history

### 3. Budget adjustment update

`get_budget_adjustment(year, month)`:
- Sum `expected_amount` for all `status='pending'` refunds
- Sum `remaining` (expected_amount - total_refunded) for all `status='partial'` refunds
- Return combined total
- `resolved` and `closed` are excluded (no adjustment)

### 4. Auto-split on link when refund amount > remaining

In `link_refund()`, when the refund transaction amount exceeds the pending refund's remaining:
1. Use the existing split transaction infrastructure to split the refund transaction
2. Split 1: amount = remaining amount needed, description = original description
3. Split 2: amount = excess, description = original description
4. Link Split 1 to the pending refund (using the split's id and source)
5. The original transaction stays in the main table; splits go to `split_transactions`

This uses the same split mechanism as manual splits from TransactionsTable.

### 5. `get_all_pending` enrichment

Ensure links are enriched for all statuses returned (not just pending). The enrichment already works but verify it handles `partial` and `closed` correctly.

---

## Frontend Changes

### 6. LinkRefundModal

- Fetch both `pending` AND `partial` status refunds (change query from `getAll("pending")` to `getAll("pending,partial")` or fetch both)
- For partial refunds in the list: show "₪X remaining of ₪Y" so user knows how much is left to link
- Amount input max = remaining on the selected pending refund

### 7. RefundsView (Transactions page, Refunds tab)

Currently read-only. Add full management:

**For each active refund (pending/partial):**
- "Link Refund" button -> opens LinkRefundModal in reverse mode (same as budget page)
- "Close" button -> closes as partial/done (with confirmation)
- "Cancel" button -> deletes the pending refund (with confirmation)

**For each linked refund within an active refund:**
- "Unlink" button -> disconnects the transaction from the refund

**For resolved/closed refunds:**
- Read-only display (no action buttons)
- Show closed refunds with a distinct badge color (e.g., gray or blue) vs resolved (green)

**Grouping:**
- Active section: pending + partial (as today)
- Completed section: resolved + closed

### 8. Budget PendingRefundsSection

- Show both `pending` and `partial` refunds (partial may already show — verify)
- For partial: show progress indicator (e.g., "₪600 / ₪1000 refunded")
- Add "Close" button alongside existing link/cancel buttons
- Both desktop inline and mobile tap-to-reveal patterns

### 9. TransactionsTable

- Unlink works once backend is fixed (no frontend changes needed)
- No other changes

---

## Files to Modify

**Backend:**
- `backend/services/pending_refunds_service.py` — add `unlink_refund`, `close_pending_refund`, update `link_refund` (auto-split), update `get_budget_adjustment`
- `backend/routes/pending_refunds.py` — add close endpoint, fix unlink route to call service method
- `backend/repositories/pending_refunds_repository.py` — add `get_link_by_id` if needed

**Frontend:**
- `frontend/src/components/modals/LinkRefundModal.tsx` — fetch partial refunds too, show remaining
- `frontend/src/components/transactions/RefundsView.tsx` — add action buttons, unlink, close, cancel, link
- `frontend/src/components/budget/PendingRefundsSection.tsx` — add close button, show partial progress
- `frontend/src/locales/en.json` — new i18n keys for close, partial status, etc.
- `frontend/src/locales/he.json` — Hebrew translations

---

## Out of Scope

- Audit trail / cancelled status preservation (records are deleted on cancel, as today)
- Date-based filtering for budget adjustment (year/month params remain unused)
- Refund notifications or alerts
