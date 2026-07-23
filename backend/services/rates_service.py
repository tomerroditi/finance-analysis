"""
Interest rate series service.

Owns the Bank of Israel key-rate step function that prime-based loan
types are priced against. The series is seeded from a bundled history
file (``backend/resources/boi_rates.yaml``) and can be topped up from
the BoI public API.

Design choices (mirrors ``UpdateService``):

- **Refresh never raises.** Offline, 5xx, malformed JSON — all collapse
  to a structured ``{"status": "unavailable"}`` result. The seeded
  history keeps every rate computation working without network access.
- **Prime is derived, never stored.** Everyday Israeli "prime" is the
  BoI key rate plus a constant 1.5%; storing only the BoI series keeps
  one source of truth.
"""

import logging
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import yaml
from sqlalchemy.orm import Session

from backend.constants.loans import BOI_RATE_SERIES, PRIME_SERIES, PRIME_SPREAD_PCT
from backend.errors import ValidationException
from backend.repositories.interest_rates_repository import InterestRatesRepository

logger = logging.getLogger(__name__)

BOI_RATES_SEED_PATH = Path(__file__).parent.parent / "resources" / "boi_rates.yaml"
BOI_PUBLIC_API_URL = "https://www.boi.org.il/PublicApi/GetInterestRate"
HTTP_TIMEOUT_SECONDS = 5.0


class RatesService:
    """
    Service for interest rate series — seeding, lookups, and refresh.
    """

    def __init__(self, db: Session):
        """
        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.rates_repo = InterestRatesRepository(db)

    def ensure_seeded(self) -> None:
        """Seed the BoI series from the bundled history file if empty."""
        if self.rates_repo.count_series(BOI_RATE_SERIES) > 0:
            return
        try:
            with open(BOI_RATES_SEED_PATH, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except OSError:
            logger.warning("BoI rates seed file missing: %s", BOI_RATES_SEED_PATH)
            return
        points = data.get(BOI_RATE_SERIES, [])
        if points:
            self.rates_repo.upsert_points(BOI_RATE_SERIES, points, source="seed")

    def get_history(self, series: str = BOI_RATE_SERIES) -> List[Dict[str, Any]]:
        """Get the full step-point history of a series.

        Parameters
        ----------
        series : str
            ``boi_rate`` or ``prime`` (derived as BoI + 1.5).

        Returns
        -------
        list[dict]
            Points with ``date`` and ``value``, ascending by date.

        Raises
        ------
        ValidationException
            If the series name is unknown.
        """
        if series not in (BOI_RATE_SERIES, PRIME_SERIES):
            raise ValidationException(f"Unknown rate series: {series}")

        self.ensure_seeded()
        df = self.rates_repo.get_series(BOI_RATE_SERIES)
        if df.empty:
            return []

        offset = PRIME_SPREAD_PCT if series == PRIME_SERIES else 0.0
        return [
            {"date": row["date"], "value": round(float(row["value"]) + offset, 4)}
            for _, row in df.iterrows()
        ]

    def get_current(self) -> Dict[str, Any]:
        """Get the latest known BoI rate and derived prime.

        Returns
        -------
        dict
            ``boi_rate``, ``prime``, and ``as_of`` (date of the latest
            point) — all ``None`` when the series is empty.
        """
        history = self.get_history(BOI_RATE_SERIES)
        if not history:
            return {"boi_rate": None, "prime": None, "as_of": None}
        latest = history[-1]
        return {
            "boi_rate": latest["value"],
            "prime": round(latest["value"] + PRIME_SPREAD_PCT, 4),
            "as_of": latest["date"],
        }

    def get_prime_at(self, at_date: str) -> Optional[float]:
        """Get the prime rate in effect on a given date.

        Parameters
        ----------
        at_date : str
            Date in YYYY-MM-DD format.

        Returns
        -------
        float or None
            Prime rate (BoI + 1.5) at that date, or ``None`` when the
            series has no point on or before the date.
        """
        history = self.get_history(BOI_RATE_SERIES)
        value = None
        for point in history:
            if point["date"] <= at_date:
                value = point["value"]
            else:
                break
        return None if value is None else round(value + PRIME_SPREAD_PCT, 4)

    def get_prime_steps(self, from_date: str) -> List[Dict[str, Any]]:
        """Get prime as a step function starting at ``from_date``.

        The first step is anchored exactly at ``from_date`` (using the
        rate in effect that day) so callers can treat the result as a
        complete piecewise-constant rate curve for a loan originated on
        that date.

        Parameters
        ----------
        from_date : str
            Start date in YYYY-MM-DD format.

        Returns
        -------
        list[dict]
            Points with ``date`` and ``value`` (prime, percent),
            ascending — empty when the series has no data at all.
        """
        history = self.get_history(PRIME_SERIES)
        if not history:
            return []

        anchor_value = None
        steps = []
        for point in history:
            if point["date"] <= from_date:
                anchor_value = point["value"]
            else:
                steps.append(point)
        if anchor_value is None:
            # Loan predates the whole series — anchor at the earliest point.
            anchor_value = steps[0]["value"] if steps else history[0]["value"]
        return [{"date": from_date, "value": anchor_value}] + steps

    def refresh_from_boi(self) -> Dict[str, Any]:
        """Fetch the current key rate from the BoI public API.

        Appends a new step point (dated today, source ``fetched``) when
        the fetched rate differs from the latest known point. Any
        failure — offline, HTTP error, unexpected payload — returns
        ``{"status": "unavailable"}`` without raising.

        Returns
        -------
        dict
            ``status`` (``updated`` / ``unchanged`` / ``unavailable``)
            plus the current rate info on success.
        """
        try:
            response = httpx.get(BOI_PUBLIC_API_URL, timeout=HTTP_TIMEOUT_SECONDS)
            response.raise_for_status()
            payload = response.json()
            rate = payload.get("currentInterest")
            if rate is None:
                rate = payload.get("interestRate")
            rate = float(rate)
        except Exception as exc:  # noqa: BLE001 — never raise, degrade gracefully
            logger.warning("BoI rate refresh failed: %s", exc)
            return {"status": "unavailable", **self.get_current()}

        current = self.get_current()
        if current["boi_rate"] is not None and abs(current["boi_rate"] - rate) < 1e-9:
            return {"status": "unchanged", **current}

        today = date.today().strftime("%Y-%m-%d")
        self.rates_repo.upsert_points(
            BOI_RATE_SERIES, [{"date": today, "value": rate}], source="fetched"
        )
        return {"status": "updated", **self.get_current()}
