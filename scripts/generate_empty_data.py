"""Generate a pre-built empty SQLite database for the finance analysis dashboard.

Produces ``backend/resources/empty_data.db`` — every ORM table created, the
``categories`` table seeded from the bundled default-categories YAML, every
other table empty.

Used by the Vercel deployment: when a visitor toggles demo mode off, the
empty DB is copied over to ``/tmp/finance-analysis/data.db`` so the app has
a usable empty state with default categories instead of pointing at a
nonexistent file.

Regenerate when the ORM schema changes (new tables) or the default category
set / icons change. Small additive column drift is handled at runtime by
``sync_missing_columns`` in ``backend/demo_setup.py``.

Usage
-----
    python scripts/generate_empty_data.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from backend.models.base import Base  # noqa: E402
# Importing the package re-exports every model class, ensuring all tables
# are registered on Base.metadata before create_all runs.
from backend.models import (  # noqa: F401, E402
    BankBalance,
    BankTransaction,
    BudgetRule,
    CashBalance,
    CashTransaction,
    Category,
    CreditCardTransaction,
    InsuranceAccount,
    InsuranceTransaction,
    Investment,
    InvestmentBalanceSnapshot,
    Liability,
    ManualInvestmentTransaction,
    PendingRefund,
    RefundLink,
    RetirementGoal,
    ScrapingHistory,
    SplitTransaction,
    TaggingRule,
)
from backend.repositories.tagging_repository import (  # noqa: E402
    DEFAULT_CATEGORIES_ICONS_PATH,
    DEFAULT_CATEGORIES_PATH,
    TaggingRepository,
)


DB_PATH = PROJECT_ROOT / "backend" / "resources" / "empty_data.db"


def main() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()

    engine = create_engine(f"sqlite:///{DB_PATH}", poolclass=NullPool)
    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    with SessionLocal() as db:
        TaggingRepository(db).seed_from_yaml(
            DEFAULT_CATEGORIES_PATH, DEFAULT_CATEGORIES_ICONS_PATH
        )

    print(f"Wrote {DB_PATH}")


if __name__ == "__main__":
    main()
