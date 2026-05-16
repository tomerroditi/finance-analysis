"""Unit tests for the ImportedAccount ORM model."""

from sqlalchemy.orm import Session

from backend.models.imported_account import ImportedAccount


class TestImportedAccountModel:
    """Tests for the ImportedAccount ORM model."""

    def test_insert_and_retrieve(self, db_session: Session):
        """Insert a record and retrieve it back with all fields preserved."""
        account = ImportedAccount(
            service="banks",
            provider="Hapoalim Manual",
            account_name="Checking",
            mapping_json='{"date": {"column": "Date", "format": "iso"}}',
        )
        db_session.add(account)
        db_session.commit()

        retrieved = db_session.query(ImportedAccount).first()
        assert retrieved.id is not None
        assert retrieved.service == "banks"
        assert retrieved.provider == "Hapoalim Manual"
        assert retrieved.account_name == "Checking"
        assert "Date" in retrieved.mapping_json
        assert retrieved.created_at is not None
        assert retrieved.updated_at is not None

    def test_tablename(self):
        """Table name comes from the Tables enum."""
        from backend.constants.tables import Tables
        assert ImportedAccount.__tablename__ == Tables.IMPORTED_ACCOUNTS.value
