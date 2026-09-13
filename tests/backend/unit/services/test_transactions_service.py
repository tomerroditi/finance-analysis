"""Tests for TransactionsService using real in-memory SQLite database."""

import warnings
from datetime import date, datetime

import pandas as pd
import pytest

from backend.constants.categories import PRIOR_WEALTH_TAG, IncomeCategories
from backend.constants.tables import Tables, TransactionsTableFields
from backend.errors import EntityNotFoundException, ValidationException
from backend.models.cash_balance import CashBalance
from backend.models.transaction import (
    BankTransaction,
    CashTransaction,
    CreditCardTransaction,
    SplitTransaction,
)
from backend.repositories.split_transactions_repository import (
    SplitTransactionsRepository,
)
from backend.services.budget_month_override_service import (
    BudgetMonthOverrideService,
)
from backend.services.pending_refunds_service import PendingRefundsService
from backend.services.transactions_service import TransactionsService


def _add_cash(db_session, tx_id="cash-1", amount=-100.0, date="2024-02-10",
              account_name="Wallet", **overrides) -> int:
    """Insert one deletable cash transaction and return its unique_id."""
    fields = dict(
        id=tx_id, date=date, provider="CASH", account_name=account_name,
        description="spend", amount=amount, category="Food", tag="Groceries",
        source="cash_transactions", type="normal", status="completed",
    )
    fields.update(overrides)
    tx = CashTransaction(**fields)
    db_session.add(tx)
    db_session.commit()
    db_session.refresh(tx)
    return tx.unique_id


def _add_bank(db_session, tx_id, amount, date="2024-01-15", provider="hapoalim",
              account_name="Checking", **overrides) -> int:
    """Insert one bank transaction and return its unique_id."""
    fields = dict(
        id=tx_id, date=date, provider=provider, account_name=account_name,
        description=tx_id, amount=amount, category="Food", tag="Groceries",
        source="bank_transactions", type="normal", status="completed",
    )
    fields.update(overrides)
    tx = BankTransaction(**fields)
    db_session.add(tx)
    db_session.commit()
    db_session.refresh(tx)
    return tx.unique_id


def _split_ids(db_session, unique_id: int, source: str) -> list[int]:
    """Return the split ids currently attached to a parent."""
    return [
        s.id
        for s in db_session.query(SplitTransaction)
        .filter_by(transaction_id=unique_id, source=source)
        .order_by(SplitTransaction.id)
        .all()
    ]


class TestTransactionsServiceDataRetrieval:
    """Tests for TransactionsService data retrieval methods."""

    def test_get_data_for_analysis_empty_db(self, db_session):
        """Verify empty DataFrame returned when no transactions exist."""
        service = TransactionsService(db_session)
        result = service.get_data_for_analysis()
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_get_data_for_analysis_empty_db_has_canonical_columns(self, db_session):
        """Verify the empty result still exposes the canonical analysis columns.

        Downstream consumers (analysis/budget services) index into columns
        like ``date``, ``source``, and ``category``. An empty DataFrame
        without columns triggers ``KeyError`` for those consumers, so the
        service must always return the canonical schema.
        """
        service = TransactionsService(db_session)
        result = service.get_data_for_analysis()

        assert result.empty
        for column in service.ANALYSIS_COLUMNS:
            assert column in result.columns

    def test_get_data_for_analysis_merges_sources(self, db_session, seed_base_transactions):
        """Verify data from CC, bank, cash, and manual_investments are merged."""
        service = TransactionsService(db_session)
        result = service.get_data_for_analysis()

        assert not result.empty

        source_col = TransactionsTableFields.SOURCE.value
        sources = result[source_col].unique()
        assert "credit_card_transactions" in sources
        assert "bank_transactions" in sources
        assert "cash_transactions" in sources

    def test_get_data_for_analysis_includes_prior_wealth(
        self, db_session, seed_prior_wealth_transactions
    ):
        """Verify bank prior wealth synthetic rows are included."""
        service = TransactionsService(db_session)
        result = service.get_data_for_analysis()

        tag_col = TransactionsTableFields.TAG.value
        source_col = TransactionsTableFields.SOURCE.value

        bank_pw_rows = result[
            (result[tag_col] == PRIOR_WEALTH_TAG) & (result[source_col] == "bank_balances")
        ]
        assert len(bank_pw_rows) == 2  # hapoalim + leumi

        all_pw_rows = result[result[tag_col] == PRIOR_WEALTH_TAG]
        assert len(all_pw_rows) == 3  # 2 bank balance + 1 cash

    def test_get_data_for_analysis_merges_without_dtype_warning(
        self,
        db_session,
        seed_base_transactions,
        seed_split_transactions,
        seed_prior_wealth_transactions,
    ):
        """Verify the source frames agree on dtypes before they are concatenated.

        ``split_id`` used to be an ``object`` column of ``None`` on frames the
        split-expansion path never touched (cash, the synthetic prior-wealth
        rows) and ``float64`` everywhere else. Concatenating an all-NA column
        with a differently-typed one makes pandas emit a ``FutureWarning``
        about all-NA entries no longer being excluded from dtype inference.
        """
        service = TransactionsService(db_session)

        with warnings.catch_warnings():
            warnings.simplefilter("error", FutureWarning)
            result = service.get_data_for_analysis()

        split_id_col = TransactionsTableFields.SPLIT_ID.value
        frames = [
            service.get_table_for_analysis(service_name)
            for service_name in ("credit_cards", "banks", "cash", "manual_investments")
        ] + [
            service._build_bank_prior_wealth_rows(),
            service._build_investment_prior_wealth_rows(),
        ]
        dtypes = {
            frame[split_id_col].dtype for frame in frames if split_id_col in frame.columns
        }
        assert dtypes == {result[split_id_col].dtype}

    def test_get_table_for_analysis_single_service(self, db_session, seed_base_transactions):
        """Verify filtering by a single service."""
        service = TransactionsService(db_session)
        cc_data = service.get_table_for_analysis("credit_cards")

        source_col = TransactionsTableFields.SOURCE.value
        assert not cc_data.empty
        assert all(cc_data[source_col] == "credit_card_transactions")

    def test_get_all_transactions_invalid_service(self, db_session):
        """Verify ValueError for invalid service name."""
        service = TransactionsService(db_session)
        with pytest.raises(ValueError, match="service must be one of"):
            service.get_all_transactions("invalid_service")

    def test_get_untagged_transactions(self, db_session, seed_untagged_transactions):
        """Verify only untagged (null category) transactions returned."""
        service = TransactionsService(db_session)
        result = service.get_untagged_transactions("credit_cards")

        category_col = TransactionsTableFields.CATEGORY.value
        assert not result.empty
        assert result[category_col].isna().all()
        assert len(result) == 4

    def test_get_transactions_by_tag(self, db_session, seed_base_transactions):
        """Verify filtering by category and optional tag."""
        service = TransactionsService(db_session)

        food_txns = service.get_transactions_by_tag("Food")
        category_col = TransactionsTableFields.CATEGORY.value
        assert not food_txns.empty
        assert all(food_txns[category_col] == "Food")

        grocery_txns = service.get_transactions_by_tag("Food", "Groceries")
        tag_col = TransactionsTableFields.TAG.value
        assert not grocery_txns.empty
        assert all(grocery_txns[tag_col] == "Groceries")
        assert len(grocery_txns) < len(food_txns)

    def test_get_data_for_analysis_includes_investment_prior_wealth(
        self, db_session, seed_investments
    ):
        """Verify investment prior wealth synthetic rows appear in analysis data."""
        stock_fund = seed_investments["investments"][0]
        stock_fund.prior_wealth_amount = 12000.0
        db_session.commit()

        service = TransactionsService(db_session)
        result = service.get_data_for_analysis()

        tag_col = TransactionsTableFields.TAG.value
        source_col = TransactionsTableFields.SOURCE.value

        inv_pw_rows = result[
            (result[tag_col] == PRIOR_WEALTH_TAG) & (result[source_col] == "investments")
        ]
        # Only stock_fund is open (bond_fund is closed), so 1 row
        assert len(inv_pw_rows) == 1
        assert inv_pw_rows.iloc[0]["amount"] == pytest.approx(12000.0)
        assert inv_pw_rows.iloc[0]["category"] == IncomeCategories.OTHER_INCOME.value


