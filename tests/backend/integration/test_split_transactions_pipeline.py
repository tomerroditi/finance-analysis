"""
Integration tests for the split transactions pipeline.

Tests the full flow from splitting a base transaction through
analysis output, covering the interaction between
TransactionsRepository, SplitTransactionsRepository, and
TransactionsService.
"""

import pandas as pd
from sqlalchemy.orm import Session

from backend.repositories.split_transactions_repository import (
    SplitTransactionsRepository,
)
from backend.repositories.transactions_repository import TransactionsRepository
from backend.services.transactions_service import TransactionsService


class TestSplitTransactionsPipeline:
    """Tests for the end-to-end split transaction pipeline."""

    def test_split_transaction(
        self, db_session: Session, seed_base_transactions: list
    ):
        """Split a base transaction into 2 parts, verify children created and parent marked as split_parent."""
        repo = TransactionsRepository(db_session)

        # Pick cc_jan_1 (amount=-150, category=Food, tag=Groceries)
        cc_df = repo.cc_repo.get_table()
        parent_row = cc_df[cc_df["id"] == "cc_jan_1"].iloc[0]
        parent_unique_id = int(parent_row["unique_id"])

        splits = [
            {"amount": -100.0, "category": "Food", "tag": "Groceries"},
            {"amount": -50.0, "category": "Home", "tag": "Cleaning"},
        ]
        success = repo.split_transaction(
            parent_unique_id, "credit_card_transactions", splits
        )
        assert success is True

        # Verify parent type changed to split_parent
        cc_df_after = repo.cc_repo.get_table()
        parent_after = cc_df_after[cc_df_after["id"] == "cc_jan_1"].iloc[0]
        assert parent_after["type"] == "split_parent"

        # Verify split children created
        split_repo = SplitTransactionsRepository(db_session)
        children = split_repo.get_splits_for_transaction(
            parent_unique_id, "credit_card_transactions"
        )
        assert len(children) == 2
        assert set(children["category"].tolist()) == {"Food", "Home"}

    def test_split_children_in_analysis(
        self, db_session: Session, seed_base_transactions: list
    ):
        """Verify split children appear in get_data_for_analysis output."""
        repo = TransactionsRepository(db_session)
        service = TransactionsService(db_session)

        # Split cc_jan_1 (-150) into two parts
        cc_df = repo.cc_repo.get_table()
        parent_row = cc_df[cc_df["id"] == "cc_jan_1"].iloc[0]
        parent_unique_id = int(parent_row["unique_id"])

        splits = [
            {"amount": -90.0, "category": "Food", "tag": "Groceries"},
            {"amount": -60.0, "category": "Entertainment", "tag": "Cinema"},
        ]
        repo.split_transaction(
            parent_unique_id, "credit_card_transactions", splits
        )

        analysis_df = service.get_data_for_analysis(include_split_parents=False)

        # Split children should be present in the analysis data
        split_children = analysis_df[
            (analysis_df["type"] == "split_child")
        ]
        assert len(split_children) >= 2

        # Verify the split amounts are present
        child_amounts = sorted(split_children["amount"].tolist())
        assert -90.0 in child_amounts
        assert -60.0 in child_amounts

    def test_split_parent_excluded_from_analysis(
        self, db_session: Session, seed_base_transactions: list
    ):
        """Verify split parent is excluded when include_split_parents=False (default)."""
        repo = TransactionsRepository(db_session)
        service = TransactionsService(db_session)

        # Split cc_jan_1
        cc_df = repo.cc_repo.get_table()
        parent_row = cc_df[cc_df["id"] == "cc_jan_1"].iloc[0]
        parent_unique_id = int(parent_row["unique_id"])

        splits = [
            {"amount": -100.0, "category": "Food", "tag": "Groceries"},
            {"amount": -50.0, "category": "Home", "tag": "Cleaning"},
        ]
        repo.split_transaction(
            parent_unique_id, "credit_card_transactions", splits
        )

        # Default: include_split_parents=False
        analysis_df = service.get_data_for_analysis(include_split_parents=False)

        # The parent (with original unique_id) should NOT appear as a normal row
        # split_parent type rows should be absent
        parent_rows = analysis_df[
            (analysis_df["id"] == "cc_jan_1")
            & (analysis_df["type"] == "split_parent")
        ]
        assert len(parent_rows) == 0, (
            "Split parent should be excluded from analysis by default"
        )

        # With include_split_parents=True, the parent SHOULD appear
        analysis_with_parents = service.get_data_for_analysis(
            include_split_parents=True
        )
        # The parent's original amount should still be present somewhere
        # Either as split_parent in the service layer or via the repo layer
        all_ids = analysis_with_parents["id"].tolist()
        assert "cc_jan_1" in all_ids, (
            "Split parent should be included when include_split_parents=True"
        )

    def test_revert_split(
        self, db_session: Session, seed_base_transactions: list
    ):
        """Revert a split, verify children deleted and parent restored to normal type."""
        repo = TransactionsRepository(db_session)
        split_repo = SplitTransactionsRepository(db_session)

        # Split cc_jan_1
        cc_df = repo.cc_repo.get_table()
        parent_row = cc_df[cc_df["id"] == "cc_jan_1"].iloc[0]
        parent_unique_id = int(parent_row["unique_id"])

        splits = [
            {"amount": -100.0, "category": "Food", "tag": "Groceries"},
            {"amount": -50.0, "category": "Home", "tag": "Cleaning"},
        ]
        repo.split_transaction(
            parent_unique_id, "credit_card_transactions", splits
        )

        # Confirm split exists
        children_before = split_repo.get_splits_for_transaction(
            parent_unique_id, "credit_card_transactions"
        )
        assert len(children_before) == 2

        # Revert the split
        success = repo.revert_split(
            parent_unique_id, "credit_card_transactions"
        )
        assert success is True

        # Verify children deleted
        children_after = split_repo.get_splits_for_transaction(
            parent_unique_id, "credit_card_transactions"
        )
        assert len(children_after) == 0

        # Verify parent restored to normal type
        cc_df_after = repo.cc_repo.get_table()
        parent_after = cc_df_after[cc_df_after["id"] == "cc_jan_1"].iloc[0]
        assert parent_after["type"] == "normal"

    def test_split_amounts_sum_to_parent(
        self, db_session: Session, seed_split_transactions: dict
    ):
        """Verify sum of split child amounts equals parent amount."""
        split_repo = SplitTransactionsRepository(db_session)

        cc_parent = seed_split_transactions["cc_parent"]
        bank_parent = seed_split_transactions["bank_parent"]

        # CC parent: -300 split into -150, -100, -50
        cc_children = split_repo.get_splits_for_transaction(
            cc_parent.unique_id, "credit_card_transactions"
        )
        cc_child_sum = cc_children["amount"].sum()
        assert cc_child_sum == cc_parent.amount, (
            f"CC split children sum ({cc_child_sum}) should equal "
            f"parent amount ({cc_parent.amount})"
        )

        # Bank parent: -200 split into -120, -80
        bank_children = split_repo.get_splits_for_transaction(
            bank_parent.unique_id, "bank_transactions"
        )
        bank_child_sum = bank_children["amount"].sum()
        assert bank_child_sum == bank_parent.amount, (
            f"Bank split children sum ({bank_child_sum}) should equal "
            f"parent amount ({bank_parent.amount})"
        )

    def test_split_children_independent_categories(
        self, db_session: Session, seed_base_transactions: list
    ):
        """Verify each split child can have a different category and tag."""
        repo = TransactionsRepository(db_session)
        split_repo = SplitTransactionsRepository(db_session)

        # Split bank_jan_2 (Rent Payment, -3000) into 3 different categories
        bank_df = repo.bank_repo.get_table()
        parent_row = bank_df[bank_df["id"] == "bank_jan_2"].iloc[0]
        parent_unique_id = int(parent_row["unique_id"])

        splits = [
            {"amount": -1500.0, "category": "Home", "tag": "Rent"},
            {"amount": -1000.0, "category": "Home", "tag": "Maintenance"},
            {"amount": -500.0, "category": "Other", "tag": None},
        ]
        repo.split_transaction(
            parent_unique_id, "bank_transactions", splits
        )

        children = split_repo.get_splits_for_transaction(
            parent_unique_id, "bank_transactions"
        )
        assert len(children) == 3

        # Verify each child has the expected distinct category/tag pair
        categories = children["category"].tolist()
        assert "Home" in categories
        assert "Other" in categories

        tags = children["tag"].tolist()
        assert "Rent" in tags
        assert "Maintenance" in tags
        assert None in tags or pd.isna(tags[-1])

        # Verify all amounts are distinct
        amounts = sorted(children["amount"].tolist())
        assert amounts == [-1500.0, -1000.0, -500.0]
