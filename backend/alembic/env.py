"""Alembic migration environment for the app's SQLite database."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Imported for their side effect of registering tables on ``Base.metadata``.
from backend.models import (  # noqa: F401
    bank_balance,
    budget,
    cash_balance,
    category,
    credential,
    investment,
    pending_refund,
    scraping,
    tagging_rules,
    transaction,
)
from backend.models.base import Base

config = context.config

# Only the standalone ``alembic`` CLI owns logging. When the app runs
# migrations at startup it has already configured logging, and ``fileConfig``
# would replace the root handlers and disable every existing logger
# (``backend.*``, ``uvicorn.*``) for the rest of the process.
if config.config_file_name is not None and config.attributes.get(
    "configure_logger", True
):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode, emitting SQL instead of executing it.

    The context is configured with just a URL, so no DBAPI is needed; calls
    to ``context.execute()`` write the statement to the script output.
    """
    from backend.database import get_database_url

    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a live database connection."""
    from backend.database import get_database_url

    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