class TestTransactionsServiceCRUD:
    """Tests for TransactionsService create/update/delete operations."""

    def test_create_cash_transaction(self, db_session):
        """Verify creating a cash transaction persists it and forces provider CASH."""
        service = TransactionsService(db_session)
        data = {
            "date": date(2024, 4, 1),
            "account_name": "Cash Wallet",
            "description": "Test cash purchase",
            "amount": -50.0,
            "provider": "MANUAL",  # overridden to "CASH"
            "category": "Food",
            "tag": "Groceries",
        }
        service.create_transaction(data, "cash")

        result = service.get_all_transactions("cash")
        user_rows = result[result["tag"] != PRIOR_WEALTH_TAG]
        assert len(user_rows) == 1
        assert user_rows.iloc[0]["description"] == "Test cash purchase"
        assert user_rows.iloc[0]["amount"] == -50.0
        assert user_rows.iloc[0]["provider"] == "CASH"

    def test_create_manual_investments_transaction(self, db_session):
        """Verify creating a manual investment transaction."""
        service = TransactionsService(db_session)
        data = {
            "date": date(2024, 4, 1),
            "account_name": "Investment Account",
            "description": "Monthly deposit",
            "amount": -2000.0,
            "provider": "manual_investments",
            "category": "Investments",
            "tag": "Stock Fund",
        }
        service.create_transaction(data, "manual_investments")

        result = service.get_table_for_analysis("manual_investments")
        user_rows = result[result["tag"] != PRIOR_WEALTH_TAG]
        assert len(user_rows) == 1
        assert user_rows.iloc[0]["description"] == "Monthly deposit"

    def test_create_transaction_invalid_service(self, db_session):
        """Verify ValueError for unsupported service."""
        service = TransactionsService(db_session)
        data = {
            "date": date(2024, 4, 1),
            "account_name": "Test",
            "description": "Test",
            "amount": -100.0,
        }
        with pytest.raises(ValueError, match="Can only create cash or manual_investments"):
            service.create_transaction(data, "credit_cards")

    def test_update_transaction_manual_source(self, db_session):
        """Verify manual sources can edit description/amount and provider stays CASH."""
        service = TransactionsService(db_session)
        unique_id = _add_cash(db_session, description="Original description", amount=-50.0)

        updates = {
            "description": "Updated description",
            "amount": -75.0,
            "provider": "updated_provider",
        }
        assert service.update_transaction(unique_id, "cash_transactions", updates) is True

        updated_df = service.get_all_transactions("cash")
        updated_row = updated_df[updated_df["unique_id"] == unique_id].iloc[0]
        assert updated_row["description"] == "Updated description"
        assert updated_row["amount"] == -75.0
        assert updated_row["provider"] == "CASH"

    def test_update_transaction_scraped_source_only_tags(
        self, db_session, seed_base_transactions
    ):
        """Verify scraped sources can only update category/tag."""
        service = TransactionsService(db_session)

        cc_df = service.get_all_transactions("credit_cards")
        unique_id = int(cc_df.iloc[0]["unique_id"])
        original_description = cc_df.iloc[0]["description"]

        updates = {
            "description": "Should not update",
            "category": "Transport",
            "tag": "Gas",
        }
        assert service.update_transaction(
            unique_id, "credit_card_transactions", updates
        ) is True

        updated_df = service.get_all_transactions("credit_cards")
        updated_row = updated_df[updated_df["unique_id"] == unique_id].iloc[0]
        assert updated_row["description"] == original_description
        assert updated_row["category"] == "Transport"
        assert updated_row["tag"] == "Gas"

    def test_update_cash_transaction_date(self, db_session):
        """Verify updating a cash transaction's date is persisted."""
        service = TransactionsService(db_session)
        unique_id = _add_cash(db_session)

        assert service.update_transaction(
            unique_id, "cash_transactions", {"date": "2024-06-15"}
        ) is True

        updated_df = service.get_all_transactions("cash")
        updated_row = updated_df[updated_df["unique_id"] == unique_id].iloc[0]
        assert str(updated_row["date"]) == "2024-06-15"

    def test_update_cash_transaction_account_name_recalculates_both_balances(
        self, db_session
    ):
        """Verify changing account_name recalculates balances for old and new accounts."""
        from backend.services.cash_balance_service import CashBalanceService

        service = TransactionsService(db_session)
        cash_balance_svc = CashBalanceService(db_session)

        # Order matters: the -50 must already be in the wallet when its
        # balance is fixed at 200, so prior wealth is derived as 250.
        unique_id = _add_cash(db_session, account_name="Wallet A", amount=-50.0)
        cash_balance_svc.set_balance("Wallet A", 200.0)
        cash_balance_svc.set_balance("Wallet B", 0.0)

        assert service.update_transaction(
            unique_id, "cash_transactions", {"account_name": "Wallet B"}
        ) is True

        wallet_a = cash_balance_svc.get_by_account_name("Wallet A")
        wallet_b = cash_balance_svc.get_by_account_name("Wallet B")
        assert wallet_a is not None and wallet_b is not None
        # Wallet A's balance was fixed at 200 with the -50 inside it, so its
        # prior wealth is 250; moving the row out leaves 250. Wallet B (prior
        # wealth 0) now carries the -50.
        assert wallet_a["balance"] == pytest.approx(250.0)
        assert wallet_b["balance"] == pytest.approx(-50.0)

    def test_update_transaction_date_ignored_for_scraped_source(
        self, db_session, seed_base_transactions
    ):
        """Verify date and account_name updates are ignored for scraped (non-manual) sources."""
        service = TransactionsService(db_session)

        cc_df = service.get_all_transactions("credit_cards")
        unique_id = int(cc_df.iloc[0]["unique_id"])
        original_date = cc_df.iloc[0]["date"]

        assert service.update_transaction(
            unique_id,
            "credit_card_transactions",
            {"date": "2099-01-01", "account_name": "Hacked", "category": "Food"},
        ) is True

        updated_df = service.get_all_transactions("credit_cards")
        updated_row = updated_df[updated_df["unique_id"] == unique_id].iloc[0]
        assert str(updated_row["date"]) == str(original_date)
        assert updated_row["account_name"] != "Hacked"
        assert updated_row["category"] == "Food"

    def test_update_transaction_nonexistent_id_raises_not_found(self, db_session):
        """Updating a unique_id that does not exist is a 404, not a silent no-op."""
        service = TransactionsService(db_session)
        with pytest.raises(EntityNotFoundException, match="not found"):
            service.update_transaction(
                99999, "cash_transactions", {"description": "ghost"}
            )

    def test_update_transaction_invalid_date_rejected(self, db_session):
        """A manual date that is not YYYY-MM-DD is rejected before it is stored."""
        service = TransactionsService(db_session)
        unique_id = _add_cash(db_session)

        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            service.update_transaction(
                unique_id, "cash_transactions", {"date": "15/06/2024"}
            )

        assert db_session.get(CashTransaction, unique_id).date == "2024-02-10"

    def test_delete_transaction_cash(self, db_session):
        """Verify deleting a cash transaction removes the row and recalculates the balance."""
        db_session.add(CashBalance(
            account_name="Wallet", balance=0.0, prior_wealth_amount=0.0,
            last_manual_update="2024-01-01",
        ))
        db_session.commit()
        unique_id = _add_cash(db_session, amount=-30.0)
        service = TransactionsService(db_session)

        service.delete_transaction(unique_id, "cash_transactions")

        assert db_session.get(CashTransaction, unique_id) is None
        balance = db_session.query(CashBalance).filter_by(account_name="Wallet").one()
        assert balance.balance == pytest.approx(0.0)

    @pytest.mark.parametrize(
        ("service_name", "source"),
        [
            ("credit_cards", "credit_card_transactions"),
            ("banks", "bank_transactions"),
        ],
    )
    def test_delete_transaction_scraped_source_forbidden(
        self, db_session, seed_base_transactions, service_name, source
    ):
        """Verify PermissionError when deleting a scraped (CC/bank) transaction."""
        service = TransactionsService(db_session)
        uid = int(service.get_all_transactions(service_name).iloc[0]["unique_id"])

        with pytest.raises(PermissionError, match="Deletion of .* prohibited"):
            service.delete_transaction(uid, source)

    def test_delete_transaction_protected_tag(self, db_session):
        """Verify PermissionError when deleting a system-generated Prior Wealth transaction."""
        service = TransactionsService(db_session)
        unique_id = _add_cash(
            db_session, tx_id="pw_test_1", date="2024-01-01", provider="MANUAL",
            account_name=PRIOR_WEALTH_TAG, description="Prior Wealth Offset (cash)",
            amount=100.0, category="Other Income", tag=PRIOR_WEALTH_TAG,
        )

        with pytest.raises(PermissionError, match="Cannot manually delete .*system-generated"):
            service.delete_transaction(unique_id, "cash_transactions")

    def test_bulk_tag_transactions(self, db_session, seed_untagged_transactions):
        """Verify bulk tagging updates multiple transactions."""
        service = TransactionsService(db_session)

        untagged = service.get_untagged_transactions("credit_cards")
        unique_ids = untagged["unique_id"].astype(int).tolist()
        assert len(unique_ids) >= 2

        service.bulk_tag_transactions(
            unique_ids, "credit_card_transactions", "Food", "Groceries",
        )

        cc_df = service.get_all_transactions("credit_cards")
        tagged = cc_df[cc_df["unique_id"].isin(unique_ids)]
        assert all(tagged["category"] == "Food")
        assert all(tagged["tag"] == "Groceries")


