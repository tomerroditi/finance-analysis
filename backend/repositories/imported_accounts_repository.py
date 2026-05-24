"""Repository for ImportedAccount records (CRUD)."""

import pandas as pd
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models.imported_account import ImportedAccount


class ImportedAccountsRepository:
    """CRUD for file-import data source metadata."""

    def __init__(self, db: Session):
        """
        Parameters
        ----------
        db : Session
            SQLAlchemy session.
        """
        self.db = db

    def get_all(self) -> pd.DataFrame:
        """Return all imported accounts as a DataFrame.

        Returns
        -------
        pd.DataFrame
            Empty DataFrame if no rows; otherwise has columns
            ``id, service, provider, account_name, mapping_json,
            created_at, updated_at``.
        """
        stmt = select(ImportedAccount)
        return pd.read_sql(stmt, self.db.bind)

    def get_by_id(self, account_id: int) -> ImportedAccount | None:
        """Return the ORM row for ``account_id`` or ``None``."""
        return self.db.get(ImportedAccount, account_id)

    def exists_for_triple(
        self, service: str, provider: str, account_name: str
    ) -> bool:
        """True if a row exists for the (service, provider, account_name) triple."""
        stmt = select(ImportedAccount).where(
            ImportedAccount.service == service,
            ImportedAccount.provider == provider,
            ImportedAccount.account_name == account_name,
        )
        return self.db.execute(stmt).first() is not None

    def create(
        self,
        service: str,
        provider: str,
        account_name: str,
        mapping_json: dict,
    ) -> ImportedAccount:
        """Insert a new imported account.

        Parameters
        ----------
        mapping_json : dict
            Column mapping; persisted as JSON.

        Raises
        ------
        ValueError
            If a row with the same (service, provider, account_name) triple
            already exists.
        """
        record = ImportedAccount(
            service=service,
            provider=provider,
            account_name=account_name,
            mapping_json=mapping_json,
        )
        self.db.add(record)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise ValueError(
                f"Imported account ({service}, {provider}, {account_name}) "
                "already exists"
            )
        self.db.refresh(record)
        return record

    def update_mapping(
        self, account_id: int, mapping_json: dict
    ) -> ImportedAccount:
        """Replace ``mapping_json`` for ``account_id``.

        Raises
        ------
        ValueError
            If the row does not exist.
        """
        record = self.db.get(ImportedAccount, account_id)
        if record is None:
            raise ValueError(f"Imported account {account_id} not found")
        record.mapping_json = mapping_json
        self.db.commit()
        self.db.refresh(record)
        return record

    def delete(self, account_id: int) -> bool:
        """Delete the row by id. Returns True if deleted, False if not found."""
        record = self.db.get(ImportedAccount, account_id)
        if record is None:
            return False
        self.db.delete(record)
        self.db.commit()
        return True
