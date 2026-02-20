"""
Centralized configuration management for the Finance Analysis backend.
Handles environment switching between production and test modes.
"""

import os


class AppConfig:
    """Singleton configuration manager for the Finance Analysis backend.

    Provides a single shared instance (via ``__new__``) that controls whether
    the application runs in production or test mode. In test mode all paths
    point to an isolated ``test_env/`` subdirectory so tests never touch
    production data. Paths can also be overridden via environment variables
    (``FAD_USER_DIR``, ``FAD_DB_PATH``, ``FAD_CREDENTIALS_PATH``, etc.).
    """

    _instance = None
    _test_mode = False

    # Base user directory
    _base_user_dir = os.environ.get(
        "FAD_USER_DIR", os.path.join(os.path.expanduser("~"), ".finance-analysis")
    )

    def __new__(cls):
        """Return the shared singleton instance, creating it on first call."""
        if cls._instance is None:
            cls._instance = super(AppConfig, cls).__new__(cls)
        return cls._instance

    @property
    def is_test_mode(self) -> bool:
        """Return ``True`` when the application is running in test mode."""
        return self._test_mode

    def set_test_mode(self, enabled: bool):
        """Enable or disable test mode.

        When enabling, the test user directory is created if it does not exist.

        Parameters
        ----------
        enabled : bool
            ``True`` to switch to the isolated test environment,
            ``False`` to switch back to production.
        """
        self._test_mode = enabled
        # Ensure test directory exists if entering test mode
        if enabled:
            os.makedirs(self.get_user_dir(), exist_ok=True)

    def get_user_dir(self) -> str:
        """Get the current user directory based on mode."""
        if self._test_mode:
            return os.path.join(self._base_user_dir, "test_env")
        return self._base_user_dir

    def get_db_path(self) -> str:
        """Get the current database path."""
        # Allow override via env var in non-test mode only
        if not self._test_mode and os.environ.get("FAD_DB_PATH"):
            return os.environ.get("FAD_DB_PATH")

        filename = "test_data.db" if self._test_mode else "data.db"
        return os.path.join(self.get_user_dir(), filename)

    def get_credentials_path(self) -> str:
        """Get the current credentials file path."""
        if not self._test_mode and os.environ.get("FAD_CREDENTIALS_PATH"):
            return os.environ.get("FAD_CREDENTIALS_PATH")

        return os.path.join(self.get_user_dir(), "credentials.yaml")

    def get_categories_path(self) -> str:
        """Get the current categories file path."""
        if not self._test_mode and os.environ.get("FAD_CATEGORIES_PATH"):
            return os.environ.get("FAD_CATEGORIES_PATH")

        return os.path.join(self.get_user_dir(), "categories.yaml")

    def get_categories_icons_path(self) -> str:
        """Get the current categories icons file path."""
        if not self._test_mode and os.environ.get("FAD_CATEGORIES_ICONS_PATH"):
            return os.environ.get("FAD_CATEGORIES_ICONS_PATH")

        return os.path.join(self.get_user_dir(), "categories_icons.yaml")
