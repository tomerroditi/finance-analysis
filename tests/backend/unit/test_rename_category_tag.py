"""Tests for category and tag renaming functionality.

Validates the CategoriesTagsService.rename_category and rename_tag methods,
including protection checks, collision detection, title-casing, and cascade
to all dependent repositories.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

import backend.services.tagging_service as ts
from backend.constants.categories import PROTECTED_CATEGORIES, PROTECTED_TAGS
from backend.models.budget import BudgetRule
from backend.models.category import Category
from backend.models.tagging_rules import TaggingRule
from backend.models.transaction import (
    BankTransaction,
    CreditCardTransaction,
    SplitTransaction,
)
from backend.services.tagging_service import CategoriesTagsService


def _make_service(categories_and_tags: dict) -> CategoriesTagsService:
    """Create a CategoriesTagsService with mocked dependencies.

    Parameters
    ----------
    categories_and_tags : dict
        Category-to-tags mapping to use as the service's config.

    Returns
    -------
    CategoriesTagsService
        Service instance with all repos replaced by MagicMocks.
    """
    with patch.object(CategoriesTagsService, "__init__", lambda self, db: None):
        service = CategoriesTagsService(None)
    service.categories_and_tags = categories_and_tags
    service.tagging_repo = MagicMock()
    service.transactions_repo = MagicMock()
    service.split_transactions_repo = MagicMock()
    service.tagging_rules_repo = MagicMock()
    service.budget_repo = MagicMock()
    service._invalidate_cache = MagicMock()
    return service


class TestRenameCategory:
    """Tests for CategoriesTagsService.rename_category."""

    def test_protected_category_returns_false(self):
        """Renaming a protected category should return False."""
        for cat in PROTECTED_CATEGORIES:
            service = _make_service({cat: []})
            assert service.rename_category(cat, "New Name") is False

    def test_nonexistent_category_returns_false(self):
        """Renaming a category not in the config should return False."""
        service = _make_service({"Food": []})
        assert service.rename_category("NonExistent", "New Name") is False

    def test_collision_returns_false(self):
        """Renaming to an existing category name should return False."""
        service = _make_service({"Food": [], "Shopping": []})
        assert service.rename_category("Food", "Shopping") is False

    def test_case_insensitive_collision(self):
        """Renaming to an existing name differing only in case should return False."""
        service = _make_service({"Food": [], "Shopping": []})
        assert service.rename_category("Food", "shopping") is False

    def test_empty_name_returns_false(self):
        """Renaming to empty string should return False."""
        service = _make_service({"Food": []})
        assert service.rename_category("Food", "  ") is False

    def test_successful_rename_cascades(self):
        """Successful rename should cascade to all repos and invalidate cache."""
        service = _make_service({"Food": ["Groceries"]})
        result = service.rename_category("Food", "Dining")
        assert result is True
        service.transactions_repo.rename_category.assert_called_once_with("Food", "Dining")
        service.split_transactions_repo.rename_category.assert_called_once_with("Food", "Dining")
        service.tagging_rules_repo.rename_category.assert_called_once_with("Food", "Dining")
        service.budget_repo.rename_category.assert_called_once_with("Food", "Dining")
        service.tagging_repo.rename_category.assert_called_once_with("Food", "Dining")
        service._invalidate_cache.assert_called_once()

    def test_rename_applies_title_case(self):
        """New name should be title-cased."""
        service = _make_service({"Food": []})
        service.rename_category("Food", "my dining")
        service.tagging_repo.rename_category.assert_called_once_with("Food", "My Dining")

    def test_same_case_change_allowed(self):
        """Renaming to same name with different casing should be allowed."""
        service = _make_service({"food stuff": []})
        result = service.rename_category("food stuff", "Food Stuff")
        assert result is True


class TestRenameTag:
    """Tests for CategoriesTagsService.rename_tag."""

    def test_protected_tag_returns_false(self):
        """Renaming a protected tag should return False."""
        for tag in PROTECTED_TAGS:
            service = _make_service({"Other Income": [tag]})
            assert service.rename_tag("Other Income", tag, "New Tag") is False

    def test_nonexistent_category_returns_false(self):
        """Renaming a tag in a nonexistent category should return False."""
        service = _make_service({"Food": ["Groceries"]})
        assert service.rename_tag("NonExistent", "Groceries", "New Tag") is False

    def test_nonexistent_tag_returns_false(self):
        """Renaming a tag that doesn't exist should return False."""
        service = _make_service({"Food": ["Groceries"]})
        assert service.rename_tag("Food", "NonExistent", "New Tag") is False

    def test_collision_returns_false(self):
        """Renaming to an existing tag in same category should return False."""
        service = _make_service({"Food": ["Groceries", "Restaurants"]})
        assert service.rename_tag("Food", "Groceries", "Restaurants") is False

    def test_empty_name_returns_false(self):
        """Renaming to empty string should return False."""
        service = _make_service({"Food": ["Groceries"]})
        assert service.rename_tag("Food", "Groceries", "  ") is False

    def test_successful_rename_cascades(self):
        """Successful rename should cascade to all repos and invalidate cache."""
        service = _make_service({"Food": ["Groceries"]})
        result = service.rename_tag("Food", "Groceries", "Supermarket")
        assert result is True
        service.transactions_repo.rename_tag.assert_called_once_with("Food", "Groceries", "Supermarket")
        service.split_transactions_repo.rename_tag.assert_called_once_with("Food", "Groceries", "Supermarket")
        service.tagging_rules_repo.rename_tag.assert_called_once_with("Food", "Groceries", "Supermarket")
        service.budget_repo.rename_tag.assert_called_once_with(
            "Food", "Groceries", "Supermarket"
        )
        service.tagging_repo.rename_tag.assert_called_once_with("Food", "Groceries", "Supermarket")
        service._invalidate_cache.assert_called_once()

    def test_rename_applies_title_case(self):
        """New tag name should be title-cased."""
        service = _make_service({"Food": ["Groceries"]})
        service.rename_tag("Food", "Groceries", "organic food")
        service.tagging_repo.rename_tag.assert_called_once_with("Food", "Groceries", "Organic Food")


