"""
Unit tests for AppConfig singleton configuration manager.

Covers singleton behavior, demo mode switching, directory resolution,
database/credentials/categories path generation, and environment variable overrides.
"""

import os

import pytest

from backend.config import AppConfig


@pytest.fixture(autouse=True)
def reset_config():
    """Reset AppConfig singleton state between tests."""
    config = AppConfig()
    original_demo_mode = config._demo_mode
    original_base_dir = config._base_user_dir
    yield
    config._demo_mode = original_demo_mode
    config._base_user_dir = original_base_dir


class TestAppConfig:
    """Tests for AppConfig singleton behavior and path resolution."""

    def test_singleton_returns_same_instance(self):
        """Verify AppConfig() always returns the same object."""
        config_a = AppConfig()
        config_b = AppConfig()
        assert config_a is config_b

    def test_is_demo_mode_default_false(self):
        """Verify default demo mode is False."""
        config = AppConfig()
        config._demo_mode = False
        assert config.is_demo_mode is False

    def test_set_demo_mode_true(self, tmp_path):
        """Verify enabling demo mode sets is_demo_mode to True."""
        config = AppConfig()
        config._base_user_dir = str(tmp_path)
        config.set_demo_mode(True)
        assert config.is_demo_mode is True

    def test_set_demo_mode_false(self):
        """Verify disabling demo mode sets is_demo_mode to False."""
        config = AppConfig()
        config.set_demo_mode(False)
        assert config.is_demo_mode is False

    def test_get_user_dir_normal_mode(self, tmp_path):
        """Verify get_user_dir returns the base directory in normal mode."""
        config = AppConfig()
        config._demo_mode = False
        config._base_user_dir = str(tmp_path)
        assert config.get_user_dir() == str(tmp_path)

    def test_get_user_dir_demo_mode(self, tmp_path):
        """Verify get_user_dir returns base_dir/demo_env in demo mode."""
        config = AppConfig()
        config._base_user_dir = str(tmp_path)
        config._demo_mode = True
        expected = os.path.join(str(tmp_path), "demo_env")
        assert config.get_user_dir() == expected

    def test_get_db_path_normal(self, tmp_path):
        """Verify get_db_path returns base_dir/data.db in normal mode."""
        config = AppConfig()
        config._demo_mode = False
        config._base_user_dir = str(tmp_path)
        expected = os.path.join(str(tmp_path), "data.db")
        assert config.get_db_path() == expected

    def test_get_db_path_demo_mode(self, tmp_path):
        """Verify get_db_path returns demo_env/demo_data.db in demo mode."""
        config = AppConfig()
        config._base_user_dir = str(tmp_path)
        config._demo_mode = True
        expected = os.path.join(str(tmp_path), "demo_env", "demo_data.db")
        assert config.get_db_path() == expected

    def test_get_db_path_env_override(self, monkeypatch, tmp_path):
        """Verify FAD_DB_PATH env var overrides get_db_path in non-demo mode."""
        config = AppConfig()
        config._demo_mode = False
        config._base_user_dir = str(tmp_path)
        custom_path = str(tmp_path / "custom" / "my.db")
        monkeypatch.setenv("FAD_DB_PATH", custom_path)
        assert config.get_db_path() == custom_path

    def test_get_db_path_env_ignored_in_demo_mode(self, monkeypatch, tmp_path):
        """Verify FAD_DB_PATH env var is ignored when demo mode is enabled."""
        config = AppConfig()
        config._base_user_dir = str(tmp_path)
        config._demo_mode = True
        monkeypatch.setenv("FAD_DB_PATH", "/should/not/be/used")
        expected = os.path.join(str(tmp_path), "demo_env", "demo_data.db")
        assert config.get_db_path() == expected

    def test_get_credentials_path_normal(self, tmp_path):
        """Verify get_credentials_path returns base_dir/credentials.yaml in normal mode."""
        config = AppConfig()
        config._demo_mode = False
        config._base_user_dir = str(tmp_path)
        expected = os.path.join(str(tmp_path), "credentials.yaml")
        assert config.get_credentials_path() == expected

    def test_get_credentials_path_env_override(self, monkeypatch, tmp_path):
        """Verify FAD_CREDENTIALS_PATH env var overrides get_credentials_path."""
        config = AppConfig()
        config._demo_mode = False
        config._base_user_dir = str(tmp_path)
        custom_path = str(tmp_path / "custom_creds.yaml")
        monkeypatch.setenv("FAD_CREDENTIALS_PATH", custom_path)
        assert config.get_credentials_path() == custom_path

    def test_get_credentials_path_env_ignored_in_demo_mode(self, monkeypatch, tmp_path):
        """Verify FAD_CREDENTIALS_PATH env var is ignored in demo mode."""
        config = AppConfig()
        config._base_user_dir = str(tmp_path)
        config._demo_mode = True
        monkeypatch.setenv("FAD_CREDENTIALS_PATH", "/should/not/be/used")
        expected = os.path.join(str(tmp_path), "demo_env", "credentials.yaml")
        assert config.get_credentials_path() == expected

    def test_get_categories_path_normal(self, tmp_path):
        """Verify get_categories_path returns base_dir/categories.yaml in normal mode."""
        config = AppConfig()
        config._demo_mode = False
        config._base_user_dir = str(tmp_path)
        expected = os.path.join(str(tmp_path), "categories.yaml")
        assert config.get_categories_path() == expected

    def test_get_categories_path_env_override(self, monkeypatch, tmp_path):
        """Verify FAD_CATEGORIES_PATH env var overrides get_categories_path."""
        config = AppConfig()
        config._demo_mode = False
        config._base_user_dir = str(tmp_path)
        custom_path = str(tmp_path / "custom_cats.yaml")
        monkeypatch.setenv("FAD_CATEGORIES_PATH", custom_path)
        assert config.get_categories_path() == custom_path

    def test_get_categories_path_env_ignored_in_demo_mode(self, monkeypatch, tmp_path):
        """Verify FAD_CATEGORIES_PATH env var is ignored in demo mode."""
        config = AppConfig()
        config._base_user_dir = str(tmp_path)
        config._demo_mode = True
        monkeypatch.setenv("FAD_CATEGORIES_PATH", "/should/not/be/used")
        expected = os.path.join(str(tmp_path), "demo_env", "categories.yaml")
        assert config.get_categories_path() == expected

    def test_get_categories_icons_path_normal(self, tmp_path):
        """Verify get_categories_icons_path returns base_dir/categories_icons.yaml."""
        config = AppConfig()
        config._demo_mode = False
        config._base_user_dir = str(tmp_path)
        expected = os.path.join(str(tmp_path), "categories_icons.yaml")
        assert config.get_categories_icons_path() == expected

    def test_get_categories_icons_path_env_override(self, monkeypatch, tmp_path):
        """Verify FAD_CATEGORIES_ICONS_PATH env var overrides get_categories_icons_path."""
        config = AppConfig()
        config._demo_mode = False
        config._base_user_dir = str(tmp_path)
        custom_path = str(tmp_path / "custom_icons.yaml")
        monkeypatch.setenv("FAD_CATEGORIES_ICONS_PATH", custom_path)
        assert config.get_categories_icons_path() == custom_path

    def test_get_categories_icons_path_env_ignored_in_demo_mode(self, monkeypatch, tmp_path):
        """Verify FAD_CATEGORIES_ICONS_PATH env var is ignored in demo mode."""
        config = AppConfig()
        config._base_user_dir = str(tmp_path)
        config._demo_mode = True
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
