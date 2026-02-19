"""
Unit tests for TaggingRepository YAML-based category and tag CRUD operations.

Covers loading/saving YAML files, category add/delete, tag add/delete/relocate,
icon management, and default file creation fallback behavior.
"""

import os

import pytest
import yaml

from backend.errors import EntityAlreadyExistsException, EntityNotFoundException
from backend.repositories.tagging_repository import TaggingRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def categories_file(tmp_path):
    """Create a temporary categories YAML file with two categories."""
    file_path = str(tmp_path / "categories.yaml")
    categories = {
        "Food": ["Groceries", "Restaurants"],
        "Transport": ["Gas", "Parking"],
    }
    with open(file_path, "w") as f:
        yaml.dump(categories, f)
    return file_path


@pytest.fixture
def empty_categories_file(tmp_path):
    """Create an empty YAML file path (file does not exist on disk)."""
    return str(tmp_path / "nonexistent_categories.yaml")


@pytest.fixture
def icons_file(tmp_path, monkeypatch):
    """Create a temporary icons YAML file and patch AppConfig to use it."""
    file_path = str(tmp_path / "categories_icons.yaml")
    icons = {"Food": "burger", "Transport": "car"}
    with open(file_path, "w") as f:
        yaml.dump(icons, f)
    monkeypatch.setattr(
        "backend.config.AppConfig.get_categories_icons_path",
        lambda self: file_path,
    )
    return file_path


# ---------------------------------------------------------------------------
# Class 1: Load / save / get operations
# ---------------------------------------------------------------------------


class TestTaggingRepositoryLoad:
    """Tests for loading, saving, and reading categories from YAML files."""

    def test_load_categories_from_file(self, categories_file):
        """Verify loading a valid YAML file returns the expected dict."""
        result = TaggingRepository.load_categories_from_file(categories_file)
        assert isinstance(result, dict)
        assert "Food" in result
        assert result["Food"] == ["Groceries", "Restaurants"]
        assert "Transport" in result
        assert result["Transport"] == ["Gas", "Parking"]

    def test_load_categories_from_nonexistent_file(self, tmp_path):
        """Verify loading from a nonexistent path returns an empty dict."""
        missing_path = str(tmp_path / "does_not_exist.yaml")
        result = TaggingRepository.load_categories_from_file(missing_path)
        assert result == {}

    def test_load_categories_from_empty_file(self, tmp_path):
        """Verify loading an empty YAML file returns an empty dict."""
        empty_path = str(tmp_path / "empty.yaml")
        with open(empty_path, "w") as f:
            f.write("")
        result = TaggingRepository.load_categories_from_file(empty_path)
        assert result == {}

    def test_save_categories_to_file(self, tmp_path):
        """Verify saving categories writes valid YAML that can be re-read."""
        file_path = str(tmp_path / "saved.yaml")
        categories = {"Health": ["Doctor", "Pharmacy"], "Shopping": ["Clothes"]}

        TaggingRepository.save_categories_to_file(categories, file_path)

        with open(file_path, "r") as f:
            loaded = yaml.load(f, Loader=yaml.FullLoader)
        assert loaded == categories

    def test_get_categories_from_existing_file(self, categories_file):
        """Verify get_categories reads from an existing file correctly."""
        result = TaggingRepository.get_categories(categories_file)
        assert "Food" in result
        assert "Transport" in result
        assert result["Food"] == ["Groceries", "Restaurants"]

    def test_get_categories_creates_from_defaults_if_missing(self, tmp_path, monkeypatch):
        """Verify get_categories copies defaults when the target file is missing."""
        missing_file = str(tmp_path / "categories.yaml")

        # Provide a small default file for the test
        default_path = str(tmp_path / "default_categories.yaml")
        default_cats = {"DefaultCat": ["Tag1", "Tag2"]}
        with open(default_path, "w") as f:
            yaml.dump(default_cats, f)

        monkeypatch.setattr(
            "backend.repositories.tagging_repository.DEFAULT_CATEGORIES_PATH",
            default_path,
        )

        result = TaggingRepository.get_categories(missing_file)

        assert result == default_cats
        # The file should now exist on disk
        assert os.path.exists(missing_file)
        with open(missing_file, "r") as f:
            written = yaml.load(f, Loader=yaml.FullLoader)
        assert written == default_cats

    def test_get_categories_creates_empty_when_no_defaults(self, tmp_path, monkeypatch):
        """Verify get_categories returns empty dict when defaults file is also missing."""
        missing_file = str(tmp_path / "categories.yaml")
        monkeypatch.setattr(
            "backend.repositories.tagging_repository.DEFAULT_CATEGORIES_PATH",
            str(tmp_path / "nonexistent_defaults.yaml"),
        )

        result = TaggingRepository.get_categories(missing_file)

        assert result == {}
        assert os.path.exists(missing_file)


