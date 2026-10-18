"""One-time data repairs that need the application's own services.

An Alembic revision runs against the schema of its own point in history, so it
repairs data with raw SQL and never imports the ORM or a service — a model
that later gains a column would break every older database still migrating
through it. Some repairs are only expressible through a service (carving a
split, cascading a tag). Those are registered here and run once per database
after every revision has applied, when the schema matches the code; the
``applied_data_fixes`` table remembers which have run.

Fixes run at startup on the database the process opened, never on the demo
database, which is rebuilt from its snapshot instead.
"""

import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

from backend.repositories.applied_data_fixes_repository import (
    AppliedDataFixesRepository,
)

logger = logging.getLogger(__name__)


def _align_linked_refund_tags(db: Session) -> None:
    """Move linked refund money under its purchase's tag.

    Links made before refunds followed their purchase's tag left the refund
    under its own; the budget then overstated the purchase's tag and
    understated the refund's by the same amount.
    """
    from backend.services.refund_tag_alignment import RefundTagAlignmentService

    aligned = RefundTagAlignmentService(db).fix_mismatches()
    if aligned:
        logger.info("Aligned %d linked refunds with their purchases' tags", aligned)


#: Every one-time fix, by the name recorded once it has run. Never rename an
#: entry: the name is how a database knows the fix already ran.
DATA_FIXES: dict[str, Callable[[Session], None]] = {
    "align_linked_refund_tags": _align_linked_refund_tags,
}


def run_pending_data_fixes(db: Session) -> list[str]:
    """Run every registered fix this database has not had yet.

    A fix that raises is logged and left unrecorded, so the next start tries
    it again; the fixes after it still run.

    Parameters
    ----------
    db : Session
        Session on the database to repair.

    Returns
    -------
    list[str]
        Names of the fixes applied by this call.
    """
    repo = AppliedDataFixesRepository(db)
    done = repo.get_names()
    applied = []
    for name, fix in DATA_FIXES.items():
        if name in done:
            continue
        try:
            fix(db)
        except Exception:
            db.rollback()
            logger.exception("Data fix %s failed; it will be retried", name)
            continue
        repo.mark_applied(name)
        applied.append(name)
    return applied