class TestTransactionsServicePriorWealth:
    """Tests for prior wealth offset synchronization."""

    def test_create_manual_investments_transaction_updates_prior_wealth(
        self, db_session, seed_investments
    ):
        """Verify creating a manual_investments transaction recalculates Investment.prior_wealth_amount."""
        service = TransactionsService(db_session)
        stock_fund = seed_investments["investments"][0]

        data = {
            "date": date(2024, 3, 1),
            "description": "Extra deposit",
            "amount": -3000.0,
            "account_name": "Investment Account",
            "category": "Investments",
            "tag": "Stock Fund",
        }
        service.create_transaction(data, "manual_investments")

        db_session.refresh(stock_fund)
        # Existing txns: -10000 + -2000 = -12000, plus new -3000 = -15000 → prior_wealth = 15000
        assert stock_fund.prior_wealth_amount == pytest.approx(15000.0)

    def test_delete_manual_investments_transaction_updates_prior_wealth(
        self, db_session, seed_investments
    ):
        """Verify deleting a manual_investments transaction recalculates Investment.prior_wealth_amount."""
        service = TransactionsService(db_session)
        stock_fund = seed_investments["investments"][0]
        txns = seed_investments["transactions"]
        inv_txn_2 = next(t for t in txns if t.id == "inv_txn_2")

        service.delete_transaction(inv_txn_2.unique_id, "manual_investment_transactions")

        db_session.refresh(stock_fund)
        # After deleting -2000, remaining: -10000 → prior_wealth = 10000
        assert stock_fund.prior_wealth_amount == pytest.approx(10000.0)


