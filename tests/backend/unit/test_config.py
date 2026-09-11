"""
Unit tests for AppConfig singleton configuration manager.

Covers singleton behavior, demo mode switching, directory resolution,
database/credentials/categories path generation, and environment variable overrides.
"""

import contextvars
import os

import pytest

from backend.config import AppConfig, _demo_mode_ctx


class TestAppConfig:
    """Tests for AppConfig singleton behavior and path resolution."""

    def test_singleton_returns_same_instance(self):
        """Verify AppConfig() always returns the same object."""
        config_a = AppConfig()
        config_b = AppConfig()
        assert config_a is config_b

    def test_is_demo_mode_default_false(self):
        """Verify a fresh context (nothing ever set) reads real mode."""
        assert contextvars.Context().run(lambda: AppConfig().is_demo_mode) is False

    def test_set_demo_mode_true(self, tmp_path):
        """Verify enabling demo mode sets is_demo_mode to True."""
        config = AppConfig()
        config._base_user_dir = str(tmp_path)
        config.set_demo_mode(True)
        assert config.is_demo_mode is True

    def test_set_demo_mode_false(self, tmp_path):
        """Verify disabling demo mode after enabling it reads real mode again."""
        config = AppConfig()
        config._base_user_dir = str(tmp_path)
        config.set_demo_mode(True)
        config.set_demo_mode(False)
        assert config.is_demo_mode is False

    def test_get_user_dir_normal_mode(self, tmp_path):
        """Verify get_user_dir returns the base directory in normal mode."""
        config = AppConfig()
        config.set_demo_mode(False)
        config._base_user_dir = str(tmp_path)
        assert config.get_user_dir() == str(tmp_path)

    def test_get_user_dir_demo_mode(self, tmp_path):
        """Verify get_user_dir returns base_dir/demo_env in demo mode."""
        config = AppConfig()
        config._base_user_dir = str(tmp_path)
        config.set_demo_mode(True)
        expected = os.path.join(str(tmp_path), "demo_env")
        assert config.get_user_dir() == expected

    def test_get_db_path_normal(self, tmp_path):
        """Verify get_db_path returns base_dir/data.db in normal mode."""
        config = AppConfig()
        config.set_demo_mode(False)
        config._base_user_dir = str(tmp_path)
        expected = os.path.join(str(tmp_path), "data.db")
        assert config.get_db_path() == expected

    def test_get_db_path_demo_mode(self, tmp_path):
        """Verify get_db_path returns demo_env/demo_data.db in demo mode."""
        config = AppConfig()
        config._base_user_dir = str(tmp_path)
        config.set_demo_mode(True)
        expected = os.path.join(str(tmp_path), "demo_env", "demo_data.db")
        assert config.get_db_path() == expected

    def test_get_db_path_env_override(self, monkeypatch, tmp_path):
        """Verify FAD_DB_PATH env var overrides get_db_path in non-demo mode."""
        config = AppConfig()
        config.set_demo_mode(False)
        config._base_user_dir = str(tmp_path)
        custom_path = str(tmp_path / "custom" / "my.db")
        monkeypatch.setenv("FAD_DB_PATH", custom_path)
        assert config.get_db_path() == custom_path

    def test_get_db_path_env_ignored_in_demo_mode(self, monkeypatch, tmp_path):
        """Verify FAD_DB_PATH env var is ignored when demo mode is enabled."""
        config = AppConfig()
        config._base_user_dir = str(tmp_path)
        config.set_demo_mode(True)
        monkeypatch.setenv("FAD_DB_PATH", "/should/not/be/used")
        expected = os.path.join(str(tmp_path), "demo_env", "demo_data.db")
        assert config.get_db_path() == expected

    def test_get_credentials_path_normal(self, tmp_path):
        """Verify get_credentials_path returns base_dir/credentials.yaml in normal mode."""
        config = AppConfig()
        config.set_demo_mode(False)
        config._base_user_dir = str(tmp_path)
        expected = os.path.join(str(tmp_path), "credentials.yaml")
        assert config.get_credentials_path() == expected

    def test_get_credentials_path_env_override(self, monkeypatch, tmp_path):
        """Verify FAD_CREDENTIALS_PATH env var overrides get_credentials_path."""
        config = AppConfig()
        config.set_demo_mode(False)
        config._base_user_dir = str(tmp_path)
        custom_path = str(tmp_path / "custom_creds.yaml")
        monkeypatch.setenv("FAD_CREDENTIALS_PATH", custom_path)
        assert config.get_credentials_path() == custom_path

    def test_get_credentials_path_env_ignored_in_demo_mode(self, monkeypatch, tmp_path):
        """Verify FAD_CREDENTIALS_PATH env var is ignored in demo mode."""
        config = AppConfig()
        config._base_user_dir = str(tmp_path)
        config.set_demo_mode(True)
        monkeypatch.setenv("FAD_CREDENTIALS_PATH", "/should/not/be/used")
        expected = os.path.join(str(tmp_path), "demo_env", "credentials.yaml")
        assert config.get_credentials_path() == expected

    def test_get_categories_path_normal(self, tmp_path):
        """Verify get_categories_path returns base_dir/categories.yaml in normal mode."""
        config = AppConfig()
        config.set_demo_mode(False)
        config._base_user_dir = str(tmp_path)
        expected = os.path.join(str(tmp_path), "categories.yaml")
        assert config.get_categories_path() == expected

    def test_get_categories_path_env_override(self, monkeypatch, tmp_path):
        """Verify FAD_CATEGORIES_PATH env var overrides get_categories_path."""
        config = AppConfig()
        config.set_demo_mode(False)
        config._base_user_dir = str(tmp_path)
        custom_path = str(tmp_path / "custom_cats.yaml")
        monkeypatch.setenv("FAD_CATEGORIES_PATH", custom_path)
        assert config.get_categories_path() == custom_path

    def test_get_categories_path_env_ignored_in_demo_mode(self, monkeypatch, tmp_path):
        """Verify FAD_CATEGORIES_PATH env var is ignored in demo mode."""
        config = AppConfig()
        config._base_user_dir = str(tmp_path)
        config.set_demo_mode(True)
        monkeypatch.setenv("FAD_CATEGORIES_PATH", "/should/not/be/used")
        expected = os.path.join(str(tmp_path), "demo_env", "categories.yaml")
        assert config.get_categories_path() == expected

    def test_get_categories_icons_path_normal(self, tmp_path):
        """Verify get_categories_icons_path returns base_dir/categories_icons.yaml."""
        config = AppConfig()
        config.set_demo_mode(False)
        config._base_user_dir = str(tmp_path)
        expected = os.path.join(str(tmp_path), "categories_icons.yaml")
        assert config.get_categories_icons_path() == expected

    def test_get_categories_icons_path_env_override(self, monkeypatch, tmp_path):
        """Verify FAD_CATEGORIES_ICONS_PATH env var overrides get_categories_icons_path."""
        config = AppConfig()
        config.set_demo_mode(False)
        config._base_user_dir = str(tmp_path)
        custom_path = str(tmp_path / "custom_icons.yaml")
        monkeypatch.setenv("FAD_CATEGORIES_ICONS_PATH", custom_path)
        assert config.get_categories_icons_path() == custom_path

    def test_get_categories_icons_path_env_ignored_in_demo_mode(self, monkeypatch, tmp_path):
        """Verify FAD_CATEGORIES_ICONS_PATH env var is ignored in demo mode."""
        config = AppConfig()
        config._base_user_dir = str(tmp_path)
        config.set_demo_mode(True)
        monkeypatch.setenv("FAD_CATEGORIES_ICONS_PATH", "/should/not/be/used")
        expected = os.path.join(str(tmp_path), "demo_env", "categories_icons.yaml")
        assert config.get_categories_icons_path() == expected

    def test_set_demo_mode_creates_directory(self, tmp_path):
        """Verify set_demo_mode(True) creates the demo_env directory."""
        config = AppConfig()
        config._base_user_dir = str(tmp_path)
        demo_env_dir = os.path.join(str(tmp_path), "demo_env")

        assert not os.path.exists(demo_env_dir)
        config.set_demo_mode(True)
        assert os.path.isdir(demo_env_dir)


