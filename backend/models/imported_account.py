"""Imported-account metadata for file-based data sources.

Each row represents one user-created account that ingests transactions
via uploaded CSV/XLSX files instead of via scraping. The saved
``mapping_json`` blob holds the column mapping the user defined once;
subsequent uploads reuse it.
"""

from sqlalchemy import Column, Integer, String, UniqueConstraint

from backend.constants.tables import Tables
from backend.models.base import Base, TimestampMixin


class ImportedAccount(Base, TimestampMixin):
    """ORM model for file-import data sources.

    Attributes
    ----------
    id : int
        Auto-incremented primary key.
    service : str
        One of ``"banks"``, ``"credit_cards"``, ``"cash"``. Determines
        which transactions table imported rows land in.
    provider : str
        Free-text provider label (e.g. ``"Hapoalim Manual"``,
        ``"Discover"``, ``"Imported"``).
    account_name : str
        Display label, unique within ``(service, provider)``.
    mapping_json : str
        JSON-encoded column mapping. See the design spec for the schema.
    """

    __tablename__ = Tables.IMPORTED_ACCOUNTS.value
    __table_args__ = (
        UniqueConstraint(
            "service", "provider", "account_name",
            name="uq_imported_accounts_service_provider_name",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    service = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    account_name = Column(String, nullable=False)
    mapping_json = Column(String, nullable=False)
