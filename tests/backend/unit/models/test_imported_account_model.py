"""Unit tests for the ImportedAccount ORM model."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.constants.tables import Tables
from backend.models.imported_account import ImportedAccount


class TestImportedAccountModel:
    """Tests for the ImportedAccount ORM model."""

    def test_insert_and_retrieve(self, db_session: Session):
        """Insert a record and retrieve it back with all fields preserved."""
        account = ImportedAccount(
            service="banks",
            provider="Hapoalim Manual",
            account_name="Checking",
            mapping_json={"date": {"column": "Date", "format": "iso"}},
        )
        db_session.add(account)
        db_session.commit()

        retrieved = db_session.query(ImportedAccount).first()
        assert retrieved.id is not None
        assert retrieved.service == "banks"
        assert retrieved.provider == "Hapoalim Manual"
        assert retrieved.account_name == "Checking"
        assert retrieved.mapping_json == {"date": {"column": "Date", "format": "iso"}}
        assert retrieved.created_at is not None
        assert retrieved.updated_at is not None

    def test_tablename(self):
        """Table name comes from the Tables enum."""
        assert ImportedAccount.__tablename__ == Tables.IMPORTED_ACCOUNTS.value

    def test_unique_constraint_rejects_duplicate(self, db_session: Session):
        """Same (service, provider, account_name) triple violates the constraint."""
        db_session.add(ImportedAccount(
            service="banks", provider="X", account_name="Y", mapping_json={},
        ))
        db_session.commit()
        db_session.add(ImportedAccount(
            service="banks", provider="X", account_name="Y", mapping_json={},
        ))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_different_account_names_same_provider_allowed(self, db_session: Session):
        """Same provider with different account_name does not violate the constraint."""
        db_session.add_all([
            ImportedAccount(
                service="banks", provider="X", account_name="A", mapping_json={},
            ),
            ImportedAccount(
                service="banks", provider="X", account_name="B", mapping_json={},
            ),
        ])
        db_session.commit()
        assert db_session.query(ImportedAccount).count() == 2
