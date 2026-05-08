"""Cleanup utilities used by the Windows NSIS uninstaller, the macOS
``Uninstall.command`` script, and the in-app ``POST /api/uninstall`` route.

A single source of truth for what counts as "Finance Analysis state" on a
machine: the user-data directory and Keychain entries. Imported as a
library and runnable as a CLI (``python -m backend.uninstall``).
"""

from backend.uninstall.cleanup import CleanupReport, run

__all__ = ["CleanupReport", "run"]