class TestTransactionsServiceTaggingById:
    """Tests for update_tagging_by_id method."""

    @pytest.mark.parametrize(
        ("table_name", "service_name"),
        [
            (Tables.CREDIT_CARD.value, "credit_cards"),
            (Tables.BANK.value, "banks"),
            (Tables.CASH.value, "cash"),
        ],
    )
    def test_update_tagging_by_table_name(
        self, db_session, seed_base_transactions, table_name, service_name
    ):
        """Verify tagging update by table name lands on the right row."""
        service = TransactionsService(db_session)
        uid = int(service.get_all_transactions(service_name).iloc[0]["unique_id"])

        service.update_tagging_by_id(table_name, uid, "Transport", "Gas")

        updated = service.get_all_transactions(service_name)
        row = updated[updated["unique_id"] == uid].iloc[0]
        assert row["category"] == "Transport"
        assert row["tag"] == "Gas"

    def test_update_tagging_accepts_service_alias(
        self, db_session, seed_base_transactions
    ):
        """The legacy tag endpoint's service spelling (``credit_cards``) dispatches too.

        The endpoint documented ``credit_card``/``bank``/``cash`` while the
        service only matched table names, so a documented value was a 400.
        """
        service = TransactionsService(db_session)
        uid = int(service.get_all_transactions("credit_cards").iloc[0]["unique_id"])

        service.update_tagging_by_id("credit_cards", uid, "Entertainment", "Cinema")

        row = db_session.get(CreditCardTransaction, uid)
        assert (row.category, row.tag) == ("Entertainment", "Cinema")

    def test_update_tagging_invalid_table_raises(self, db_session):
        """Verify ValueError raised for an invalid table name."""
        service = TransactionsService(db_session)
        with pytest.raises(ValueError, match="Invalid table name"):
            service.update_tagging_by_id("nonexistent_table", 1, "Food", "Coffee")


class TestTransactionsServiceDateMethods:
    """Tests for get_latest_data_date and get_earliest_data_date methods."""

    def test_get_latest_data_date_with_data(self, db_session, seed_base_transactions):
        """Verify latest date is the earliest of the populated tables' max dates.

        CC latest: 2024-03-25, bank latest: 2024-03-10, cash latest:
        2024-03-22; manual-investment and insurance tables are empty and
        must not drag the result to a placeholder date.
        """
        service = TransactionsService(db_session)
        assert service.get_latest_data_date() == datetime(2024, 3, 10)

    def test_get_earliest_data_date_with_data(self, db_session, seed_base_transactions):
        """Verify earliest date returns the minimum date across all tables."""
        service = TransactionsService(db_session)
        assert service.get_earliest_data_date() == datetime(2024, 1, 1)

    def test_get_latest_data_date_empty_db(self, db_session):
        """Verify None is returned when no table has any data."""
        service = TransactionsService(db_session)
        assert service.get_latest_data_date() is None

    def test_get_earliest_data_date_empty_db(self, db_session):
        """Verify fallback to current datetime when no data exists."""
        service = TransactionsService(db_session)
        earliest = service.get_earliest_data_date()

        assert isinstance(earliest, datetime)
        assert abs((datetime.now() - earliest).total_seconds()) < 5


class TestTransactionsServiceStaticMethods:
    """Tests for static utility methods on TransactionsService."""

    def test_get_table_columns_for_display(self, db_session):
        """Verify returned column list includes all expected display columns."""
        service = TransactionsService(db_session)
        columns = service.get_table_columns_for_display()

        assert columns == [
            "provider", "account_name", "account_number", "date", "description",
            "amount", "category", "tag", "id", "status", "type", "unique_id",
            "source",
        ]

    @pytest.mark.parametrize(
        ("value", "expected"), [("", None), ("Food", "Food"), (None, None)]
    )
    def test_normalize_empty_string(self, value, expected):
        """Verify empty strings become None and other values pass through."""
        assert TransactionsService._normalize_empty_string(value) is expected or (
            TransactionsService._normalize_empty_string(value) == expected
        )

    def test_update_transaction_empty_updates_returns_false(
        self, db_session, seed_base_transactions
    ):
        """Verify update_transaction returns False when no valid updates provided."""
        service = TransactionsService(db_session)
        unique_id = int(service.get_all_transactions("credit_cards").iloc[0]["unique_id"])

        assert service.update_transaction(
            unique_id, "credit_card_transactions", {}
        ) is False


class TestBuildPriorWealthRowsEmptyData:
    """Tests for early exit paths in prior wealth row builders."""

    def test_build_bank_prior_wealth_rows_empty_balances(self, db_session):
        """Verify empty DataFrame returned when no bank balances exist."""
        result = TransactionsService(db_session)._build_bank_prior_wealth_rows()
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_build_investment_prior_wealth_rows_empty_investments(self, db_session):
        """Verify empty DataFrame returned when no investments exist."""
        result = TransactionsService(db_session)._build_investment_prior_wealth_rows()
        assert isinstance(result, pd.DataFrame)
        assert result.empty


