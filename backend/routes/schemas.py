"""Shared Pydantic schemas and parameter types for route requests and responses."""

from datetime import date
from typing import Annotated

from fastapi import Path
from pydantic import AfterValidator, BaseModel, ConfigDict

from backend.errors import ValidationException

# Calendar bounds shared by request bodies and path parameters. Years outside
# this window are typos, not budgets, and used to reach the service layer as
# real rows (or, for auto-fill, hundreds of them).
MIN_YEAR = 2000
MAX_YEAR = 2100

YearPath = Path(ge=MIN_YEAR, le=MAX_YEAR)
MonthPath = Path(ge=1, le=12)


def _check_iso_date(value: str) -> str:
    """Return ``value`` unchanged if it parses as a ``YYYY-MM-DD`` date.

    Unvalidated date strings are persisted verbatim and only blow up later,
    when analytics parse them — at which point every endpoint reading the
    record 500s and it can no longer be listed or deleted.

    Parameters
    ----------
    value : str
        Candidate ISO date string.

    Returns
    -------
    str
        The unchanged ``value``.

    Raises
    ------
    ValueError
        If ``value`` is not a valid ISO date; inside a request model Pydantic
        turns it into a 422 validation error.
    """
    date.fromisoformat(value)
    return value


# A request-body ``str`` field that must be a ``YYYY-MM-DD`` date (else 422).
IsoDateStr = Annotated[str, AfterValidator(_check_iso_date)]


def require_iso_date(value: str, field_name: str) -> str:
    """Validate a ``YYYY-MM-DD`` query parameter, answering 400 when it is not one.

    The query-parameter counterpart of :data:`IsoDateStr`: those endpoints
    have always reported a malformed date as a 400 with a readable message
    rather than a 422.

    Parameters
    ----------
    value : str
        Candidate ISO date string.
    field_name : str
        Name of the parameter being validated, used in the error message.

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
        return _check_iso_date(value)
    except (TypeError, ValueError) as e:
        raise ValidationException(
            f"{field_name} must be a valid date in YYYY-MM-DD format"
        ) from e


class ApiRequestModel(BaseModel):
    """Base for request bodies: rejects NaN/Infinity in every float field.

    Python's JSON parser accepts ``NaN``/``Infinity`` literals and bare
    ``float`` fields let them through, so a single poisoned money value would
    NaN-propagate through every pandas aggregation. Request models with
    numeric fields must inherit from this base instead of ``BaseModel``.
    """

    model_config = ConfigDict(allow_inf_nan=False)


class StatusResponse(BaseModel):
    """Generic ``{"status": ...}`` acknowledgement returned by write endpoints."""

    status: str
