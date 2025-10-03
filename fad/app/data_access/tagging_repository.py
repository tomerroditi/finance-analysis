import os
from typing import Dict, List

import yaml


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