"""
Unit tests for InvestmentsService snapshot-related methods.
"""

from unittest.mock import MagicMock

import pandas as pd
from sqlalchemy.orm import Session

from backend.models.investment import Investment
from backend.services.investments_service import InvestmentsService


def _create_investment(db_session: Session, tag: str = "Test Fund", **kwargs) -> int:
    """Helper to create an investment and return its ID."""
    inv = Investment(
        category="Investments",
        tag=tag,
        type="etf",
        name=kwargs.get("name", "Test"),
        interest_rate=kwargs.get("interest_rate"),
        interest_rate_type=kwargs.get("interest_rate_type", "fixed"),
        created_date="2024-01-01",
    )
    db_session.add(inv)
    db_session.commit()
    db_session.refresh(inv)
    return inv.id


def _make_service(db_session: Session, transactions_df: pd.DataFrame | None = None) -> InvestmentsService:
    """Create an InvestmentsService, optionally mocking transaction data."""
    service = InvestmentsService(db_session)
    if transactions_df is not None:
        mock_txn_service = MagicMock()
        mock_txn_service.get_transactions_by_tag.return_value = transactions_df
        service.transactions_service = mock_txn_service
    return service


class TestSnapshotCRUD:
    """Tests for snapshot create/read/delete via the service layer."""

    def test_create_snapshot(self, db_session: Session):
        """Verify creating a balance snapshot via the service."""
        inv_id = _create_investment(db_session)
        service = _make_service(db_session)

        service.create_balance_snapshot(inv_id, "2025-01-15", 50000.0)

        snapshots = service.get_balance_snapshots(inv_id)
        assert len(snapshots) == 1
        assert snapshots[0]["balance"] == 50000.0
        assert snapshots[0]["source"] == "manual"

    def test_get_balance_snapshots_returns_list_of_dicts(self, db_session: Session):
        """Verify snapshots are returned as list of JSON-safe dicts."""
        inv_id = _create_investment(db_session)
        service = _make_service(db_session)

        service.create_balance_snapshot(inv_id, "2025-01-01", 50000.0)
        service.create_balance_snapshot(inv_id, "2025-02-01", 55000.0)

        snapshots = service.get_balance_snapshots(inv_id)
        assert len(snapshots) == 2
        assert all(isinstance(s, dict) for s in snapshots)

    def test_delete_snapshot(self, db_session: Session):
        """Verify deleting a snapshot by ID."""
        inv_id = _create_investment(db_session)
        service = _make_service(db_session)

        service.create_balance_snapshot(inv_id, "2025-01-15", 50000.0)
        snapshots = service.get_balance_snapshots(inv_id)
        snapshot_id = snapshots[0]["id"]

        service.delete_balance_snapshot(snapshot_id)

        remaining = service.get_balance_snapshots(inv_id)
        assert len(remaining) == 0


class TestSnapshotAwareBalance:
    """Tests for snapshot-aware balance resolution."""

    def test_current_balance_uses_latest_snapshot(self, db_session: Session):
        """Verify current balance returns latest snapshot value when available."""
        inv_id = _create_investment(db_session)
        service = _make_service(db_session)

        service.create_balance_snapshot(inv_id, "2025-06-01", 75000.0)

        balance = service.calculate_current_balance(inv_id)
        assert balance == 75000.0

    def test_current_balance_falls_back_to_transactions(self, db_session: Session):
        """Verify current balance falls back to transaction-based when no snapshots."""
        inv_id = _create_investment(db_session)
        txn_df = pd.DataFrame(
            [{"date": "2025-01-01", "amount": -10000, "description": "Deposit"}]
        )
        service = _make_service(db_session, transactions_df=txn_df)

        balance = service.calculate_current_balance(inv_id)
        assert balance == 10000.0


