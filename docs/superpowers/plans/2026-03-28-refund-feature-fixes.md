# Refund Feature Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix refund disconnect, add partial refund handling with close-as-partial, auto-split on oversized link, and full RefundsView management UI.

**Architecture:** Backend service gets 3 new methods (unlink, close, updated budget adjustment) and auto-split logic in link_refund. Frontend gets action buttons in RefundsView and PendingRefundsSection, plus LinkRefundModal fetches partial refunds too.

**Tech Stack:** FastAPI, SQLAlchemy, React 19, TanStack Query, i18next

---

### Task 1: Backend — Add `unlink_refund` service method and fix route

**Files:**
- Modify: `backend/services/pending_refunds_service.py`
- Modify: `backend/repositories/pending_refunds_repository.py`
- Test: `tests/backend/unit/services/test_pending_refunds_service.py`

- [ ] **Step 1: Add `get_link_by_id` to repository**

In `backend/repositories/pending_refunds_repository.py`, add after `delete_refund_link`:

```python
def get_link_by_id(self, link_id: int) -> RefundLink | None:
    """
    Get a refund link by ID.

    Parameters
    ----------
    link_id : int
        ID of the link.

    Returns
    -------
    RefundLink or None
        The link if found, None otherwise.
    """
    return self.db.get(RefundLink, link_id)
```

- [ ] **Step 2: Write failing tests for unlink_refund**

Add to `tests/backend/unit/services/test_pending_refunds_service.py`:

```python
class TestUnlinkRefund:
    """Tests for unlink_refund with status recalculation."""

    def test_unlink_refund_reverts_resolved_to_partial(self, db_session):
        """Unlinking one of multiple links reverts resolved to partial."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        service.link_refund(pending["id"], 99, "banks", 60.0)
        result = service.link_refund(pending["id"], 100, "banks", 40.0)
        assert result["status"] == "resolved"

        # Get link IDs
        details = service.get_pending_by_id(pending["id"])
        link_id = details["links"][1]["id"]  # Second link (40.0)

        result = service.unlink_refund(link_id)
        assert result["status"] == "partial"
        assert result["total_refunded"] == 60.0

    def test_unlink_refund_reverts_partial_to_pending(self, db_session):
        """Unlinking the only link reverts partial to pending."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        service.link_refund(pending["id"], 99, "banks", 50.0)

        details = service.get_pending_by_id(pending["id"])
        link_id = details["links"][0]["id"]

        result = service.unlink_refund(link_id)
        assert result["status"] == "pending"
        assert result["total_refunded"] == 0

    def test_unlink_refund_not_found(self, db_session):
        """Error when link not found."""
        service = PendingRefundsService(db_session)
        with pytest.raises(EntityNotFoundException):
            service.unlink_refund(9999)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `poetry run pytest tests/backend/unit/services/test_pending_refunds_service.py::TestUnlinkRefund -v`
Expected: FAIL — `AttributeError: 'PendingRefundsService' object has no attribute 'unlink_refund'`

- [ ] **Step 4: Implement `unlink_refund` in service**

Add to `backend/services/pending_refunds_service.py`:

```python
def unlink_refund(self, link_id: int) -> dict:
    """
    Unlink a refund transaction from its pending refund and recalculate status.

    Parameters
    ----------
    link_id : int
        ID of the refund link to remove.

    Returns
    -------
    dict
        Updated pending refund status with recalculated totals.

    Raises
    ------
    EntityNotFoundException
        If link not found.
    """
    link = self.repo.get_link_by_id(link_id)
    if not link:
        raise EntityNotFoundException(f"Refund link {link_id} not found")

    pending_refund_id = link.pending_refund_id
    pending = self.repo.get_by_id(pending_refund_id)
    if not pending:
        raise EntityNotFoundException(
            f"Pending refund {pending_refund_id} not found"
        )

    # Delete the link
    self.repo.delete_refund_link(link_id)

    # Recalculate status
    links = self.repo.get_links_for_pending(pending_refund_id)
    total_refunded = links["amount"].sum() if not links.empty else 0

    if total_refunded <= 0:
        new_status = "pending"
    elif total_refunded >= pending.expected_amount:
        new_status = "resolved"
    else:
        new_status = "partial"

    self.repo.update_status(pending_refund_id, new_status)

    remaining = max(0, pending.expected_amount - total_refunded)
    return {
        "id": pending_refund_id,
        "status": new_status,
        "expected_amount": pending.expected_amount,
        "total_refunded": total_refunded,
        "remaining": remaining,
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `poetry run pytest tests/backend/unit/services/test_pending_refunds_service.py::TestUnlinkRefund -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add backend/services/pending_refunds_service.py backend/repositories/pending_refunds_repository.py tests/backend/unit/services/test_pending_refunds_service.py
git commit -m "feat(refunds): add unlink_refund service method with status recalculation"
```

---

### Task 2: Backend — Add `close_pending_refund` endpoint and `closed` status

**Files:**
- Modify: `backend/services/pending_refunds_service.py`
- Modify: `backend/routes/pending_refunds.py`
- Modify: `backend/models/pending_refund.py` (docstring only — status already a string column)
- Test: `tests/backend/unit/services/test_pending_refunds_service.py`

- [ ] **Step 1: Write failing tests for close_pending_refund**

Add to `tests/backend/unit/services/test_pending_refunds_service.py`:

```python
class TestClosePendingRefund:
    """Tests for closing a pending refund as accepted partial."""

    def test_close_pending_refund(self, db_session):
        """Close a pending refund sets status to closed."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)

        result = service.close_pending_refund(pending["id"])
        assert result["status"] == "closed"

    def test_close_partial_refund(self, db_session):
        """Close a partial refund preserves links and sets status to closed."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        service.link_refund(pending["id"], 99, "banks", 50.0)

        result = service.close_pending_refund(pending["id"])
        assert result["status"] == "closed"
        assert result["total_refunded"] == 50.0

    def test_close_resolved_refund_rejected(self, db_session):
        """Cannot close an already resolved refund."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
        service.link_refund(pending["id"], 99, "banks", 100.0)

        with pytest.raises(ValidationException):
            service.close_pending_refund(pending["id"])

    def test_close_not_found(self, db_session):
        """Error when pending refund not found."""
        service = PendingRefundsService(db_session)
        with pytest.raises(EntityNotFoundException):
            service.close_pending_refund(9999)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/backend/unit/services/test_pending_refunds_service.py::TestClosePendingRefund -v`
Expected: FAIL — `AttributeError: 'PendingRefundsService' object has no attribute 'close_pending_refund'`

- [ ] **Step 3: Implement `close_pending_refund` in service**

Add to `backend/services/pending_refunds_service.py`:

```python
def close_pending_refund(self, pending_refund_id: int) -> dict:
    """
    Close a pending refund, accepting whatever has been refunded so far.

    Parameters
    ----------
    pending_refund_id : int
        ID of the pending refund to close.

    Returns
    -------
    dict
        Updated pending refund with closed status.

    Raises
    ------
    EntityNotFoundException
        If pending refund not found.
    ValidationException
        If refund is already resolved or closed.
    """
    pending = self.repo.get_by_id(pending_refund_id)
    if not pending:
        raise EntityNotFoundException(
            f"Pending refund {pending_refund_id} not found"
        )

    if pending.status in ("resolved", "closed"):
        raise ValidationException(
            f"Cannot close a refund that is already {pending.status}"
        )

    self.repo.update_status(pending_refund_id, "closed")

    links = self.repo.get_links_for_pending(pending_refund_id)
    total_refunded = links["amount"].sum() if not links.empty else 0

    return {
        "id": pending_refund_id,
        "status": "closed",
        "expected_amount": pending.expected_amount,
        "total_refunded": total_refunded,
        "remaining": max(0, pending.expected_amount - total_refunded),
    }
```

- [ ] **Step 4: Add the close route**

Add to `backend/routes/pending_refunds.py`, before the `unlink_refund` route:

```python
@router.post("/{pending_id}/close")
async def close_pending_refund(
    pending_id: int,
    db: Session = Depends(get_db),
):
    """Close a pending refund, accepting the current partial refund amount."""
    service = PendingRefundsService(db)
    return service.close_pending_refund(pending_id)
```

- [ ] **Step 5: Update model docstring**

In `backend/models/pending_refund.py`, update the `status` docstring from:
```
Current status: 'pending', 'resolved', or 'partial'.
```
to:
```
Current status: 'pending', 'partial', 'resolved', or 'closed'.
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `poetry run pytest tests/backend/unit/services/test_pending_refunds_service.py::TestClosePendingRefund -v`
Expected: 4 passed

- [ ] **Step 7: Commit**

```bash
git add backend/services/pending_refunds_service.py backend/routes/pending_refunds.py backend/models/pending_refund.py tests/backend/unit/services/test_pending_refunds_service.py
git commit -m "feat(refunds): add close_pending_refund endpoint for accepting partial refunds"
```

---

### Task 3: Backend — Update budget adjustment to include partial refunds

**Files:**
- Modify: `backend/services/pending_refunds_service.py`
- Test: `tests/backend/unit/services/test_pending_refunds_service.py`

- [ ] **Step 1: Write failing tests**

Add to the existing `TestGetBudgetAdjustment` class in `tests/backend/unit/services/test_pending_refunds_service.py`:

```python
def test_budget_adjustment_includes_partial_remaining(self, db_session):
    """Verify budget adjustment includes remaining amount of partial refunds."""
    service = PendingRefundsService(db_session)
    # Pending: full 100 excluded
    service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
    # Partial: 200 expected, 80 refunded -> 120 remaining excluded
    partial = service.mark_as_pending_refund("transaction", 2, "banks", 200.0)
    service.link_refund(partial["id"], 99, "banks", 80.0)

    result = service.get_budget_adjustment(2024, 1)
    assert result == 220.0  # 100 + 120

def test_budget_adjustment_excludes_closed(self, db_session):
    """Verify budget adjustment excludes closed refunds."""
    service = PendingRefundsService(db_session)
    pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)
    service.link_refund(pending["id"], 99, "banks", 50.0)
    service.close_pending_refund(pending["id"])

    result = service.get_budget_adjustment(2024, 1)
    assert result == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/backend/unit/services/test_pending_refunds_service.py::TestGetBudgetAdjustment -v`
Expected: New tests FAIL

- [ ] **Step 3: Update `get_budget_adjustment`**

Replace the `get_budget_adjustment` method in `backend/services/pending_refunds_service.py`:

```python
def get_budget_adjustment(self, year: int, month: int) -> float:
    """
    Calculate total amount to exclude from budget for pending refunds.

    Includes full expected_amount for pending refunds and remaining
    amount for partial refunds. Excludes resolved and closed refunds.

    Parameters
    ----------
    year : int
        Budget year (reserved for future filtering).
    month : int
        Budget month (reserved for future filtering).

    Returns
    -------
    float
        Total amount expecting refund (to exclude from budget).
    """
    # Get pending refunds (full expected_amount)
    pending_df = self.repo.get_all_pending_refunds(status="pending")
    pending_total = pending_df["expected_amount"].sum() if not pending_df.empty else 0.0

    # Get partial refunds (remaining = expected - refunded)
    partial_df = self.repo.get_all_pending_refunds(status="partial")
    partial_remaining = 0.0
    if not partial_df.empty:
        for _, row in partial_df.iterrows():
            links = self.repo.get_links_for_pending(int(row["id"]))
            total_refunded = links["amount"].sum() if not links.empty else 0
            partial_remaining += max(0, row["expected_amount"] - total_refunded)

    return pending_total + partial_remaining
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/backend/unit/services/test_pending_refunds_service.py::TestGetBudgetAdjustment -v`
Expected: All tests pass

- [ ] **Step 5: Also update `get_active_pending_identifiers` to exclude `closed`**

In the `get_active_pending_identifiers` method, change the filter from:
```python
active_pending = pending_df[pending_df["status"] != "resolved"]
```
to:
```python
active_pending = pending_df[~pending_df["status"].isin(["resolved", "closed"])]
```

- [ ] **Step 6: Commit**

```bash
git add backend/services/pending_refunds_service.py tests/backend/unit/services/test_pending_refunds_service.py
git commit -m "feat(refunds): update budget adjustment to include partial remaining, exclude closed"
```

---

### Task 4: Backend — Auto-split refund transaction when amount exceeds remaining

**Files:**
- Modify: `backend/services/pending_refunds_service.py`
- Test: `tests/backend/unit/services/test_pending_refunds_service.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/backend/unit/services/test_pending_refunds_service.py`:

```python
class TestLinkRefundAutoSplit:
    """Tests for auto-split when refund amount exceeds pending remaining."""

    def test_auto_split_when_amount_exceeds_remaining(self, db_session, seed_base_transactions):
        """Auto-split refund transaction when amount > remaining."""
        from backend.models.transaction import BankTransaction, SplitTransaction

        # Find a bank transaction to use as source expense
        expense_txn = db_session.query(BankTransaction).filter(
            BankTransaction.amount < 0
        ).first()
        assert expense_txn is not None

        # Create a positive bank transaction to use as refund (amount > expected)
        refund_txn = BankTransaction(
            id="test-refund-oversized",
            date="2024-01-15",
            provider="hapoalim",
            account_name="Main Account",
            description="Large refund",
            amount=150.0,
            category="Shopping",
            tag="Online",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        db_session.add(refund_txn)
        db_session.flush()

        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund(
            "transaction", expense_txn.unique_id, "banks", 100.0,
        )

        result = service.link_refund(
            pending["id"], refund_txn.unique_id, "bank_transactions", 150.0,
        )

        # Should resolve with only the needed amount
        assert result["status"] == "resolved"
        assert result["total_refunded"] == 100.0

        # Original transaction should be marked as split_parent
        db_session.refresh(refund_txn)
        assert refund_txn.type == "split_parent"

        # Should have 2 splits
        splits = db_session.query(SplitTransaction).filter(
            SplitTransaction.transaction_id == refund_txn.unique_id,
        ).all()
        assert len(splits) == 2
        amounts = sorted([s.amount for s in splits])
        assert amounts[0] == 50.0   # remainder
        assert amounts[1] == 100.0  # linked portion

    def test_no_split_when_amount_equals_remaining(self, db_session):
        """No split when refund amount exactly matches remaining."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)

        result = service.link_refund(pending["id"], 99, "banks", 100.0)
        assert result["status"] == "resolved"
        assert result["total_refunded"] == 100.0

    def test_no_split_when_amount_less_than_remaining(self, db_session):
        """No split when refund amount is less than remaining."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund("transaction", 1, "banks", 100.0)

        result = service.link_refund(pending["id"], 99, "banks", 50.0)
        assert result["status"] == "partial"
        assert result["total_refunded"] == 50.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/backend/unit/services/test_pending_refunds_service.py::TestLinkRefundAutoSplit -v`
Expected: First test FAILS (no auto-split logic yet)

- [ ] **Step 3: Implement auto-split in `link_refund`**

Update the `link_refund` method in `backend/services/pending_refunds_service.py`. Add the auto-split logic before the "Add the link" section:

```python
def link_refund(
    self,
    pending_refund_id: int,
    refund_transaction_id: int,
    refund_source: str,
    amount: float,
) -> dict:
    """
    Link a refund transaction to a pending refund.

    If the refund amount exceeds the remaining expected amount, the refund
    transaction is automatically split: one part covers the remaining amount
    and is linked, the other part keeps the excess.

    Parameters
    ----------
    pending_refund_id : int
        ID of the pending refund.
    refund_transaction_id : int
        unique_id of the refund transaction.
    refund_source : str
        Table where refund lives (e.g. 'bank_transactions').
    amount : float
        Amount this refund covers.

    Returns
    -------
    dict
        Updated pending refund status with total refunded.

    Raises
    ------
    EntityNotFoundException
        If pending refund not found.
    """
    pending = self.repo.get_by_id(pending_refund_id)
    if not pending:
        raise EntityNotFoundException(
            f"Pending refund {pending_refund_id} not found"
        )

    # Calculate current remaining
    existing_links = self.repo.get_links_for_pending(pending_refund_id)
    already_refunded = existing_links["amount"].sum() if not existing_links.empty else 0
    remaining = max(0, pending.expected_amount - already_refunded)

    # Auto-split if refund amount exceeds remaining
    actual_link_amount = amount
    if amount > remaining and remaining > 0:
        actual_link_amount = remaining
        excess = amount - remaining

        # Split the refund transaction using the transactions repository
        from backend.repositories.transactions_repository import TransactionsRepository
        trans_repo = TransactionsRepository(self.db)

        # Get the original transaction to preserve its category/tag
        from sqlalchemy import select
        repo = trans_repo.repo_map.get(refund_source)
        if repo:
            model = repo.model
            txn = self.db.execute(
                select(model).where(model.unique_id == refund_transaction_id)
            ).scalar_one_or_none()

            if txn:
                category = txn.category or ""
                tag = txn.tag or ""
                trans_repo.split_transaction(
                    unique_id=refund_transaction_id,
                    source=refund_source,
                    splits=[
                        {"amount": actual_link_amount, "category": category, "tag": tag},
                        {"amount": excess, "category": category, "tag": tag},
                    ],
                )

    # Add the link with the actual amount (capped to remaining)
    self.repo.add_refund_link(
        pending_refund_id=pending_refund_id,
        refund_transaction_id=refund_transaction_id,
        refund_source=refund_source,
        amount=actual_link_amount,
    )

    # Calculate total refunded
    links = self.repo.get_links_for_pending(pending_refund_id)
    total_refunded = links["amount"].sum() if not links.empty else 0

    # Determine new status
    if total_refunded >= pending.expected_amount:
        new_status = "resolved"
    else:
        new_status = "partial"

    self.repo.update_status(pending_refund_id, new_status)

    remaining = max(0, pending.expected_amount - total_refunded)

    return {
        "id": pending_refund_id,
        "status": new_status,
        "expected_amount": pending.expected_amount,
        "total_refunded": total_refunded,
        "remaining": remaining,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/backend/unit/services/test_pending_refunds_service.py::TestLinkRefundAutoSplit -v`
Expected: All 3 tests pass

- [ ] **Step 5: Run all existing tests to ensure no regressions**

Run: `poetry run pytest tests/backend/unit/services/test_pending_refunds_service.py -v`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add backend/services/pending_refunds_service.py tests/backend/unit/services/test_pending_refunds_service.py
git commit -m "feat(refunds): auto-split refund transaction when amount exceeds remaining"
```

---

### Task 5: Backend — Add route tests for new endpoints

**Files:**
- Modify: `tests/backend/routes/test_pending_refunds_routes.py`

- [ ] **Step 1: Read existing route tests**

Read `tests/backend/routes/test_pending_refunds_routes.py` to understand the test_client pattern used.

- [ ] **Step 2: Add route tests**

Add to `tests/backend/routes/test_pending_refunds_routes.py`:

```python
class TestCloseRefundRoute:
    """Tests for POST /pending-refunds/{id}/close endpoint."""

    def test_close_pending_refund(self, test_client):
        """Close a pending refund returns closed status."""
        # Create a pending refund
        create_resp = test_client.post("/api/pending-refunds/", json={
            "source_type": "transaction",
            "source_id": 1,
            "source_table": "banks",
            "expected_amount": 100.0,
        })
        pending_id = create_resp.json()["id"]

        response = test_client.post(f"/api/pending-refunds/{pending_id}/close")
        assert response.status_code == 200
        assert response.json()["status"] == "closed"

    def test_close_nonexistent_refund(self, test_client):
        """Close nonexistent refund returns 404."""
        response = test_client.post("/api/pending-refunds/9999/close")
        assert response.status_code == 404


class TestUnlinkRefundRoute:
    """Tests for DELETE /pending-refunds/links/{id} endpoint."""

    def test_unlink_refund(self, test_client):
        """Unlink a refund returns updated status."""
        # Create pending + link
        create_resp = test_client.post("/api/pending-refunds/", json={
            "source_type": "transaction",
            "source_id": 1,
            "source_table": "banks",
            "expected_amount": 100.0,
        })
        pending_id = create_resp.json()["id"]

        link_resp = test_client.post(f"/api/pending-refunds/{pending_id}/link", json={
            "refund_transaction_id": 99,
            "refund_source": "banks",
            "amount": 50.0,
        })
        assert link_resp.status_code == 200

        # Get link ID
        details = test_client.get(f"/api/pending-refunds/{pending_id}")
        link_id = details.json()["links"][0]["id"]

        response = test_client.delete(f"/api/pending-refunds/links/{link_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "pending"

    def test_unlink_nonexistent_link(self, test_client):
        """Unlink nonexistent link returns 404."""
        response = test_client.delete("/api/pending-refunds/links/9999")
        assert response.status_code == 404
```

- [ ] **Step 3: Run route tests**

Run: `poetry run pytest tests/backend/routes/test_pending_refunds_routes.py -v`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add tests/backend/routes/test_pending_refunds_routes.py
git commit -m "test(refunds): add route tests for close and unlink endpoints"
```

---

### Task 6: Frontend — Add `closed` status to types and API, add `close` API method

**Files:**
- Modify: `frontend/src/services/api.ts`

- [ ] **Step 1: Update PendingRefund type**

In `frontend/src/services/api.ts`, update the `PendingRefund` interface status type from:
```typescript
status: "pending" | "resolved" | "partial";
```
to:
```typescript
status: "pending" | "resolved" | "partial" | "closed";
```

- [ ] **Step 2: Add close API method**

Add to the `pendingRefundsApi` object:
```typescript
close: (id: number) => api.post(`/pending-refunds/${id}/close`),
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/services/api.ts
git commit -m "feat(refunds): add closed status type and close API method"
```

---

### Task 7: Frontend — Add i18n keys for new refund features

**Files:**
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/he.json`

- [ ] **Step 1: Add English keys**

Add these keys to `en.json`:

In the `transactions.refunds` section:
```json
"closed": "Closed",
"closeRefund": "Close Refund",
"confirmClose": "Close this refund? The unrefunded amount will count as an expense.",
"confirmUnlink": "Unlink this refund transaction?",
"confirmCancel": "Cancel this refund expectation? All linked refunds will be unlinked.",
"refundedOf": "{{refunded}} of {{expected}} refunded",
"partiallyRefunded": "Partially Refunded"
```

In the `budget` section:
```json
"closeRefund": "Close Refund",
"confirmCloseRefund": "Close this refund? The unrefunded remainder will count as an expense."
```

- [ ] **Step 2: Add Hebrew keys**

Add matching keys to `he.json`:

In the `transactions.refunds` section:
```json
"closed": "סגור",
"closeRefund": "סגור החזר",
"confirmClose": "לסגור את ההחזר? הסכום שלא הוחזר ייחשב כהוצאה.",
"confirmUnlink": "לנתק את תנועת ההחזר?",
"confirmCancel": "לבטל את בקשת ההחזר? כל ההחזרים המקושרים ינותקו.",
"refundedOf": "{{refunded}} מתוך {{expected}} הוחזרו",
"partiallyRefunded": "הוחזר חלקית"
```

In the `budget` section:
```json
"closeRefund": "סגור החזר",
"confirmCloseRefund": "לסגור את ההחזר? היתרה שלא הוחזרה תיחשב כהוצאה."
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/locales/en.json frontend/src/locales/he.json
git commit -m "feat(refunds): add i18n keys for close, unlink, and partial refund UI"
```

---

### Task 8: Frontend — Update LinkRefundModal to fetch partial refunds

**Files:**
- Modify: `frontend/src/components/modals/LinkRefundModal.tsx`

- [ ] **Step 1: Update pending refunds query to include partial**

In `LinkRefundModal.tsx`, change the query that fetches pending refunds for normal mode:

From:
```typescript
queryFn: () => pendingRefundsApi.getAll("pending").then((res) => res.data),
```
To:
```typescript
queryFn: async () => {
  const [pending, partial] = await Promise.all([
    pendingRefundsApi.getAll("pending").then((res) => res.data),
    pendingRefundsApi.getAll("partial").then((res) => res.data),
  ]);
  return [...pending, ...partial];
},
```

- [ ] **Step 2: Show remaining for partial refunds in the list**

In the pending refund card in the normal mode list, after the expected_amount display, add a remaining indicator for partial refunds:

```tsx
<div className="font-bold text-amber-400">
  {formatCurrency(pending.expected_amount)}
</div>
{pending.status === "partial" && pending.remaining !== undefined && (
  <div className="text-xs text-emerald-400">
    {t("budget.remaining")}: {formatCurrency(pending.remaining)}
  </div>
)}
```

- [ ] **Step 3: Update amount auto-calculation for partial refunds**

When selecting a pending refund in normal mode, use `remaining` instead of `expected_amount`:

From:
```typescript
setLinkAmount(
  Math.min(
    refundTransaction?.amount || 0,
    pending.remaining || pending.expected_amount,
  ),
);
```
This already uses `remaining` with fallback — verify it works correctly.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/modals/LinkRefundModal.tsx
git commit -m "feat(refunds): fetch partial refunds in LinkRefundModal, show remaining"
```

---

### Task 9: Frontend — Add full management to RefundsView

**Files:**
- Modify: `frontend/src/components/transactions/RefundsView.tsx`

- [ ] **Step 1: Add imports and state**

Add to imports:
```typescript
import { useState } from "react";
import { useQueryClient, useMutation } from "@tanstack/react-query";
import { Link2, X, Lock, Unlink } from "lucide-react";
import { LinkRefundModal } from "../modals/LinkRefundModal";
```

Add state inside the component:
```typescript
const queryClient = useQueryClient();
const [linkingRefund, setLinkingRefund] = useState<PendingRefund | null>(null);
```

- [ ] **Step 2: Add mutation hooks**

Add inside the component:

```typescript
const closeMutation = useMutation({
  mutationFn: (id: number) => pendingRefundsApi.close(id),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ["pendingRefunds"] });
    queryClient.invalidateQueries({ queryKey: ["budgetAnalysis"] });
  },
});