class TestDemoModeContextIsolation:
    """Tests that the demo flag is context-local, not process-global."""

    def test_set_returns_token_and_reset_restores(self, tmp_path):
        """Verify set_demo_mode returns a token that reset_demo_mode honours."""
        from backend.config import AppConfig

        config = AppConfig()
        # Pinned so set_demo_mode(True)'s os.makedirs(get_user_dir()) never
        # touches the real ~/.finance-analysis/demo_env on the dev machine
        # running this test.
        config._base_user_dir = str(tmp_path)
        token = config.set_demo_mode(True)
        assert config.is_demo_mode is True
        config.reset_demo_mode(token)
        assert config.is_demo_mode is False

    def test_separate_contexts_do_not_leak(self, tmp_path):
        """Verify demo mode set in one context is invisible in another."""
        from backend.config import AppConfig

        def read_flag() -> bool:
            return AppConfig().is_demo_mode

        config = AppConfig()
        # Pinned so set_demo_mode(True)'s os.makedirs(get_user_dir()) never
        # touches the real ~/.finance-analysis/demo_env on the dev machine
        # running this test.
        config._base_user_dir = str(tmp_path)
        token = config.set_demo_mode(True)
        try:
            # A fresh Context() holds no values, so the var falls back to
            # its default rather than seeing what this context just set.
            fresh = contextvars.Context()
            assert fresh.run(read_flag) is False
        finally:
            # Without this reset the flag leaks into every later test in
            # this module — pytest runs them all in one context.
            config.reset_demo_mode(token)

    def test_forced_mode_overrides_contextvar(self):
        """Verify _forced_mode wins over whatever the context holds."""
        from backend.config import AppConfig

        config = AppConfig()
        token = config.set_demo_mode(False)
        AppConfig._forced_mode = True
        try:
            assert config.is_demo_mode is True
        finally:
            AppConfig._forced_mode = None
            config.reset_demo_mode(token)


