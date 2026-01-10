"""
Scraping history repository with pure SQLAlchemy (no Streamlit dependencies).

This module manages scraping attempt history and daily limits.
"""
from datetime import datetime, date, timedelta
from typing import List, Dict

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.naming_conventions import Tables, ScrapingHistoryTableFields


class ScrapingHistoryRepository:
    """
    Repository for managing scraping history data and daily limits.
    
    Tracks when accounts were last scraped and enforces daily limits
    to prevent excessive requests to financial institutions.
    """
    FAILED = 'failed'
    SUCCESS = 'success'
    CANCELED = 'canceled'
    IN_PROGRESS = 'in_progress'

    def __init__(self, db: Session):
        """
        Initialize the ScrapingHistoryRepository.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db
        self._ensure_table_exists()

    def _ensure_table_exists(self) -> None:
        """Create the scraping history table if it doesn't exist."""
        self.db.execute(
            text(f"""
                CREATE TABLE IF NOT EXISTS {Tables.SCRAPING_HISTORY.value} (
                    {ScrapingHistoryTableFields.SERVICE_NAME.value} TEXT NOT NULL,
                    {ScrapingHistoryTableFields.PROVIDER_NAME.value} TEXT NOT NULL,
                    {ScrapingHistoryTableFields.ACCOUNT_NAME.value} TEXT NOT NULL,
                    {ScrapingHistoryTableFields.DATE.value} TEXT NOT NULL,
                    {ScrapingHistoryTableFields.STATUS.value} TEXT NOT NULL,
                    {ScrapingHistoryTableFields.START_DATE.value} TEXT
                )
            """)
        )
        self.db.commit()

    def record_scrape_start(self, service_name: str, provider_name: str, account_name: str, start_date: datetime.date) -> int:
        """
        Record a scrape start for an account and return the unique scrape id.

        Parameters
        ----------
        service_name : str
            The service name (banks, credit_cards).
        provider_name : str
            The provider name.
        account_name : str
            The account name.
        start_date : str
            The date used for scraping.

        Returns
        -------
        int
            The unique scrape id.
        """
        result = self.db.execute(
            text(f"""
                INSERT OR REPLACE INTO {Tables.SCRAPING_HISTORY.value} 
                ({ScrapingHistoryTableFields.SERVICE_NAME.value},
                 {ScrapingHistoryTableFields.PROVIDER_NAME.value},
                 {ScrapingHistoryTableFields.ACCOUNT_NAME.value},
                 {ScrapingHistoryTableFields.DATE.value},
                 {ScrapingHistoryTableFields.STATUS.value},
                 {ScrapingHistoryTableFields.START_DATE.value})
                VALUES (:service_name, :provider_name, :account_name, :date, :status, :start_date)
            """),
            {
                "service_name": service_name,
                "provider_name": provider_name,
                "account_name": account_name,
                "date": datetime.now().isoformat(),
                "status": self.IN_PROGRESS,
                "start_date": start_date.isoformat()
            }
        )
        self.db.commit()
        return result.lastrowid
    
    def record_scrape_end(self, scrape_id: int, status: str) -> None:
        self.db.execute(
            text(f"""
                UPDATE {Tables.SCRAPING_HISTORY.value}
                SET {ScrapingHistoryTableFields.STATUS.value} = :status
                WHERE {ScrapingHistoryTableFields.ID.value} = :scrape_id
            """),
            {
                "status": status,
                "scrape_id": scrape_id
            }
        )
        self.db.commit()

    def get_scraping_status(self, service_name: str, provider_name: str, account_name: str) -> str:
        result = self.db.execute(
            text(f"""
                SELECT {ScrapingHistoryTableFields.STATUS.value} FROM {Tables.SCRAPING_HISTORY.value}
                WHERE {ScrapingHistoryTableFields.SERVICE_NAME.value} = :service_name
                    AND {ScrapingHistoryTableFields.PROVIDER_NAME.value} = :provider_name
                    AND {ScrapingHistoryTableFields.ACCOUNT_NAME.value} = :account_name
                LIMIT 1
            """),
            {
                "service_name": service_name,
                "provider_name": provider_name,
                "account_name": account_name,
            }
        )
        return result.scalar()

    def get_scraping_history(self) -> pd.DataFrame:
        """Get the complete scraping history as a DataFrame."""
        result = self.db.execute(
            text(f"""
                SELECT * FROM {Tables.SCRAPING_HISTORY.value}
                ORDER BY {ScrapingHistoryTableFields.DATE.value} DESC
            """)
        )
        columns = result.keys()
        data = result.fetchall()
        return pd.DataFrame(data, columns=columns)

    def get_last_successful_scrape_date(
        self, 
        service_name: str, 
        provider_name: str, 
        account_name: str
    ) -> str | None:
        """Get the last successful scraping date for an account."""
        result = self.db.execute(
            text(f"""
                SELECT {ScrapingHistoryTableFields.DATE.value} 
                FROM {Tables.SCRAPING_HISTORY.value}
                WHERE {ScrapingHistoryTableFields.SERVICE_NAME.value} = :service_name
                    AND {ScrapingHistoryTableFields.PROVIDER_NAME.value} = :provider_name
                    AND {ScrapingHistoryTableFields.ACCOUNT_NAME.value} = :account_name
                    AND {ScrapingHistoryTableFields.STATUS.value} = :success
                ORDER BY {ScrapingHistoryTableFields.DATE.value} DESC
                LIMIT 1
            """),
            {
                "service_name": service_name,
                "provider_name": provider_name,
                "account_name": account_name,
                "success": self.SUCCESS
            }
        )
        row = result.first()
        return row[0] if row else None

    def clear_old_records(self, days_to_keep: int = 30) -> None:
        """Clear scraping history records older than specified days."""
        cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).isoformat()
        self.db.execute(
            text(f"""
                DELETE FROM {Tables.SCRAPING_HISTORY.value}
                WHERE {ScrapingHistoryTableFields.DATE.value} < :cutoff_date
            """),
            {"cutoff_date": cutoff_date}
        )
        self.db.commit()
