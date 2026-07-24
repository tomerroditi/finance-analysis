"""
Investments API routes.

Provides endpoints for investment tracking.
"""

from datetime import date as date_type
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import field_validator
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.errors import ValidationException
from backend.routes.schemas import ApiRequestModel
from backend.services.investments_service import InvestmentsService

router = APIRouter()


def _parse_iso_date(value: str, field_name: str) -> str:
    """Validate that ``value`` is a ``YYYY-MM-DD`` date string.

    Unvalidated date strings are persisted verbatim and only blow up later,
    when analytics parse them — at which point every investment analysis
    endpoint 500s and the offending record can no longer be listed or
    deleted.

    Parameters
    ----------
    value : str
        Candidate ISO date string.
    field_name : str
        Name of the field being validated, used in the error message.

    Returns
    -------
    str
        The unchanged ``value`` when it parses as an ISO date.

    Raises
    ------
    ValidationException
        If ``value`` is not a valid ``YYYY-MM-DD`` date.
    """
    try:
        date_type.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValidationException(
            f"{field_name} must be a valid date in YYYY-MM-DD format"
        )
    return value


class InvestmentCreate(ApiRequestModel):
    category: str
    tag: str
    type: str
    name: str
    interest_rate: Optional[float] = None
    interest_rate_type: str = "fixed"
    rate_spread: Optional[float] = None
    commission_deposit: Optional[float] = None
    commission_management: Optional[float] = None
    commission_withdrawal: Optional[float] = None
    liquidity_date: Optional[str] = None
    maturity_date: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("liquidity_date", "maturity_date")
    @classmethod
    def validate_dates(cls, v: Optional[str]) -> Optional[str]:
        """Ensure optional dates are valid ISO date strings."""
        if v is not None:
            date_type.fromisoformat(v)
        return v


class InvestmentUpdate(ApiRequestModel):
    name: Optional[str] = None
    interest_rate: Optional[float] = None
    interest_rate_type: Optional[str] = None
    rate_spread: Optional[float] = None
    closed_date: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("closed_date")
    @classmethod
    def validate_closed_date(cls, v: Optional[str]) -> Optional[str]:
        """Ensure closed_date is a valid ISO date string."""
        if v is not None:
            date_type.fromisoformat(v)
        return v


class BalanceSnapshotCreate(ApiRequestModel):
    date: str
    balance: float

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        """Ensure the snapshot date is a valid ISO date string."""
        date_type.fromisoformat(v)
        return v


class BalanceSnapshotUpdate(ApiRequestModel):
    date: Optional[str] = None
    balance: Optional[float] = None

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        """Ensure the snapshot date is a valid ISO date string."""
        if v is not None:
            date_type.fromisoformat(v)
        return v


@router.get("/")
def get_investments(
    include_closed: bool = False, db: Session = Depends(get_database)
) -> list[dict[str, Any]]:
    """Return all investment records.

    Parameters
    ----------
    include_closed : bool, optional
        When ``True``, include investments that have been closed.
        Defaults to ``False`` (active investments only).
    """
    service = InvestmentsService(db)
    return service.get_all_investments(include_closed=include_closed)


@router.get("/{investment_id}")
def get_investment(
    investment_id: int, db: Session = Depends(get_database)
) -> dict[str, Any]:
    """Get a specific investment by ID."""
    service = InvestmentsService(db)
    return service.get_investment(investment_id)


