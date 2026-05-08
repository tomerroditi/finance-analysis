"""Single source of truth for "removing Finance Analysis state from this machine".

The same routine is invoked from three call sites:

1. The Windows NSIS uninstaller (via ``python -m backend.uninstall``).
2. The macOS ``Uninstall Finance Analysis.command`` script.
3. The in-app ``POST /api/uninstall`` route (macOS only).

Centralising the logic in one place keeps the three flows consistent: they
all know about the same Keychain service names, the same user-data
directory layout, and the same demo-mode counterpart. The CLI emits a
JSON report so the calling installer/script can show a useful summary
even though it can't import Python state.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


KEYRING_SERVICE_NAMES = (
    "finance-analysis-app",
    "finance-analysis-app-demo",
)

CREDENTIAL_FIELDS = ("password", "secret", "otp_key", "otpLongTermToken")


@dataclass
class CleanupReport:
    """Structured summary of what cleanup did or skipped."""

    wipe_data: bool
    user_dir: str
    user_dir_existed: bool
    user_dir_removed: bool
    keyring_entries_deleted: int
    keyring_entries_attempted: int
    errors: List[str] = field(default_factory=list)
    dry_run: bool = False

    def as_dict(self) -> dict:
        """Return a plain-dict view suitable for ``json.dumps``."""
        return asdict(self)


def _resolve_user_dir() -> Path:
    """Return the canonical Finance Analysis user-data directory.

    Reuses :class:`backend.config.AppConfig` when available so this module
    respects ``FAD_USER_DIR`` overrides (used by tests and by the demo-mode
    plumbing). Falls back to ``~/.finance-analysis`` on import failure so
    the standalone CLI still works when run from outside a fully-configured
    environment.
    """
    try:
        from backend.config import AppConfig

        config = AppConfig()
        # We always operate on the *base* user dir, never the demo subdir,
        # so a wipe nukes both production and demo state.
        base = Path(config._base_user_dir)  # noqa: SLF001
    except Exception:
        base = Path.home() / ".finance-analysis"
    return base


def _enumerate_credential_keys_from_db(
    user_dir: Path,
) -> List[tuple[str, str, str]]:
    """List ``(service, provider, account_name)`` triples from the credentials DB.

    Used to delete the Keychain entries we know about. Best-effort: if the
    DB doesn't exist, isn't readable, or hasn't been initialised yet we
    return an empty list and let the caller fall back to the
    ``finance-analysis-app`` service-level wipe.
    """
    db_path = user_dir / "data.db"
    if not db_path.is_file():
        return []
    try:
        import sqlite3

        with sqlite3.connect(str(db_path)) as conn:
            rows = conn.execute(
                "SELECT service, provider, account_name FROM credentials",
            ).fetchall()
        return [tuple(r) for r in rows]  # type: ignore[misc]
    except Exception as exc:
        logger.debug("Couldn't enumerate credentials from %s: %s", db_path, exc)
        return []


def _delete_keyring_entries(
    triples: List[tuple[str, str, str]],
    *,
    dry_run: bool,
) -> tuple[int, int, List[str]]:
    """Delete every keyring entry the credentials repository would create.

    Returns ``(deleted, attempted, errors)``. Treats both
    ``finance-analysis-app`` and the ``-demo`` namespace, and tries every
    sensitive field name that ``CredentialsRepository`` writes
    (``password``, ``secret``, ``otp_key``, ``otpLongTermToken``).

    A non-existent entry is not an error — keyring's
    ``PasswordDeleteError`` is silently swallowed, matching the credential
    repository's behaviour.
    """
    attempted = 0
    deleted = 0
    errors: List[str] = []

    try:
        import keyring
        import keyring.errors
    except Exception as exc:
        errors.append(f"keyring unavailable: {exc}")
        return 0, 0, errors

    for service in KEYRING_SERVICE_NAMES:
        for triple in triples:
            svc, provider, account = triple
            for field_name in CREDENTIAL_FIELDS:
                key = f"{svc}_{provider}_{account}_{field_name}"
                attempted += 1
                if dry_run:
                    continue
                try:
                    keyring.delete_password(service, key)
                    deleted += 1
                except keyring.errors.PasswordDeleteError:
                    pass
                except Exception as exc:
                    errors.append(f"{service}/{key}: {exc}")
    return deleted, attempted, errors


def run(
    *,
    wipe_data: bool,
    dry_run: bool = False,
    user_dir: Optional[Path] = None,
) -> CleanupReport:
    """Remove Keychain entries and (optionally) the user-data directory.

    Parameters
    ----------
    wipe_data
        When ``True`` the Finance Analysis user-data directory
        (``~/.finance-analysis`` by default) is removed in addition to the
        Keychain entries. When ``False`` only Keychain entries are removed
        — the database, credentials YAML, and categories YAML are left in
        place so a re-install picks up where the user left off.
    dry_run
        When ``True`` no destructive operations are performed but the
        report still describes what *would* have been removed. Used by the
        unit tests and available via ``--dry-run`` on the CLI.
    user_dir
        Override for the user-data directory. Used by tests; production
        callers should leave this ``None`` so :class:`AppConfig` is
        consulted.

    Returns
    -------
    CleanupReport
        Structured summary of what happened, including any non-fatal
        errors. Errors are appended to the report rather than raised so
        the calling installer can finish the rest of its work even if
        Keychain access fails on the user's machine.
    """
    base = (user_dir or _resolve_user_dir()).expanduser()

    triples = _enumerate_credential_keys_from_db(base)
    deleted, attempted, kr_errors = _delete_keyring_entries(triples, dry_run=dry_run)

    user_dir_existed = base.is_dir()
    user_dir_removed = False
    errors = list(kr_errors)

    if wipe_data and user_dir_existed:
        if dry_run:
            user_dir_removed = True
        else:
            try:
                shutil.rmtree(base)
                user_dir_removed = True
            except Exception as exc:
                errors.append(f"removing {base}: {exc}")

    return CleanupReport(
        wipe_data=wipe_data,
        user_dir=str(base),
        user_dir_existed=user_dir_existed,
        user_dir_removed=user_dir_removed,
        keyring_entries_deleted=deleted,
        keyring_entries_attempted=attempted,
        errors=errors,
        dry_run=dry_run,
    )


def cli(argv: Optional[List[str]] = None) -> int:
    """Module entry point for ``python -m backend.uninstall``.

    Returns 0 on success, 1 if any non-fatal errors were collected.
    Always prints a JSON report to stdout so the calling installer can
    surface what happened.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="backend.uninstall",
        description="Remove Finance Analysis state from this machine.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--wipe",
        action="store_true",
        help="Delete Keychain entries AND the user-data directory.",
    )
    group.add_argument(
        "--keep-data",
        action="store_true",
        help="Delete Keychain entries only; preserve user data.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be removed without doing it.",
    )
    args = parser.parse_args(argv)

    report = run(wipe_data=args.wipe, dry_run=args.dry_run)
    print(json.dumps(report.as_dict(), indent=2))
    return 1 if report.errors else 0
