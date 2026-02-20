"""Tagging repository for category and tag management.

This repository handles DB-based storage for categories, tags, and icons.
"""

import os
from typing import Optional

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.errors import EntityAlreadyExistsException, EntityNotFoundException
from backend.models.category import Category

BACKEND_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CATEGORIES_PATH = os.path.join(
    BACKEND_PATH, "resources", "default_categories.yaml"
)
DEFAULT_CATEGORIES_ICONS_PATH = os.path.join(
    BACKEND_PATH, "resources", "categories_icons.yaml"
)


class TaggingRepository:
    """Repository for category and tag CRUD operations backed by SQLite."""

    def __init__(self, db: Session):
        self.db = db

    def _get_category(self, name: str) -> Category:
        """Fetch a category by name or raise EntityNotFoundException."""
        cat = self.db.execute(
            select(Category).where(Category.name == name)
        ).scalar_one_or_none()
        if cat is None:
            raise EntityNotFoundException(f"Category '{name}' not found")
        return cat

    def get_categories(self) -> dict[str, list[str]]:
        """Get all categories and their tags as a dict."""
        rows = self.db.execute(select(Category)).scalars().all()
        return {row.name: list(row.tags) for row in rows}

    def add_category(
        self, name: str, tags: list[str], icon: Optional[str] = None
    ) -> None:
        """Add a new category. Raises EntityAlreadyExistsException on duplicate."""
        existing = self.db.execute(
            select(Category).where(Category.name == name)
        ).scalar_one_or_none()
        if existing is not None:
            raise EntityAlreadyExistsException(
                f"Category '{name}' already exists"
            )
        self.db.add(Category(name=name, tags=tags, icon=icon))
        self.db.commit()

    def delete_category(self, name: str) -> None:
        """Delete a category. Raises EntityNotFoundException if not found."""
        cat = self._get_category(name)
        self.db.delete(cat)
        self.db.commit()

    def add_tag(self, category: str, tag: str) -> None:
        """Add a tag to a category's tags list."""
        cat = self._get_category(category)
        if tag in cat.tags:
            raise EntityAlreadyExistsException(
                f"Tag '{tag}' already exists in category '{category}'"
            )
        cat.tags = [*cat.tags, tag]
        self.db.commit()

    def delete_tag(self, category: str, tag: str) -> None:
        """Remove a tag from a category's tags list."""
        cat = self._get_category(category)
        if tag not in cat.tags:
            raise EntityNotFoundException(
                f"Tag '{tag}' not found in category '{category}'"
            )
        cat.tags = [t for t in cat.tags if t != tag]
        self.db.commit()

    def relocate_tag(
        self, tag: str, old_category: str, new_category: str
    ) -> None:
        """Move a tag from one category to another."""
        old_cat = self._get_category(old_category)
        if tag not in old_cat.tags:
            raise EntityNotFoundException(
                f"Tag '{tag}' not found in category '{old_category}'"
            )
        new_cat = self._get_category(new_category)

        old_cat.tags = [t for t in old_cat.tags if t != tag]
        if tag not in new_cat.tags:
            new_cat.tags = [*new_cat.tags, tag]
        self.db.commit()

    def get_categories_icons(self) -> dict[str, str]:
        """Get mapping of category names to icons (excludes nulls)."""
        rows = self.db.execute(select(Category)).scalars().all()
        return {row.name: row.icon for row in rows if row.icon is not None}

    def update_category_icon(self, category: str, icon: str) -> bool:
        """Update a category's icon. Returns False if unchanged."""
        cat = self._get_category(category)
        if cat.icon == icon:
            return False
        cat.icon = icon
        self.db.commit()
        return True

    def seed_from_yaml(self, categories_path: str, icons_path: str) -> None:
        """Seed categories from YAML files if the table is empty.

        Parameters
        ----------
        categories_path : str
            Path to YAML file with {category_name: [tags]} structure.
        icons_path : str
            Path to YAML file with {category_name: icon_emoji} structure.
        """
        existing = self.db.execute(select(Category)).first()
        if existing is not None:
            return

        categories = {}
        if os.path.exists(categories_path):
            with open(categories_path, "r") as f:
                categories = yaml.safe_load(f) or {}

        icons = {}
        if os.path.exists(icons_path):
            with open(icons_path, "r") as f:
                icons = yaml.safe_load(f) or {}

        for name, tags in categories.items():
            self.db.add(
                Category(name=name, tags=tags or [], icon=icons.get(name))
            )
        self.db.commit()