const cancelMutation = useMutation({
  mutationFn: (id: number) => pendingRefundsApi.cancel(id),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ["pendingRefunds"] });
    queryClient.invalidateQueries({ queryKey: ["budgetAnalysis"] });
  },
});

const unlinkMutation = useMutation({
  mutationFn: (linkId: number) => pendingRefundsApi.unlinkRefund(linkId),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ["pendingRefunds"] });
    queryClient.invalidateQueries({ queryKey: ["budgetAnalysis"] });
    queryClient.invalidateQueries({ queryKey: ["transactions"] });
  },
});
```

- [ ] **Step 3: Update grouping to include `closed`**

Change the grouping in `groupedRefunds`:
```typescript
const active = refunds.filter((r) => r.status !== "resolved" && r.status !== "closed");
const completed = refunds.filter((r) => r.status === "resolved" || r.status === "closed");
```

Rename `resolved` to `completed` throughout and update the section header to show both resolved and closed.

- [ ] **Step 4: Add action buttons to active refund cards**

In the `renderRefundCard` function, add an action bar inside the header area (after the expected amount display), only for active refunds:

```tsx
{(item.status === "pending" || item.status === "partial") && (
  <div className="flex items-center gap-2 mt-2">
    <button
      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors"
      onClick={() => setLinkingRefund(item)}
    >
      <Link2 size={14} />
      {t("budget.linkRefund")}
    </button>
    <button
      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-colors"
      onClick={() => {
        if (window.confirm(t("transactions.refunds.confirmClose"))) {
          closeMutation.mutate(item.id);
        }
      }}
    >
      <Lock size={14} />
      {t("transactions.refunds.closeRefund")}
    </button>
    <button
      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors"
      onClick={() => {
        if (window.confirm(t("transactions.refunds.confirmCancel"))) {
          cancelMutation.mutate(item.id);
        }
      }}
    >
      <X size={14} />
      {t("common.cancel")}
    </button>
  </div>
)}
```

- [ ] **Step 5: Add unlink button to linked refund items**

In the linked refunds list, add an unlink button for active refunds. Change the link item rendering:

```tsx
{item.links.map((link) => (
  <div
    key={link.id}
    className="ps-4 py-1 flex justify-between items-center group"
  >
    <div className="flex items-center gap-2">
      <span className="text-emerald-400 font-mono font-medium">
        +{formatCurrency(link.amount)}
      </span>
      <span className="text-[var(--text-muted)]">•</span>
      <span className="text-sm">
        {link.description || t("transactions.refunds.refundTransaction")}
      </span>
      <span className="text-xs text-[var(--text-muted)]">
        ({link.date})
      </span>
    </div>
    <div className="flex items-center gap-2">
      <span className="text-xs text-[var(--text-muted)] opacity-50 group-hover:opacity-100 transition-opacity">
        {humanizeService(link.refund_source)}
      </span>
      {(item.status === "pending" || item.status === "partial") && (
        <button
          className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-500/10 text-red-400/70 hover:text-red-400 transition-all"
          title={t("transactions.refunds.confirmUnlink")}
          onClick={() => {
            if (window.confirm(t("transactions.refunds.confirmUnlink"))) {
              unlinkMutation.mutate(link.id);
            }
          }}
        >
          <Unlink size={14} />
        </button>
      )}
    </div>
  </div>
))}
```

- [ ] **Step 6: Add status badge for closed items**

Update the status badge rendering to handle `closed`:
```tsx
<div
  className={`p-2 rounded-lg ${
    item.status === "resolved"
      ? "bg-emerald-500/10 text-emerald-500"
      : item.status === "closed"
        ? "bg-slate-500/10 text-slate-400"
        : "bg-amber-500/10 text-amber-500"
  }`}