@router.get("/analysis/portfolio")
def get_portfolio_analysis(
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Get portfolio-level analysis and metrics."""
    service = InvestmentsService(db)
    return service.get_portfolio_overview()


@router.get("/analysis/balance-history")
def get_portfolio_balance_history(
    include_closed: bool = False,
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Get balance-over-time data for all investments."""
    service = InvestmentsService(db)
    return service.get_portfolio_balance_history(include_closed=include_closed)


@router.get("/{investment_id}/analysis")
def get_investment_analysis(
    investment_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Return detailed analysis for a specific investment.

    Parameters
    ----------
    investment_id : int
        ID of the investment to analyse.
    start_date : str, optional
        ISO date string (YYYY-MM-DD) to restrict the transaction history.
    end_date : str, optional
        ISO date string (YYYY-MM-DD) to restrict the transaction history.
    """
    service = InvestmentsService(db)
    return service.get_investment_analysis(investment_id, start_date, end_date)


@router.post("/")
def create_investment(
    investment: InvestmentCreate, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Create a new investment."""
    service = InvestmentsService(db)
    service.create_investment(
        category=investment.category,
        tag=investment.tag,
        type_=investment.type,
        name=investment.name,
        interest_rate=investment.interest_rate,
        interest_rate_type=investment.interest_rate_type,
        rate_spread=investment.rate_spread,
        commission_deposit=investment.commission_deposit,
        commission_management=investment.commission_management,
        commission_withdrawal=investment.commission_withdrawal,
        liquidity_date=investment.liquidity_date,
        maturity_date=investment.maturity_date,
        notes=investment.notes,
    )
    return {"status": "success"}


@router.put("/{investment_id}")
def update_investment(
    investment_id: int,
    investment: InvestmentUpdate,
    db: Session = Depends(get_database),
) -> dict[str, str]:
    """Update an investment."""
    service = InvestmentsService(db)
    updates = {k: v for k, v in investment.model_dump().items() if v is not None}
    service.update_investment(investment_id, **updates)
    return {"status": "success"}


@router.post("/{investment_id}/close")
def close_investment(
    investment_id: int, closed_date: str, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Mark an investment as closed.

    Parameters
    ----------
    investment_id : int
        ID of the investment to close.
    closed_date : str
        ISO date string (YYYY-MM-DD) recording when the investment was closed.

    Raises
    ------
    ValidationException
        If ``closed_date`` is not a valid ``YYYY-MM-DD`` date.
    """
    _parse_iso_date(closed_date, "closed_date")
    service = InvestmentsService(db)
    service.close_investment(investment_id, closed_date)
    return {"status": "success"}


@router.post("/{investment_id}/reopen")
def reopen_investment(
    investment_id: int, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Reopen a closed investment."""
    service = InvestmentsService(db)
    service.reopen_investment(investment_id)
    return {"status": "success"}


@router.delete("/{investment_id}")
def delete_investment(
    investment_id: int, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Delete an investment."""
    service = InvestmentsService(db)
    service.delete_investment(investment_id)
    return {"status": "success"}


# ── Balance Snapshot Routes ───────────────────────────────────────


@router.get("/{investment_id}/balances")
def get_balance_snapshots(
    investment_id: int, db: Session = Depends(get_database)
) -> list[dict[str, Any]]:
    """Get all balance snapshots for an investment."""
    service = InvestmentsService(db)
    return service.get_balance_snapshots(investment_id)


@router.post("/{investment_id}/balances")
def create_balance_snapshot(
    investment_id: int,
    snapshot: BalanceSnapshotCreate,
    db: Session = Depends(get_database),
) -> dict[str, str]:
    """Create or update a balance snapshot for a specific date."""
    service = InvestmentsService(db)
    service.create_balance_snapshot(investment_id, snapshot.date, snapshot.balance)
    return {"status": "success"}


@router.post("/{investment_id}/balances/calculate")
def calculate_fixed_rate_snapshots(
    investment_id: int,
    end_date: Optional[str] = None,
    db: Session = Depends(get_database),
) -> dict[str, str]:
    """Trigger fixed-rate auto-calculation of balance snapshots."""
    service = InvestmentsService(db)
    service.calculate_fixed_rate_snapshots(investment_id, end_date=end_date)
    return {"status": "success"}


@router.put("/{investment_id}/balances/{snapshot_id}")
def update_balance_snapshot(
    investment_id: int,
    snapshot_id: int,
    snapshot: BalanceSnapshotUpdate,
    db: Session = Depends(get_database),
) -> dict[str, str]:
    """Update an existing balance snapshot."""
    service = InvestmentsService(db)
    updates = {k: v for k, v in snapshot.model_dump().items() if v is not None}
    service.update_balance_snapshot(snapshot_id, **updates)
    return {"status": "success"}


@router.delete("/{investment_id}/balances/{snapshot_id}")
def delete_balance_snapshot(
    investment_id: int,
    snapshot_id: int,
    db: Session = Depends(get_database),
) -> dict[str, str]:
    """Delete a balance snapshot."""
    service = InvestmentsService(db)
    service.delete_balance_snapshot(snapshot_id)
    return {"status": "success"}
