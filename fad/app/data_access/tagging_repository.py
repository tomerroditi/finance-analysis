import os
from typing import Dict, List

import yaml

from fad import SRC_PATH


class TaggingRepository:
    """
    Repository for basic CRUD operations on tagging data.
    Contains only data access logic, no business logic.
    """

    @staticmethod
    def load_categories_from_file(file_path: str) -> dict[str, list[str]]:
        """Load categories and tags from a YAML file."""
        with open(file_path, 'r') as file:
            return yaml.load(file, Loader=yaml.FullLoader)

    @staticmethod
    def save_categories_to_file(categories_and_tags: Dict[str, List[str]], file_path: str) -> None:
        """Save categories and tags to a YAML file."""
        with open(file_path, 'w') as file:
            yaml.dump(categories_and_tags, file)

    @staticmethod
    def file_exists(file_path: str) -> bool:
        """Check if a file exists."""
        return os.path.exists(file_path)

    @staticmethod
    def create_directory(dir_path: str) -> None:
        """Create directory if it doesn't exist."""
        os.makedirs(dir_path, exist_ok=True)

    @staticmethod
    def get_categories_icons() -> Dict[str, str]:
        """
        Get the icon for a given category.
        If the category does not have an icon, returns None.

        Parameters:
        ----------
        category: str
            The category to get the icon for.
        file_path: str
            The path to the file where icons are stored.

        Returns:
        str
            The icon for the category, or None if the category does not have an icon.
        """
        file_path = os.path.join(SRC_PATH, 'resources', 'categories_icons.yaml')
        if not os.path.exists(file_path):
            return {}

        with open(file_path, 'r') as file:
            icons = yaml.load(file, Loader=yaml.FullLoader)
        return icons

    @staticmethod
    def update_category_icon(category: str, icon: str) -> bool:
        """
        Set the icon for a given category.

        Parameters:
        ----------
        category: str
            The category to set the icon for.
        icon: str
            The icon to set for the category.
        file_path: str
            The path to the file where icons are stored.
            
        Returns:
        --------
        bool
            True if the new icon is different from the old one, False otherwise.
        """
        file_path = os.path.join(SRC_PATH, 'resources', 'categories_icons.yaml')

        if not os.path.exists(os.path.dirname(file_path)):
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

        icons = {}
        if os.path.exists(file_path):
            with open(file_path, 'r') as file:
                icons = yaml.load(file, Loader=yaml.FullLoader) or {}

        if category in icons and icons[category] == icon:
            return False  # No change

        icons[category] = icon
        with open(file_path, 'w') as file:
            yaml.dump(icons, file)
        return True