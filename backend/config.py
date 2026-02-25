"""
Centralized configuration management for the Finance Analysis backend.
Handles environment switching between production and demo modes.
"""

import os


class AppConfig:
    """
    Singleton configuration manager.
    """

    _instance = None
    _demo_mode = False

    # Base user directory
    _base_user_dir = os.environ.get(
        "FAD_USER_DIR", os.path.join(os.path.expanduser("~"), ".finance-analysis")
    )

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AppConfig, cls).__new__(cls)
        return cls._instance

    @property
    def is_demo_mode(self) -> bool:
        return self._demo_mode

    @property
    def is_test_mode(self) -> bool:
        """Backwards-compatible alias for is_demo_mode."""
        return self._demo_mode

    def set_demo_mode(self, enabled: bool):
        self._demo_mode = enabled
        # Ensure demo directory exists if entering demo mode
        if enabled:
            os.makedirs(self.get_user_dir(), exist_ok=True)

    def set_test_mode(self, enabled: bool):
        """Backwards-compatible alias for set_demo_mode."""
        self.set_demo_mode(enabled)

    def get_user_dir(self) -> str:
        """Get the current user directory based on mode."""
        if self._demo_mode:
            return os.path.join(self._base_user_dir, "demo_env")
        return self._base_user_dir

    def get_db_path(self) -> str:
        """Get the current database path."""
        # Allow override via env var in non-demo mode only
        if not self._demo_mode and os.environ.get("FAD_DB_PATH"):
            return os.environ.get("FAD_DB_PATH")

        filename = "demo_data.db" if self._demo_mode else "data.db"
        return os.path.join(self.get_user_dir(), filename)

    def get_credentials_path(self) -> str:
        """Get the current credentials file path."""
        if not self._demo_mode and os.environ.get("FAD_CREDENTIALS_PATH"):
            return os.environ.get("FAD_CREDENTIALS_PATH")

        return os.path.join(self.get_user_dir(), "credentials.yaml")

    def get_categories_path(self) -> str:
        """Get the current categories file path."""
        if not self._demo_mode and os.environ.get("FAD_CATEGORIES_PATH"):
            return os.environ.get("FAD_CATEGORIES_PATH")

        return os.path.join(self.get_user_dir(), "categories.yaml")

    def get_categories_icons_path(self) -> str:
        """Get the current categories icons file path."""
        if not self._demo_mode and os.environ.get("FAD_CATEGORIES_ICONS_PATH"):
            return os.environ.get("FAD_CATEGORIES_ICONS_PATH")

        return os.path.join(self.get_user_dir(), "categories_icons.yaml")
