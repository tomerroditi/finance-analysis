"""Unit tests for ImportedAccountsService — import execution."""

from sqlalchemy.orm import Session

from backend.models.transaction import BankTransaction, CashTransaction
from backend.services.imported_accounts_service import (
    ImportedAccountsService,
)


CSV_BYTES = (
    b"date,description,amount\n"
    b"2026-03-01,Coffee shop,-12.50\n"
    b"2026-03-03,Salary,8500.00\n"
    b"2026-03-05,Refund,45.00\n"
)


MAPPING = {
    "skip_rows": 0,
    "date": {"column": "date", "format": "iso"},
    "description": {"column": "description"},
    "amount": {
        "mode": "single",
        "column": "amount",
        "sign_convention": "positive_is_income",
    },
    "category": {"column": None},
    "tag": {"column": None},
    "account_number": {"column": None},
}


class TestImportExecution:
    """Import flow: parse, dedup, tag, insert."""

    def test_first_upload_inserts_all_rows(self, db_session: Session):
        """A fresh import inserts every row into the matching service's table."""
        service = ImportedAccountsService(db_session)
        dto = service.create("banks", "Hapoalim", "Checking", MAPPING)

        summary = service.import_file(
            account_id=dto.id, raw=CSV_BYTES, filename="test.csv"
        )

        assert summary["inserted"] == 3
        assert summary["skipped_duplicates"] == 0
        assert summary["dropped_invalid"] == 0

        rows = db_session.query(BankTransaction).filter_by(
            provider="Hapoalim", account_name="Checking"
        ).all()
        assert len(rows) == 3
        assert all(r.source == "bank_transactions" for r in rows)
        assert all(r.type == "normal" for r in rows)

    def test_dedup_skips_repeats(self, db_session: Session):
        """Reuploading the same file inserts nothing new."""
        service = ImportedAccountsService(db_session)
        dto = service.create("banks", "Hapoalim", "Checking", MAPPING)
        service.import_file(account_id=dto.id, raw=CSV_BYTES, filename="test.csv")
        summary = service.import_file(
            account_id=dto.id, raw=CSV_BYTES, filename="test.csv"
        )
        assert summary["inserted"] == 0
        assert summary["skipped_duplicates"] == 3

    def test_partial_overlap_only_new_rows_inserted(self, db_session: Session):
        """A second file that overlaps with the first imports only new rows."""
        service = ImportedAccountsService(db_session)
        dto = service.create("banks", "Hapoalim", "Checking", MAPPING)
        service.import_file(account_id=dto.id, raw=CSV_BYTES, filename="first.csv")

        second_file = (
            b"date,description,amount\n"
            b"2026-03-03,Salary,8500.00\n"      # dup
            b"2026-03-05,Refund,45.00\n"         # dup
            b"2026-03-10,Withdrawal,-200.00\n"   # new
        )
        summary = service.import_file(
            account_id=dto.id, raw=second_file, filename="second.csv"
        )
        assert summary["inserted"] == 1
        assert summary["skipped_duplicates"] == 2

    def test_cash_service_recalculates_balance(self, db_session: Session, monkeypatch):
        """Cash imports trigger CashBalanceService.recalculate_current_balance."""
        from backend.services import imported_accounts_service as iam

        called = {"with_account": None}

        class FakeCashService:
            def __init__(self, _db):
                pass
            def recalculate_current_balance(self, account_name):
                called["with_account"] = account_name

        monkeypatch.setattr(iam, "CashBalanceService", FakeCashService)

        service = ImportedAccountsService(db_session)
        dto = service.create("cash", "MANUAL", "Wallet", MAPPING)
        service.import_file(account_id=dto.id, raw=CSV_BYTES, filename="test.csv")

        rows = db_session.query(CashTransaction).filter_by(account_name="Wallet").all()
        assert len(rows) == 3
        assert called["with_account"] == "Wallet"

    def test_dropped_invalid_counted(self, db_session: Session):
        """Rows with unparseable amount/date are dropped and reported."""
        bad_csv = (
            b"date,description,amount\n"
            b"2026-03-01,ok,-12.50\n"
            b"2026-03-03,bad,notanumber\n"
        )
        service = ImportedAccountsService(db_session)
        dto = service.create("banks", "X", "Y", MAPPING)
        summary = service.import_file(
            account_id=dto.id, raw=bad_csv, filename="bad.csv"
        )
        assert summary["inserted"] == 1
        assert summary["dropped_invalid"] == 1

    def test_account_not_found_raises(self, db_session: Session):
        """Importing to a non-existent account raises ValueError."""
        import pytest
        service = ImportedAccountsService(db_session)
        with pytest.raises(ValueError, match="not found"):
            service.import_file(account_id=999, raw=CSV_BYTES, filename="x.csv")
