"""Service for file-import data source CRUD and import execution.

This module currently exposes the CRUD surface. The import-execution
path (parse → dedup → tag → insert) lands in a follow-on task.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import delete
from sqlalchemy.orm import Session

from backend.models.transaction import (
    BankTransaction,
    CashTransaction,
    CreditCardTransaction,
)
from backend.repositories.credentials_repository import CredentialsRepository
from backend.repositories.imported_accounts_repository import (
    ImportedAccountsRepository,
)


ServiceType = Literal["banks", "credit_cards", "cash"]

_TX_MODEL_BY_SERVICE = {
    "banks": BankTransaction,
    "credit_cards": CreditCardTransaction,
    "cash": CashTransaction,
}


@dataclass
class ImportedAccountDTO:
    """Frontend-friendly view of an imported account row."""

    id: int
    service: str
    provider: str
    account_name: str
    mapping: dict[str, Any]


class ImportedAccountsService:
    """CRUD + import execution for file-import data sources."""

    def __init__(self, db: Session):
        """
        Parameters
        ----------
        db : Session
            SQLAlchemy session.
        """
        self.db = db
        self.repo = ImportedAccountsRepository(db)

    # ---------- CRUD ----------

    def list_accounts(self) -> list[ImportedAccountDTO]:
        """Return all imported accounts as DTOs."""
        df = self.repo.get_all()
        if df.empty:
            return []
        return [
            ImportedAccountDTO(
                id=int(row.id),
                service=row.service,
                provider=row.provider,
                account_name=row.account_name,
                mapping=row.mapping_json,  # JSON column returns a dict
            )
            for row in df.itertuples(index=False)
        ]

    def create(
        self,
        service_type: ServiceType,
        provider: str,
        account_name: str,
        mapping: dict[str, Any],
    ) -> ImportedAccountDTO:
        """Create a new imported account.

        Validates the (service, provider, account_name) triple is unique
        across both imported accounts and connected (scraped) accounts.

        Raises
        ------
        ValueError
            If a connected account or imported account already uses the
            triple.
        """
        if self._credential_collision(service_type, provider, account_name):
            raise ValueError(
                f"A connected account already uses ({service_type}, "
                f"{provider}, {account_name})"
            )
        record = self.repo.create(
            service=service_type,
            provider=provider,
            account_name=account_name,
            mapping_json=mapping,
        )
        return ImportedAccountDTO(
            id=record.id,
            service=record.service,
            provider=record.provider,
            account_name=record.account_name,
            mapping=mapping,
        )

    def update_mapping(
        self, account_id: int, mapping: dict[str, Any]
    ) -> ImportedAccountDTO:
        """Replace the saved mapping for ``account_id``."""
        record = self.repo.update_mapping(account_id, mapping)
        return ImportedAccountDTO(
            id=record.id,
            service=record.service,
            provider=record.provider,
            account_name=record.account_name,
            mapping=mapping,
        )

    def delete(self, account_id: int) -> bool:
        """Delete an imported account and cascade-delete its transactions.

        Returns
        -------
        bool
            ``True`` if the account was deleted, ``False`` if it didn't exist.
        """
        record = self.repo.get_by_id(account_id)
        if record is None:
            return False
        model = _TX_MODEL_BY_SERVICE[record.service]
        self.db.execute(
            delete(model).where(
                model.provider == record.provider,
                model.account_name == record.account_name,
            )
        )
        return self.repo.delete(account_id)

    # ---------- helpers ----------

    def _credential_collision(
        self, service_type: str, provider: str, account_name: str
    ) -> bool:
        """True if a connected (scraped) account exists for the triple.

        Implemented as a method so tests can monkeypatch it without
        touching the OS keyring.
        """
        try:
            creds = CredentialsRepository(self.db)
            accounts = creds.list_accounts()
        except Exception:
            # CredentialsRepository can raise on missing YAML / keyring in
            # some environments; treat as "no collision".
            return False
        for acc in accounts:
            if (
                acc.get("service") == service_type
                and acc.get("provider") == provider
                and acc.get("account_name") == account_name
            ):
                return True
        return False