# ---------------------------------------------------------------------------
# Class 2: Category operations
# ---------------------------------------------------------------------------


class TestTaggingRepositoryCategoryOperations:
    """Tests for adding and deleting categories."""

    def test_add_category(self, categories_file):
        """Verify adding a new category persists it with tags."""
        TaggingRepository.add_category("Health", ["Doctor", "Pharmacy"], categories_file)

        result = TaggingRepository.get_categories(categories_file)
        assert "Health" in result
        assert result["Health"] == ["Doctor", "Pharmacy"]
        # Original categories should still be present
        assert "Food" in result
        assert "Transport" in result

    def test_add_category_with_empty_tags(self, categories_file):
        """Verify adding a category with an empty tag list succeeds."""
        TaggingRepository.add_category("Salary", [], categories_file)

        result = TaggingRepository.get_categories(categories_file)
        assert "Salary" in result
        assert result["Salary"] == []

    def test_add_category_already_exists(self, categories_file):
        """Verify adding a duplicate category raises EntityAlreadyExistsException."""
        with pytest.raises(EntityAlreadyExistsException, match="Food"):
            TaggingRepository.add_category("Food", ["NewTag"], categories_file)

    def test_delete_category(self, categories_file):
        """Verify deleting an existing category removes it from the file."""
        TaggingRepository.delete_category("Food", categories_file)

        result = TaggingRepository.get_categories(categories_file)
        assert "Food" not in result
        # Other categories remain
        assert "Transport" in result

    def test_delete_category_not_found(self, categories_file):
        """Verify deleting a nonexistent category raises EntityNotFoundException."""
        with pytest.raises(EntityNotFoundException, match="NonExistent"):
            TaggingRepository.delete_category("NonExistent", categories_file)


# ---------------------------------------------------------------------------
# Class 3: Tag operations
# ---------------------------------------------------------------------------


class TestTaggingRepositoryTagOperations:
    """Tests for adding and deleting tags within categories."""

    def test_add_tag(self, categories_file):
        """Verify adding a tag to an existing category appends it."""
        TaggingRepository.add_tag("Food", "Snacks", categories_file)

        result = TaggingRepository.get_categories(categories_file)
        assert "Snacks" in result["Food"]
        assert result["Food"] == ["Groceries", "Restaurants", "Snacks"]

    def test_add_tag_already_exists(self, categories_file):
        """Verify adding a duplicate tag raises EntityAlreadyExistsException."""
        with pytest.raises(EntityAlreadyExistsException, match="Groceries"):
            TaggingRepository.add_tag("Food", "Groceries", categories_file)

    def test_add_tag_category_not_found(self, categories_file):
        """Verify adding a tag to a nonexistent category raises EntityNotFoundException."""
        with pytest.raises(EntityNotFoundException, match="NonExistent"):
            TaggingRepository.add_tag("NonExistent", "SomeTag", categories_file)

    def test_delete_tag(self, categories_file):
        """Verify deleting a tag removes it from the category."""
        TaggingRepository.delete_tag("Food", "Groceries", categories_file)

        result = TaggingRepository.get_categories(categories_file)
        assert "Groceries" not in result["Food"]
        assert result["Food"] == ["Restaurants"]

    def test_delete_tag_not_found(self, categories_file):
        """Verify deleting a nonexistent tag raises EntityNotFoundException."""
        with pytest.raises(EntityNotFoundException, match="NonExistentTag"):
            TaggingRepository.delete_tag("Food", "NonExistentTag", categories_file)

    def test_delete_tag_category_not_found(self, categories_file):
        """Verify deleting a tag from a nonexistent category raises EntityNotFoundException."""
        with pytest.raises(EntityNotFoundException, match="NonExistent"):
            TaggingRepository.delete_tag("NonExistent", "SomeTag", categories_file)