>
  {item.status === "resolved" ? (
    <CheckCircle2 size={20} />
  ) : item.status === "closed" ? (
    <Lock size={20} />
  ) : (
    <CircleDashed size={20} />
  )}
</div>
```

- [ ] **Step 7: Add LinkRefundModal at end of component**

Before the closing `</div>` of the return:
```tsx
{linkingRefund && (
  <LinkRefundModal
    isOpen={!!linkingRefund}
    onClose={() => setLinkingRefund(null)}
    pendingRefund={linkingRefund}
  />
)}
```

- [ ] **Step 8: Update completed section header**

```tsx
{groupedRefunds.completed.length > 0 && (
  <section>
    <h2 className="text-lg font-semibold mb-4 flex items-center gap-2 text-emerald-400">
      <CheckCircle2 size={20} />
      {t("transactions.refunds.resolved")} ({groupedRefunds.completed.length})
    </h2>
    {groupedRefunds.completed.map(renderRefundCard)}
  </section>
)}
```

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/transactions/RefundsView.tsx
git commit -m "feat(refunds): add full management UI to RefundsView (link, close, cancel, unlink)"
```

---

### Task 10: Frontend — Add close button to PendingRefundsSection (Budget page)

**Files:**
- Modify: `frontend/src/components/budget/PendingRefundsSection.tsx`

