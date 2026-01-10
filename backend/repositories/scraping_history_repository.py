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

    MAX_FAILED_ATTEMPTS_PER_DAY = 3

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

    def record_scraping_attempt(
        self, 
        service_name: str, 
        provider_name: str,
        account_name: str, 
        status: str, 
        start_date: str | date = None
    ) -> None:
        """
        Record a scraping attempt for an account.

        Parameters
        ----------
        service_name : str
            The service name (banks, credit_cards).
        provider_name : str
            The provider name.
        account_name : str
            The account name.
        status : str
            The scraping status ('success', 'failed', 'canceled').
        start_date : str | date, optional
            The date used for scraping.
        """
        if status not in [self.SUCCESS, self.FAILED, self.CANCELED]:
            raise ValueError(f"Invalid status: {status}")

        current_time = datetime.now()
        self.db.execute(
            text(f"""
                INSERT OR REPLACE INTO {Tables.SCRAPING_HISTORY.value} 
                ({ScrapingHistoryTableFields.SERVICE_NAME.value},
                 {ScrapingHistoryTableFields.PROVIDER_NAME.value},
                 {ScrapingHistoryTableFields.ACCOUNT_NAME.value},
                 {ScrapingHistoryTableFields.DATE.value},
                 {ScrapingHistoryTableFields.STATUS.value},
                 {ScrapingHistoryTableFields.START_DATE.value})
                VALUES (:service_name, :provider_name, :account_name, :last_scraped, :status, :start_date)
            """),
            {
                "service_name": service_name,
                "provider_name": provider_name,
                "account_name": account_name,
                "last_scraped": current_time.isoformat(),
                "status": status,
                "start_date": start_date.isoformat() if isinstance(start_date, date) else start_date
            }
        )
        self.db.commit()

    def can_scrape_today(self, service_name: str, provider_name: str, account_name: str) -> bool:
        """
        Check if an account can be scraped today.

        Blocks if:
        - Already scraped successfully today
        - More than MAX_FAILED_ATTEMPTS_PER_DAY failed attempts today
        """
        today = date.today().isoformat()
        
        # Check for successful scrape today
        success_result = self.db.execute(
            text(f"""
                SELECT 1 FROM {Tables.SCRAPING_HISTORY.value}
                WHERE {ScrapingHistoryTableFields.SERVICE_NAME.value} = :service_name
                    AND {ScrapingHistoryTableFields.PROVIDER_NAME.value} = :provider_name
                    AND {ScrapingHistoryTableFields.ACCOUNT_NAME.value} = :account_name
                    AND DATE({ScrapingHistoryTableFields.DATE.value}) = DATE(:date)
                    AND {ScrapingHistoryTableFields.STATUS.value} = :success
                LIMIT 1
            """),
            {
                "service_name": service_name,
                "provider_name": provider_name,
                "account_name": account_name,
                "date": today,
                "success": self.SUCCESS
            }
        )
        if success_result.first() is not None:
            return False

        # Check failed attempts
        fail_result = self.db.execute(
            text(f"""
                SELECT COUNT(*) FROM {Tables.SCRAPING_HISTORY.value}
                WHERE {ScrapingHistoryTableFields.SERVICE_NAME.value} = :service_name
                    AND {ScrapingHistoryTableFields.PROVIDER_NAME.value} = :provider_name
                    AND {ScrapingHistoryTableFields.ACCOUNT_NAME.value} = :account_name
                    AND DATE({ScrapingHistoryTableFields.DATE.value}) = DATE(:date)
                    AND {ScrapingHistoryTableFields.STATUS.value} = :failed
            """),
            {
                "service_name": service_name,
                "provider_name": provider_name,
                "account_name": account_name,
                "date": today,
                "failed": self.FAILED
            }
        )
        if (fail_result.scalar() or 0) >= self.MAX_FAILED_ATTEMPTS_PER_DAY:
            return False

        # Check canceled attempts
        canceled_result = self.db.execute(
            text(f"""
                SELECT COUNT(*) FROM {Tables.SCRAPING_HISTORY.value}
                WHERE {ScrapingHistoryTableFields.SERVICE_NAME.value} = :service_name
                    AND {ScrapingHistoryTableFields.PROVIDER_NAME.value} = :provider_name
                    AND {ScrapingHistoryTableFields.ACCOUNT_NAME.value} = :account_name
                    AND DATE({ScrapingHistoryTableFields.DATE.value}) = DATE(:date)
                    AND {ScrapingHistoryTableFields.STATUS.value} = :canceled
            """),
            {
                "service_name": service_name,
                "provider_name": provider_name,
                "account_name": account_name,
                "date": today,
                "canceled": self.CANCELED
            }
        )
        if (canceled_result.scalar() or 0) >= self.MAX_FAILED_ATTEMPTS_PER_DAY:
            return False

        return True

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

    def get_todays_scraping_summary(self) -> Dict[str, List[str] | Dict[str, int]]:
        """Get a summary of accounts scraped today."""
        today = date.today().isoformat()
        result = self.db.execute(
            text(f"""
                SELECT 
                    {ScrapingHistoryTableFields.SERVICE_NAME.value},
                    {ScrapingHistoryTableFields.PROVIDER_NAME.value},
                    {ScrapingHistoryTableFields.ACCOUNT_NAME.value},
                    {ScrapingHistoryTableFields.STATUS.value}
                FROM {Tables.SCRAPING_HISTORY.value}
                WHERE DATE({ScrapingHistoryTableFields.DATE.value}) = DATE(:date)
            """),
            {"date": today}
        )
        columns = result.keys()
        df = pd.DataFrame(result.fetchall(), columns=columns)

        successful = []
        failed = {}
        canceled = {}

        if not df.empty:
            for _, row in df.iterrows():
                account_id = (
                    f"{row[ScrapingHistoryTableFields.SERVICE_NAME.value]} - "
                    f"{row[ScrapingHistoryTableFields.PROVIDER_NAME.value]} - "
                    f"{row[ScrapingHistoryTableFields.ACCOUNT_NAME.value]}"
                )
                status = row[ScrapingHistoryTableFields.STATUS.value]
                if status == self.SUCCESS:
                    successful.append(account_id)
                elif status == self.FAILED:
                    failed[account_id] = failed.get(account_id, 0) + 1
                elif status == self.CANCELED:
                    canceled[account_id] = canceled.get(account_id, 0) + 1

        all_accounts = set(successful) | set(failed.keys()) | set(canceled.keys())
        unavailable = set(successful) | {k for k, v in failed.items() if v >= self.MAX_FAILED_ATTEMPTS_PER_DAY}
        
        return {
            "succeed_today": successful,
            "failed_today": failed,
            "canceled_today": canceled,
            "available_to_scrape": list(all_accounts - unavailable),
            "unavailable_to_scrape": list(unavailable)
        }

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
