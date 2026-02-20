"""
Scraping history repository with SQLAlchemy ORM.
"""

from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from backend.models.scraping import ScrapingHistory


class ScrapingHistoryRepository:
    """
    Repository for managing scraping history data and daily limits using ORM.
    """

    FAILED = "failed"
    SUCCESS = "success"
    CANCELED = "canceled"
    IN_PROGRESS = "in_progress"
    WAITING_FOR_2FA = "waiting_for_2fa"

    def __init__(self, db: Session):
        """
        Parameters
        ----------
        db : Session
            SQLAlchemy database session used for all ORM operations.
        """
        self.db = db

    def _ensure_table_exists(self) -> None:
        pass

    def record_scrape_start(
        self,
        service_name: str,
        provider_name: str,
        account_name: str,
        start_date: datetime.date,
        status: str = IN_PROGRESS,
    ) -> int:
        """Record the start of a scraping operation and return its ID.

        Parameters
        ----------
        service_name : str
            Name of the financial service being scraped (e.g. "credit_cards", "banks").
        provider_name : str
            Name of the specific provider being scraped (e.g. "isracard", "hapoalim").
        account_name : str
            Identifier of the account being scraped.
        start_date : datetime.date
            Start date for the data range to be scraped.
        status : str, optional
            Initial status to record for the operation, by default IN_PROGRESS.

        Returns
        -------
        int
            Unique scraping history record ID used to update the record on completion
            via `record_scrape_end`.
        """
        history = ScrapingHistory(
            service_name=service_name,
            provider_name=provider_name,
            account_name=account_name,
            date=datetime.now().isoformat(),
            status=status,
            start_date=start_date.isoformat(),
        )
        self.db.add(history)
        self.db.commit()
        return history.id

    def record_scrape_end(
        self, scrape_id: int, status: str, error_message: str = None
    ) -> None:
        """Update a scraping record with its final status and optional error.

        Parameters
        ----------
        scrape_id : int
            ID of the scraping record to update, as returned by `record_scrape_start`.
        status : str
            Final status of the scraping operation. Expected values are SUCCESS,
            FAILED, or CANCELED.
        error_message : str, optional
            Human-readable error details if status is FAILED, by default None.

        Returns
        -------
        None
        """
        stmt = (
            update(ScrapingHistory)
            .where(ScrapingHistory.id == scrape_id)
            .values(status=status, error_message=error_message)
        )
        self.db.execute(stmt)
        self.db.commit()

    def get_scraping_status(self, scrape_id: int) -> str | None:
        """Get the current status of a scraping operation.

        Parameters
        ----------
        scrape_id : int
            ID of the scraping record to look up.

        Returns
        -------
        str or None
            Current status string for the record. Possible values are IN_PROGRESS,
            SUCCESS, FAILED, CANCELED, or WAITING_FOR_2FA. Returns None if no
            record with the given ID exists.
        """
        stmt = select(ScrapingHistory.status).where(ScrapingHistory.id == scrape_id)
        return self.db.execute(stmt).scalar()

    def get_error_message(self, scrape_id: int) -> str | None:
        """Get the error message for a failed scraping operation.

        Parameters
        ----------
        scrape_id : int
            ID of the scraping record to look up.

        Returns
        -------
        str or None
            Error message string recorded for the operation, or None if no error
            was recorded or no record with the given ID exists.
        """
        stmt = select(ScrapingHistory.error_message).where(
            ScrapingHistory.id == scrape_id
        )
        return self.db.execute(stmt).scalar()

    def get_scraping_history(self) -> pd.DataFrame:
        """Get the complete scraping history as a DataFrame.

        Returns
        -------
        pd.DataFrame
            All scraping history rows ordered by date descending. Columns include:
            id, service_name, provider_name, account_name, date, status,
            start_date, error_message.
        """
        stmt = select(ScrapingHistory).order_by(ScrapingHistory.date.desc())
        return pd.read_sql(stmt, self.db.bind)

    def get_last_successful_scrape_date(
        self, service_name: str, provider_name: str, account_name: str
    ) -> str | None:
        """Get the last successful scraping date for an account.

        Parameters
        ----------
        service_name : str
            Name of the financial service (e.g. "credit_cards", "banks").
        provider_name : str
            Name of the specific provider (e.g. "isracard", "hapoalim").
        account_name : str
            Identifier of the account.

        Returns
        -------
        str or None
            ISO datetime string of the most recent successful scrape for the
            given account, or None if the account has never been scraped
            successfully.
        """
        stmt = (
            select(ScrapingHistory.date)
            .where(
                ScrapingHistory.service_name == service_name,
                ScrapingHistory.provider_name == provider_name,
                ScrapingHistory.account_name == account_name,
                ScrapingHistory.status == self.SUCCESS,
            )
            .order_by(ScrapingHistory.date.desc())
            .limit(1)
        )

        return self.db.execute(stmt).scalar()

    def clear_old_records(self, days_to_keep: int = 30) -> None:
        """Clear scraping history records older than specified days.

        Parameters
        ----------
        days_to_keep : int, optional
            Records whose date is older than this many days from now will be
            deleted, by default 30.

        Returns
        -------
        None
        """
        cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).isoformat()
        stmt = delete(ScrapingHistory).where(ScrapingHistory.date < cutoff_date)
        self.db.execute(stmt)
        self.db.commit()
