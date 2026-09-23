"""Tests that startup migrations leave the application's logging intact.

``env.py`` used to call ``logging.config.fileConfig`` unconditionally. Run
in-process at startup, that replaced the root handlers (the packaged app's
rotating log file included) and disabled every logger created before it, so
nothing from ``backend.*`` or ``uvicorn.*`` was logged after migrations ran.
"""

import logging
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command

from backend.migrations_runner import in_process_alembic_config
from backend.models import Base

ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point Alembic's online ``env.py`` at a fresh, fully created temp DB."""
    url = f"sqlite:///{tmp_path / 'startup.db'}"
    engine = sa.create_engine(url)
    Base.metadata.create_all(bind=engine)
    engine.dispose()
    monkeypatch.setattr(
        "backend.database.get_database_url", lambda *a, **k: url
    )
    return url


class TestStartupMigrationLogging:
    """Running startup migrations must not reconfigure logging."""

    def test_existing_loggers_stay_enabled(self, temp_db):
        """A logger created before migrations still emits afterwards."""
        probe = logging.getLogger("backend.startup_logging_probe")
        probe.disabled = False

        command.upgrade(in_process_alembic_config(ALEMBIC_INI), "head")

        assert probe.disabled is False

    def test_root_handlers_are_untouched(self, temp_db):
        """The app's root handlers (e.g. the packaged log file) survive."""
        root = logging.getLogger()
        sentinel = logging.NullHandler()
        root.addHandler(sentinel)
        try:
            command.upgrade(in_process_alembic_config(ALEMBIC_INI), "head")
            assert sentinel in root.handlers
        finally:
            root.removeHandler(sentinel)

    def test_config_opts_out_of_file_logging(self):
        """The startup config carries the flag ``env.py`` checks."""
        config = in_process_alembic_config(ALEMBIC_INI)

        assert config.attributes["configure_logger"] is False
