"""
Scraping history repository with SQLAlchemy ORM.
"""
from datetime import datetime, date, timedelta
from typing import List, Dict

import pandas as pd
from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session

from backend.models.scraping import ScrapingHistory
from backend.naming_conventions import Tables, ScrapingHistoryTableFields


class ScrapingHistoryRepository:
    """
    Repository for managing scraping history data and daily limits using ORM.
    """
    FAILED = 'failed'
    SUCCESS = 'success'
    CANCELED = 'canceled'
    IN_PROGRESS = 'in_progress'
    WAITING_FOR_2FA = 'waiting_for_2fa'

    def __init__(self, db: Session):
        self.db = db

    def _ensure_table_exists(self) -> None:
        pass

    def record_scrape_start(self, service_name: str, provider_name: str, account_name: str, start_date: datetime.date, status: str = IN_PROGRESS) -> int:
        """
        Record a scrape start for an account and return the unique scrape id.
        """
        # Original logic used INSERT OR REPLACE based on... checking constraints? 
        # But SQLite schema didn't have specific unique constraint on (service, provider, account, date) 
        # other than implicit or explicit rowid.
        # However, calling it multiple times for same day should probably create new entries 
        # or update existing?
        # "INSERT OR REPLACE" suggests if PK matches. But standard INSERT doesn't assume PK unless provided.
        # Here we just want to create a new record for this "attempt".
        
        history = ScrapingHistory(
            service_name=service_name,
            provider_name=provider_name,
            account_name=account_name,
            date=datetime.now().isoformat(),
            status=status,
            start_date=start_date.isoformat()
        )
        self.db.add(history)
        self.db.commit()
        return history.id
    
    def record_scrape_end(self, scrape_id: int, status: str) -> None:
        stmt = (
            update(ScrapingHistory)
            .where(ScrapingHistory.id == scrape_id)
            .values(status=status)
        )
        self.db.execute(stmt)
        self.db.commit()

    def get_scraping_status(self, scrape_id: int) -> str | None:
        stmt = select(ScrapingHistory.status).where(ScrapingHistory.id == scrape_id)
        return self.db.execute(stmt).scalar()

    def get_scraping_history(self) -> pd.DataFrame:
        """Get the complete scraping history as a DataFrame."""
        stmt = select(ScrapingHistory).order_by(ScrapingHistory.date.desc())
        return pd.read_sql(stmt, self.db.bind)

    def get_last_successful_scrape_date(
        self, 
        service_name: str, 
        provider_name: str, 
        account_name: str
    ) -> str | None:
        """Get the last successful scraping date for an account."""
        stmt = select(ScrapingHistory.date).where(
            ScrapingHistory.service_name == service_name,
            ScrapingHistory.provider_name == provider_name,
            ScrapingHistory.account_name == account_name,
            ScrapingHistory.status == self.SUCCESS
        ).order_by(ScrapingHistory.date.desc()).limit(1)
        
        return self.db.execute(stmt).scalar()

    def clear_old_records(self, days_to_keep: int = 30) -> None:
        """Clear scraping history records older than specified days."""
        cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).isoformat()
        stmt = delete(ScrapingHistory).where(ScrapingHistory.date < cutoff_date)
        self.db.execute(stmt)
        self.db.commit()