class TestBulkTagTransactionsOptionalFields:
    """Tests for bulk_tag_transactions applying optional fields."""

    def test_bulk_tag_with_description_and_amount(
        self, db_session, seed_base_transactions
    ):
        """Verify bulk_tag applies description and amount for cash transactions."""
        db_session.add(CashBalance(
            account_name="Cash Wallet", balance=0.0, prior_wealth_amount=0.0,
            last_manual_update="2024-01-01",
        ))
        db_session.commit()

        service = TransactionsService(db_session)
        cash_df = service.get_all_transactions("cash")
        uids = [int(cash_df.iloc[0]["unique_id"]), int(cash_df.iloc[1]["unique_id"])]

        service.bulk_tag_transactions(
            transaction_ids=uids, source="cash_transactions", category="Food",
            tag="Bulk", description="Bulk Updated", amount=-99.0,
        )

        updated = service.get_all_transactions("cash")
        for uid in uids:
            row = updated[updated["unique_id"] == uid].iloc[0]
            assert row["category"] == "Food"
            assert row["tag"] == "Bulk"
            assert row["description"] == "Bulk Updated"
            assert row["amount"] == -99.0

    def test_bulk_tag_with_account_name_and_date(
        self, db_session, seed_base_transactions
    ):
        """Verify bulk_tag applies account_name and date for cash transactions."""
        for name in ("Cash Wallet", "New Wallet"):
            db_session.add(CashBalance(
                account_name=name, balance=0.0, prior_wealth_amount=0.0,
                last_manual_update="2024-01-01",
            ))
        db_session.commit()

        service = TransactionsService(db_session)
        uid = int(service.get_all_transactions("cash").iloc[0]["unique_id"])

        service.bulk_tag_transactions(
            transaction_ids=[uid], source="cash_transactions", category="Transport",
            tag="Bus", account_name="New Wallet", date="2024-06-15",
        )

        row = db_session.get(CashTransaction, uid)
        assert (row.tag, row.account_name, row.date) == ("Bus", "New Wallet", "2024-06-15")

    def test_bulk_tag_amount_and_date_dropped_for_scraped_source(
        self, db_session, seed_base_transactions
    ):
        """Scraped rows take the tag but silently keep their amount and date."""
        service = TransactionsService(db_session)
        uid = int(service.get_all_transactions("credit_cards").iloc[0]["unique_id"])
        before = db_session.get(CreditCardTransaction, uid)
        original = (before.amount, before.date, before.description)

        service.bulk_tag_transactions(
            transaction_ids=[uid], source="credit_card_transactions",
            category="Food", tag="Bulk", description="rewritten",
            amount=-1.0, date="2030-01-01",
        )

        db_session.expire_all()
        after = db_session.get(CreditCardTransaction, uid)
        assert (after.category, after.tag) == ("Food", "Bulk")
        assert (after.amount, after.date, after.description) == original

    def test_bulk_tag_with_missing_and_existing_ids(self, db_session, monkeypatch):
        """A missing id is skipped, the existing one is updated, one recalculation runs."""
        from unittest.mock import MagicMock

        from backend.services import cash_balance_service

        recalc = MagicMock()
        monkeypatch.setattr(
            cash_balance_service.CashBalanceService,
            "recalculate_current_balance",
            recalc,
        )
        uid = _add_cash(db_session, category=None, tag=None)
        service = TransactionsService(db_session)

        service.bulk_tag_transactions(
            [99999, uid], "cash_transactions", "Food", "Snacks"
        )

        db_session.expire_all()
        row = db_session.get(CashTransaction, uid)
        assert (row.category, row.tag) == ("Food", "Snacks")
        assert db_session.get(CashTransaction, 99999) is None
        recalc.assert_called_once()
        assert recalc.call_args.args[-1] == "Wallet"


class TestGetUntaggedTransactionsAccountFilter:
    """Tests for get_untagged_transactions with account_number filter for banks."""

    def test_untagged_bank_transactions_filtered_by_account(
        self, db_session, seed_untagged_transactions
    ):
        """Verify untagged bank transactions filtered by account_number."""
        service = TransactionsService(db_session)

        assert not service.get_untagged_transactions("banks").empty
        assert service.get_untagged_transactions(
            "banks", account_number="nonexistent_account"
        ).empty

    def test_untagged_cc_transactions_ignores_account_filter(
        self, db_session, seed_untagged_transactions
    ):
        """Verify account_number filter is ignored for credit card transactions."""
        service = TransactionsService(db_session)
        untagged = service.get_untagged_transactions(
            "credit_cards", account_number="anything"
        )
        assert not untagged.empty


class TestGetTableForAnalysisSplitExpansion:
    """Tests for get_table_for_analysis split transaction expansion and concatenation."""

    def test_split_expansion_replaces_parent_with_slices(self, db_session):
        """A split parent is replaced by exactly its slices, each carrying its split id."""
        parent = CreditCardTransaction(
            id="42", date="2024-02-08", provider="isracard", account_name="Main Card",
            description="Splittable Purchase", amount=-300.0, category=None, tag=None,
            source="credit_card_transactions", type="split_parent", status="completed",
        )
        db_session.add(parent)
        db_session.flush()
        db_session.add_all([
            SplitTransaction(
                transaction_id=parent.unique_id, source="credit_card_transactions",
                amount=-200.0, category="Food", tag="Groceries",
            ),
            SplitTransaction(
                transaction_id=parent.unique_id, source="credit_card_transactions",
                amount=-100.0, category="Home", tag="Cleaning",
            ),
        ])
        db_session.commit()

        result = TransactionsService(db_session).get_table_for_analysis("credit_cards")

        split_id_col = TransactionsTableFields.SPLIT_ID.value
        assert len(result) == 2
        assert set(result["amount"]) == {-200.0, -100.0}
        assert -300.0 not in set(result["amount"])
        assert result[split_id_col].notna().all()
        assert set(result["type"]) == {"split_child"}

    def test_get_table_for_analysis_adds_split_id_column_when_missing(
        self, db_session, seed_base_transactions
    ):
        """Verify split_id column is added (all-NA) when no splits exist."""
        result = TransactionsService(db_session).get_table_for_analysis("credit_cards")

        split_id_col = TransactionsTableFields.SPLIT_ID.value
        assert split_id_col in result.columns
        assert result[split_id_col].isna().all()

    def test_split_children_carry_split_id(
        self, db_session, seed_base_transactions, seed_split_transactions
    ):
        """Every split child carries the id of its slice; unsplit rows carry none."""
        result = TransactionsService(db_session).get_table_for_analysis("credit_cards")

        split_id_col = TransactionsTableFields.SPLIT_ID.value
        children = result[result["type"] == "split_child"]
        assert len(children) == 3
        assert children[split_id_col].notna().all()
        assert result[result["type"] != "split_child"][split_id_col].isna().all()

    def test_include_split_parents_keeps_parent_beside_children(
        self, db_session, seed_split_transactions
    ):
        """``include_split_parents=True`` yields the -300 parent plus its slices.

        The flag used to be dropped on the way to the repository, so the
        audit view was identical to the default view.
        """
        result = TransactionsService(db_session).get_table_for_analysis(
            "credit_cards", include_split_parents=True
        )

        parents = result[result["type"] == "split_parent"]
        children = result[result["type"] == "split_child"]
        assert len(parents) == 1
        assert parents.iloc[0]["amount"] == -300.0
        assert pd.isna(parents.iloc[0][TransactionsTableFields.SPLIT_ID.value])
        assert sorted(children["amount"]) == [-150.0, -100.0, -50.0]

    def test_get_table_for_analysis_empty_table(self, db_session):
        """Verify empty DataFrame returned for table with no transactions."""
        result = TransactionsService(db_session).get_table_for_analysis("credit_cards")
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_splits_from_other_service_not_applied_when_unique_ids_collide(
        self, db_session
    ):
        """Splits for a bank transaction must not attach to a CC transaction that shares the same unique_id.

        unique_id is an autoincrement per-table integer so the same value
        can exist in both bank_transactions and credit_card_transactions. A
        bank split whose transaction_id equals the unique_id of an unrelated
        CC row must not appear in the CC analysis output.
        """
        cc_tx = CreditCardTransaction(
            id="EXT-CC-1", date="2025-08-31", provider="isracard",
            account_name="Main Card", description="FLUGHAFEN BERLIN BRA",
            amount=-15.53, category="USA", tag="other",
            source="credit_card_transactions", type="normal", status="completed",
        )
        db_session.add(cc_tx)
        db_session.flush()
        db_session.add(SplitTransaction(
            transaction_id=cc_tx.unique_id, source="bank_transactions",
            amount=1000.0, category="Bachelorette Party", tag="DJ",
        ))
        db_session.commit()

        result = TransactionsService(db_session).get_table_for_analysis("credit_cards")

        flughafen_rows = result[result["description"] == "FLUGHAFEN BERLIN BRA"]
        assert len(flughafen_rows) == 1
        assert flughafen_rows.iloc[0]["category"] == "USA"
        assert result[result["category"] == "Bachelorette Party"].empty


