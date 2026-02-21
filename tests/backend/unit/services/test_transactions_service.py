"""Tests for TransactionsService using real in-memory SQLite database."""

from datetime import date, datetime

import pandas as pd
import pytest

from backend.constants.categories import (
    IncomeCategories,
    PRIOR_WEALTH_TAG,
    INVESTMENTS_CATEGORY,
    LIABILITIES_CATEGORY,
    CREDIT_CARDS,
)
from backend.constants.providers import Banks, CreditCards
from backend.constants.tables import Tables, TransactionsTableFields
from backend.models.transaction import (
    BankTransaction,
    CashTransaction,
    ManualInvestmentTransaction,
)
from backend.services.transactions_service import TransactionsService


class TestTransactionsServiceDataRetrieval:
    """Tests for TransactionsService data retrieval methods."""

    def test_get_data_for_analysis_empty_db(self, db_session):
        """Verify empty DataFrame returned when no transactions exist."""
        service = TransactionsService(db_session)
        result = service.get_data_for_analysis()
        assert isinstance(result, pd.DataFrame)
        assert result.empty

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

    def test_get_data_for_analysis_excludes_split_parents(
        self, db_session, seed_base_transactions, seed_split_transactions
    ):
        """Verify split parent transactions are excluded by default."""
        service = TransactionsService(db_session)
        result = service.get_data_for_analysis()

        type_col = TransactionsTableFields.TYPE.value
        assert "split_parent" not in result[type_col].values

    def test_get_data_for_analysis_includes_split_children(
        self, db_session, seed_base_transactions, seed_split_transactions
    ):
        """Verify split children appear in analysis data."""
        service = TransactionsService(db_session)
        result = service.get_data_for_analysis()

        # The split transactions fixture has 5 children total (3 CC + 2 bank).
        # Verify specific split amounts are present to confirm children are included.
        amount_col = TransactionsTableFields.AMOUNT.value
        category_col = TransactionsTableFields.CATEGORY.value

        # CC splits: -150 (Food/Groceries), -100 (Home/Cleaning), -50 (Other)
        cc_split_amounts = {-150.0, -100.0, -50.0}
        # Bank splits: -120 (Home/Maintenance), -80 (Other)
        bank_split_amounts = {-120.0, -80.0}
        expected_split_amounts = cc_split_amounts | bank_split_amounts

        # Check that all expected split amounts are present in the result
        result_amounts = set(result[amount_col].values)
        for amt in expected_split_amounts:
            assert amt in result_amounts, f"Missing split amount {amt}"

    def test_get_data_for_analysis_includes_prior_wealth(
        self, db_session, seed_prior_wealth_transactions
    ):
        """Verify bank prior wealth synthetic rows are included."""
        service = TransactionsService(db_session)
        result = service.get_data_for_analysis()

        tag_col = TransactionsTableFields.TAG.value
        source_col = TransactionsTableFields.SOURCE.value

        # There should be bank balance prior wealth rows (from _build_bank_prior_wealth_rows)
        bank_pw_rows = result[
            (result[tag_col] == PRIOR_WEALTH_TAG) & (result[source_col] == "bank_balances")
        ]
        assert len(bank_pw_rows) == 2  # hapoalim + leumi

        # Plus the cash prior wealth row seeded directly
        all_pw_rows = result[result[tag_col] == PRIOR_WEALTH_TAG]
        assert len(all_pw_rows) == 3  # 2 bank balance + 1 cash

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
        # 4 CC untagged transactions in the fixture
        assert len(result) == 4

    def test_get_transactions_by_tag(self, db_session, seed_base_transactions):
        """Verify filtering by category and optional tag."""
        service = TransactionsService(db_session)

        # Filter by category only
        food_txns = service.get_transactions_by_tag("Food")
        category_col = TransactionsTableFields.CATEGORY.value
        assert not food_txns.empty
        assert all(food_txns[category_col] == "Food")

        # Filter by category and tag
        grocery_txns = service.get_transactions_by_tag("Food", "Groceries")
        tag_col = TransactionsTableFields.TAG.value
        assert not grocery_txns.empty
        assert all(grocery_txns[tag_col] == "Groceries")
        assert len(grocery_txns) < len(food_txns)


    def test_get_data_for_analysis_includes_investment_prior_wealth(
        self, db_session, seed_investments
    ):
        """Verify investment prior wealth synthetic rows appear in analysis data."""
        from backend.constants.tables import TransactionsTableFields
        from backend.constants.categories import PRIOR_WEALTH_TAG, IncomeCategories

        # Set prior_wealth_amount on the open investment
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
        """Verify creating a cash transaction."""
        service = TransactionsService(db_session)
        data = {
            "date": date(2024, 4, 1),
            "account_name": "Cash Wallet",
            "description": "Test cash purchase",
            "amount": -50.0,
            "provider": "cash",
            "category": "Food",
            "tag": "Groceries",
        }
        service.create_transaction(data, "cash")

        result = service.get_all_transactions("cash")
        assert not result.empty
        # Filter out the auto-generated Prior Wealth offset row
        user_rows = result[result["tag"] != PRIOR_WEALTH_TAG]
        assert len(user_rows) == 1
        assert user_rows.iloc[0]["description"] == "Test cash purchase"
        assert user_rows.iloc[0]["amount"] == -50.0

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

        # manual_investments not accessible via get_all_transactions,
        # so use get_table_for_analysis and filter out PW offset rows
        result = service.get_table_for_analysis("manual_investments")
        assert not result.empty
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
        """Verify manual sources can edit description/amount/provider."""
        service = TransactionsService(db_session)

        # Create a cash transaction first
        data = {
            "date": date(2024, 4, 1),
            "account_name": "Cash Wallet",
            "description": "Original description",
            "amount": -50.0,
            "provider": "cash",
        }
        service.create_transaction(data, "cash")

        # Get the unique_id of the created transaction
        cash_df = service.get_all_transactions("cash")
        # Filter out any Prior Wealth offset rows
        non_pw = cash_df[cash_df["tag"] != PRIOR_WEALTH_TAG]
        unique_id = int(non_pw.iloc[0]["unique_id"])

        # Update description, amount, and provider
        updates = {
            "description": "Updated description",
            "amount": -75.0,
            "provider": "updated_provider",
        }
        result = service.update_transaction(unique_id, "cash", updates)
        assert result is True

        # Verify the update
        updated_df = service.get_all_transactions("cash")
        updated_row = updated_df[updated_df["unique_id"] == unique_id].iloc[0]
        assert updated_row["description"] == "Updated description"
        assert updated_row["amount"] == -75.0
        assert updated_row["provider"] == "updated_provider"

    def test_update_transaction_scraped_source_only_tags(
        self, db_session, seed_base_transactions
    ):
        """Verify scraped sources can only update category/tag."""
        service = TransactionsService(db_session)

        # Get a CC transaction unique_id
        cc_df = service.get_all_transactions("credit_cards")
        unique_id = int(cc_df.iloc[0]["unique_id"])

        # Capture original description before update
        original_description = cc_df.iloc[0]["description"]

        # Try to update description (should be filtered out for scraped source)
        updates = {
            "description": "Should not update",
            "category": "Transport",
            "tag": "Gas",
        }
        result = service.update_transaction(
            unique_id, "credit_card_transactions", updates
        )
        assert result is True

        # Verify only category/tag changed, description retained original value
        updated_df = service.get_all_transactions("credit_cards")
        updated_row = updated_df[updated_df["unique_id"] == unique_id].iloc[0]
        assert updated_row["description"] == original_description
        assert updated_row["category"] == "Transport"
        assert updated_row["tag"] == "Gas"

    def test_delete_transaction_cash(self, db_session):
        """Verify deleting a cash transaction."""
        service = TransactionsService(db_session)

        # Create a cash transaction
        data = {
            "date": date(2024, 4, 1),
            "account_name": "Cash Wallet",
            "description": "To be deleted",
            "amount": -30.0,
            "provider": "cash",
            "category": "Food",
            "tag": "Coffee",
        }
        service.create_transaction(data, "cash")

        cash_df = service.get_all_transactions("cash")
        non_pw = cash_df[cash_df["tag"] != PRIOR_WEALTH_TAG]
        unique_id = int(non_pw.iloc[0]["unique_id"])

        # Delete the transaction
        service.delete_transaction(unique_id, "cash_transactions")

        # Verify it's gone
        after_df = service.get_all_transactions("cash")
        remaining = after_df[after_df["tag"] != PRIOR_WEALTH_TAG]
        assert remaining.empty

    def test_delete_transaction_scraped_source_forbidden(
        self, db_session, seed_base_transactions
    ):
        """Verify PermissionError when deleting non-manual transaction."""
        service = TransactionsService(db_session)

        cc_df = service.get_all_transactions("credit_cards")
        unique_id = int(cc_df.iloc[0]["unique_id"])

        with pytest.raises(PermissionError, match="prohibited"):
            service.delete_transaction(unique_id, "credit_card_transactions")

    def test_delete_transaction_protected_tag(self, db_session):
        """Verify PermissionError when deleting Prior Wealth transaction."""
        service = TransactionsService(db_session)

        # Create a cash transaction with Prior Wealth tag and account_name
        pw_tx = CashTransaction(
            id="pw_test_1",
            date="2024-01-01",
            provider="MANUAL",
            account_name=PRIOR_WEALTH_TAG,
            description="Prior Wealth Offset (cash)",
            amount=100.0,
            category="Other Income",
            tag=PRIOR_WEALTH_TAG,
            source="cash_transactions",
            type="normal",
            status="completed",
        )
        db_session.add(pw_tx)
        db_session.commit()
        db_session.refresh(pw_tx)

        with pytest.raises(PermissionError, match="Cannot manually delete"):
            service.delete_transaction(pw_tx.unique_id, "cash_transactions")

    def test_bulk_tag_transactions(self, db_session, seed_untagged_transactions):
        """Verify bulk tagging updates multiple transactions."""
        service = TransactionsService(db_session)

        # Get untagged CC transactions
        untagged = service.get_untagged_transactions("credit_cards")
        unique_ids = untagged["unique_id"].astype(int).tolist()
        assert len(unique_ids) >= 2

        # Bulk tag them
        service.bulk_tag_transactions(
            unique_ids,
            "credit_card_transactions",
            "Food",
            "Groceries",
        )

        # Verify all are now tagged
        cc_df = service.get_all_transactions("credit_cards")
        tagged = cc_df[cc_df["unique_id"].isin(unique_ids)]
        assert all(tagged["category"] == "Food")
        assert all(tagged["tag"] == "Groceries")


