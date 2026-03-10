"""Tests for the /api/tagging API endpoints."""

import pytest

import backend.services.tagging_service as ts
from backend.models.category import Category


@pytest.fixture(autouse=True)
def seed_route_categories(db_session):
    """Seed categories into the DB and reset cache for each route test."""
    ts._categories_cache = None
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
    ts._categories_cache = None


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
        ts._categories_cache = None

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
