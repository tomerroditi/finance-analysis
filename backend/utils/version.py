"""Single source of truth for the application version.

Reads ``[tool.poetry].version`` from ``pyproject.toml`` once at import
time. Falls back to ``"0.0.0"`` when the file is missing — that happens
in unusual environments (a partial install, a tarball without
``pyproject.toml``) and we'd rather degrade than crash. The fallback is
also what the in-app update check shows as the "current" version when
the file isn't reachable, which keeps the toast suppressed instead of
falsely promising an upgrade.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

try:
    import tomllib  # type: ignore[unused-ignore]
except ModuleNotFoundError:  # Python <3.11 (we require 3.12, but be safe)
    import tomli as tomllib  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

_FALLBACK = "0.0.0"


def _project_root() -> Path:
    """Walk up from this file to find the directory containing ``pyproject.toml``."""
    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        candidate = parent / "pyproject.toml"
        if candidate.is_file():
            return parent
    return here.parent


@lru_cache(maxsize=1)
def get_app_version() -> str:
    """Return the Finance Analysis version string (e.g. ``"1.15.1"``).

    Cached after the first call — the answer doesn't change during a
    process lifetime.
    """
    pyproject = _project_root() / "pyproject.toml"
    if not pyproject.is_file():
        logger.debug("pyproject.toml not found at %s; using fallback version", pyproject)
        return _FALLBACK
    try:
        with pyproject.open("rb") as fh:
            data = tomllib.load(fh)
        return data.get("tool", {}).get("poetry", {}).get("version", _FALLBACK)
    except Exception as exc:
        logger.warning("Couldn't read version from %s: %s", pyproject, exc)
        return _FALLBACK