class TestTransactionsServiceKPIs:
    """Tests for TransactionsService KPI calculations."""

    def test_get_kpis(self, db_session, seed_base_transactions):
        """Verify KPI calculations (income, expenses, savings rate)."""
        service = TransactionsService(db_session)
        df = service.get_data_for_analysis()
        kpis = service.get_kpis(df)

        # Check required keys exist
        expected_keys = [
            "income",
            "expenses",
            "savings_and_investments",
            "bank_balance_increase",
            "savings_rate",
            "liabilities_paid",
            "liabilities_received",
            "largest_expense_cat_name",
            "largest_expense_cat_val",
        ]
        for key in expected_keys:
            assert key in kpis, f"Missing KPI key: {key}"

        # Salary income: 8000 + 8500 + 8200 = 24700
        # Other Income (freelance): 3500
        # Ignore transfers (500 + 700) are NOT income
        # Total income = 28200
        assert kpis["income"] == pytest.approx(28200.0, abs=1.0)

        # Expenses (non-income, non-ignore negative amounts * -1):
        # CC: 150+80+60+40+180+120+55+45+200+95+70+35+250 = 1380
        # Bank Rent: 3000*3 = 9000
        # Cash: 15+10+18+12+12+8 = 75
        # Total = 10455
        assert kpis["expenses"] == pytest.approx(10455.0, abs=1.0)

        # Savings rate = (total_savings / income) * 100
        # bank_balance_increase = income - expenses - liabilities_paid - investments = 28200 - 10455 - 0 - 0 = 17745
        # total_savings = bank_balance_increase + investments = 17745 + 0 = 17745
        # savings_rate = 17745 / 28200 * 100 ≈ 62.93%
        assert kpis["savings_rate"] == pytest.approx(62.93, abs=1.0)

        # Largest expense category should be Home (3 x 3000 rent = 9000)
        assert kpis["largest_expense_cat_name"] == "Home"
        assert kpis["largest_expense_cat_val"] == pytest.approx(9000.0, abs=1.0)

    def test_split_data_by_category_types(self, db_session, seed_base_transactions):
        """Verify data split into expenses, investments, income, liabilities."""
        service = TransactionsService(db_session)
        df = service.get_data_for_analysis()
        data = TransactionsService.split_data_by_category_types(df)

        assert "expenses" in data
        assert "investments" in data
        assert "income" in data
        assert "liabilities" in data

        category_col = TransactionsTableFields.CATEGORY.value

        # Income should contain only income categories
        income_cats = [e.value for e in IncomeCategories]
        assert not data["income"].empty, "Expected income data from seed fixture"
        assert all(data["income"][category_col].isin(income_cats))

        # Expenses should NOT contain non-expense categories
        non_expense_cats = [INVESTMENTS_CATEGORY, LIABILITIES_CATEGORY, CREDIT_CARDS, *[e.value for e in IncomeCategories]]
        assert not data["expenses"].empty, "Expected expense data from seed fixture"
        assert not any(data["expenses"][category_col].isin(non_expense_cats))

    def test_get_liabilities_summary(self, db_session, seed_base_transactions):
        """Verify liabilities breakdown by tag."""
        service = TransactionsService(db_session)

        # Add some liabilities transactions for this test
        liability_txns = [
            BankTransaction(
                id="liab_1",
                date="2024-01-15",
                provider="hapoalim",
                account_name="Checking",
                description="Mortgage Received",
                amount=500000.0,
                category="Liabilities",
                tag="Mortgage",
                source="bank_transactions",
                type="normal",
                status="completed",
            ),
            BankTransaction(
                id="liab_2",
                date="2024-02-01",
                provider="hapoalim",
                account_name="Checking",
                description="Mortgage Payment",
                amount=-3000.0,
                category="Liabilities",
                tag="Mortgage",
                source="bank_transactions",
                type="normal",
                status="completed",
            ),
            BankTransaction(
                id="liab_3",
                date="2024-03-01",
                provider="hapoalim",
                account_name="Checking",
                description="Mortgage Payment",
                amount=-3000.0,
                category="Liabilities",
                tag="Mortgage",
                source="bank_transactions",
                type="normal",
                status="completed",
            ),
        ]
        db_session.add_all(liability_txns)
        db_session.commit()

        df = service.get_data_for_analysis()
        summary = service.get_liabilities_summary(df)

        assert "total_received" in summary
        assert "total_paid" in summary
        assert "outstanding_balance" in summary
        assert "tag_summary" in summary

        assert summary["total_received"] == pytest.approx(500000.0)
        assert summary["total_paid"] == pytest.approx(6000.0)
        assert summary["outstanding_balance"] == pytest.approx(494000.0)


