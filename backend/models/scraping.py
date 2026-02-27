"""
Scraping history model.
"""

from sqlalchemy import Column, Integer, String

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
        Error details populated when ``status`` is ``FAILED``.
    """

    __tablename__ = Tables.SCRAPING_HISTORY.value

    id = Column(Integer, primary_key=True, autoincrement=True)

    service_name = Column(String, nullable=False)
    provider_name = Column(String, nullable=False)
    account_name = Column(String, nullable=False)
    date = Column(String, nullable=False)  # Timestamp of scrape
    status = Column(String, nullable=False)
    start_date = Column(
        String, nullable=True
    )  # The 'start_date' parameter used for scraping
    error_message = Column(String, nullable=True)  # Error details for failed scrapes
    error_type = Column(String, nullable=True)  # Error category (e.g. CREDENTIALS, TWO_FACTOR_REQUIRED)