class TestBaseUserDirOverride:
    """Tests for the singleton's base-directory override slot."""

    def test_env_var_is_honoured_when_no_override_is_set(self, monkeypatch, tmp_path):
        """Verify FAD_USER_DIR is resolved at call time while un-pinned."""
        config = AppConfig()
        assert config._base_user_dir_override is None
        monkeypatch.setenv("FAD_USER_DIR", str(tmp_path / "env-dir"))
        assert config.get_user_dir() == str(tmp_path / "env-dir")

    def test_override_wins_over_env_and_none_unpins(self, monkeypatch, tmp_path):
        """Verify assigning a path pins the singleton and ``None`` releases it."""
        config = AppConfig()
        monkeypatch.setenv("FAD_USER_DIR", str(tmp_path / "env-dir"))
        config._base_user_dir = str(tmp_path / "pinned")
        assert config.get_user_dir() == str(tmp_path / "pinned")
        config._base_user_dir = None
        assert config.get_user_dir() == str(tmp_path / "env-dir")

    def test_override_lives_on_the_instance_not_the_class(self, tmp_path):
        """Verify the setter and the reader use the same (instance) slot.

        The old class-level default let a caller save the class attribute,
        assign through the setter (which wrote the instance), and "restore"
        the class attribute — leaving the pin in place for every later test.
        """
        config = AppConfig()
        config._base_user_dir = str(tmp_path)
        assert "_base_user_dir_override" in vars(config)
        assert "_base_user_dir_override" not in vars(AppConfig)