class TestGetDataForAnalysisSessionCache:
    """get_data_for_analysis memoizes the merged analysis frame per session."""

    def test_second_call_uses_cache(
        self, db_session, seed_base_transactions, monkeypatch
    ):
        """The expensive merge runs once for two identical calls."""
        from backend.services import transactions_service as ts_module

        service = ts_module.TransactionsService(db_session)
        calls = {"n": 0}
        original = ts_module.TransactionsService.get_table_for_analysis

        def counting(self, *args, **kwargs):
            calls["n"] += 1
            return original(self, *args, **kwargs)

        monkeypatch.setattr(
            ts_module.TransactionsService, "get_table_for_analysis", counting
        )

        first = service.get_data_for_analysis()
        second = service.get_data_for_analysis()

        assert calls["n"] == 4  # one pass over the 4 source tables, not two
        pd.testing.assert_frame_equal(
            first.reset_index(drop=True), second.reset_index(drop=True)
        )

    def test_split_parents_variants_cached_separately(
        self, db_session, seed_base_transactions, seed_split_transactions
    ):
        """include_split_parents=True/False must not collide in the cache."""
        service = TransactionsService(db_session)
        without = service.get_data_for_analysis(include_split_parents=False)
        with_parents = service.get_data_for_analysis(include_split_parents=True)

        assert "split_parent" not in set(without["type"])
        assert (with_parents["type"] == "split_parent").sum() == 2
        assert len(with_parents) > len(without)


class TestClearCategoryAndTag:
    """Locks in that empty-string category/tag values clear the fields.

    The service normalises empty strings to None at
    ``_normalize_empty_string``. Routes that wrap this service strip
    ``None`` values via Pydantic ``exclude_none=True``, so the frontend
    must send ``""`` to clear. These tests pin that contract so a future
    refactor cannot silently break the per-row / bulk clear actions.
    """

    def test_update_transaction_clears_category_and_tag_via_empty_string(self, db_session):
        """Empty strings on both fields wipe category and tag to None."""
        service = TransactionsService(db_session)
        uid = _add_bank(db_session, "clear_tag_test_1", -100.0)

        assert service.update_transaction(
            uid, "bank_transactions", {"category": "", "tag": ""}
        ) is True
        refreshed = service.transactions_repository.get_transaction_by_id(
            uid, "bank_transactions"
        )
        assert pd.isna(refreshed.category)
        assert pd.isna(refreshed.tag)

    def test_update_transaction_clears_only_tag_when_only_tag_is_empty(self, db_session):
        """Clearing only the tag preserves the category."""
        service = TransactionsService(db_session)
        uid = _add_bank(db_session, "clear_tag_test_2", -100.0)

        assert service.update_transaction(uid, "bank_transactions", {"tag": ""}) is True
        refreshed = service.transactions_repository.get_transaction_by_id(
            uid, "bank_transactions"
        )
        assert refreshed.category == "Food"
        assert pd.isna(refreshed.tag)

    def test_bulk_tag_transactions_clears_category_and_tag_via_empty_string(self, db_session):
        """Bulk-tag with empty strings clears category and tag on all listed IDs.

        ``bulk_tag_transactions`` runs one ``UPDATE ... WHERE unique_id IN``
        over the filtered updates. ``None`` is dropped by the
        ``if updates.get('category') is not None`` guard; an empty string
        passes the guard and is normalised to None.
        """
        ids = [
            _add_bank(db_session, "bulk_clear_1", -100.0),
            _add_bank(db_session, "bulk_clear_2", -100.0),
        ]
        service = TransactionsService(db_session)

        service.bulk_tag_transactions(ids, "bank_transactions", category="", tag="")

        for uid in ids:
            refreshed = service.transactions_repository.get_transaction_by_id(
                uid, "bank_transactions"
            )
            assert pd.isna(refreshed.category)
            assert pd.isna(refreshed.tag)

    def test_bulk_tag_transactions_with_none_does_not_clear(self, db_session):
        """Regression guard: passing None to the bulk endpoint must NOT clear.

        This documents the asymmetry that motivates sending ``""`` from the
        frontend. If this test ever starts failing (i.e. None DOES clear),
        the frontend implementation needs to be revisited — sending None
        from the UI would suddenly become destructive.
        """
        ids = [
            _add_bank(db_session, "bulk_none_1", -100.0),
            _add_bank(db_session, "bulk_none_2", -100.0),
        ]
        service = TransactionsService(db_session)

        service.bulk_tag_transactions(ids, "bank_transactions", category=None, tag=None)

        for uid in ids:
            refreshed = service.transactions_repository.get_transaction_by_id(
                uid, "bank_transactions"
            )
            assert refreshed.category == "Food"


