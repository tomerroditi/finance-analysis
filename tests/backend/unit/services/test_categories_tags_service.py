"""
Tests for CategoriesTagsService.

Covers reading categories/tags/icons, adding/deleting categories,
and adding/deleting/reallocating tags.
"""

import pytest

import backend.services.tagging_service as ts
from backend.constants.categories import PROTECTED_CATEGORIES
from backend.services.tagging_service import CategoriesTagsService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_categories_cache():
    """Reset categories cache before each test."""
    ts._categories_cache = {}
    yield
    ts._categories_cache = {}


@pytest.fixture
def categories_service(db_session, seed_categories):
    """Create CategoriesTagsService backed by seeded DB categories."""
    return CategoriesTagsService(db_session)


# ---------------------------------------------------------------------------
# Class 1: Read operations
# ---------------------------------------------------------------------------


class TestCategoriesTagsServiceRead:
    """Tests for reading categories, tags, and icons."""

    def test_get_categories_and_tags(self, categories_service, sample_categories_yaml):
        """Verify categories are loaded from the database."""
        result = categories_service.get_categories_and_tags()

        assert isinstance(result, dict)
        assert "Food" in result
        assert "Groceries" in result["Food"]
        assert "Transport" in result
        assert result == sample_categories_yaml

    def test_get_categories_and_tags_copy(self, categories_service):
        """Verify copy=True returns a deep copy that does not affect the original."""
        copy = categories_service.get_categories_and_tags(copy=True)
        # Mutate the copy
        copy["Food"].append("Fast Food")
        copy["NewCategory"] = ["Tag1"]

        # Original cache should be unaffected
        original = categories_service.get_categories_and_tags()
        assert "Fast Food" not in original["Food"]
        assert "NewCategory" not in original

    def test_get_categories_icons(self, db_session, seed_categories):
        """Verify icons are loaded via TaggingRepository.get_categories_icons."""
        from backend.models.category import Category
        from sqlalchemy import select

        # Set an icon on Food category
        food = db_session.execute(
            select(Category).where(Category.name == "Food")
        ).scalar_one()
        food.icon = "fork-and-knife"
        db_session.commit()

        ts._categories_cache = {}
        service = CategoriesTagsService(db_session)
        icons = service.get_categories_icons()

        assert icons["Food"] == "fork-and-knife"


# ---------------------------------------------------------------------------
# Class 2: Category management
# ---------------------------------------------------------------------------


class TestCategoriesTagsServiceCategories:
    """Tests for adding and deleting categories."""

    def test_add_category(self, categories_service):
        """Verify a new category is added successfully."""
        result = categories_service.add_category("Utilities", ["Electric", "Water"])

        assert result is True
        assert "Utilities" in categories_service.categories_and_tags
        assert categories_service.categories_and_tags["Utilities"] == [
            "Electric",
            "Water",
        ]

    def test_add_category_duplicate_rejected(self, categories_service):
        """Verify adding a category that already exists returns False."""
        # "Food" already exists in seed_categories
        result = categories_service.add_category("Food", ["New Tag"])

        assert result is False

    def test_add_category_empty_name_rejected(self, categories_service):
        """Verify adding a category with an empty or whitespace-only name returns False."""
        assert categories_service.add_category("", []) is False
        assert categories_service.add_category("   ", []) is False
        assert categories_service.add_category(None, []) is False

    def test_add_category_title_case(self, categories_service):
        """Verify category name is normalized to title case."""
        result = categories_service.add_category("health care", ["Doctor"])

        assert result is True
        assert "Health Care" in categories_service.categories_and_tags
        # Original casing should not appear
        assert "health care" not in categories_service.categories_and_tags

    def test_delete_category(
        self, categories_service, db_session, seed_base_transactions
    ):
        """Verify deleting a category removes it and nullifies related transactions."""
        # "Food" category has transactions in seed_base_transactions
        assert "Food" in categories_service.categories_and_tags

        result = categories_service.delete_category("Food")

        assert result is True
        assert "Food" not in categories_service.categories_and_tags

    def test_delete_category_protected(self, categories_service):
        """Verify protected categories cannot be deleted."""
        for protected in PROTECTED_CATEGORIES:
            result = categories_service.delete_category(protected)
            assert result is False, f"Protected category '{protected}' should not be deletable"


