"""Run the app's Alembic migrations in-process."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from backend.runtime import bundle_root

if TYPE_CHECKING:
    from alembic.config import Config

logger = logging.getLogger(__name__)


def alembic_ini_path() -> Path:
    """Return where ``alembic.ini`` lives for this build.

    Returns
    -------
    Path
        ``alembic.ini`` under :func:`backend.runtime.bundle_root`.
    """
    return bundle_root() / "alembic.ini"


def in_process_alembic_config(alembic_ini: Path) -> "Config":
    """Build the Alembic config for migrations run inside the app process.

    Parameters
    ----------
    alembic_ini : Path
        Path to ``alembic.ini``.

    Returns
    -------
    Config
        Config that tells ``env.py`` to leave the app's logging alone —
        ``fileConfig`` would otherwise replace the root handlers and disable
        every logger created before it.
    """
    from alembic.config import Config

    config = Config(str(alembic_ini))
    config.attributes["configure_logger"] = False
    return config


def upgrade_to_head() -> bool:
    """Apply every pending migration to the database the app is using.

    ``env.py`` wires the URL to ``get_database_url()``, so this targets the
    same database (real or demo) the current context resolves.

    Returns
    -------
    bool
        ``False`` when ``alembic.ini`` could not be found and nothing ran.
    """
    from alembic import command

    alembic_ini = alembic_ini_path()
    if not alembic_ini.is_file():
        logger.warning("alembic.ini not found at %s — skipping migrations", alembic_ini)
        return False
    command.upgrade(in_process_alembic_config(alembic_ini), "head")
    return True
