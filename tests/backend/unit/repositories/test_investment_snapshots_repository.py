"""
Unit tests for InvestmentSnapshotsRepository CRUD operations.
"""

import pytest
from sqlalchemy.orm import Session

from backend.errors import EntityNotFoundException
from backend.models.investment import Investment
from backend.models.investment_balance_snapshot import InvestmentBalanceSnapshot
from backend.repositories.investment_snapshots_repository import (
    InvestmentSnapshotsRepository,
)


def _create_investment(db_session: Session, tag: str = "Test Fund") -> int:
    """Create a minimal investment record and return its ID.

    Parameters
    ----------
    db_session : Session
        Active SQLAlchemy session.
    tag : str
        Tag name for the investment. Defaults to ``"Test Fund"``.

    Returns
    -------
    int
        The auto-generated primary key of the new investment.
    """
    inv = Investment(
        category="Investments",
        tag=tag,
        type="etf",
        name=f"Test {tag}",
        created_date="2024-01-01",
    )
    db_session.add(inv)
    db_session.commit()
    db_session.refresh(inv)
    return inv.id


class TestUpsertSnapshot:
    """Tests for the upsert_snapshot method."""

    def test_upsert_creates_new_snapshot(self, db_session: Session):
        """Verify upsert_snapshot creates a new snapshot when none exists for the date."""
        inv_id = _create_investment(db_session)
        repo = InvestmentSnapshotsRepository(db_session)

        repo.upsert_snapshot(inv_id, "2024-06-15", 50000.0)

        df = repo.get_snapshots_for_investment(inv_id)
        assert len(df) == 1
        row = df.iloc[0]
        assert row["investment_id"] == inv_id
        assert row["date"] == "2024-06-15"
        assert row["balance"] == 50000.0
        assert row["source"] == "manual"

    def test_upsert_updates_existing_snapshot_for_same_date(self, db_session: Session):
        """Verify upsert_snapshot updates balance when a snapshot already exists for the date."""
        inv_id = _create_investment(db_session)
        repo = InvestmentSnapshotsRepository(db_session)

        repo.upsert_snapshot(inv_id, "2024-06-15", 50000.0)
        repo.upsert_snapshot(inv_id, "2024-06-15", 55000.0, source="scraped")

        df = repo.get_snapshots_for_investment(inv_id)
        assert len(df) == 1
        row = df.iloc[0]
        assert row["balance"] == 55000.0
        assert row["source"] == "scraped"


class TestGetSnapshotsForInvestment:
    """Tests for the get_snapshots_for_investment method."""

    def test_returns_ordered_by_date_asc(self, db_session: Session):
        """Verify snapshots are returned ordered by date ascending."""
        inv_id = _create_investment(db_session)
        repo = InvestmentSnapshotsRepository(db_session)

        repo.upsert_snapshot(inv_id, "2024-03-01", 30000.0)
        repo.upsert_snapshot(inv_id, "2024-01-01", 10000.0)
        repo.upsert_snapshot(inv_id, "2024-02-01", 20000.0)

        df = repo.get_snapshots_for_investment(inv_id)
        assert len(df) == 3
        assert list(df["date"]) == ["2024-01-01", "2024-02-01", "2024-03-01"]
        assert list(df["balance"]) == [10000.0, 20000.0, 30000.0]

    def test_returns_empty_dataframe_when_no_snapshots(self, db_session: Session):
        """Verify an empty DataFrame is returned for an investment with no snapshots."""
        inv_id = _create_investment(db_session)
        repo = InvestmentSnapshotsRepository(db_session)

        df = repo.get_snapshots_for_investment(inv_id)
        assert df.empty


class TestGetLatestSnapshotOnOrBefore:
    """Tests for the get_latest_snapshot_on_or_before method."""

    def test_finds_correct_snapshot_before_date(self, db_session: Session):
        """Verify the latest snapshot on or before target date is returned."""
        inv_id = _create_investment(db_session)
        repo = InvestmentSnapshotsRepository(db_session)

        repo.upsert_snapshot(inv_id, "2024-01-01", 10000.0)
        repo.upsert_snapshot(inv_id, "2024-02-01", 20000.0)
        repo.upsert_snapshot(inv_id, "2024-03-01", 30000.0)

        result = repo.get_latest_snapshot_on_or_before(inv_id, "2024-02-15")
        assert result is not None
        assert result["date"] == "2024-02-01"
        assert result["balance"] == 20000.0

    def test_exact_date_match(self, db_session: Session):
        """Verify exact date match is included in the result."""
        inv_id = _create_investment(db_session)
        repo = InvestmentSnapshotsRepository(db_session)

        repo.upsert_snapshot(inv_id, "2024-02-01", 20000.0)
        repo.upsert_snapshot(inv_id, "2024-03-01", 30000.0)

        result = repo.get_latest_snapshot_on_or_before(inv_id, "2024-02-01")
        assert result is not None
        assert result["date"] == "2024-02-01"
        assert result["balance"] == 20000.0

    def test_returns_none_when_no_snapshots_before_date(self, db_session: Session):
        """Verify None is returned when no snapshots exist on or before the target date."""
        inv_id = _create_investment(db_session)
        repo = InvestmentSnapshotsRepository(db_session)

        repo.upsert_snapshot(inv_id, "2024-06-01", 50000.0)

        result = repo.get_latest_snapshot_on_or_before(inv_id, "2024-05-31")
        assert result is None


