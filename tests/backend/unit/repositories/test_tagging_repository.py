"""Unit tests for TaggingRepository DB-backed category and tag CRUD operations."""

import pytest
import yaml

from backend.errors import EntityAlreadyExistsException, EntityNotFoundException
from backend.models.category import Category
from backend.repositories.tagging_repository import TaggingRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def seeded_repo(db_session):
    """Create a TaggingRepository with two seeded categories."""
    db_session.add(Category(name="Food", tags=["Groceries", "Restaurants"]))
    db_session.add(Category(name="Transport", tags=["Gas", "Parking"]))
    db_session.commit()
    return TaggingRepository(db_session)


@pytest.fixture
def empty_repo(db_session):
    """Create a TaggingRepository with no categories."""
    return TaggingRepository(db_session)


# ---------------------------------------------------------------------------
# Class 1: Read operations
# ---------------------------------------------------------------------------


class TestTaggingRepositoryRead:
    """Tests for reading categories from the database."""

    def test_get_categories(self, seeded_repo):
        """Verify get_categories returns dict of category name to tags list."""
        result = seeded_repo.get_categories()
        assert isinstance(result, dict)
        assert result["Food"] == ["Groceries", "Restaurants"]
        assert result["Transport"] == ["Gas", "Parking"]

    def test_get_categories_empty(self, empty_repo):
        """Verify get_categories returns empty dict when no categories exist."""
        result = empty_repo.get_categories()
        assert result == {}

    def test_get_categories_icons(self, db_session):
        """Verify get_categories_icons returns name-to-icon mapping."""
        db_session.add(Category(name="Food", tags=[], icon="🍔"))
        db_session.add(Category(name="Transport", tags=[], icon="🚗"))
        db_session.add(Category(name="Salary", tags=[], icon=None))
        db_session.commit()

        repo = TaggingRepository(db_session)
        icons = repo.get_categories_icons()
        assert icons == {"Food": "🍔", "Transport": "🚗"}

    def test_get_categories_icons_empty(self, empty_repo):
        """Verify get_categories_icons returns empty dict when no categories."""
        assert empty_repo.get_categories_icons() == {}


# ---------------------------------------------------------------------------
# Class 2: Category operations
# ---------------------------------------------------------------------------


class TestTaggingRepositoryCategoryOperations:
    """Tests for adding and deleting categories."""

    def test_add_category(self, seeded_repo):
        """Verify adding a new category persists it with tags."""
        seeded_repo.add_category("Health", ["Doctor", "Pharmacy"])
        result = seeded_repo.get_categories()
        assert "Health" in result
        assert result["Health"] == ["Doctor", "Pharmacy"]
        assert "Food" in result

    def test_add_category_with_icon(self, empty_repo):
        """Verify adding a category with an icon stores it."""
        empty_repo.add_category("Food", ["Groceries"], icon="🍔")
        icons = empty_repo.get_categories_icons()
        assert icons["Food"] == "🍔"

    def test_add_category_with_empty_tags(self, seeded_repo):
        """Verify adding a category with empty tag list succeeds."""
        seeded_repo.add_category("Salary", [])
        result = seeded_repo.get_categories()
        assert result["Salary"] == []

    def test_add_category_already_exists(self, seeded_repo):
        """Verify adding a duplicate category raises EntityAlreadyExistsException."""
        with pytest.raises(EntityAlreadyExistsException, match="Food"):
            seeded_repo.add_category("Food", ["NewTag"])

    def test_delete_category(self, seeded_repo):
        """Verify deleting an existing category removes it."""
        seeded_repo.delete_category("Food")
        result = seeded_repo.get_categories()
        assert "Food" not in result
        assert "Transport" in result

    def test_delete_category_not_found(self, seeded_repo):
        """Verify deleting a nonexistent category raises EntityNotFoundException."""
        with pytest.raises(EntityNotFoundException, match="NonExistent"):
            seeded_repo.delete_category("NonExistent")


# ---------------------------------------------------------------------------
# Class 3: Tag operations
# ---------------------------------------------------------------------------


class TestTaggingRepositoryTagOperations:
    """Tests for adding and deleting tags within categories."""

    def test_add_tag(self, seeded_repo):
        """Verify adding a tag to an existing category appends it."""
        seeded_repo.add_tag("Food", "Snacks")
        result = seeded_repo.get_categories()
        assert "Snacks" in result["Food"]

    def test_add_tag_already_exists(self, seeded_repo):
        """Verify adding a duplicate tag raises EntityAlreadyExistsException."""
        with pytest.raises(EntityAlreadyExistsException, match="Groceries"):
            seeded_repo.add_tag("Food", "Groceries")

    def test_add_tag_category_not_found(self, seeded_repo):
        """Verify adding a tag to a nonexistent category raises EntityNotFoundException."""
        with pytest.raises(EntityNotFoundException, match="NonExistent"):
            seeded_repo.add_tag("NonExistent", "SomeTag")

    def test_delete_tag(self, seeded_repo):
        """Verify deleting a tag removes it from the category."""
        seeded_repo.delete_tag("Food", "Groceries")
        result = seeded_repo.get_categories()
        assert "Groceries" not in result["Food"]
        assert result["Food"] == ["Restaurants"]

    def test_delete_tag_not_found(self, seeded_repo):
        """Verify deleting a nonexistent tag raises EntityNotFoundException."""
        with pytest.raises(EntityNotFoundException, match="NonExistentTag"):
            seeded_repo.delete_tag("Food", "NonExistentTag")

    def test_delete_tag_category_not_found(self, seeded_repo):
        """Verify deleting a tag from a nonexistent category raises EntityNotFoundException."""
        with pytest.raises(EntityNotFoundException, match="NonExistent"):
            seeded_repo.delete_tag("NonExistent", "SomeTag")