# ---------------------------------------------------------------------------
# Class 3: Tag management
# ---------------------------------------------------------------------------


class TestCategoriesTagsServiceTags:
    """Tests for adding, deleting, and reallocating tags."""

    def test_add_tag(self, categories_service):
        """Verify adding a new tag to an existing category."""
        result = categories_service.add_tag("Food", "Bakery")

        assert result is True
        assert "Bakery" in categories_service.categories_and_tags["Food"]

    def test_add_tag_duplicate_rejected(self, categories_service):
        """Verify adding a duplicate tag to a category returns False."""
        # "Groceries" already exists under "Food"
        result = categories_service.add_tag("Food", "Groceries")

        assert result is False

    def test_delete_tag(
        self, categories_service, db_session, seed_base_transactions
    ):
        """Verify deleting a tag removes it from the category and nullifies transactions."""
        assert "Groceries" in categories_service.categories_and_tags["Food"]

        result = categories_service.delete_tag("Food", "Groceries")

        assert result is True
        assert "Groceries" not in categories_service.categories_and_tags["Food"]

    def test_reallocate_tag(
        self, categories_service, db_session, seed_base_transactions
    ):
        """Verify moving a tag between categories updates the in-memory dict."""
        assert "Groceries" in categories_service.categories_and_tags["Food"]
        assert "Groceries" not in categories_service.categories_and_tags["Home"]

        result = categories_service.reallocate_tag("Food", "Home", "Groceries")

        assert result is True
        assert "Groceries" not in categories_service.categories_and_tags["Food"]
        assert "Groceries" in categories_service.categories_and_tags["Home"]

    def test_reallocate_tag_invalid_category(self, categories_service):
        """Verify reallocating a tag to a non-existent category returns False."""
        result = categories_service.reallocate_tag(
            "Food", "NonExistent", "Groceries"
        )

        assert result is False
        # Tag should remain in the original category
        assert "Groceries" in categories_service.categories_and_tags["Food"]

    def test_add_new_credit_card_tags(self, categories_service, db_session):
        """Verify CC account tags are added to the Credit Cards category."""
        from backend.models.category import Category
        from backend.models.transaction import CreditCardTransaction

        # Add "Credit Cards" category to DB
        db_session.add(Category(name="Credit Cards", tags=[]))
        db_session.commit()
        categories_service._invalidate_cache()

        # Insert a credit card transaction so get_unique_accounts_tags returns data
        cc_tx = CreditCardTransaction(
            id="cc_test_1",
            date="2024-01-01",
            provider="isracard",
            account_name="Main Card",
            account_number="12345678",
            description="Test",
            amount=-50.0,
            source="credit_card_transactions",
        )
        db_session.add(cc_tx)
        db_session.commit()

        result = categories_service.add_new_credit_card_tags()

        assert result is True
        cc_tags = categories_service.categories_and_tags["Credit Cards"]
        # Should contain the tag derived from the CC transaction
        assert len(cc_tags) > 0
        # The tag format is "provider - account_name - last4digits"
        # add_tag normalizes to title case, so "isracard" becomes "Isracard"
        assert any("Isracard" in tag for tag in cc_tags)


# ---------------------------------------------------------------------------
# Class N: Unused category detection
# ---------------------------------------------------------------------------


