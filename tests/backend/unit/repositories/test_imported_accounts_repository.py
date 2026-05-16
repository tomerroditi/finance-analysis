"""Unit tests for ImportedAccountsRepository."""

import pytest
from sqlalchemy.orm import Session

from backend.repositories.imported_accounts_repository import (
    ImportedAccountsRepository,
)


class TestImportedAccountsRepository:
    """Tests for ImportedAccountsRepository CRUD."""

    def test_get_all_empty(self, db_session: Session):
        """Get all returns empty DataFrame when no records exist."""
        repo = ImportedAccountsRepository(db_session)
        result = repo.get_all()
        assert result.empty

    def test_create_and_retrieve(self, db_session: Session):
        """Create persists a record and get_by_id returns it."""
        repo = ImportedAccountsRepository(db_session)
        record = repo.create(
            service="banks",
            provider="Hapoalim Manual",
            account_name="Checking",
            mapping_json={"key": "value"},
        )
        assert record.id is not None
        fetched = repo.get_by_id(record.id)
        assert fetched is not None
        assert fetched.service == "banks"

    def test_create_duplicate_triple_raises(self, db_session: Session):
        """Creating a second row with same (service, provider, account_name) raises ValueError."""
        repo = ImportedAccountsRepository(db_session)
        repo.create("banks", "Hapoalim", "Checking", {})
        with pytest.raises(ValueError, match="already exists"):
            repo.create("banks", "Hapoalim", "Checking", {})

    def test_create_same_name_different_service_allowed(self, db_session: Session):
        """Same account_name + provider is allowed across different services."""
        repo = ImportedAccountsRepository(db_session)
        repo.create("banks", "Generic", "Main", {})
        repo.create("credit_cards", "Generic", "Main", {})
        assert len(repo.get_all()) == 2

    def test_get_all_returns_dataframe(self, db_session: Session):
        """Get all returns a DataFrame with expected columns."""
        repo = ImportedAccountsRepository(db_session)
        repo.create("banks", "A", "Acc1", {})
        repo.create("credit_cards", "B", "Acc2", {})
        result = repo.get_all()
        assert len(result) == 2
        assert {"id", "service", "provider", "account_name", "mapping_json"}.issubset(
            result.columns
        )

    def test_update_mapping(self, db_session: Session):
        """Update mapping mutates only mapping_json."""
        repo = ImportedAccountsRepository(db_session)
        record = repo.create("banks", "X", "Y", {"old": True})
        updated = repo.update_mapping(record.id, {"new": True})
        assert updated.mapping_json == {"new": True}
        assert updated.service == "banks"

    def test_update_mapping_not_found_raises(self, db_session: Session):
        """Updating a missing id raises ValueError."""
        repo = ImportedAccountsRepository(db_session)
        with pytest.raises(ValueError, match="not found"):
            repo.update_mapping(999, {})

    def test_delete(self, db_session: Session):
        """Delete removes the row and returns True."""
        repo = ImportedAccountsRepository(db_session)
        record = repo.create("banks", "X", "Y", {})
        assert repo.delete(record.id) is True
        assert repo.get_by_id(record.id) is None

    def test_delete_not_found(self, db_session: Session):
        """Deleting a missing id returns False."""
        repo = ImportedAccountsRepository(db_session)
        assert repo.delete(999) is False

    def test_exists_for_triple(self, db_session: Session):
        """exists_for_triple flags collisions without raising."""
        repo = ImportedAccountsRepository(db_session)
        repo.create("banks", "X", "Y", {})
        assert repo.exists_for_triple("banks", "X", "Y") is True
        assert repo.exists_for_triple("banks", "X", "Z") is False