# ---------------------------------------------------------------------------
# Class 4: Relocate tag
# ---------------------------------------------------------------------------


class TestTaggingRepositoryRelocate:
    """Tests for moving tags between categories."""

    def test_relocate_tag(self, seeded_repo):
        """Verify relocating a tag moves it from old to new category."""
        seeded_repo.relocate_tag("Groceries", "Food", "Transport")
        result = seeded_repo.get_categories()
        assert "Groceries" not in result["Food"]
        assert "Groceries" in result["Transport"]

    def test_relocate_tag_old_category_not_found(self, seeded_repo):
        """Verify relocating from a nonexistent category raises EntityNotFoundException."""
        with pytest.raises(EntityNotFoundException, match="NonExistent"):
            seeded_repo.relocate_tag("SomeTag", "NonExistent", "Food")

    def test_relocate_tag_tag_not_in_old(self, seeded_repo):
        """Verify relocating a tag not in the old category raises EntityNotFoundException."""
        with pytest.raises(EntityNotFoundException, match="MissingTag"):
            seeded_repo.relocate_tag("MissingTag", "Food", "Transport")

    def test_relocate_tag_new_category_not_found(self, seeded_repo):
        """Verify relocating to a nonexistent category raises EntityNotFoundException."""
        with pytest.raises(EntityNotFoundException, match="NonExistent"):
            seeded_repo.relocate_tag("Groceries", "Food", "NonExistent")

    def test_relocate_tag_already_in_new_category(self, db_session):
        """Verify relocating a tag already in new category does not duplicate."""
        db_session.add(Category(name="Food", tags=["Groceries", "Restaurants"]))
        db_session.add(Category(name="Shopping", tags=["Groceries", "Clothes"]))
        db_session.commit()
        repo = TaggingRepository(db_session)

        repo.relocate_tag("Groceries", "Food", "Shopping")
        result = repo.get_categories()
        assert "Groceries" not in result["Food"]
        assert result["Shopping"].count("Groceries") == 1


# ---------------------------------------------------------------------------
# Class 5: Icon operations
# ---------------------------------------------------------------------------


class TestTaggingRepositoryIcons:
    """Tests for category icon loading and updating."""

    def test_update_category_icon_new(self, seeded_repo):
        """Verify setting an icon on a category without one returns True."""
        result = seeded_repo.update_category_icon("Food", "🍔")
        assert result is True
        assert seeded_repo.get_categories_icons()["Food"] == "🍔"

    def test_update_category_icon_changed(self, db_session):
        """Verify changing an existing icon returns True."""
        db_session.add(Category(name="Food", tags=[], icon="🍔"))
        db_session.commit()
        repo = TaggingRepository(db_session)

        result = repo.update_category_icon("Food", "🍕")
        assert result is True
        assert repo.get_categories_icons()["Food"] == "🍕"

    def test_update_category_icon_same_value(self, db_session):
        """Verify updating an icon to the same value returns False."""
        db_session.add(Category(name="Food", tags=[], icon="🍔"))
        db_session.commit()
        repo = TaggingRepository(db_session)

        result = repo.update_category_icon("Food", "🍔")
        assert result is False

    def test_update_category_icon_not_found(self, seeded_repo):
        """Verify updating icon for nonexistent category raises EntityNotFoundException."""
        with pytest.raises(EntityNotFoundException, match="NonExistent"):
            seeded_repo.update_category_icon("NonExistent", "❓")


# ---------------------------------------------------------------------------
# Class 6: Seeding from YAML
# ---------------------------------------------------------------------------


class TestTaggingRepositorySeeding:
    """Tests for seeding categories from YAML files."""

    def test_seed_from_yaml(self, db_session, tmp_path):
        """Verify seeding from YAML files populates DB correctly."""
        cat_path = str(tmp_path / "categories.yaml")
        icons_path = str(tmp_path / "icons.yaml")

        with open(cat_path, "w") as f:
            yaml.dump({"Food": ["Groceries"], "Salary": []}, f)
        with open(icons_path, "w") as f:
            yaml.dump({"Food": "🍔"}, f)

        repo = TaggingRepository(db_session)
        repo.seed_from_yaml(cat_path, icons_path)

        result = repo.get_categories()
        assert result == {"Food": ["Groceries"], "Salary": []}
        assert repo.get_categories_icons() == {"Food": "🍔"}

    def test_seed_skips_when_table_not_empty(self, seeded_repo, tmp_path):
        """Verify seeding is skipped when categories already exist."""
        cat_path = str(tmp_path / "categories.yaml")
        icons_path = str(tmp_path / "icons.yaml")

        with open(cat_path, "w") as f:
            yaml.dump({"NewCat": ["NewTag"]}, f)
        with open(icons_path, "w") as f:
            yaml.dump({}, f)

        seeded_repo.seed_from_yaml(cat_path, icons_path)

        result = seeded_repo.get_categories()
        assert "NewCat" not in result
        assert "Food" in result
