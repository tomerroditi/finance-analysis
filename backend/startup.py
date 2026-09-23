"""One-time work the API does when the process starts and stops.

Nothing here may import keyring-backed code at module level: ``backend.main``
imports this module unconditionally, and the Vercel runtime ships without
``keyring``. Keyring-backed modules are imported inside the functions, which
the lifespan only calls after its Vercel guard.
"""

import logging
import os

from sqlalchemy.orm import Session

from backend.config import AppConfig
from backend.database import get_db_context, get_engine
from backend.migrations_runner import upgrade_to_head
from backend.models import Base

logger = logging.getLogger(__name__)


def _seed_categories(db: Session, config: AppConfig) -> None:
    """Seed the categories table from YAML when it is empty.

    A user-supplied categories file wins over the bundled defaults.

    Parameters
    ----------
    db : Session
        Session to seed through.
    config : AppConfig
        Resolves the user's categories file.
    """
    from backend.repositories.tagging_repository import (
        DEFAULT_CATEGORIES_ICONS_PATH,
        DEFAULT_CATEGORIES_PATH,
        TaggingRepository,
    )

    user_categories_path = config.get_categories_path()
    categories_path = (
        user_categories_path
        if os.path.exists(user_categories_path)
        else DEFAULT_CATEGORIES_PATH
    )
    TaggingRepository(db).seed_from_yaml(categories_path, DEFAULT_CATEGORIES_ICONS_PATH)


def _migrate_credentials(db: Session, config: AppConfig) -> None:
    """Move legacy YAML credentials into the DB and encrypt plaintext rows.

    The YAML import only runs while the credentials table is empty, and it
    also removes the legacy plaintext file; rows written before at-rest field
    encryption existed are then encrypted in place.

    Parameters
    ----------
    db : Session
        Session to migrate through.
    config : AppConfig
        Resolves the legacy credentials file.
    """
    from backend.repositories.credentials_repository import CredentialsRepository

    creds_repo = CredentialsRepository(db)
    creds_repo.migrate_from_yaml(config.get_credentials_path())
    creds_repo.encrypt_plaintext_rows()


def run_startup_tasks() -> None:
    """Bring the database up to date and seed first-run data."""
    logger.info("Starting Finance Analysis API...")
    Base.metadata.create_all(bind=get_engine())
    # ``create_all`` only creates missing tables — it never adds columns to
    # existing ones — so without Alembic every schema change after the
    # initial install would silently fail to land and the ORM would raise
    # "no such column" on first query. Every migration is idempotent (each
    # inspects the schema before altering), so this is safe on fresh installs.
    upgrade_to_head()
    with get_db_context() as db:
        config = AppConfig()
        _seed_categories(db, config)
        _migrate_credentials(db, config)


async def run_shutdown_tasks() -> None:
    """Stop the background scraper event loop."""
    logger.info("Shutting down Finance Analysis API...")
    from backend.services.scraping_service import shutdown_scraper_loop

    await shutdown_scraper_loop()