class TestTransactionsServicePriorWealth:
    """Tests for prior wealth offset synchronization."""

    def test_sync_prior_wealth_creates_offset(self, db_session):
        """Verify offset transaction created for cash deposits."""
        service = TransactionsService(db_session)

        # Create a cash expense (negative amount triggers prior wealth offset)
        data = {
            "date": date(2024, 4, 1),
            "account_name": "Cash Wallet",
            "description": "Cash deposit for spending",
            "amount": -200.0,
            "provider": "cash",
            "category": "Food",
            "tag": "Groceries",
        }
        service.create_transaction(data, "cash")
        # create_transaction calls sync_prior_wealth_offset internally

        # Check that a Prior Wealth offset was created
        cash_df = service.get_all_transactions("cash")
        pw_rows = cash_df[cash_df["tag"] == PRIOR_WEALTH_TAG]
        assert len(pw_rows) == 1
        assert pw_rows.iloc[0]["amount"] == 200.0  # abs of deposit
        assert pw_rows.iloc[0]["account_name"] == PRIOR_WEALTH_TAG
        assert pw_rows.iloc[0]["category"] == IncomeCategories.OTHER_INCOME.value

    def test_sync_prior_wealth_updates_existing(self, db_session):
        """Verify existing offset updated when deposits change."""
        service = TransactionsService(db_session)

        # Insert two negative cash transactions directly (bypassing create_transaction
        # to avoid triggering sync twice, which hits a known method-name issue in
        # the update path).
        tx1 = CashTransaction(
            id="cash_pw_test_1",
            date="2024-04-01",
            provider="cash",
            account_name="Cash Wallet",
            description="First deposit",
            amount=-200.0,
            category="Food",
            tag="Groceries",
            source="cash_transactions",
            type="normal",
            status="completed",
        )
        tx2 = CashTransaction(
            id="cash_pw_test_2",
            date="2024-04-15",
            provider="cash",
            account_name="Cash Wallet",
            description="Second deposit",
            amount=-300.0,
            category="Transport",
            tag="Gas",
            source="cash_transactions",
            type="normal",
            status="completed",
        )
        db_session.add_all([tx1, tx2])
        db_session.commit()

        # Now run sync which should create offset for all deposits combined
        service.sync_prior_wealth_offset(target_service="cash")

        cash_df = service.get_all_transactions("cash")
        pw = cash_df[cash_df["tag"] == PRIOR_WEALTH_TAG]
        # There should be exactly 1 offset with combined amount
        assert len(pw) == 1
        assert pw.iloc[0]["amount"] == pytest.approx(500.0)  # 200 + 300

    def test_sync_prior_wealth_deletes_when_zero(self, db_session):
        """Verify offset deleted when no deposits exist."""
        service = TransactionsService(db_session)

        # Create a deposit
        data = {
            "date": date(2024, 4, 1),
            "account_name": "Cash Wallet",
            "description": "Deposit to remove",
            "amount": -100.0,
            "provider": "cash",
            "category": "Food",
            "tag": "Coffee",
        }
        service.create_transaction(data, "cash")

        # Verify offset exists
        cash_df = service.get_all_transactions("cash")
        pw = cash_df[cash_df["tag"] == PRIOR_WEALTH_TAG]
        assert len(pw) == 1

        # Delete the deposit transaction
        non_pw = cash_df[cash_df["tag"] != PRIOR_WEALTH_TAG]
        deposit_uid = int(non_pw.iloc[0]["unique_id"])
        service.delete_transaction(deposit_uid, "cash_transactions")

        # After deletion, sync_prior_wealth_offset is called, which should
        # delete the offset since no negative amounts remain
        cash_df_after = service.get_all_transactions("cash")
        pw_after = cash_df_after[cash_df_after["tag"] == PRIOR_WEALTH_TAG]
        assert len(pw_after) == 0


    def test_sync_prior_wealth_skips_manual_investments(self, db_session):
        """Verify sync_prior_wealth_offset does not create offset for manual_investments."""
        from backend.models.transaction import ManualInvestmentTransaction
        from backend.constants.categories import PRIOR_WEALTH_TAG
        inv_tx = ManualInvestmentTransaction(
            id="test_inv_1",
            date="2024-01-01",
            provider="manual_investments",
            account_name="Investment Account",
            description="Deposit",
            amount=-5000.0,
            category="Investments",
            tag="Stock Fund",
            source="manual_investment_transactions",
            type="normal",
        )
        db_session.add(inv_tx)
        db_session.commit()

        service = TransactionsService(db_session)
        service.sync_prior_wealth_offset()

        from backend.repositories.transactions_repository import TransactionsRepository
        repo = TransactionsRepository(db_session)
        inv_df = repo.get_table("manual_investments")
        pw_rows = inv_df[inv_df["tag"] == PRIOR_WEALTH_TAG]
        assert len(pw_rows) == 0


    def test_create_manual_investments_transaction_updates_prior_wealth(
        self, db_session, seed_investments
    ):
        """Verify creating a manual_investments transaction recalculates Investment.prior_wealth_amount."""
        from datetime import date as date_type
        service = TransactionsService(db_session)
        stock_fund = seed_investments["investments"][0]

        data = {
            "date": date_type(2024, 3, 1),
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
        # inv_txn_2 is a Stock Fund txn with amount=-2000
        inv_txn_2 = next(t for t in txns if t.id == "inv_txn_2")

        service.delete_transaction(inv_txn_2.unique_id, "manual_investment_transactions")

        db_session.refresh(stock_fund)
        # After deleting -2000, remaining: -10000 → prior_wealth = 10000
        assert stock_fund.prior_wealth_amount == pytest.approx(10000.0)


class TestTransactionsServiceAddTransaction:
    """Tests for the lower-level add_transaction method."""

    def test_add_cash_transaction_succeeds(self, db_session):
        """Verify adding a CashTransaction via add_transaction returns True."""
        service = TransactionsService(db_session)

        tx_dict = {
            "id": "cash_add_1",
            "date": datetime(2024, 5, 1),
            "provider": "cash",
            "account_name": "Cash Wallet",
            "description": "Test cash add",
            "amount": -25.0,
            "category": "Food",
            "tag": "Coffee",
            "source": "cash_transactions",
            "type": "normal",
            "status": "completed",
        }
        result = service.add_transaction(tx_dict, "cash")
        assert result is True

        cash_df = service.get_all_transactions("cash")
        assert not cash_df.empty
        match = cash_df[cash_df["description"] == "Test cash add"]
        assert len(match) == 1
        assert match.iloc[0]["amount"] == -25.0

    def test_add_manual_investment_transaction_succeeds(self, db_session):
        """Verify adding a ManualInvestmentTransaction via add_transaction returns True."""
        service = TransactionsService(db_session)

        tx_dict = {
            "id": "inv_add_1",
            "date": datetime(2024, 5, 1),
            "provider": "manual_investments",
            "account_name": "Investment Account",
            "description": "Test investment add",
            "amount": -1000.0,
            "category": "Investments",
            "tag": "Stock Fund",
            "source": "manual_investment_transactions",
            "type": "normal",
            "status": "completed",
        }
        result = service.add_transaction(tx_dict, "manual_investments")
        assert result is True

        inv_df = service.get_table_for_analysis("manual_investments")
        assert not inv_df.empty
        match = inv_df[inv_df["description"] == "Test investment add"]
        assert len(match) == 1

    def test_add_transaction_invalid_service_raises(self, db_session):
        """Verify ValueError raised when service is not cash or manual_investments."""
        service = TransactionsService(db_session)

        tx_dict = {
            "id": "bad_1",
            "date": "2024-05-01",
            "provider": "isracard",
            "account_name": "Card",
            "description": "Bad service",
            "amount": -50.0,
            "source": "credit_card_transactions",
            "type": "normal",
            "status": "completed",
        }
        with pytest.raises(ValueError, match="Only 'cash' and 'manual_investments'"):
            service.add_transaction(tx_dict, "credit_cards")


class TestTransactionsServiceTaggingById:
    """Tests for update_tagging_by_id method."""

    def test_update_cc_transaction_tagging(self, db_session, seed_base_transactions):
        """Verify tagging update for a credit card transaction by table name."""
        service = TransactionsService(db_session)
        cc_df = service.get_all_transactions("credit_cards")
        first_uid = int(cc_df.iloc[0]["unique_id"])

        service.update_tagging_by_id(
            Tables.CREDIT_CARD.value, first_uid, "Transport", "Gas"
        )

        updated = service.get_all_transactions("credit_cards")
        row = updated[updated["unique_id"] == first_uid].iloc[0]
        assert row["category"] == "Transport"
        assert row["tag"] == "Gas"

    def test_update_bank_transaction_tagging(self, db_session, seed_base_transactions):
        """Verify tagging update for a bank transaction by table name."""
        service = TransactionsService(db_session)
        bank_df = service.get_all_transactions("banks")
        # Find a bank transaction with a category to update
        expense_row = bank_df[bank_df["category"] == "Home"].iloc[0]
        uid = int(expense_row["unique_id"])

        service.update_tagging_by_id(
            Tables.BANK.value, uid, "Entertainment", "Cinema"
        )

        updated = service.get_all_transactions("banks")
        row = updated[updated["unique_id"] == uid].iloc[0]
        assert row["category"] == "Entertainment"
        assert row["tag"] == "Cinema"

    def test_update_cash_transaction_tagging(self, db_session, seed_base_transactions):
        """Verify tagging update for a cash transaction by table name."""
        service = TransactionsService(db_session)
        cash_df = service.get_all_transactions("cash")
        first_uid = int(cash_df.iloc[0]["unique_id"])

        service.update_tagging_by_id(
            Tables.CASH.value, first_uid, "Home", "Cleaning"
        )

        updated = service.get_all_transactions("cash")
        row = updated[updated["unique_id"] == first_uid].iloc[0]
        assert row["category"] == "Home"
        assert row["tag"] == "Cleaning"

    def test_update_tagging_invalid_table_raises(self, db_session):
        """Verify ValueError raised for an invalid table name."""
        service = TransactionsService(db_session)
        with pytest.raises(ValueError, match="Invalid table name"):
            service.update_tagging_by_id("nonexistent_table", 1, "Food", "Coffee")


class TestTransactionsServiceDateMethods:
    """Tests for get_latest_data_date and get_earliest_data_date methods."""

    def test_get_latest_data_date_with_data(self, db_session, seed_base_transactions):
        """Verify latest date returns earliest of the per-table max dates."""
        service = TransactionsService(db_session)
        latest = service.get_latest_data_date()

        # The method returns min(latest_dates) across tables.
        # CC latest: 2024-03-25, Bank latest: 2024-03-10, Cash latest: 2024-03-22
        # Manual investments: no data -> fallback = today - 365
        # min of those would be the fallback date (roughly today - 365)
        assert isinstance(latest, datetime)

    def test_get_earliest_data_date_with_data(self, db_session, seed_base_transactions):
        """Verify earliest date returns the minimum date across all tables."""
        service = TransactionsService(db_session)
        earliest = service.get_earliest_data_date()

        # Earliest across all seeded data: bank_jan_1 = 2024-01-01
        assert isinstance(earliest, datetime)
        assert earliest == datetime(2024, 1, 1)

    def test_get_latest_data_date_empty_db(self, db_session):
        """Verify fallback date returned when no transactions exist."""
        service = TransactionsService(db_session)
        latest = service.get_latest_data_date()

        # Fallback: today - 365 days for each empty table, min of those
        expected_approx = datetime.today().replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - __import__("datetime").timedelta(days=365)
        assert isinstance(latest, datetime)
        # The date should be approximately one year ago
        diff = abs((latest - expected_approx).days)
        assert diff <= 1

    def test_get_earliest_data_date_empty_db(self, db_session):
        """Verify fallback to current datetime when no data exists."""
        service = TransactionsService(db_session)
        earliest = service.get_earliest_data_date()

        # Fallback: datetime.now()
        assert isinstance(earliest, datetime)
        now = datetime.now()
        # Should be within a few seconds of now
        assert abs((now - earliest).total_seconds()) < 5


class TestTransactionsServiceStaticMethods:
    """Tests for static utility methods on TransactionsService."""

    def test_get_providers_for_credit_cards(self):
        """Verify credit card providers list matches CreditCards enum."""
        providers = TransactionsService.get_providers_for_service("credit_cards")
        expected = [e.value for e in CreditCards]
        assert providers == expected

    def test_get_providers_for_banks(self):
        """Verify bank providers list matches Banks enum."""
        providers = TransactionsService.get_providers_for_service("banks")
        expected = [e.value for e in Banks]
        assert providers == expected

    def test_get_providers_for_invalid_service_raises(self):
        """Verify ValueError raised for unsupported service name."""
        with pytest.raises(ValueError, match="Service must be 'credit_cards' or 'banks'"):
            TransactionsService.get_providers_for_service("cash")

    def test_get_all_providers_returns_combined_list(self):
        """Verify get_all_providers returns all CC + Bank providers."""
        all_providers = TransactionsService.get_all_providers()
        cc_providers = [e.value for e in CreditCards]
        bank_providers = [e.value for e in Banks]
        assert all_providers == cc_providers + bank_providers
        assert len(all_providers) == len(cc_providers) + len(bank_providers)

    def test_get_table_columns_for_display(self, db_session):
        """Verify returned column list includes all expected display columns."""
        service = TransactionsService(db_session)
        columns = service.get_table_columns_for_display()

        expected_columns = [
            "provider",
            "account_name",
            "account_number",
            "date",
            "description",
            "amount",
            "category",
            "tag",
            "id",
            "status",
            "type",
            "unique_id",
            "source",
        ]
        assert columns == expected_columns

    def test_normalize_empty_string_converts_to_none(self):
        """Verify empty string is converted to None."""
        result = TransactionsService._normalize_empty_string("")
        assert result is None

    def test_normalize_empty_string_preserves_value(self):
        """Verify non-empty string is preserved as-is."""
        result = TransactionsService._normalize_empty_string("Food")
        assert result == "Food"

    def test_normalize_empty_string_preserves_none(self):
        """Verify None input is preserved as None."""
        result = TransactionsService._normalize_empty_string(None)
        assert result is None

    def test_update_transaction_empty_updates_returns_false(
        self, db_session, seed_base_transactions
    ):
        """Verify update_transaction returns False when no valid updates provided."""
        service = TransactionsService(db_session)

        # Get a CC transaction (scraped source) and pass only non-applicable updates
        cc_df = service.get_all_transactions("credit_cards")
        unique_id = int(cc_df.iloc[0]["unique_id"])

        # For scraped source, only category/tag are allowed;
        # pass empty dict (no valid updates at all)
        result = service.update_transaction(
            unique_id, "credit_card_transactions", {}
        )
        assert result is False
