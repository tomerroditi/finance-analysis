"""
Unit tests for SplitTransactionsRepository CRUD operations.
"""

from sqlalchemy.orm import Session

from backend.repositories.split_transactions_repository import SplitTransactionsRepository


class TestSplitTransactionsRepository:
    """Tests for SplitTransactionsRepository operations."""

    def test_add_split(self, db_session: Session):
        """Verify adding a split returns its ID."""
        repo = SplitTransactionsRepository(db_session)
        split_id = repo.add_split(
            transaction_id=100,
            source="credit_card_transactions",
            amount=-50.0,
            category="Food",
            tag="Groceries",
        )

        assert isinstance(split_id, int)
        assert split_id > 0

    def test_get_data_empty(self, db_session: Session):
        """Verify get_data returns empty DataFrame when no splits exist."""
        repo = SplitTransactionsRepository(db_session)
        result = repo.get_data()

        assert result.empty

    def test_get_data_with_splits(self, db_session: Session):
        """Verify get_data returns all splits."""
        repo = SplitTransactionsRepository(db_session)
        repo.add_split(100, "credit_card_transactions", -30.0, "Food", "Groceries")
        repo.add_split(100, "credit_card_transactions", -20.0, "Food", "Restaurants")
        repo.add_split(200, "bank_transactions", -150.0, "Transport", "Gas")

        result = repo.get_data()
        assert len(result) == 3
        assert set(result["tag"].tolist()) == {"Groceries", "Restaurants", "Gas"}

    def test_get_splits_for_transaction(self, db_session: Session):
        """Verify filtering splits by transaction_id and source."""
        repo = SplitTransactionsRepository(db_session)
        repo.add_split(100, "credit_card_transactions", -30.0, "Food", "Groceries")
        repo.add_split(100, "credit_card_transactions", -20.0, "Food", "Restaurants")
        repo.add_split(200, "credit_card_transactions", -80.0, "Transport", "Gas")
        repo.add_split(100, "bank_transactions", -50.0, "Bills", "Electricity")

        result = repo.get_splits_for_transaction(100, "credit_card_transactions")
        assert len(result) == 2
        assert set(result["tag"].tolist()) == {"Groceries", "Restaurants"}

    def test_update_split(self, db_session: Session):
        """Verify updating split amount/category/tag."""
        repo = SplitTransactionsRepository(db_session)
        split_id = repo.add_split(100, "credit_card_transactions", -50.0, "Food", "Groceries")

        repo.update_split(split_id, amount=-75.0, category="Transport", tag="Gas")

        result = repo.get_data()
        assert len(result) == 1
        row = result.iloc[0]
        assert row["amount"] == -75.0
        assert row["category"] == "Transport"
        assert row["tag"] == "Gas"

    def test_delete_split(self, db_session: Session):
        """Verify deleting a single split."""
        repo = SplitTransactionsRepository(db_session)
        split_id_1 = repo.add_split(100, "credit_card_transactions", -30.0, "Food", "Groceries")
        repo.add_split(100, "credit_card_transactions", -20.0, "Food", "Restaurants")

        repo.delete_split(split_id_1)

        result = repo.get_data()
        assert len(result) == 1
        assert result.iloc[0]["tag"] == "Restaurants"

    def test_delete_all_splits_for_transaction(self, db_session: Session):
        """Verify deleting all splits for a transaction."""
        repo = SplitTransactionsRepository(db_session)
        repo.add_split(100, "credit_card_transactions", -30.0, "Food", "Groceries")
        repo.add_split(100, "credit_card_transactions", -20.0, "Food", "Restaurants")
        repo.add_split(200, "credit_card_transactions", -80.0, "Transport", "Gas")

        repo.delete_all_splits_for_transaction(100, "credit_card_transactions")

        result = repo.get_data()
        assert len(result) == 1
        assert result.iloc[0]["transaction_id"] == 200

    def test_nullify_category_and_tag(self, db_session: Session):
        """Verify nullifying category and tag for splits matching both category and tag."""
        repo = SplitTransactionsRepository(db_session)
        repo.add_split(100, "credit_card_transactions", -30.0, "Food", "Groceries")
        repo.add_split(101, "credit_card_transactions", -20.0, "Food", "Restaurants")
        repo.add_split(102, "bank_transactions", -80.0, "Transport", "Gas")

        repo.nullify_category_and_tag("Food", "Groceries")

        result = repo.get_data()
        groceries_row = result[result["transaction_id"] == 100].iloc[0]
        assert groceries_row["category"] is None
        assert groceries_row["tag"] is None

        # "Food/Restaurants" should be untouched (different tag)
        restaurants_row = result[result["transaction_id"] == 101].iloc[0]
        assert restaurants_row["category"] == "Food"
        assert restaurants_row["tag"] == "Restaurants"

        # "Transport/Gas" should be untouched (different category)
        gas_row = result[result["transaction_id"] == 102].iloc[0]
        assert gas_row["category"] == "Transport"
        assert gas_row["tag"] == "Gas"

    def test_update_category_for_tag(self, db_session: Session):
        """Verify updating category for splits with a specific old category and tag."""
        repo = SplitTransactionsRepository(db_session)
        repo.add_split(100, "credit_card_transactions", -30.0, "Food", "Groceries")
        repo.add_split(101, "credit_card_transactions", -20.0, "Food", "Restaurants")
        repo.add_split(102, "bank_transactions", -80.0, "Transport", "Gas")

        repo.update_category_for_tag("Food", "Essentials", "Groceries")

        result = repo.get_data()
        groceries_row = result[result["transaction_id"] == 100].iloc[0]
        assert groceries_row["category"] == "Essentials"
        assert groceries_row["tag"] == "Groceries"

        # "Food/Restaurants" should keep original category (different tag)
        restaurants_row = result[result["transaction_id"] == 101].iloc[0]
        assert restaurants_row["category"] == "Food"

        # "Transport/Gas" should be untouched
        gas_row = result[result["transaction_id"] == 102].iloc[0]
        assert gas_row["category"] == "Transport"

    def test_nullify_category(self, db_session: Session):
        """Verify nullifying category and tag for all splits matching a category."""
        repo = SplitTransactionsRepository(db_session)
        repo.add_split(100, "credit_card_transactions", -30.0, "Food", "Groceries")
        repo.add_split(101, "credit_card_transactions", -20.0, "Food", "Restaurants")
        repo.add_split(102, "bank_transactions", -80.0, "Transport", "Gas")

        repo.nullify_category("Food")

        result = repo.get_data()
        food_rows = result[result["transaction_id"].isin([100, 101])]
        assert food_rows["category"].isna().all()
        assert food_rows["tag"].isna().all()

        # "Transport/Gas" should be untouched
        gas_row = result[result["transaction_id"] == 102].iloc[0]
        assert gas_row["category"] == "Transport"
        assert gas_row["tag"] == "Gas"
