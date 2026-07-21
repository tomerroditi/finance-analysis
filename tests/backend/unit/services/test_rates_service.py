"""Tests for RatesService — seeding, prime derivation, lookups, and refresh."""

from unittest.mock import MagicMock, patch

import pytest

from backend.errors import ValidationException
from backend.repositories.interest_rates_repository import InterestRatesRepository
from backend.services.rates_service import RatesService


class TestRatesSeeding:
    """Tests for lazy seeding from the bundled BoI history file."""

    def test_ensure_seeded_populates_empty_series(self, db_session):
        """Verify the bundled YAML seeds the boi_rate series on first access."""
        service = RatesService(db_session)
        history = service.get_history("boi_rate")

        assert len(history) > 20
        # Known anchor points from the bundled history
        assert {"date": "2023-05-22", "value": 4.75} in history
        assert {"date": "2026-01-05", "value": 4.0} in history
        # Ascending by date
        dates = [p["date"] for p in history]
        assert dates == sorted(dates)

    def test_ensure_seeded_is_idempotent(self, db_session):
        """Verify calling ensure_seeded twice does not duplicate points."""
        service = RatesService(db_session)
        service.ensure_seeded()
        count_first = InterestRatesRepository(db_session).count_series("boi_rate")
        service.ensure_seeded()
        count_second = InterestRatesRepository(db_session).count_series("boi_rate")

        assert count_first == count_second


class TestRatesLookups:
    """Tests for prime derivation and step-function lookups."""

    @pytest.fixture()
    def seeded(self, db_session):
        """Service with a small controlled series instead of the bundled seed."""
        repo = InterestRatesRepository(db_session)
        repo.upsert_points(
            "boi_rate",
            [
                {"date": "2022-01-01", "value": 0.1},
                {"date": "2023-01-01", "value": 4.5},
                {"date": "2024-01-01", "value": 4.0},
            ],
            source="seed",
        )
        return RatesService(db_session)

    def test_prime_history_adds_constant_spread(self, seeded):
        """Verify the prime series is the BoI series shifted by +1.5."""
        boi = seeded.get_history("boi_rate")
        prime = seeded.get_history("prime")

        assert [p["date"] for p in boi] == [p["date"] for p in prime]
        for b, p in zip(boi, prime):
            assert abs(p["value"] - (b["value"] + 1.5)) < 1e-9

    def test_unknown_series_raises(self, seeded):
        """Verify asking for an unknown series raises ValidationException."""
        with pytest.raises(ValidationException):
            seeded.get_history("libor")

    def test_get_current_returns_latest_point(self, seeded):
        """Verify get_current reflects the newest step point."""
        current = seeded.get_current()

        assert current["boi_rate"] == 4.0
        assert current["prime"] == 5.5
        assert current["as_of"] == "2024-01-01"

    def test_get_prime_at_walks_step_function(self, seeded):
        """Verify get_prime_at returns the step in effect at the date."""
        assert seeded.get_prime_at("2022-06-01") == 1.6      # 0.1 + 1.5
        assert seeded.get_prime_at("2023-01-01") == 6.0      # step day inclusive
        assert seeded.get_prime_at("2025-01-01") == 5.5      # latest holds
        assert seeded.get_prime_at("2021-01-01") is None     # before the series

    def test_get_prime_steps_anchors_at_from_date(self, seeded):
        """Verify get_prime_steps starts exactly at from_date with the in-effect rate."""
        steps = seeded.get_prime_steps("2022-06-15")

        assert steps[0] == {"date": "2022-06-15", "value": 1.6}
        assert [s["date"] for s in steps[1:]] == ["2023-01-01", "2024-01-01"]

    def test_get_prime_steps_predating_series_anchors_at_earliest(self, seeded):
        """Verify a from_date before the series anchors at the earliest known rate."""
        steps = seeded.get_prime_steps("2020-01-01")

        assert steps[0] == {"date": "2020-01-01", "value": 1.6}


class TestRatesRefresh:
    """Tests for the BoI public API refresh — must never raise."""

    @pytest.fixture()
    def seeded(self, db_session):
        """Service with one known point."""
        InterestRatesRepository(db_session).upsert_points(
            "boi_rate", [{"date": "2024-01-01", "value": 4.5}], source="seed"
        )
        return RatesService(db_session)

    def test_refresh_appends_new_rate(self, seeded):
        """Verify a fetched rate that differs from the latest appends a new point."""
        response = MagicMock()
        response.json.return_value = {"currentInterest": 4.25}
        response.raise_for_status.return_value = None

        with patch("backend.services.rates_service.httpx.get", return_value=response):
            result = seeded.refresh_from_boi()

        assert result["status"] == "updated"
        assert result["boi_rate"] == 4.25
        history = seeded.get_history("boi_rate")
        assert len(history) == 2
        assert history[-1]["value"] == 4.25

    def test_refresh_unchanged_rate_adds_nothing(self, seeded):
        """Verify a fetched rate equal to the latest leaves the series untouched."""
        response = MagicMock()
        response.json.return_value = {"currentInterest": 4.5}
        response.raise_for_status.return_value = None

        with patch("backend.services.rates_service.httpx.get", return_value=response):
            result = seeded.refresh_from_boi()

        assert result["status"] == "unchanged"
        assert len(seeded.get_history("boi_rate")) == 1

    def test_refresh_network_failure_degrades_gracefully(self, seeded):
        """Verify network errors collapse to status=unavailable without raising."""
        with patch(
            "backend.services.rates_service.httpx.get",
            side_effect=OSError("offline"),
        ):
            result = seeded.refresh_from_boi()

        assert result["status"] == "unavailable"
        # Last known rates still reported
        assert result["boi_rate"] == 4.5

    def test_refresh_malformed_payload_degrades_gracefully(self, seeded):
        """Verify an unexpected JSON payload collapses to status=unavailable."""
        response = MagicMock()
        response.json.return_value = {"unexpected": True}
        response.raise_for_status.return_value = None

        with patch("backend.services.rates_service.httpx.get", return_value=response):
            result = seeded.refresh_from_boi()

        assert result["status"] == "unavailable"
