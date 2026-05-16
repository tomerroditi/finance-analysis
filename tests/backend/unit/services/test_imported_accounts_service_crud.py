"""Unit tests for ImportedAccountsService — CRUD path."""

import pytest
from sqlalchemy.orm import Session

from backend.services.imported_accounts_service import (
    ImportedAccountsService,
    ImportedAccountDTO,
)


def _default_mapping() -> dict:
    return {
        "skip_rows": 0,
        "date": {"column": "date", "format": "iso"},
        "description": {"column": "description"},
        "amount": {
            "mode": "single",
            "column": "amount",
            "sign_convention": "positive_is_income",
        },
    }


class TestImportedAccountsServiceCrud:
    """CRUD wrapper behaviour."""

    def test_list_empty(self, db_session: Session):
        """list_accounts returns [] on an empty DB."""
        service = ImportedAccountsService(db_session)
        assert service.list_accounts() == []

    def test_create_returns_dto(self, db_session: Session):
        """create returns an ImportedAccountDTO with the new id."""
        service = ImportedAccountsService(db_session)
        dto = service.create(
            service_type="banks",
            provider="Hapoalim",
            account_name="Checking",
            mapping=_default_mapping(),
        )
        assert isinstance(dto, ImportedAccountDTO)
        assert dto.id is not None
        assert dto.service == "banks"
        assert dto.mapping["amount"]["mode"] == "single"

    def test_create_duplicate_in_imported_raises(self, db_session: Session):
        """Creating the same triple twice raises ValueError."""
        service = ImportedAccountsService(db_session)
        service.create("banks", "H", "A", _default_mapping())
        with pytest.raises(ValueError, match="already exists"):
            service.create("banks", "H", "A", _default_mapping())

    def test_create_collides_with_credential_raises(self, db_session: Session, monkeypatch):
        """If a credential exists for the same triple, creation is blocked."""
        service = ImportedAccountsService(db_session)

        def fake_collides(_service, _provider, _account_name):
            return True

        monkeypatch.setattr(service, "_credential_collision", fake_collides)
        with pytest.raises(ValueError, match="connected account"):
            service.create("banks", "H", "A", _default_mapping())

    def test_list_after_create_returns_dto(self, db_session: Session):
        """list_accounts round-trips the created account."""
        service = ImportedAccountsService(db_session)
        service.create("banks", "H", "A", _default_mapping())
        listed = service.list_accounts()
        assert len(listed) == 1
        assert isinstance(listed[0], ImportedAccountDTO)
        assert listed[0].service == "banks"
        assert listed[0].mapping["amount"]["column"] == "amount"

    def test_update_mapping(self, db_session: Session):
        """update_mapping persists a new mapping."""
        service = ImportedAccountsService(db_session)
        dto = service.create("banks", "H", "A", _default_mapping())
        new_mapping = _default_mapping()
        new_mapping["skip_rows"] = 3
        updated = service.update_mapping(dto.id, new_mapping)
        assert updated.mapping["skip_rows"] == 3

    def test_delete_cascades_transactions(self, db_session: Session):
        """Deleting an account also removes its imported transactions."""
        from backend.models.transaction import BankTransaction

        service = ImportedAccountsService(db_session)
        dto = service.create("banks", "H", "Acc", _default_mapping())
        # Seed a transaction that belongs to this account.
        db_session.add(BankTransaction(
            id="x1", date="2026-03-01", provider="H", account_name="Acc",
            description="Coffee", amount=-12.5, source="bank_transactions",
            type="normal", status="completed",
        ))
        # Seed an unrelated transaction (different account) — must survive.
        db_session.add(BankTransaction(
            id="x2", date="2026-03-01", provider="H", account_name="Other",
            description="Other", amount=-10, source="bank_transactions",
            type="normal", status="completed",
        ))
        db_session.commit()

        service.delete(dto.id)

        remaining = db_session.query(BankTransaction).all()
        assert len(remaining) == 1
        assert remaining[0].account_name == "Other"

    def test_delete_returns_false_when_missing(self, db_session: Session):
        """delete returns False if the account doesn't exist."""
        service = ImportedAccountsService(db_session)
        assert service.delete(999) is False