class TestSplitTransactionValidation:
    """Service-level guards on split_transaction and revert_split."""

    def test_split_rejects_slices_that_do_not_sum_to_parent(self, db_session):
        """Slices off by more than a cent are rejected and nothing is written."""
        uid = _add_cash(db_session, amount=-100.0)
        service = TransactionsService(db_session)

        with pytest.raises(ValidationException, match="sum"):
            service.split_transaction(
                uid, "cash_transactions",
                [{"amount": -60.0, "category": "Food", "tag": None},
                 {"amount": -50.0, "category": "Other", "tag": None}],
            )

        assert db_session.get(CashTransaction, uid).type == "normal"
        assert _split_ids(db_session, uid, "cash_transactions") == []

    def test_split_rejects_empty_slice_list(self, db_session):
        """An empty slice list is rejected before the parent is flipped."""
        uid = _add_cash(db_session)
        service = TransactionsService(db_session)

        with pytest.raises(ValidationException, match="at least one"):
            service.split_transaction(uid, "cash_transactions", [])

        assert db_session.get(CashTransaction, uid).type == "normal"

    def test_split_nonexistent_id_raises_not_found(self, db_session):
        """Splitting an id that does not exist is a 404."""
        with pytest.raises(EntityNotFoundException, match="not found"):
            TransactionsService(db_session).split_transaction(
                99999, "cash_transactions",
                [{"amount": -1.0, "category": "Food", "tag": None}],
            )

    def test_split_unknown_source_raises_value_error(self, db_session):
        """An unknown source is a bad request, not a missing row."""
        with pytest.raises(ValueError, match="Invalid source"):
            TransactionsService(db_session).split_transaction(
                1, "not_a_table",
                [{"amount": -1.0, "category": "Food", "tag": None}],
            )

    def test_revert_split_nonexistent_id_raises_not_found(self, db_session):
        """Reverting an id that does not exist is a 404, not a silent success."""
        with pytest.raises(EntityNotFoundException, match="not found"):
            TransactionsService(db_session).revert_split(99999, "cash_transactions")

    def test_revert_split_on_unsplit_transaction_raises_not_found(self, db_session):
        """Reverting a transaction that was never split is a 404."""
        uid = _add_cash(db_session)
        with pytest.raises(EntityNotFoundException, match="not split"):
            TransactionsService(db_session).revert_split(uid, "cash_transactions")
        assert db_session.get(CashTransaction, uid).type == "normal"


class TestSplitSliceRefundsArePurged:
    """A pending refund marked on a slice must not outlive that slice.

    ``split_transactions`` ids are recycled by SQLite just like transaction
    ids, so a refund left behind attaches itself to whichever slice next
    receives the id — including the replacement slices of a re-split.
    """

    @staticmethod
    def _split_and_mark(db_session) -> tuple[int, int]:
        """Split a cash row and mark its first slice; return (parent uid, slice id)."""
        uid = _add_cash(db_session, amount=-100.0)
        TransactionsService(db_session).split_transaction(
            uid, "cash_transactions",
            [{"amount": -60.0, "category": "Food", "tag": "Groceries"},
             {"amount": -40.0, "category": "Other", "tag": "Misc"}],
        )
        slice_id = _split_ids(db_session, uid, "cash_transactions")[0]
        PendingRefundsService(db_session).mark_as_pending_refund(
            "split", slice_id, "cash_transactions", 60.0
        )
        return uid, slice_id

    def test_purged_on_parent_delete(self, db_session):
        """Deleting the parent removes the slice refund and its month override."""
        uid, slice_id = self._split_and_mark(db_session)
        overrides = BudgetMonthOverrideService(db_session)
        overrides.set_override("split", slice_id, "cash_transactions", 2024, 3)

        TransactionsService(db_session).delete_transaction(uid, "cash_transactions")

        assert PendingRefundsService(db_session).get_all_pending() == []
        assert overrides.get_all() == []

    def test_purged_on_revert_split(self, db_session):
        """Reverting the split removes the slice refund and its month override."""
        uid, slice_id = self._split_and_mark(db_session)
        overrides = BudgetMonthOverrideService(db_session)
        overrides.set_override("split", slice_id, "cash_transactions", 2024, 3)

        TransactionsService(db_session).revert_split(uid, "cash_transactions")

        assert PendingRefundsService(db_session).get_all_pending() == []
        assert overrides.get_all() == []
        assert db_session.get(CashTransaction, uid).type == "normal"

    def test_purged_on_resplit(self, db_session):
        """Re-splitting replaces the slices, so the old slice's refund goes too."""
        uid, _ = self._split_and_mark(db_session)

        TransactionsService(db_session).split_transaction(
            uid, "cash_transactions",
            [{"amount": -100.0, "category": "Food", "tag": "Groceries"}],
        )

        assert PendingRefundsService(db_session).get_all_pending() == []
        assert len(_split_ids(db_session, uid, "cash_transactions")) == 1

    def test_recycled_split_id_does_not_inherit_refund(self, db_session):
        """A new slice that receives a deleted slice's id starts clean."""
        uid, slice_id = self._split_and_mark(db_session)
        TransactionsService(db_session).revert_split(uid, "cash_transactions")

        # SQLite hands the freed id straight back to the next slice.
        TransactionsService(db_session).split_transaction(
            uid, "cash_transactions",
            [{"amount": -100.0, "category": "Food", "tag": "Groceries"}],
        )
        new_ids = _split_ids(db_session, uid, "cash_transactions")
        assert new_ids == [slice_id]

        ids = PendingRefundsService(db_session).get_active_pending_identifiers()
        assert ids["split_ids"] == set()
        # …and the slice can be marked afresh.
        PendingRefundsService(db_session).mark_as_pending_refund(
            "split", slice_id, "cash_transactions", 10.0
        )


