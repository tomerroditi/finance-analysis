"""
Scraping history model.
"""

from sqlalchemy import Column, Index, Integer, String

from backend.models.base import Base, TimestampMixin
from backend.constants.tables import Tables


class ScrapingHistory(Base, TimestampMixin):
    """ORM model recording each scraping attempt for audit and rate-limiting purposes.

    The repository enforces a daily limit of one successful scrape per account by
    querying this table before starting a new scrape.

    Attributes
    ----------
    service_name : str
        Service type scraped (e.g. ``banks``, ``credit_cards``).
    provider_name : str
        Provider identifier (e.g. ``hapoalim``, ``isracard``).
    account_name : str
        User-assigned account label.
    date : str
        ISO timestamp of when the scrape ran.
    status : str
        Outcome: ``SUCCESS``, ``FAILED``, or ``CANCELED``.
    start_date : str, optional
        The ``start_date`` parameter passed to the scraper (oldest data to fetch).
    error_message : str, optional
        Technical error details populated when ``status`` is ``FAILED`` — the
        provider's own message, HTTP body or exception text. Written for
        diagnosis, not for display as-is.
    error_type : str, optional
        Machine-readable failure category (``INVALID_PASSWORD``,
        ``ACCOUNT_BLOCKED``, ``TIMEOUT``, ``GENERAL_ERROR``, …) mirroring the
        scraper's ``ScrapingResult.error_type``. Kept separate from
        ``error_message`` so the UI can show friendly, translated copy while the
        raw provider text stays available for debugging.
    """

    __tablename__ = Tables.SCRAPING_HISTORY.value
    __table_args__ = (
        Index(
            "ix_scraping_history_service_provider_account_status",
            "service_name",
            "provider_name",
            "account_name",
            "status",
        ),
        Index("ix_scraping_history_date", "date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    service_name = Column(String, nullable=False)
    provider_name = Column(String, nullable=False)
    account_name = Column(String, nullable=False)
    date = Column(String, nullable=False)  # Timestamp of scrape
    status = Column(String, nullable=False)
    start_date = Column(
        String, nullable=True
    )  # The 'start_date' parameter used for scraping
    # Technical detail for failed scrapes (provider message / exception text).
    error_message = Column(String, nullable=True)
    # Failure category driving the user-facing message; see class docstring.
    error_type = Column(String, nullable=True)
