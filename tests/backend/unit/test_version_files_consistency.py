"""Regression tests for the Commitizen ``version_files`` release wiring.

``release.yml`` bumps the version on every merge to ``main`` by rewriting the
files listed under ``[tool.commitizen] version_files`` in ``pyproject.toml``.
``frontend/package-lock.json`` was missing from that list, so the lockfile
stayed pinned at 1.52.1 while ``package.json`` moved to 1.56.3 — every fresh
clone or worktree running ``npm install`` got a spurious two-line diff to
remember not to commit.

Adding the lockfile brings a hazard worth guarding. Commitizen matches the
pattern *per line* and then does a plain substring replace of the current
version on every matching line (``commitizen.bump.update_version_in_files``),
so the ``"version"`` pattern also visits all ~690 dependency entries. A
dependency pinned at a version string containing the app's own version would
be silently rewritten during a release, corrupting the lockfile on ``main``
inside a ``[skip ci]`` bump commit. That is not hypothetical: the lockfile
already carries a package at ``1.52.0``, one patch release away from a
collision with the app version at the time.

These tests fail at PR time — before the merge that triggers the bump — so a
collision is caught while it is still cheap to resolve.
"""

import json
import re
from pathlib import Path

import pytest
import tomllib

REPO_ROOT = Path(__file__).resolve().parents[3]
PYPROJECT = REPO_ROOT / "pyproject.toml"
PACKAGE_JSON = REPO_ROOT / "frontend" / "package.json"
PACKAGE_LOCK = REPO_ROOT / "frontend" / "package-lock.json"


def _app_version() -> str:
    """Return the canonical version from ``pyproject.toml``."""
    with PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)["tool"]["poetry"]["version"]


def _version_files() -> list[str]:
    """Return the raw ``version_files`` entries from the Commitizen config."""
    with PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)["tool"]["commitizen"]["version_files"]


class TestVersionFilesCoverage:
    """Every file carrying the app version must be bumped by Commitizen."""

    @pytest.mark.parametrize(
        "expected",
        ["frontend/package.json", "frontend/package-lock.json"],
    )
    def test_frontend_manifests_are_listed(self, expected):
        """package.json and its lockfile must both be in ``version_files``."""
        paths = [entry.partition(":")[0] for entry in _version_files()]
        assert expected in paths, (
            f"{expected} is missing from [tool.commitizen] version_files, so "
            "the release bump will leave its version field stale."
        )


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


class TestNoDependencyVersionCollision:
    """No dependency may collide with the version Commitizen rewrites."""

    def test_no_dependency_shares_the_app_version(self):
        """A dependency pinned at the app version would be corrupted.

        Commitizen replaces the current version string on every line matching
        ``"version"``. A dependency whose own version *contains* that string
        would be rewritten alongside the two root fields, breaking the
        lockfile's integrity checks on the next ``npm ci``.
        """
        version = _app_version()
        lock = json.loads(PACKAGE_LOCK.read_text())

        collisions = sorted(
            name
            for name, entry in lock.get("packages", {}).items()
            # The root entry ("") is the one that *should* be rewritten.
            if name and version in str(entry.get("version", ""))
        )

        assert not collisions, (
            f"These dependencies carry the app version ({version}) and would "
            f"be rewritten by the release bump: {collisions}. Pin them to a "
            "different version, or narrow the frontend/package-lock.json "
            "pattern in [tool.commitizen] version_files."
        )

    def test_no_other_lockfile_line_carries_the_app_version(self):
        """Only the two root version fields may contain the app version.

        Catches collisions the parsed-JSON check cannot see — a ``resolved``
        URL or an ``integrity`` hash that happens to embed the version string
        on a line the ``"version"`` pattern also matches.
        """
        version = _app_version()
        pattern = re.compile(r'"version"')

        offenders = [
            (number, line.strip())
            for number, line in enumerate(
                PACKAGE_LOCK.read_text().splitlines(), start=1
            )
            if pattern.search(line) and version in line
        ]

        assert len(offenders) == 2, (
            "Expected exactly the two root version fields to match the "
            f"Commitizen pattern, found {len(offenders)}: {offenders}"
        )
