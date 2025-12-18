"""
Tagging repository for category and tag management.

This repository handles file-based storage for categories and tags.
No Streamlit dependencies - uses pure YAML file I/O.
"""
import os
from typing import Dict, List, Optional

import yaml


# Default paths - can be overridden via environment variables
USER_DIR = os.environ.get('FAD_USER_DIR', os.path.join(os.path.expanduser('~'), '.finance-analysis'))
CATEGORIES_PATH = os.environ.get('FAD_CATEGORIES_PATH', os.path.join(USER_DIR, 'categories.yaml'))
SRC_PATH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TaggingRepository:
    """
    Repository for basic CRUD operations on tagging data.
    
    Handles file-based storage for categories and tags using YAML files.
    """

    @staticmethod
    def load_categories_from_file(file_path: str) -> Dict[str, List[str]]:
        """Load categories and tags from a YAML file."""
        with open(file_path, 'r') as file:
            return yaml.load(file, Loader=yaml.FullLoader) or {}

    @staticmethod
    def save_categories_to_file(categories_and_tags: Dict[str, List[str]], file_path: str) -> None:
        """Save categories and tags to a YAML file."""
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
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
    def get_categories_icons(resources_path: Optional[str] = None) -> Dict[str, str]:
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
        if resources_path is None:
            # Try to locate fad/resources
            fad_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'fad')
            resources_path = os.path.join(fad_path, 'resources')
        
        file_path = os.path.join(resources_path, 'categories_icons.yaml')
        if not os.path.exists(file_path):
            return {}

        with open(file_path, 'r') as file:
            return yaml.load(file, Loader=yaml.FullLoader) or {}

    @staticmethod
    def update_category_icon(category: str, icon: str, resources_path: Optional[str] = None) -> bool:
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
        if resources_path is None:
            fad_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'fad')
            resources_path = os.path.join(fad_path, 'resources')
        
        file_path = os.path.join(resources_path, 'categories_icons.yaml')

        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        icons = {}
        if os.path.exists(file_path):
            with open(file_path, 'r') as file:
                icons = yaml.load(file, Loader=yaml.FullLoader) or {}

        if category in icons and icons[category] == icon:
            return False

        icons[category] = icon
        with open(file_path, 'w') as file:
            yaml.dump(icons, file)
        return True
