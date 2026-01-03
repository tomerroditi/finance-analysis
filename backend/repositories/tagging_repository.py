"""
Tagging repository for category and tag management.

This repository handles file-based storage for categories and tags.
No Streamlit dependencies - uses pure YAML file I/O.
"""
import os
from typing import Dict, List
from backend.errors import EntityNotFoundException, EntityAlreadyExistsException

import yaml


# Default paths - can be overridden via environment variables
USER_DIR = os.environ.get('FAD_USER_DIR', os.path.join(os.path.expanduser('~'), '.finance-analysis'))
CATEGORIES_PATH = os.environ.get('FAD_CATEGORIES_PATH', os.path.join(USER_DIR, 'categories.yaml'))
CATEGORIES_ICONS_PATH = os.environ.get('FAD_CATEGORIES_ICONS_PATH', os.path.join(USER_DIR, 'categories_icons.yaml'))
BACKEND_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CATEGORIES_PATH = os.path.join(BACKEND_PATH, 'resources', 'default_categories.yaml')
DEFAULT_CATEGORIES_ICONS_PATH = os.path.join(BACKEND_PATH, 'resources', 'categories_icons.yaml')


class TaggingRepository:
    """
    Repository for basic CRUD operations on tagging data.
    
    Handles file-based storage for categories and tags using YAML files.
    """
    @staticmethod
    def get_categories(file_path: str = CATEGORIES_PATH) -> Dict[str, List[str]]:
        """Get categories and tags from a YAML file."""
        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            if os.path.exists(DEFAULT_CATEGORIES_PATH):
                categories = TaggingRepository.load_categories_from_file(DEFAULT_CATEGORIES_PATH)
            else:
                categories = {}

            with open(file_path, 'w') as file:
                yaml.dump(categories, file)
            
            return categories

        with open(file_path, 'r') as file:
            return yaml.load(file, Loader=yaml.FullLoader) or {}

    @staticmethod
    def add_category(category: str, tags: List[str], file_path: str = CATEGORIES_PATH) -> None:
        """Add a new category and its tags to the YAML file."""
        categories = TaggingRepository.get_categories(file_path)
        if category in categories:
            raise EntityAlreadyExistsException(f"Category '{category}' already exists")
        categories[category] = tags
        with open(file_path, 'w') as file:
            yaml.dump(categories, file)

    @staticmethod
    def delete_category(category: str, file_path: str = CATEGORIES_PATH) -> None:
        """Remove a category and its tags from the YAML file."""
        categories = TaggingRepository.get_categories(file_path)
        if category in categories:
            del categories[category]
            with open(file_path, 'w') as file:
                yaml.dump(categories, file)
        else:
            raise EntityNotFoundException(f"Category '{category}' not found")

    @staticmethod
    def get_categories_icons() -> Dict[str, str]:
        """
        Get category icons mapping.

        Parameters
        ----------
        resources_path : str, optional
            Path to the resources directory. Defaults to fad/resources.

        Returns
        -------
        Dict[str, str]
            Mapping of category names to icon strings.
        """
        if not os.path.exists(CATEGORIES_ICONS_PATH) or os.path.getsize(CATEGORIES_ICONS_PATH) == 0:
            with open(DEFAULT_CATEGORIES_ICONS_PATH, 'r') as file:
                default_icons = yaml.load(file, Loader=yaml.FullLoader)
            with open(CATEGORIES_ICONS_PATH, 'w') as file:
                yaml.dump(default_icons, file)
            return default_icons

        with open(CATEGORIES_ICONS_PATH, 'r') as file:
            return yaml.load(file, Loader=yaml.FullLoader)

    @staticmethod
    def update_category_icon(category: str, icon: str) -> bool:
        """
        Set the icon for a category.

        Parameters
        ----------
        category : str
            The category name.
        icon : str
            The icon string.
        resources_path : str, optional
            Path to the resources directory.

        Returns
        -------
        bool
            True if the icon was changed, False if it was already set.
        """
        icons = TaggingRepository.get_categories_icons()

        if category in icons and icons[category] == icon:
            return False

        icons[category] = icon
        with open(CATEGORIES_ICONS_PATH, 'w') as file:
            yaml.dump(icons, file)
        return True

    @staticmethod
    def add_tag(category: str, tag: str, file_path: str = CATEGORIES_PATH) -> None:
        """Add a tag to a category."""
        categories = TaggingRepository.get_categories(file_path)
        if category in categories:
            if tag in categories[category]:
                raise EntityAlreadyExistsException(f"Tag '{tag}' already exists in category '{category}'")
            categories[category].append(tag)
            with open(file_path, 'w') as file:
                yaml.dump(categories, file)
        else:
            raise EntityNotFoundException(f"Category '{category}' not found")

    @staticmethod
    def delete_tag(category: str, tag: str, file_path: str = CATEGORIES_PATH) -> None:
        """Remove a tag from a category."""
        categories = TaggingRepository.get_categories(file_path)
        if category in categories:
            if tag not in categories[category]:
                raise EntityNotFoundException(f"Tag '{tag}' not found in category '{category}'")
            categories[category].remove(tag)
            with open(file_path, 'w') as file:
                yaml.dump(categories, file)
        else:
            raise EntityNotFoundException(f"Category '{category}' not found")

    @staticmethod
    def relocate_tag(tag: str, old_category: str, new_category: str, file_path: str = CATEGORIES_PATH) -> None:
        """Move a tag from one category to another."""
        categories = TaggingRepository.get_categories(file_path)
        if old_category not in categories:
            raise EntityNotFoundException(f"Category '{old_category}' not found")
        if tag not in categories[old_category]:
            raise EntityNotFoundException(f"Tag '{tag}' not found in category '{old_category}'")
        if new_category not in categories:
            raise EntityNotFoundException(f"Category '{new_category}' not found")
        if tag not in categories[new_category]:
            categories[new_category].append(tag)
        categories[old_category].remove(tag)
        with open(file_path, 'w') as file:
            yaml.dump(categories, file)