# ---------------------------------------------------------------------------
# Class 4: Relocate tag
# ---------------------------------------------------------------------------


class TestTaggingRepositoryRelocate:
    """Tests for moving tags between categories."""

    def test_relocate_tag(self, categories_file):
        """Verify relocating a tag moves it from old to new category."""
        TaggingRepository.relocate_tag("Groceries", "Food", "Transport", categories_file)

        result = TaggingRepository.get_categories(categories_file)
        assert "Groceries" not in result["Food"]
        assert "Groceries" in result["Transport"]

    def test_relocate_tag_old_category_not_found(self, categories_file):
        """Verify relocating from a nonexistent category raises EntityNotFoundException."""
        with pytest.raises(EntityNotFoundException, match="NonExistent"):
            TaggingRepository.relocate_tag("SomeTag", "NonExistent", "Food", categories_file)

    def test_relocate_tag_tag_not_in_old(self, categories_file):
        """Verify relocating a tag not in the old category raises EntityNotFoundException."""
        with pytest.raises(EntityNotFoundException, match="MissingTag"):
            TaggingRepository.relocate_tag("MissingTag", "Food", "Transport", categories_file)

    def test_relocate_tag_new_category_not_found(self, categories_file):
        """Verify relocating to a nonexistent category raises EntityNotFoundException."""
        with pytest.raises(EntityNotFoundException, match="NonExistent"):
            TaggingRepository.relocate_tag("Groceries", "Food", "NonExistent", categories_file)

    def test_relocate_tag_already_in_new_category(self, tmp_path):
        """Verify relocating a tag that already exists in new category does not duplicate it."""
        file_path = str(tmp_path / "categories.yaml")
        categories = {
            "Food": ["Groceries", "Restaurants"],
            "Shopping": ["Groceries", "Clothes"],
        }
        with open(file_path, "w") as f:
            yaml.dump(categories, f)

        TaggingRepository.relocate_tag("Groceries", "Food", "Shopping", file_path)

        result = TaggingRepository.get_categories(file_path)
        assert "Groceries" not in result["Food"]
        # Should not be duplicated -- still exactly one
        assert result["Shopping"].count("Groceries") == 1


# ---------------------------------------------------------------------------
# Class 5: Icon operations
# ---------------------------------------------------------------------------


class TestTaggingRepositoryIcons:
    """Tests for category icon loading and updating."""

    def test_get_categories_icons(self, icons_file):
        """Verify get_categories_icons reads the icons YAML file."""
        result = TaggingRepository.get_categories_icons()
        assert isinstance(result, dict)
        assert result["Food"] == "burger"
        assert result["Transport"] == "car"

    def test_get_categories_icons_creates_from_defaults_when_missing(
        self, tmp_path, monkeypatch
    ):
        """Verify get_categories_icons copies defaults when the target file is missing."""
        missing_path = str(tmp_path / "missing_icons.yaml")
        monkeypatch.setattr(
            "backend.config.AppConfig.get_categories_icons_path",
            lambda self: missing_path,
        )

        default_icons_path = str(tmp_path / "default_icons.yaml")
        default_icons = {"Food": "plate", "Health": "pill"}
        with open(default_icons_path, "w") as f:
            yaml.dump(default_icons, f)
        monkeypatch.setattr(
            "backend.repositories.tagging_repository.DEFAULT_CATEGORIES_ICONS_PATH",
            default_icons_path,
        )

        result = TaggingRepository.get_categories_icons()

        assert result == default_icons
        assert os.path.exists(missing_path)

    def test_update_category_icon_new(self, icons_file):
        """Verify updating an icon for a new category returns True."""
        result = TaggingRepository.update_category_icon("Health", "pill")
        assert result is True

        icons = TaggingRepository.get_categories_icons()
        assert icons["Health"] == "pill"

    def test_update_category_icon_changed(self, icons_file):
        """Verify updating an existing icon to a new value returns True."""
        result = TaggingRepository.update_category_icon("Food", "pizza")
        assert result is True

        icons = TaggingRepository.get_categories_icons()
        assert icons["Food"] == "pizza"

    def test_update_category_icon_same_value(self, icons_file):
        """Verify updating an icon to the same value returns False (no change)."""
        result = TaggingRepository.update_category_icon("Food", "burger")
        assert result is False