class TestFixedRateCalculation:
    """Tests for fixed-rate auto-calculation of snapshots."""

    def test_calculate_fixed_rate_snapshots(self, db_session: Session):
        """Verify fixed-rate calculation generates correct daily-compounded snapshots."""
        inv_id = _create_investment(
            db_session,
            tag="Savings",
            interest_rate=10.0,
            interest_rate_type="fixed",
        )
        txn_df = pd.DataFrame(
            [{"date": "2025-01-01", "amount": -100000, "description": "Deposit"}]
        )
        service = _make_service(db_session, transactions_df=txn_df)

        service.calculate_fixed_rate_snapshots(inv_id, end_date="2026-01-01")

        snapshots = service.get_balance_snapshots(inv_id)
        assert len(snapshots) > 0
        last_snapshot = snapshots[-1]
        assert abs(last_snapshot["balance"] - 110000) < 500

    def test_calculate_fixed_rate_handles_withdrawal(self, db_session: Session):
        """Verify fixed-rate calculation correctly handles partial withdrawal."""
        inv_id = _create_investment(
            db_session,
            tag="Savings2",
            interest_rate=10.0,
            interest_rate_type="fixed",
        )
        txn_df = pd.DataFrame([
            {"date": "2025-01-01", "amount": -100000, "description": "Deposit"},
            {"date": "2025-07-01", "amount": 50000, "description": "Withdrawal"},
        ])
        service = _make_service(db_session, transactions_df=txn_df)

        service.calculate_fixed_rate_snapshots(inv_id, end_date="2026-01-01")

        snapshots = service.get_balance_snapshots(inv_id)
        last_snapshot = snapshots[-1]
        assert last_snapshot["balance"] < 80000

    def test_manual_snapshots_not_overwritten_by_calculation(self, db_session: Session):
        """Verify manual snapshots are preserved when calculating fixed-rate snapshots."""
        inv_id = _create_investment(
            db_session,
            tag="Savings3",
            interest_rate=10.0,
            interest_rate_type="fixed",
        )
        service = _make_service(db_session)

        service.create_balance_snapshot(inv_id, "2025-06-01", 99999.0)

        txn_df = pd.DataFrame(
            [{"date": "2025-01-01", "amount": -100000, "description": "Deposit"}]
        )
        service.transactions_service = MagicMock()
        service.transactions_service.get_transactions_by_tag.return_value = txn_df

        service.calculate_fixed_rate_snapshots(inv_id, end_date="2026-01-01")

        snapshots = service.get_balance_snapshots(inv_id)
        manual_snapshots = [s for s in snapshots if s["source"] == "manual"]
        assert len(manual_snapshots) == 1
        assert manual_snapshots[0]["balance"] == 99999.0


class TestSnapshotAwareProfitLoss:
    """Tests for profit/loss calculations using snapshot data."""

    def test_profit_loss_uses_snapshot_balance(self, db_session: Session):
        """Verify profit/loss uses snapshot balance instead of transaction-based."""
        inv_id = _create_investment(db_session)
        txn_df = pd.DataFrame(
            [{"date": "2024-01-01", "amount": -100000, "description": "Deposit"}]
        )
        service = _make_service(db_session, transactions_df=txn_df)

        service.create_balance_snapshot(inv_id, "2025-06-01", 120000.0)

        metrics = service.calculate_profit_loss(inv_id)
        assert metrics["current_balance"] == 120000.0
        assert metrics["absolute_profit_loss"] == 20000.0
        assert metrics["total_deposits"] == 100000.0

    def test_profit_loss_without_snapshots_uses_transactions(self, db_session: Session):
        """Verify profit/loss falls back to transaction-based when no snapshots."""
        inv_id = _create_investment(db_session)
        txn_df = pd.DataFrame(
            [{"date": "2024-01-01", "amount": -100000, "description": "Deposit"}]
        )
        service = _make_service(db_session, transactions_df=txn_df)

        metrics = service.calculate_profit_loss(inv_id)
        assert metrics["current_balance"] == 100000.0
        assert metrics["absolute_profit_loss"] == 0.0
