"""
Scraping history model.
"""

from sqlalchemy import Column, Integer, String

from backend.models.base import Base, TimestampMixin
from backend.naming_conventions import Tables


class ScrapingHistory(Base, TimestampMixin):
    """
    Model for recording scraping attempts.
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