class TestDeleteSnapshot:
    """Tests for the delete_snapshot method."""

    def test_delete_snapshot_by_id(self, db_session: Session):
        """Verify deleting a snapshot by its ID removes it from the database."""
        inv_id = _create_investment(db_session)
        repo = InvestmentSnapshotsRepository(db_session)

        repo.upsert_snapshot(inv_id, "2024-01-01", 10000.0)
        df = repo.get_snapshots_for_investment(inv_id)
        snapshot_id = int(df.iloc[0]["id"])

        repo.delete_snapshot(snapshot_id)

        df_after = repo.get_snapshots_for_investment(inv_id)
        assert df_after.empty

    def test_delete_snapshot_raises_for_nonexistent_id(self, db_session: Session):
        """Verify EntityNotFoundException is raised for a non-existent snapshot ID."""
        repo = InvestmentSnapshotsRepository(db_session)
        with pytest.raises(EntityNotFoundException):
            repo.delete_snapshot(999)


class TestUpdateSnapshot:
    """Tests for the update_snapshot method."""

    def test_update_snapshot_balance(self, db_session: Session):
        """Verify updating a snapshot's balance persists the new value."""
        inv_id = _create_investment(db_session)
        repo = InvestmentSnapshotsRepository(db_session)

        repo.upsert_snapshot(inv_id, "2024-01-01", 10000.0)
        df = repo.get_snapshots_for_investment(inv_id)
        snapshot_id = int(df.iloc[0]["id"])

        repo.update_snapshot(snapshot_id, balance=15000.0)

        df_after = repo.get_snapshots_for_investment(inv_id)
        assert df_after.iloc[0]["balance"] == 15000.0

    def test_update_snapshot_raises_for_nonexistent_id(self, db_session: Session):
        """Verify EntityNotFoundException is raised when updating a non-existent snapshot."""
        repo = InvestmentSnapshotsRepository(db_session)
        with pytest.raises(EntityNotFoundException):
            repo.update_snapshot(999, balance=10000.0)


class TestDeleteSnapshotsForInvestment:
    """Tests for the delete_snapshots_for_investment method."""

    def test_bulk_delete_all_snapshots(self, db_session: Session):
        """Verify all snapshots for an investment are deleted."""
        inv_id = _create_investment(db_session)
        repo = InvestmentSnapshotsRepository(db_session)

        repo.upsert_snapshot(inv_id, "2024-01-01", 10000.0)
        repo.upsert_snapshot(inv_id, "2024-02-01", 20000.0)
        repo.upsert_snapshot(inv_id, "2024-03-01", 30000.0)

        repo.delete_snapshots_for_investment(inv_id)

        df = repo.get_snapshots_for_investment(inv_id)
        assert df.empty

    def test_bulk_delete_with_source_filter(self, db_session: Session):
        """Verify only snapshots matching the source filter are deleted."""
        inv_id = _create_investment(db_session)
        repo = InvestmentSnapshotsRepository(db_session)

        repo.upsert_snapshot(inv_id, "2024-01-01", 10000.0, source="manual")
        repo.upsert_snapshot(inv_id, "2024-02-01", 20000.0, source="scraped")
        repo.upsert_snapshot(inv_id, "2024-03-01", 30000.0, source="manual")

        repo.delete_snapshots_for_investment(inv_id, source="scraped")

        df = repo.get_snapshots_for_investment(inv_id)
        assert len(df) == 2
        assert list(df["source"]) == ["manual", "manual"]
        assert list(df["date"]) == ["2024-01-01", "2024-03-01"]

    def test_bulk_delete_does_not_affect_other_investments(self, db_session: Session):
        """Verify deleting snapshots for one investment does not affect another."""
        inv_id_1 = _create_investment(db_session, tag="Fund A")
        inv_id_2 = _create_investment(db_session, tag="Fund B")
        repo = InvestmentSnapshotsRepository(db_session)

        repo.upsert_snapshot(inv_id_1, "2024-01-01", 10000.0)
        repo.upsert_snapshot(inv_id_2, "2024-01-01", 50000.0)

        repo.delete_snapshots_for_investment(inv_id_1)

        df_1 = repo.get_snapshots_for_investment(inv_id_1)
        df_2 = repo.get_snapshots_for_investment(inv_id_2)
        assert df_1.empty
        assert len(df_2) == 1
        assert df_2.iloc[0]["balance"] == 50000.0