class TestDeletePurgesDependentRecords:
    """Records pointing at a deleted transaction must not outlive it.

    ``unique_id`` is a per-table auto-increment and SQLite reuses rowids, so
    an orphan is silently re-adopted by the next transaction created in that
    table — landing it in the wrong budget month or attaching a stranger's
    pending refund.
    """

    def test_pending_refund_is_removed(self, db_session):
        """A pending refund does not survive its source transaction."""
        unique_id = _add_cash(db_session)
        PendingRefundsService(db_session).mark_as_pending_refund(
            "transaction", unique_id, "cash", 50.0
        )

        TransactionsService(db_session).delete_transaction(
            unique_id, "cash_transactions"
        )

        assert PendingRefundsService(db_session).get_all_pending() == []

    def test_budget_month_override_is_removed(self, db_session):
        """A budget month override does not survive its transaction."""
        unique_id = _add_cash(db_session)
        service = BudgetMonthOverrideService(db_session)
        service.set_override("transaction", unique_id, "cash_transactions", 2024, 3)

        TransactionsService(db_session).delete_transaction(
            unique_id, "cash_transactions"
        )

        assert service.get_all() == []

    def test_splits_are_removed(self, db_session):
        """Split children do not survive their parent transaction."""
        unique_id = _add_cash(db_session)
        service = TransactionsService(db_session)
        service.split_transaction(
            unique_id, "cash_transactions",
            [{"amount": -60.0, "category": "Food", "tag": "Groceries"},
             {"amount": -40.0, "category": "Other", "tag": "Misc"}],
        )

        service.delete_transaction(unique_id, "cash_transactions")

        assert SplitTransactionsRepository(db_session).get_data().empty

    def test_purge_is_scoped_to_the_source_table(self, db_session):
        """Deleting cash #N leaves bank #N's split and refund intact.

        Both tables start their auto-increment at 1, so the two rows share
        the integer; only the (table, id) pair identifies a transaction.
        """
        cash_uid = _add_cash(db_session, amount=-100.0)
        bank_uid = _add_bank(db_session, "bank-collide", -100.0)
        assert cash_uid == bank_uid
        service = TransactionsService(db_session)
        service.split_transaction(
            bank_uid, "bank_transactions",
            [{"amount": -70.0, "category": "Food", "tag": None},
             {"amount": -30.0, "category": "Other", "tag": None}],
        )
        PendingRefundsService(db_session).mark_as_pending_refund(
            "transaction", bank_uid, "bank_transactions", 40.0
        )

        service.delete_transaction(cash_uid, "cash_transactions")

        assert len(_split_ids(db_session, bank_uid, "bank_transactions")) == 2
        assert db_session.get(BankTransaction, bank_uid).type == "split_parent"
        pending = PendingRefundsService(db_session).get_all_pending()
        assert [(p["source_table"], p["source_id"]) for p in pending] == [
            ("bank_transactions", bank_uid)
        ]


class TestDeleteAccountData:
    """delete_account_data wipes one account's rows and everything hanging off them."""

    def _seed_two_accounts(self, db_session) -> dict:
        """Seed account A (to be deleted) with dependents and account B (kept)."""
        a_split = _add_bank(db_session, "a-split", -100.0, date="2024-01-10")
        a_refund_src = _add_bank(db_session, "a-refund-source", -80.0, date="2024-01-12")
        a_refund_link = _add_bank(db_session, "a-refund-link", 50.0, date="2024-01-20")
        a_override = _add_bank(db_session, "a-override", -50.0, date="2024-01-25")
        b_kept = _add_bank(
            db_session, "b-kept", -40.0, date="2024-01-11", account_name="Other"
        )
        b_refund = _add_bank(
            db_session, "b-refund", -20.0, date="2024-01-13", account_name="Other"
        )

        tx_service = TransactionsService(db_session)
        tx_service.split_transaction(
            a_split, "bank_transactions",
            [{"amount": -60.0, "category": "Food", "tag": None},
             {"amount": -40.0, "category": "Other", "tag": None}],
        )
        a_slice = _split_ids(db_session, a_split, "bank_transactions")[0]
        tx_service.split_transaction(
            b_kept, "bank_transactions",
            [{"amount": -40.0, "category": "Food", "tag": None}],
        )

        refunds = PendingRefundsService(db_session)
        a_pending = refunds.mark_as_pending_refund(
            "transaction", a_refund_src, "bank_transactions", 30.0
        )
        refunds.link_refund(a_pending["id"], a_refund_link, "bank_transactions", 30.0)
        refunds.set_source_note("bank_transactions", a_refund_link, "store credit")
        refunds.mark_as_pending_refund("split", a_slice, "bank_transactions", 10.0)
        b_pending = refunds.mark_as_pending_refund(
            "transaction", b_refund, "bank_transactions", 20.0
        )
        # B's refund is funded by an A transaction: the link must go, B's
        # pending refund must stay.
        refunds.link_refund(b_pending["id"], a_refund_link, "bank_transactions", 20.0)
        overrides = BudgetMonthOverrideService(db_session)
        overrides.set_override("transaction", a_override, "bank_transactions", 2024, 2)
        overrides.set_override("split", a_slice, "bank_transactions", 2024, 2)
        overrides.set_override("transaction", b_kept, "bank_transactions", 2024, 2)

        return {
            "a_ids": [a_split, a_refund_src, a_refund_link, a_override],
            "b_kept": b_kept,
            "b_refund": b_refund,
            "b_pending_id": b_pending["id"],
        }

    @pytest.mark.parametrize("service_name", ["banks", "bank_transactions"])
    def test_only_account_a_and_its_dependents_are_gone(self, db_session, service_name):
        """Account A's rows, splits, refunds, links, notes and overrides go; B's stay."""
        seeded = self._seed_two_accounts(db_session)
        refunds = PendingRefundsService(db_session)
        overrides = BudgetMonthOverrideService(db_session)

        result = TransactionsService(db_session).delete_account_data(
            service_name, "hapoalim", "Checking"
        )

        assert result == {"transactions_deleted": 4}
        remaining = {t.id for t in db_session.query(BankTransaction).all()}
        assert remaining == {"b-kept", "b-refund"}

        splits = SplitTransactionsRepository(db_session).get_data()
        assert splits["transaction_id"].tolist() == [seeded["b_kept"]]

        pending = refunds.get_all_pending()
        assert [p["id"] for p in pending] == [seeded["b_pending_id"]]
        assert refunds.repo.get_all_links().empty
        assert refunds.repo.get_all_source_notes().empty

        assert [(o["source_type"], o["source_id"]) for o in overrides.get_all()] == [
            ("transaction", seeded["b_kept"])
        ]

    def test_unknown_service_raises(self, db_session):
        """An unknown service name is rejected before anything is touched."""
        with pytest.raises(ValueError, match="Unknown service"):
            TransactionsService(db_session).delete_account_data(
                "not_a_service", "hapoalim", "Checking"
            )

    def test_account_without_rows_deletes_nothing(self, db_session):
        """An account with no transactions reports zero deletions."""
        _add_bank(db_session, "other", -10.0, account_name="Other")

        result = TransactionsService(db_session).delete_account_data(
            "banks", "hapoalim", "Checking"
        )

        assert result == {"transactions_deleted": 0}
        assert db_session.query(BankTransaction).count() == 1
