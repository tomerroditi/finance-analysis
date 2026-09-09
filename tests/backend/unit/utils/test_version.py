"""Tests for the single-source-of-truth app version reader.

``get_app_version`` is memoised, so every test clears the cache before and
after it runs; the pyproject location is redirected via ``_project_root``
so no test depends on the real repository file.
"""

from unittest.mock import patch

import pytest

from backend.utils import version
from backend.utils.version import _FALLBACK, _project_root, get_app_version


@pytest.fixture(autouse=True)
def _clear_version_cache():
    """Drop the lru_cache so each test sees a fresh read."""
    get_app_version.cache_clear()
    yield
    get_app_version.cache_clear()


class TestProjectRoot:
    """Locating the directory that holds ``pyproject.toml``."""

    def test_finds_the_repository_root(self):
        """The real checkout has a pyproject.toml at the returned root."""
        root = _project_root()
        assert (root / "pyproject.toml").is_file()
        assert (root / "backend" / "utils" / "version.py").is_file()

    def test_falls_back_to_the_module_directory_when_nothing_is_found(self, tmp_path):
        """With no pyproject anywhere up the tree, the module's own dir is returned."""
        fake_module = tmp_path / "pkg" / "sub" / "version.py"
        fake_module.parent.mkdir(parents=True)
        fake_module.write_text("")

        with patch.object(version, "__file__", str(fake_module)):
            assert _project_root() == fake_module.parent


class TestGetAppVersion:
    """Reading the version string with graceful degradation."""

    def test_reads_the_poetry_version(self, tmp_path):
        """The ``[tool.poetry].version`` value is returned verbatim."""
        (tmp_path / "pyproject.toml").write_text('[tool.poetry]\nversion = "9.8.7"\n')

        with patch.object(version, "_project_root", return_value=tmp_path):
            assert get_app_version() == "9.8.7"

    def test_matches_the_real_pyproject(self):
        """Against the actual checkout the value is a dotted semver, never the fallback."""
        value = get_app_version()
        assert value != _FALLBACK
        assert len(value.split(".")) == 3

    def test_missing_file_returns_fallback(self, tmp_path):
        """No pyproject at the root degrades to ``0.0.0`` instead of raising."""
        with patch.object(version, "_project_root", return_value=tmp_path):
            assert get_app_version() == _FALLBACK

    def test_missing_version_key_returns_fallback(self, tmp_path):
        """A pyproject without ``[tool.poetry].version`` degrades to the fallback."""
        (tmp_path / "pyproject.toml").write_text('[tool.poetry]\nname = "x"\n')

        with patch.object(version, "_project_root", return_value=tmp_path):
            assert get_app_version() == _FALLBACK

    def test_malformed_toml_returns_fallback(self, tmp_path):
        """A parse error is logged and degrades to the fallback."""
        (tmp_path / "pyproject.toml").write_text("[tool.poetry\nversion = ")

        with patch.object(version, "_project_root", return_value=tmp_path):
            assert get_app_version() == _FALLBACK

    def test_result_is_cached_across_calls(self, tmp_path):
        """The file is read once; a later rewrite is not observed until the cache is cleared."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[tool.poetry]\nversion = "1.0.0"\n')

        with patch.object(version, "_project_root", return_value=tmp_path):
            assert get_app_version() == "1.0.0"
            pyproject.write_text('[tool.poetry]\nversion = "2.0.0"\n')
            assert get_app_version() == "1.0.0"
            get_app_version.cache_clear()
            assert get_app_version() == "2.0.0"
