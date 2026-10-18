"""Regression tests for the Commitizen release-bump wiring.

``release.yml`` bumps the version on every merge to ``main`` by rewriting the
files listed under ``[tool.commitizen] version_files`` in ``pyproject.toml``,
then committing with ``-a``.

``frontend/package-lock.json`` carries the app version twice — top level and
the root ``packages[""]`` entry — and is not one of those files. Commitizen
matches a pattern per line and substring-replaces the version on every
matching line, and the root entry's ``"version"`` line is indented exactly like
every dependency's, so a dependency sharing the app version would be rewritten
too. That stopped being hypothetical at 2.0.0, which eight dependencies share.
A ``pre_bump_hook`` (``build/bump_lockfile_version.py``) rewrites the two app
fields by position instead; these tests pin that wiring and its precision.
"""

import json
import re
from pathlib import Path

import pytest
import tomllib

from build.bump_lockfile_version import bump

REPO_ROOT = Path(__file__).resolve().parents[3]
PYPROJECT = REPO_ROOT / "pyproject.toml"
PACKAGE_JSON = REPO_ROOT / "frontend" / "package.json"
PACKAGE_LOCK = REPO_ROOT / "frontend" / "package-lock.json"


def _app_version() -> str:
    """Return the canonical version from ``pyproject.toml``."""
    with PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)["tool"]["poetry"]["version"]


def _pre_bump_hooks() -> list[str]:
    """Return the ``pre_bump_hooks`` entries from the Commitizen config."""
    with PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)["tool"]["commitizen"].get("pre_bump_hooks", [])


def _version_files() -> list[str]:
    """Return the raw ``version_files`` entries from the Commitizen config."""
    with PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)["tool"]["commitizen"]["version_files"]


class TestVersionFilesCoverage:
    """Every file carrying the app version must be bumped by Commitizen."""

    def test_package_json_is_listed(self):
        """package.json is rewritten through ``version_files``."""
        paths = [entry.partition(":")[0] for entry in _version_files()]
        assert "frontend/package.json" in paths

    def test_lockfile_is_bumped_by_the_hook_not_a_pattern(self):
        """The lockfile is bumped by the hook, never by a line pattern."""
        paths = [entry.partition(":")[0] for entry in _version_files()]
        assert "frontend/package-lock.json" not in paths
        assert "python build/bump_lockfile_version.py" in _pre_bump_hooks()


class TestVersionsAreInSync:
    """The three recorded versions must agree at every commit."""

    def test_package_json_matches_pyproject(self):
        """``frontend/package.json`` must carry the pyproject version."""
        assert json.loads(PACKAGE_JSON.read_text())["version"] == _app_version()

    def test_lockfile_matches_pyproject(self):
        """Both version fields in the lockfile must carry that version."""
        lock = json.loads(PACKAGE_LOCK.read_text())
        version = _app_version()

        assert lock["version"] == version
        assert lock["packages"][""]["version"] == version


class TestLockfileBumpHook:
    """The hook rewrites the app's two version fields and nothing else."""

    def test_bumps_only_the_app_fields(self):
        """Dependencies sharing the app version keep it; the diff is two lines."""
        text = PACKAGE_LOCK.read_text()

        bumped = bump(text, "99.0.0")

        lock = json.loads(bumped)
        assert lock["version"] == "99.0.0"
        assert lock["packages"][""]["version"] == "99.0.0"
        before, after = text.split("\n"), bumped.split("\n")
        changed = [i for i, (x, y) in enumerate(zip(before, after, strict=True)) if x != y]
        assert len(changed) == 2
        original = json.loads(text)["packages"]
        assert {k: v.get("version") for k, v in lock["packages"].items() if k} == {
            k: v.get("version") for k, v in original.items() if k
        }
        assert bumped.endswith("\n") == text.endswith("\n")

    def test_rejects_a_lockfile_without_the_root_entry(self):
        """A lockfile not shaped the way npm writes it fails loudly."""
        with pytest.raises(ValueError):
            bump('{\n  "name": "frontend",\n  "version": "1.0.0"\n}\n', "1.0.1")