- [ ] **Step 1: Add close mutation and handler**

Add import for `useMutation`:
```typescript
import { useQueryClient, useMutation } from "@tanstack/react-query";
```

Add the close mutation inside the component:
```typescript
const closeMutation = useMutation({
  mutationFn: (id: number) => pendingRefundsApi.close(id),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ["budgetAnalysis"] });
    queryClient.invalidateQueries({ queryKey: ["pendingRefunds"] });
  },
});
```

- [ ] **Step 2: Add close button to desktop inline actions**

After the link button and before the cancel button in the desktop actions:
```tsx
<button
  className="hidden sm:block p-1.5 rounded-md hover:bg-blue-500/10 text-blue-400/70 hover:text-blue-400 transition-colors"
  title={t("budget.closeRefund")}
  onClick={() => {
    if (window.confirm(t("budget.confirmCloseRefund"))) {
      closeMutation.mutate(item.id);
    }
  }}
>
  <Lock size={16} />
</button>
```

- [ ] **Step 3: Add close button to mobile actions**

In the mobile action buttons section, add between link and cancel:
```tsx
<button
  className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-blue-400/70 hover:text-blue-400 hover:bg-blue-500/10 transition-colors"
  onClick={(e) => {
    e.stopPropagation();
    if (window.confirm(t("budget.confirmCloseRefund"))) {
      closeMutation.mutate(item.id);
    }
  }}
>
  <Lock size={14} />
  {t("budget.closeRefund")}
</button>
```