class TestRenameAndReallocateCascadeOnRealDb:
    """Rename/reallocate against a real DB, across every table that joins on a tag.

    The mocked tests above only prove the service *calls* each repository.
    These pin the rows those calls actually change — in particular that a
    budget rule's semicolon-joined ``tags`` string is edited rather than
    replaced, and that a same-named tag under a different category is left
    completely alone.
    """

    @pytest.fixture
    def seeded(self, db_session):
        """Seed two categories that share a tag name, plus rows in every table."""
        db_session.add_all(
            [
                Category(name="Food", tags=["Groceries", "Coffee"]),
                Category(name="Home", tags=["Groceries"]),
                Category(name="Transport", tags=["Gas"]),
                CreditCardTransaction(
                    id="cc-1", date="2024-01-01", provider="isracard",
                    account_name="Main", description="Shufersal", amount=-100.0,
                    category="Food", tag="Groceries",
                    source="credit_card_transactions",
                ),
                BankTransaction(
                    id="bank-1", date="2024-01-02", provider="hapoalim",
                    account_name="Checking", description="Rami Levy", amount=-200.0,
                    category="Food", tag="Groceries", source="bank_transactions",
                ),
                BankTransaction(
                    id="bank-2", date="2024-01-03", provider="hapoalim",
                    account_name="Checking", description="Cleaning supplies",
                    amount=-50.0, category="Home", tag="Groceries",
                    source="bank_transactions",
                ),
                SplitTransaction(
                    transaction_id=1, source="credit_card_transactions",
                    amount=-40.0, category="Food", tag="Groceries",
                ),
                TaggingRule(
                    name="Food rule", conditions={"type": "AND", "subconditions": []},
                    category="Food", tag="Groceries",
                ),
                TaggingRule(
                    name="Home rule", conditions={"type": "AND", "subconditions": []},
                    category="Home", tag="Groceries",
                ),
                BudgetRule(
                    name="Food multi", amount=2000.0, category="Food",
                    tags="Groceries;Coffee", year=2024, month=1,
                    period_type="monthly",
                ),
                BudgetRule(
                    name="Food single", amount=800.0, category="Food",
                    tags="Groceries", year=2024, month=2, period_type="monthly",
                ),
                BudgetRule(
                    name="Home single", amount=300.0, category="Home",
                    tags="Groceries", year=2024, month=1, period_type="monthly",
                ),
            ]
        )
        db_session.commit()
        ts._categories_cache = {}
        yield CategoriesTagsService(db_session)
        ts._categories_cache = {}

    @staticmethod
    def _pairs(db_session, model):
        """Return ``{identifier: (category, tag)}`` for one table."""
        db_session.expire_all()
        key = "name" if model is TaggingRule else "id"
        return {
            getattr(row, key): (row.category, row.tag)
            for row in db_session.execute(select(model)).scalars()
        }

    @staticmethod
    def _budgets(db_session):
        """Return ``{name: (category, tags)}`` for the budget rules."""
        db_session.expire_all()
        return {
            row.name: (row.category, row.tags)
            for row in db_session.execute(select(BudgetRule)).scalars()
        }

    def test_rename_tag_cascades_to_every_table(self, seeded, db_session):
        """Renaming Food/Groceries rewrites only Food's rows, in every table."""
        assert seeded.rename_tag("Food", "Groceries", "Supermarket") is True

        assert self._pairs(db_session, CreditCardTransaction) == {
            "cc-1": ("Food", "Supermarket")
        }
        assert self._pairs(db_session, BankTransaction) == {
            "bank-1": ("Food", "Supermarket"),
            "bank-2": ("Home", "Groceries"),
        }
        assert self._pairs(db_session, SplitTransaction) == {
            1: ("Food", "Supermarket")
        }
        assert self._pairs(db_session, TaggingRule) == {
            "Food rule": ("Food", "Supermarket"),
            "Home rule": ("Home", "Groceries"),
        }
        # The joined tag string is edited in place, not replaced wholesale.
        assert self._budgets(db_session) == {
            "Food multi": ("Food", "Supermarket;Coffee"),
            "Food single": ("Food", "Supermarket"),
            "Home single": ("Home", "Groceries"),
        }
        assert seeded.categories_and_tags["Food"] == ["Supermarket", "Coffee"]
        assert seeded.categories_and_tags["Home"] == ["Groceries"]

    def test_reallocate_tag_moves_rows_and_the_budget_rule(self, seeded, db_session):
        """Moving Food/Groceries to Transport re-categorises rows and budgets.

        A budget rule that budgets only the moved tag follows it to the new
        category; one that budgets several tags keeps its envelope where it is
        and simply drops the tag it no longer owns.
        """
        assert seeded.reallocate_tag("Food", "Transport", "Groceries") is True

        assert self._pairs(db_session, CreditCardTransaction) == {
            "cc-1": ("Transport", "Groceries")
        }
        assert self._pairs(db_session, BankTransaction) == {
            "bank-1": ("Transport", "Groceries"),
            "bank-2": ("Home", "Groceries"),
        }
        assert self._pairs(db_session, SplitTransaction) == {
            1: ("Transport", "Groceries")
        }
        assert self._pairs(db_session, TaggingRule) == {
            "Food rule": ("Transport", "Groceries"),
            "Home rule": ("Home", "Groceries"),
        }
        assert self._budgets(db_session) == {
            "Food multi": ("Food", "Coffee"),
            "Food single": ("Transport", "Groceries"),
            "Home single": ("Home", "Groceries"),
        }
        assert seeded.categories_and_tags["Food"] == ["Coffee"]
        assert seeded.categories_and_tags["Transport"] == ["Gas", "Groceries"]

    def test_failed_reallocate_leaves_every_row_untouched(self, seeded, db_session):
        """An unknown target category aborts before a single row is rewritten."""
        before_txns = self._pairs(db_session, BankTransaction)
        before_budgets = self._budgets(db_session)

        assert seeded.reallocate_tag("Food", "Nope", "Groceries") is False

        assert self._pairs(db_session, BankTransaction) == before_txns
        assert self._budgets(db_session) == before_budgets
        assert seeded.categories_and_tags["Food"] == ["Groceries", "Coffee"]

    def test_delete_unknown_category_leaves_transactions_untouched(
        self, seeded, db_session
    ):
        """``delete_category`` on a name that does not exist changes nothing.

        The nullify calls used to run *before* the existence check, so a typo
        could untag rows and delete rules while still reporting failure.
        """
        before_txns = self._pairs(db_session, BankTransaction)
        before_rules = self._pairs(db_session, TaggingRule)

        assert seeded.delete_category("Fod") is False

        assert self._pairs(db_session, BankTransaction) == before_txns
        assert self._pairs(db_session, TaggingRule) == before_rules

    def test_delete_unknown_tag_leaves_transactions_untouched(self, seeded, db_session):
        """``delete_tag`` on a tag the category lacks changes nothing."""
        before_txns = self._pairs(db_session, BankTransaction)
        before_rules = self._pairs(db_session, TaggingRule)

        assert seeded.delete_tag("Food", "Grocerys") is False

        assert self._pairs(db_session, BankTransaction) == before_txns
        assert self._pairs(db_session, TaggingRule) == before_rules

    @pytest.mark.parametrize("new_name", ["Food;Drink", "  ", ""])
    def test_rename_to_a_blank_or_semicolon_name_is_refused(self, seeded, new_name):
        """``;`` is the budget tag separator, so a name containing it is invalid."""
        assert seeded.rename_category("Food", new_name) is False
        assert seeded.rename_tag("Food", "Groceries", new_name) is False
        assert seeded.categories_and_tags["Food"] == ["Groceries", "Coffee"]

    def test_rename_to_the_same_name_is_a_clean_no_op(self, seeded, db_session):
        """Renaming to the current name succeeds without disturbing anything."""
        assert seeded.rename_category("Food", "Food") is True
        assert seeded.rename_tag("Food", "Groceries", "Groceries") is True

        assert seeded.categories_and_tags["Food"] == ["Groceries", "Coffee"]
        assert self._budgets(db_session)["Food multi"] == ("Food", "Groceries;Coffee")
