"""Tests for the /api/tagging API endpoints."""

from unittest.mock import patch

import pytest

import backend.services.tagging_service as ts
from backend.models.category import Category


@pytest.fixture(autouse=True)
def seed_route_categories(db_session):
    """Seed categories into the DB and reset cache for each route test."""
    ts._categories_cache = {}
    categories = {
        "Food": ["Groceries", "Restaurants"],
        "Transport": ["Gas", "Public Transport"],
        "Entertainment": ["Cinema", "Streaming"],
        "Salary": [],
        "Other Income": [],
        "Investments": [],
        "Ignore": [],
        "Liabilities": [],
        "Credit Cards": [],
        "Housing": ["Rent", "Utilities"],
    }
    for name, tags in categories.items():
        db_session.add(Category(name=name, tags=tags))
    db_session.commit()
    yield
    ts._categories_cache = {}


class TestTaggingRoutes:
    """Tests for category and tag management endpoints."""

    def test_get_categories(self, test_client):
        """GET /api/tagging/categories returns categories dict."""
        response = test_client.get("/api/tagging/categories")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "Food" in data
        assert "Groceries" in data["Food"]
        assert "Transport" in data

    def test_add_category(self, test_client):
        """POST /api/tagging/categories adds a new category."""
        response = test_client.post(
            "/api/tagging/categories",
            json={"name": "Health", "tags": ["Doctor", "Pharmacy"]},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        # Verify the category was added
        get_resp = test_client.get("/api/tagging/categories")
        data = get_resp.json()
        assert "Health" in data
        assert "Doctor" in data["Health"]

    def test_add_category_duplicate(self, test_client):
        """POST /api/tagging/categories with existing name still returns 200."""
        response = test_client.post(
            "/api/tagging/categories",
            json={"name": "Food", "tags": []},
        )
        # The route always returns success regardless of service result
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_delete_category(self, test_client):
        """DELETE /api/tagging/categories/{name} returns success."""
        response = test_client.delete("/api/tagging/categories/Entertainment")
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        # Verify it was deleted
        get_resp = test_client.get("/api/tagging/categories")
        assert "Entertainment" not in get_resp.json()

    def test_create_tag(self, test_client):
        """POST /api/tagging/tags adds tag to category."""
        response = test_client.post(
            "/api/tagging/tags",
            json={"category": "Food", "name": "Delivery"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        # Verify the tag was added
        get_resp = test_client.get("/api/tagging/categories")
        assert "Delivery" in get_resp.json()["Food"]

    def test_delete_tag(self, test_client):
        """DELETE /api/tagging/tags/{category}/{name} removes tag."""
        response = test_client.delete("/api/tagging/tags/Food/Groceries")
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        # Verify the tag was removed
        get_resp = test_client.get("/api/tagging/categories")
        assert "Groceries" not in get_resp.json()["Food"]

    def test_relocate_tag(self, test_client):
        """POST /api/tagging/tags/relocate moves tag between categories."""
        response = test_client.post(
            "/api/tagging/tags/relocate",
            json={
                "old_category": "Food",
                "new_category": "Entertainment",
                "tag": "Restaurants",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        # Verify the tag moved
        get_resp = test_client.get("/api/tagging/categories")
        data = get_resp.json()
        assert "Restaurants" not in data["Food"]
        assert "Restaurants" in data["Entertainment"]

    def test_get_category_icons(self, test_client, db_session):
        """GET /api/tagging/icons returns icon mapping."""
        from sqlalchemy import select

        food = db_session.execute(
            select(Category).where(Category.name == "Food")
        ).scalar_one()
        food.icon = "utensils"
        transport = db_session.execute(
            select(Category).where(Category.name == "Transport")
        ).scalar_one()
        transport.icon = "car"
        db_session.commit()
        ts._categories_cache = {}

        response = test_client.get("/api/tagging/icons")
        assert response.status_code == 200
        data = response.json()
        assert data["Food"] == "utensils"
        assert data["Transport"] == "car"

    def test_update_category_icon(self, test_client):
        """PUT /api/tagging/icons/{category} updates icon."""
        response = test_client.put("/api/tagging/icons/Food?icon=pizza")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["changed"] is True


class TestCategoryUsageRoute:
    """Tests for GET /tagging/categories/usage.

    The file-level ``seed_route_categories`` fixture (autouse) already seeds
    categories for every test here, so these don't request the brief's
    ``seed_categories`` fixture on top -- doing so double-inserts and trips
    the ``categories.name`` unique constraint.
    """

    def test_returns_an_entry_per_category(self, test_client):
        """Every category appears in the usage response."""
        response = test_client.get("/api/tagging/categories/usage")

        assert response.status_code == 200
        body = response.json()
        categories = test_client.get("/api/tagging/categories").json()
        assert set(body) == set(categories)

    def test_entry_shape(self, test_client):
        """Each entry carries last_used and unused."""
        response = test_client.get("/api/tagging/categories/usage")

        entry = next(iter(response.json().values()))
        assert set(entry) == {"last_used", "unused"}
        assert isinstance(entry["unused"], bool)

    def test_freshly_seeded_categories_are_not_unused(self, test_client):
        """Categories created just now are inside the creation grace."""
        body = test_client.get("/api/tagging/categories/usage").json()

        assert all(entry["unused"] is False for entry in body.values())


class TestTaggingRoutesRejections:
    """Service-level rejections (``False`` returns and ``ValueError``) become HTTP errors."""

    def test_add_category_blank_name_creates_nothing(self, test_client):
        """A whitespace-only category name is silently rejected by the service."""
        before = test_client.get("/api/tagging/categories").json()
        response = test_client.post("/api/tagging/categories", json={"name": "   ", "tags": []})
        assert response.status_code == 200
        assert test_client.get("/api/tagging/categories").json() == before

    @pytest.mark.parametrize(
        "method, path, body, service_method",
        [
            ("post", "/api/tagging/categories", {"name": "Health", "tags": []}, "add_category"),
            ("delete", "/api/tagging/categories/Food", None, "delete_category"),
            ("post", "/api/tagging/tags", {"category": "Food", "name": "Snacks"}, "add_tag"),
            ("delete", "/api/tagging/tags/Food/Groceries", None, "delete_tag"),
            (
                "post",
                "/api/tagging/tags/relocate",
                {"old_category": "Food", "new_category": "Transport", "tag": "Groceries"},
                "reallocate_tag",
            ),
        ],
    )
    def test_value_error_from_service_is_400(self, test_client, method, path, body, service_method):
        """A ``ValueError`` raised by the service maps to 400 with its message."""
        with patch("backend.routes.tagging.CategoriesTagsService") as mock:
            getattr(mock.return_value, service_method).side_effect = ValueError("nope")
            response = getattr(test_client, method)(path, json=body) if body is not None else getattr(test_client, method)(path)
        assert response.status_code == 400
        assert response.json()["detail"] == "nope"

    def test_delete_protected_category_reports_success_but_keeps_it(self, test_client):
        """Protected categories survive a DELETE; the endpoint stays idempotent."""
        response = test_client.delete("/api/tagging/categories/Salary")
        assert response.status_code == 200
        assert "Salary" in test_client.get("/api/tagging/categories").json()

    def test_delete_unknown_tag_is_a_no_op(self, test_client):
        """Deleting a tag the category does not have leaves the category untouched."""
        response = test_client.delete("/api/tagging/tags/Food/DoesNotExist")
        assert response.status_code == 200
        assert test_client.get("/api/tagging/categories").json()["Food"] == ["Groceries", "Restaurants"]


class TestRenameRoutes:
    """PUT /categories/{name} and PUT /tags/{category}/{name}."""

    def test_rename_category_cascades_to_listing(self, test_client):
        """A renamed category appears under its new (title-cased) name with its tags."""
        response = test_client.put("/api/tagging/categories/Food", json={"new_name": "groceries & dining"})
        assert response.status_code == 200
        categories = test_client.get("/api/tagging/categories").json()
        assert "Food" not in categories
        assert categories["Groceries & Dining"] == ["Groceries", "Restaurants"]

    @pytest.mark.parametrize(
        "old, new",
        [
            ("Salary", "Wages"),
            ("Nope", "Whatever"),
            ("Food", "Transport"),
            ("Food", "   "),
        ],
    )
    def test_rename_category_rejections_are_400(self, test_client, old, new):
        """Protected, missing, colliding and blank renames are all 400."""
        response = test_client.put(f"/api/tagging/categories/{old}", json={"new_name": new})
        assert response.status_code == 400
        assert "Cannot rename category" in response.json()["detail"]

    def test_rename_tag_cascades_to_listing(self, test_client):
        """A renamed tag is replaced in place in its category's tag list."""
        response = test_client.put("/api/tagging/tags/Food/Groceries", json={"new_name": "supermarket"})
        assert response.status_code == 200
        assert test_client.get("/api/tagging/categories").json()["Food"] == ["Supermarket", "Restaurants"]

    @pytest.mark.parametrize(
        "category, old, new",
        [
            ("Food", "Nope", "X"),
            ("Nope", "Groceries", "X"),
            ("Food", "Groceries", "Restaurants"),
            ("Food", "Groceries", ""),
        ],
    )
    def test_rename_tag_rejections_are_400(self, test_client, category, old, new):
        """Missing tag, missing category, collision and blank name are all 400."""
        response = test_client.put(f"/api/tagging/tags/{category}/{old}", json={"new_name": new})
        assert response.status_code == 400
        assert "Cannot rename tag" in response.json()["detail"]


class TestCreditCardTagDiscovery:
    """POST /add-new-credit-card-tags."""

    def test_registers_each_card_account_as_a_tag(self, test_client, db_session):
        """Unique provider/account pairs from CC transactions become Credit Cards tags."""
        from backend.models.transaction import CreditCardTransaction

        for i, (provider, account) in enumerate([("isracard", "Main"), ("isracard", "Main"), ("max", "Joint")]):
            db_session.add(
                CreditCardTransaction(
                    id=f"cc_{i}",
                    date="2024-01-0" + str(i + 1),
                    provider=provider,
                    account_name=account,
                    description="x",
                    amount=-10.0,
                    source="credit_card_transactions",
                )
            )
        db_session.commit()

        response = test_client.post("/api/tagging/add-new-credit-card-tags")
        assert response.status_code == 200
        tags = test_client.get("/api/tagging/categories").json()["Credit Cards"]
        assert len(tags) == 2
        assert all(any(p in t.lower() for p in ("isracard", "max")) for t in tags)

        # Idempotent: a second discovery adds nothing.
        test_client.post("/api/tagging/add-new-credit-card-tags")
        assert test_client.get("/api/tagging/categories").json()["Credit Cards"] == tags

    def test_with_no_card_transactions_nothing_changes(self, test_client):
        """An empty CC table leaves the Credit Cards category empty."""
        response = test_client.post("/api/tagging/add-new-credit-card-tags")
        assert response.status_code == 200
        assert test_client.get("/api/tagging/categories").json()["Credit Cards"] == []