- [ ] **Step 4: Add Lock to imports**

Update the lucide-react import:
```typescript
import { RefreshCw, Link2, X, Lock } from "lucide-react";
```

- [ ] **Step 5: Add partial refund progress indicator**

In the item amount area, after the expected_amount display, add progress for partial items:
```tsx
<span className="text-amber-400 font-semibold">
  {formatCurrency(item.expected_amount)}
</span>
{item.status === "partial" && item.total_refunded !== undefined && (
  <span className="text-xs text-emerald-400 hidden sm:inline">
    ({formatCurrency(item.total_refunded)} / {formatCurrency(item.expected_amount)})
  </span>
)}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/budget/PendingRefundsSection.tsx
git commit -m "feat(refunds): add close button and partial progress to budget PendingRefundsSection"
```

---

### Task 11: Demo data — Add diverse refund scenarios

**Files:**
- Modify: `scripts/generate_demo_data.py`

- [ ] **Step 1: Update `create_pending_refunds` function**

Replace the existing `create_pending_refunds` function with an expanded version that creates all refund states:

```python
def create_pending_refunds(session, cc_txns, bank_txns):
    """Create pending refund records covering all statuses for demo testing.

    Creates:
    1. Pending refund (no links) - jacket return
    2. Partial refund (one link, not fully covered) - electronics partial return
    3. Resolved refund (fully linked) - duplicate charge
    4. Closed refund (user accepted partial) - restaurant dispute
    """
    # 1. Pending refund: recent shopping item, no links
    recent_shopping = [
        t for t in cc_txns
        if t.category == "Shopping" and t.tag == "Online" and t.type == "normal"
        and t.amount < -100
    ]
    if recent_shopping:
        source_txn = recent_shopping[-1]
        session.add(PendingRefund(
            source_type="transaction",
            source_id=source_txn.unique_id,
            source_table="credit_card_transactions",
            expected_amount=abs(source_txn.amount),
            status="pending",
            notes="Returned jacket, waiting for refund",
        ))

    # 2. Partial refund: electronics item with one partial link
    electronics = [
        t for t in cc_txns
        if t.category == "Shopping" and t.tag == "Electronics" and t.type == "normal"
        and t.amount < -200
    ]
    if electronics:
        source_txn = electronics[-1]
        expected = abs(source_txn.amount)
        partial_amount = round(expected * 0.4, 2)

        partial_refund = PendingRefund(
            source_type="transaction",
            source_id=source_txn.unique_id,
            source_table="credit_card_transactions",
            expected_amount=expected,
            status="partial",
            notes="Partial refund for defective item, store credit pending",
        )
        session.add(partial_refund)
        session.flush()

        # Create the partial refund bank transaction
        partial_refund_txn = BankTransaction(
            id="demo-bank-refund-partial",
            date=rand_date_in_month(REFERENCE_DATE.year, REFERENCE_DATE.month, 5, 15),
            provider="hapoalim",
            account_name="Main Account",
            description="PARTIAL REFUND - VISA CAL",
            amount=partial_amount,
            category="Shopping",
            tag="Electronics",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        session.add(partial_refund_txn)
        session.flush()

        session.add(RefundLink(
            pending_refund_id=partial_refund.id,
            refund_transaction_id=partial_refund_txn.unique_id,
            refund_source="bank_transactions",
            amount=partial_amount,
        ))

    # 3. Resolved refund: fully linked
    resolved_shopping = [
        t for t in cc_txns
        if t.category == "Shopping" and t.tag == "Online" and t.type == "normal"
        and t.amount < -100 and t not in recent_shopping
    ]
    if resolved_shopping:
        source_txn = resolved_shopping[-1]
        refund_amount = abs(source_txn.amount)

        resolved_refund = PendingRefund(
            source_type="transaction",
            source_id=source_txn.unique_id,
            source_table="credit_card_transactions",
            expected_amount=refund_amount,
            status="resolved",
            notes="Duplicate charge refunded",
        )
        session.add(resolved_refund)
        session.flush()

        refund_txn = BankTransaction(
            id="demo-bank-refund-001",
            date=rand_date_in_month(REFERENCE_DATE.year, REFERENCE_DATE.month, 1, 20),
            provider="hapoalim",
            account_name="Main Account",
            description="REFUND - VISA CAL",
            amount=refund_amount,
            category="Shopping",
            tag="Online",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        session.add(refund_txn)
        session.flush()

        session.add(RefundLink(
            pending_refund_id=resolved_refund.id,
            refund_transaction_id=refund_txn.unique_id,
            refund_source="bank_transactions",
            amount=refund_amount,
        ))

    # 4. Closed refund: user accepted partial, closed it
    restaurant = [
        t for t in cc_txns
        if t.category == "Food" and t.tag == "Restaurants" and t.type == "normal"
        and t.amount < -150
    ]
    if restaurant:
        source_txn = restaurant[-1]
        expected = abs(source_txn.amount)
        closed_partial = round(expected * 0.5, 2)

        closed_refund = PendingRefund(
            source_type="transaction",
            source_id=source_txn.unique_id,
            source_table="credit_card_transactions",
            expected_amount=expected,
            status="closed",
            notes="Restaurant dispute - accepted 50% settlement",
        )
        session.add(closed_refund)
        session.flush()

        closed_refund_txn = BankTransaction(
            id="demo-bank-refund-closed",
            date=rand_date_in_month(REFERENCE_DATE.year, REFERENCE_DATE.month, 10, 20),
            provider="hapoalim",
            account_name="Main Account",
            description="SETTLEMENT - RESTAURANT DISPUTE",
            amount=closed_partial,
            category="Food",
            tag="Restaurants",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        session.add(closed_refund_txn)
        session.flush()

        session.add(RefundLink(
            pending_refund_id=closed_refund.id,
            refund_transaction_id=closed_refund_txn.unique_id,
            refund_source="bank_transactions",
            amount=closed_partial,
        ))

    session.flush()
```

- [ ] **Step 2: Run the demo data generator to verify no errors**

Run: `cd /Users/tomer/Desktop/finance-analysis/.claude/worktrees/hopeful-booth && python scripts/generate_demo_data.py --check-only 2>&1 || python -c "from scripts.generate_demo_data import *; print('Import OK')"`

If there's no `--check-only` flag, just verify the import works. The full generation will be tested manually.

- [ ] **Step 3: Commit**

```bash
git add scripts/generate_demo_data.py
git commit -m "feat(demo): add diverse refund scenarios (pending, partial, resolved, closed)"
```

---

### Task 12: Run full test suite and fix any issues

**Files:** Any files with test failures

- [ ] **Step 1: Run all backend tests**

Run: `poetry run pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 2: Run frontend type check**

Run: `cd frontend && ./node_modules/.bin/tsc -b --noEmit`
Expected: No errors

- [ ] **Step 3: Fix any failures found**

Address any test failures or type errors.

- [ ] **Step 4: Final commit if fixes were needed**

```bash
git add -A
git commit -m "fix(refunds): address test failures from refund feature changes"
```
