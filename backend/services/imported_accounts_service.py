"""Service for file-import data source CRUD and import execution.

This module exposes both the CRUD surface for file-import data sources
and the import-execution pipeline (parse → dedup → auto-tag → insert,
with cash-balance recalc as a side effect).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd
from sqlalchemy import delete, select
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
from backend.services.cash_balance_service import CashBalanceService
from backend.services.file_import_parser import (
    AmountMapping,
    ColumnMapping,
    FieldMapping,
    parse_file_with_summary,
)
from backend.services.tagging_rules_service import TaggingRulesService


logger = logging.getLogger(__name__)


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

    # ---------- Import execution ----------

    def import_file(
        self,
        account_id: int,
        raw: bytes,
        filename: str,
    ) -> dict[str, int]:
        """Parse, dedup, auto-tag, and insert rows from a file upload.

        Parameters
        ----------
        account_id : int
            ID of the imported account this upload belongs to.
        raw : bytes
            Raw uploaded file bytes.
        filename : str
            Original filename (used to pick CSV vs XLSX reader).

        Returns
        -------
        dict
            ``{"inserted": N, "skipped_duplicates": M, "dropped_invalid": K}``.

        Raises
        ------
        ValueError
            If the account does not exist, or parsing fails fundamentally.
        """
        record = self.repo.get_by_id(account_id)
        if record is None:
            raise ValueError(f"Imported account {account_id} not found")
        mapping = _dict_to_mapping(record.mapping_json)

        parsed_df, dropped = parse_file_with_summary(
            raw, filename=filename, mapping=mapping
        )
        if parsed_df.empty:
            return {
                "inserted": 0,
                "skipped_duplicates": 0,
                "dropped_invalid": dropped,
            }

        existing_hashes = self._existing_hashes_for_account(
            service=record.service,
            provider=record.provider,
            account_name=record.account_name,
            min_date=parsed_df["date"].min(),
            max_date=parsed_df["date"].max(),
        )
        parsed_df["_hash"] = parsed_df.apply(_row_hash, axis=1)
        new_rows = parsed_df[~parsed_df["_hash"].isin(existing_hashes)].copy()
        skipped = len(parsed_df) - len(new_rows)
        if new_rows.empty:
            return {
                "inserted": 0,
                "skipped_duplicates": skipped,
                "dropped_invalid": dropped,
            }

        model = _TX_MODEL_BY_SERVICE[record.service]
        source = model.__tablename__
        inserted = 0
        for _, row in new_rows.iterrows():
            category = row.get("category") if "category" in new_rows.columns else None
            tag = row.get("tag") if "tag" in new_rows.columns else None
            account_number = (
                row.get("account_number")
                if "account_number" in new_rows.columns
                else None
            )
            tx = model(
                id=row["_hash"],
                date=row["date"],
                provider=record.provider,
                account_name=record.account_name,
                account_number=account_number,
                description=row["description"],
                amount=float(row["amount"]),
                category=category if category else None,
                tag=tag if tag else None,
                source=source,
                type="normal",
                status="completed",
            )
            self.db.add(tx)
            inserted += 1
        self.db.commit()

        # Auto-tag the newly inserted rows. TaggingRulesService.apply_rules
        # operates on already-persisted bank / credit-card transactions and
        # only touches rows where category is NULL (overwrite=False), so
        # explicitly-categorized rows from the file are not overwritten.
        # Cash rows are not covered by the rules engine in this codebase,
        # which matches existing behavior for manually-entered cash.
        #
        # Auto-tagging is best-effort; never fail the import on it.
        # Rows already committed above will remain untagged on error;
        # the failure is logged so users have a breadcrumb when they
        # see uncategorized rows post-import.
        if record.service in ("banks", "credit_cards"):
            try:
                TaggingRulesService(self.db).apply_rules(overwrite=False)
            except Exception:
                self.db.rollback()
                logger.exception(
                    "Auto-tagging after import failed for account %s/%s/%s",
                    record.service, record.provider, record.account_name,
                )

        if record.service == "cash":
            CashBalanceService(self.db).recalculate_current_balance(
                record.account_name
            )

        return {
            "inserted": inserted,
            "skipped_duplicates": skipped,
            "dropped_invalid": dropped,
        }

    def _existing_hashes_for_account(
        self,
        service: str,
        provider: str,
        account_name: str,
        min_date: str,
        max_date: str,
    ) -> set[str]:
        """Hash existing transactions for this account within a date range."""
        model = _TX_MODEL_BY_SERVICE[service]
        stmt = select(
            model.date, model.description, model.amount
        ).where(
            model.provider == provider,
            model.account_name == account_name,
            model.date >= min_date,
            model.date <= max_date,
        )
        out: set[str] = set()
        for row in self.db.execute(stmt):
            out.add(_hash_triple(row.date, row.description, row.amount))
        return out

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


# ---------- module-level helpers ----------


def _row_hash(row: pd.Series) -> str:
    """Content hash for dedup: (date, description, amount)."""
    return _hash_triple(row["date"], row["description"], row["amount"])


def _hash_triple(date: str, description: str, amount: float) -> str:
    """Stable content hash used for dedup."""
    blob = f"{date}|{description}|{amount:.4f}".encode("utf-8")
    return hashlib.sha1(blob, usedforsecurity=False).hexdigest()


def _dict_to_mapping(d: dict) -> ColumnMapping:
    """Inflate a JSON mapping dict into a ColumnMapping dataclass."""

    def field(spec: dict | None) -> FieldMapping | None:
        if not spec or not spec.get("column"):
            return None
        return FieldMapping(column=spec["column"], format=spec.get("format"))

    amt = d["amount"]
    if amt["mode"] == "single":
        amount = AmountMapping(
            mode="single",
            column=amt["column"],
            sign_convention=amt.get("sign_convention", "positive_is_income"),
        )
    else:
        amount = AmountMapping(
            mode="split",
            debit_column=amt["debit_column"],
            credit_column=amt["credit_column"],
        )

    return ColumnMapping(
        skip_rows=d.get("skip_rows", 0),
        date=FieldMapping(
            column=d["date"]["column"], format=d["date"].get("format")
        ),
        description=FieldMapping(column=d["description"]["column"]),
        amount=amount,
        category=field(d.get("category")),
        tag=field(d.get("tag")),
        account_number=field(d.get("account_number")),
    )
