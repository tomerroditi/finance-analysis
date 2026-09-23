"""Facts about the environment the backend process runs in."""

import os
import sys
from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parent.parent


def is_vercel() -> bool:
    """Return whether the process is running as a Vercel serverless function.

    Returns
    -------
    bool
        ``True`` when the ``VERCEL`` env var is set (Vercel sets it, and
        ``index.py`` defaults it).
    """
    return bool(os.environ.get("VERCEL"))


def source_root() -> Path:
    """Return the repository checkout the ``backend`` package was loaded from.

    Returns
    -------
    Path
        The directory that contains ``backend/``.
    """
    return _SOURCE_ROOT


def bundle_root() -> Path:
    """Return the directory that holds the app's bundled data files.

    In a PyInstaller-frozen build that is ``sys._MEIPASS`` — the temp dir the
    bootloader extracts into at launch; everywhere else (dev, pip install,
    Vercel) it is the source checkout.

    Returns
    -------
    Path
        Root to resolve ``alembic.ini`` and ``frontend/dist`` against.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", ""))
    return _SOURCE_ROOT
