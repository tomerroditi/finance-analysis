from datetime import datetime, date
from typing import List, Dict
import pandas as pd
from sqlalchemy.sql import text
from streamlit.connections import SQLConnection

from fad.app.naming_conventions import Tables, ScrapingHistoryTableFields


class ScrapingHistoryRepository:
    """
    Repository for managing scraping history data and daily limits.

    This class provides methods for tracking when accounts were last scraped
    and enforcing daily scraping limits to prevent excessive requests to
    financial institutions.

    Attributes
    ----------
    conn : SQLConnection
        Database connection object.
    """
    FAILED = 'failed'
    SUCCESS = 'success'
    CANCELED = 'canceled'

    MAX_FAILED_ATTEMPTS_PER_DAY = 3

    def __init__(self, conn: SQLConnection = None):
        """
        Initialize the ScrapingHistoryRepository.

        Parameters
        ----------
        conn : SQLConnection, optional
            Database connection object. If None, operations will require
            a connection to be passed explicitly.
        """
        self.conn = conn
        self._ensure_table_exists()

    def _ensure_table_exists(self):
        """
        Create the scraping history table if it doesn't exist.
        """
        with self.conn.session as s:
            s.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS {Tables.SCRAPING_HISTORY.value} (
                        {ScrapingHistoryTableFields.SERVICE_NAME.value} TEXT NOT NULL,
                        {ScrapingHistoryTableFields.PROVIDER_NAME.value} TEXT NOT NULL,
                        {ScrapingHistoryTableFields.ACCOUNT_NAME.value} TEXT NOT NULL,
                        {ScrapingHistoryTableFields.LAST_SCRAPED.value} TEXT NOT NULL,
                        {ScrapingHistoryTableFields.STATUS.value} TEXT NOT NULL,
                    )
                    """
                )
            )
            s.commit()

    def record_scraping_attempt(self, service_name: str, provider_name: str,
                              account_name: str, status: str) -> None:
        """
        Record a scraping attempt for an account.

        Parameters
        ----------
        service_name : str
            The service name (banks, credit_cards).
        provider_name : str
            The provider name (hapoalim, isracard, etc.).
        account_name : str
            The account name.
        status : Literal['success', 'failed', 'cancelled']
            The scraping status.
        """
        if status not in [self.SUCCESS, self.FAILED, self.CANCELED]:
            raise ValueError(f"Invalid status: {status}. Must be one of "
                             f"'{self.SUCCESS}', '{self.FAILED}', '{self.CANCELED}'.")

        current_time = datetime.now()

        with self.conn.session as s:
            s.execute(
                text(
                    f"""
                    INSERT OR REPLACE INTO {Tables.SCRAPING_HISTORY.value} 
                    ({ScrapingHistoryTableFields.SERVICE_NAME.value},
                     {ScrapingHistoryTableFields.PROVIDER_NAME.value},
                     {ScrapingHistoryTableFields.ACCOUNT_NAME.value},
                     {ScrapingHistoryTableFields.LAST_SCRAPED.value},
                     {ScrapingHistoryTableFields.STATUS.value})
                    VALUES (:service_name, :provider_name, :account_name, :last_scraped, :status)
                    """
                ),
                {
                    "service_name": service_name,
                    "provider_name": provider_name,
                    "account_name": account_name,
                    "last_scraped": current_time.isoformat(),
                    "status": status
                }
            )
            s.commit()

    def can_scrape_today(self, service_name: str, provider_name: str, account_name: str) -> bool:
        """
        Check if an account can be scraped today:
        - block if already scraped successfully today.
        - block if more than MAX_FAILED_ATTEMPTS_PER_DAY failed attempts today.

        Parameters
        ----------
        service_name : str
            The service name (banks, credit_cards).
        provider_name : str
            The provider name (hapoalim, isracard, etc.).
        account_name : str
            The account name.

        Returns
        -------
        bool
            True if the account can be scraped today, False otherwise.
        """
        with self.conn.session as s:
            success_result = s.execute(
                text(
                    f"""
                    SELECT 1 FROM {Tables.SCRAPING_HISTORY.value}
                    WHERE {ScrapingHistoryTableFields.SERVICE_NAME.value} = :service_name
                        AND {ScrapingHistoryTableFields.PROVIDER_NAME.value} = :provider_name
                        AND {ScrapingHistoryTableFields.ACCOUNT_NAME.value} = :account_name
                        AND DATE({ScrapingHistoryTableFields.LAST_SCRAPED.value}) = DATE(:date)
                        AND {ScrapingHistoryTableFields.STATUS.value} = :success
                    LIMIT 1
                    """
                ),
                {
                    "service_name": service_name,
                    "provider_name": provider_name,
                    "account_name": account_name,
                    "date": date.today().isoformat(),
                    "success": self.SUCCESS
                }
            )

            if success_result.first() is not None:
                return False

            fail_result = s.execute(
                text(
                    f"""
                    SELECT COUNT(*) FROM {Tables.SCRAPING_HISTORY.value}
                    WHERE {ScrapingHistoryTableFields.SERVICE_NAME.value} = :service_name
                        AND {ScrapingHistoryTableFields.PROVIDER_NAME.value} = :provider_name
                        AND {ScrapingHistoryTableFields.ACCOUNT_NAME.value} = :account_name
                        AND DATE({ScrapingHistoryTableFields.LAST_SCRAPED.value}) = DATE(:date)
                        AND {ScrapingHistoryTableFields.STATUS.value} = :failed
                    """
                ),
                {
                    "service_name": service_name,
                    "provider_name": provider_name,
                    "account_name": account_name,
                    "date": date.today().isoformat(),
                    "failed": self.FAILED
                }
            )
            fail_count = fail_result.scalar() or 0
            if fail_count >= self.MAX_FAILED_ATTEMPTS_PER_DAY:
                return False

            canceled_result = s.execute(
                text(
                    f"""
                    SELECT COUNT(*) FROM {Tables.SCRAPING_HISTORY.value}
                    WHERE {ScrapingHistoryTableFields.SERVICE_NAME.value} = :service_name
                        AND {ScrapingHistoryTableFields.PROVIDER_NAME.value} = :provider_name
                        AND {ScrapingHistoryTableFields.ACCOUNT_NAME.value} = :account_name
                        AND DATE({ScrapingHistoryTableFields.LAST_SCRAPED.value}) = DATE(:date)
                        AND {ScrapingHistoryTableFields.STATUS.value} = :canceled
                    """
                ),
                {
                    "service_name": service_name,
                    "provider_name": provider_name,
                    "account_name": account_name,
                    "date": date.today().isoformat(),
                    "canceled": self.CANCELED
                }
            )
            canceled_count = canceled_result.scalar() or 0
            if canceled_count >= self.MAX_FAILED_ATTEMPTS_PER_DAY:
                return False

            return True

    def get_scraping_history(self) -> pd.DataFrame:
        """
        Get the complete scraping history.

        Returns
        -------
        pd.DataFrame
            DataFrame containing all scraping history records.
        """
        with self.conn.session as s:
            result = s.execute(
                text(
                    f"""
                    SELECT * FROM {Tables.SCRAPING_HISTORY.value}
                    ORDER BY {ScrapingHistoryTableFields.LAST_SCRAPED.value} DESC
                    """
                )
            )
            df = pd.DataFrame(result.fetchall())
            if not df.empty:
                df.columns = result.keys()
            return df

    def get_todays_scraping_summary(self) -> Dict[str, List[str] | Dict[str, int]]:
        """
        Get a summary of accounts scraped today.

        Returns
        -------
        Dict[str, List[str] | Dict[str, int]]
            Dictionary with keys:
            - 'scraped_today': List of accounts successfully scraped today.
            - 'failed_today': Dict of accounts that failed today with failure counts.
            - 'canceled_today': Dict of accounts that were canceled today with counts.
            - 'available_to_scrape': List of accounts still available to scrape today.
            - 'unavailable_to_scrape': List of accounts that cannot be scraped today.
        """
        with self.conn.session as s:
            result = s.execute(
                text(
                    f"""
                    SELECT 
                        {ScrapingHistoryTableFields.SERVICE_NAME.value},
                        {ScrapingHistoryTableFields.PROVIDER_NAME.value},
                        {ScrapingHistoryTableFields.ACCOUNT_NAME.value},
                        {ScrapingHistoryTableFields.LAST_SCRAPED.value},
                        {ScrapingHistoryTableFields.STATUS.value}
                    FROM {Tables.SCRAPING_HISTORY.value}
                    WHERE DATE({ScrapingHistoryTableFields.LAST_SCRAPED.value}) = DATE(:date)
                    """
                ),
                {"date": date.today().isoformat()}
            )
            df = pd.DataFrame(result.fetchall())
            if not df.empty:
                df.columns = result.keys()

            successful_scraped_today = []
            failed_scraped_today = {}
            canceled_scraped_today = {}
            available_to_scrape = []

            if not df.empty:
                for _, row in df.iterrows():
                    account_id = f"{row[ScrapingHistoryTableFields.SERVICE_NAME.value]} - " \
                                 f"{row[ScrapingHistoryTableFields.PROVIDER_NAME.value]} - " \
                                 f"{row[ScrapingHistoryTableFields.ACCOUNT_NAME.value]}"
                    if row[ScrapingHistoryTableFields.STATUS.value] == self.SUCCESS:
                        successful_scraped_today.append(account_id)
                    elif row[ScrapingHistoryTableFields.STATUS.value] == self.FAILED:
                        failed_scraped_today[account_id] = failed_scraped_today.get(account_id, 0) + 1
                    elif row[ScrapingHistoryTableFields.STATUS.value] == self.CANCELED:
                        canceled_scraped_today[account_id] = canceled_scraped_today.get(account_id, 0) + 1

            all_accounts = set(df.apply(
                lambda row: f"{row[ScrapingHistoryTableFields.SERVICE_NAME.value]} - "
                            f"{row[ScrapingHistoryTableFields.PROVIDER_NAME.value]} - "
                            f"{row[ScrapingHistoryTableFields.ACCOUNT_NAME.value]}",
                axis=1
            ).tolist())
            scraped_accounts = set(successful_scraped_today) | set({k: v for k, v in failed_scraped_today.items() if v >= self.MAX_FAILED_ATTEMPTS_PER_DAY}.keys())
            available_to_scrape = list(all_accounts - scraped_accounts)
            return {
                "succeed_today": successful_scraped_today,
                "failed_today": failed_scraped_today,
                "canceled_today": canceled_scraped_today,
                "available_to_scrape": available_to_scrape,
                "unavailable_to_scrape": list(scraped_accounts)
            }

    def clear_old_records(self, days_to_keep: int = 30) -> None:
        """
        Clear scraping history records older than specified days.

        Parameters
        ----------
        days_to_keep : int, default 30
            Number of days of history to keep.
        """
        cutoff_date = datetime.now() - pd.Timedelta(days=days_to_keep)
        with self.conn.session as s:
            s.execute(
                text(
                    f"""
                    DELETE FROM {Tables.SCRAPING_HISTORY.value}
                    WHERE {ScrapingHistoryTableFields.LAST_SCRAPED.value} < :cutoff_date
                    """
                ),
                {"cutoff_date": cutoff_date.isoformat()}
            )
            s.commit()