class TestGetCategoryUsage:
    """Tests for CategoriesTagsService.get_category_usage."""

    @staticmethod
    def _age_all_categories(db_session):
        """Backdate every category so the creation grace never applies."""
        from datetime import datetime

        from backend.models.category import Category

        old = datetime(2020, 1, 1)
        for cat in db_session.query(Category).all():
            cat.created_at = old
        db_session.commit()

    @staticmethod
    def _add_bank_txn(db_session, category, date_str):
        """Insert one categorized bank transaction."""
        from backend.models.transaction import BankTransaction

        db_session.add(
            BankTransaction(
                id=f"txn-{category}-{date_str}",
                date=date_str,
                provider="hapoalim",
                account_name="Main",
                description="x",
                amount=-10.0,
                category=category,
                tag=None,
                source="bank_transactions",
                type=None,
                status="completed",
            )
        )
        db_session.commit()

    @staticmethod
    def _iso_months_ago(months):
        """Return an ISO date string that many months in the past."""
        import pandas as pd

        return (
            pd.Timestamp.today().normalize() - pd.DateOffset(months=months)
        ).strftime("%Y-%m-%d")

    def test_every_category_is_present(self, categories_service, db_session):
        """The result covers every category, used or not."""
        self._age_all_categories(db_session)
        result = categories_service.get_category_usage()
        assert set(result) == set(categories_service.get_categories_and_tags())

    def test_stale_category_is_unused(self, categories_service, db_session):
        """A category whose only transaction is older than the window is unused."""
        self._age_all_categories(db_session)
        self._add_bank_txn(db_session, "Food", self._iso_months_ago(9))
        result = categories_service.get_category_usage()
        assert result["Food"]["unused"] is True
        assert result["Food"]["last_used"] == self._iso_months_ago(9)

    def test_recent_transaction_keeps_category_active(
        self, categories_service, db_session
    ):
        """A transaction inside the window keeps the category active."""
        self._age_all_categories(db_session)
        self._add_bank_txn(db_session, "Food", self._iso_months_ago(1))
        result = categories_service.get_category_usage()
        assert result["Food"]["unused"] is False

    def test_never_used_old_category_is_unused(
        self, categories_service, db_session
    ):
        """An old category with no transactions at all is unused."""
        self._age_all_categories(db_session)
        result = categories_service.get_category_usage()
        assert result["Food"]["unused"] is True
        assert result["Food"]["last_used"] is None

    def test_protected_category_is_never_unused(
        self, categories_service, db_session
    ):
        """Protected categories are exempt even with no transactions."""
        self._age_all_categories(db_session)
        result = categories_service.get_category_usage()
        for name in PROTECTED_CATEGORIES:
            if name in result:
                assert result[name]["unused"] is False

    def test_recently_created_category_is_exempt(
        self, categories_service, db_session
    ):
        """A category created inside the window is exempt despite no usage."""
        self._age_all_categories(db_session)
        from datetime import datetime

        from backend.models.category import Category

        fresh = db_session.query(Category).filter_by(name="Food").one()
        fresh.created_at = datetime.now()
        db_session.commit()
        result = categories_service.get_category_usage()
        assert result["Food"]["unused"] is False

    def test_transaction_exactly_at_cutoff_keeps_category_active(
        self, categories_service, db_session
    ):
        """A transaction dated exactly on the cutoff boundary is "recent"
        (``used_recently`` uses ``>=``), so the category stays active."""
        from backend.constants.categories import UNUSED_CATEGORY_MONTHS

        self._age_all_categories(db_session)
        self._add_bank_txn(
            db_session, "Food", self._iso_months_ago(UNUSED_CATEGORY_MONTHS)
        )
        result = categories_service.get_category_usage()
        assert result["Food"]["unused"] is False

    def test_category_created_exactly_at_cutoff_stays_in_creation_grace(
        self, categories_service, db_session
    ):
        """A category created exactly on the cutoff boundary is NOT considered
        "created before the cutoff" (``created_before_cutoff`` uses ``<``), so
        it keeps its creation grace despite having no transactions."""
        import pandas as pd
        from datetime import datetime

        from backend.constants.categories import UNUSED_CATEGORY_MONTHS
        from backend.models.category import Category

        self._age_all_categories(db_session)
        cutoff = (
            pd.Timestamp.today().normalize()
            - pd.DateOffset(months=UNUSED_CATEGORY_MONTHS)
        ).date()
        fresh = db_session.query(Category).filter_by(name="Food").one()
        fresh.created_at = datetime(cutoff.year, cutoff.month, cutoff.day)
        db_session.commit()
        result = categories_service.get_category_usage()
        assert result["Food"]["unused"] is False
