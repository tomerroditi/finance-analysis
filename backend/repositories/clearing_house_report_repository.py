"""
ClearingHouseReport data access.

Upsert and read the monthly household summaries scraped from the pension
clearing house.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.clearing_house_report import ClearingHouseReport


class ClearingHouseReportRepository:
    """ClearingHouseReport database operations."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_all(self) -> list[ClearingHouseReport]:
        """Return every stored report, oldest first."""
        stmt = select(ClearingHouseReport).order_by(
            ClearingHouseReport.calc_date, ClearingHouseReport.id
        )
        return list(self.db.execute(stmt).scalars().all())

    def upsert(
        self, provider: str, account_name: str, calc_date: str, **fields: Any
    ) -> ClearingHouseReport:
        """Create or update the report for one credential and month.

        Parameters
        ----------
        provider : str
            Scraping provider.
        account_name : str
            Credential label.
        calc_date : str
            The report's as-of date.
        **fields
            Remaining column values.

        Returns
        -------
        ClearingHouseReport
            The created or updated row.
        """
        stmt = select(ClearingHouseReport).where(
            ClearingHouseReport.provider == provider,
            ClearingHouseReport.account_name == account_name,
            ClearingHouseReport.calc_date == calc_date,
        )
        report = self.db.execute(stmt).scalars().first()
        if report is None:
            report = ClearingHouseReport(
                provider=provider, account_name=account_name, calc_date=calc_date
            )
            self.db.add(report)
        for key, value in fields.items():
            setattr(report, key, value)
        self.db.commit()
        self.db.refresh(report)
        return report
