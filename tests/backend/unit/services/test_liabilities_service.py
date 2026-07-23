"""Tests for LiabilitiesService using real in-memory SQLite database."""

from datetime import date
from unittest.mock import patch

from sqlalchemy import select

from backend.models.liability import LiabilityTransaction
from backend.services.liabilities_service import LiabilitiesService


class _FakeDate(date):
    """Date subclass that overrides today() for testing."""

    _today = date(2023, 12, 15)

    @classmethod
    def today(cls):
        return cls._today


class TestLiabilitiesService:
    """Tests for LiabilitiesService covering amortization, enrichment, and analysis."""

    def test_calculate_amortization_schedule(self):
        """Verify standard amortization: 12000 at 6% for 12 months produces correct schedule."""
        schedule = LiabilitiesService.calculate_amortization_schedule(
            principal=12000.0,
            annual_rate=6.0,
            term_months=12,
            start_date=date(2024, 1, 1),
        )

        assert len(schedule) == 12
        # Monthly payment ≈ 1032.80 (standard annuity formula)
        assert abs(schedule[0]["payment"] - 1032.80) < 0.01
        # First interest ≈ 12000 * 0.005 = 60.0
        assert abs(schedule[0]["interest_portion"] - 60.0) < 0.01
        # Last remaining balance ≈ 0
        assert abs(schedule[-1]["remaining_balance"]) < 0.01

    def test_calculate_amortization_zero_rate(self):
        """Verify zero-interest amortization: equal payments with no interest."""
        schedule = LiabilitiesService.calculate_amortization_schedule(
            principal=12000.0,
            annual_rate=0.0,
            term_months=12,
            start_date=date(2024, 1, 1),
        )

        assert len(schedule) == 12
        assert abs(schedule[0]["payment"] - 1000.0) < 0.01
        assert schedule[0]["interest_portion"] == 0.0
        assert abs(schedule[-1]["remaining_balance"]) < 0.01

    def test_get_all_liabilities_with_metrics(self, db_session, seed_liabilities):
        """Verify get_all_liabilities returns enriched records with only active entries by default."""
        service = LiabilitiesService(db_session)
        liabilities = service.get_all_liabilities(include_paid_off=False)

        assert len(liabilities) == 1
        record = liabilities[0]
        assert record["name"] == "Car Loan"

        # Enriched calculated fields must be present
        assert "monthly_payment" in record
        assert "total_interest" in record
        assert "remaining_balance" in record
        assert "total_paid" in record
        assert "percent_paid" in record

        # 3 payments of 1150 each
        assert abs(record["total_paid"] - 3450.0) < 0.01
        assert record["percent_paid"] > 0

    def test_get_liability_analysis(self, db_session, seed_liabilities):
        """Verify get_liability_analysis returns schedule, transactions, and summary."""
        service = LiabilitiesService(db_session)
        car_loan = seed_liabilities["liabilities"][0]
        analysis = service.get_liability_analysis(car_loan.id)

        assert "schedule" in analysis
        assert "transactions" in analysis
        assert "actual_vs_expected" in analysis
        assert "summary" in analysis

        # 48-month loan → 48 schedule entries
        assert len(analysis["schedule"]) == 48

        # 4 transactions: 1 disbursement + 3 payments
        assert len(analysis["transactions"]) == 4

        summary = analysis["summary"]
        assert summary["payments_made"] == 3
        assert abs(summary["total_payments"] - 3450.0) < 0.01
        assert abs(summary["total_receipts"] - 50000.0) < 0.01
        # Remaining balance is read off the schedule after 3 payments —
        # interest portions are NOT counted as principal reduction.
        expected_balance = analysis["schedule"][2]["remaining_balance"]
        assert abs(summary["remaining_balance"] - expected_balance) < 0.01
        # Strictly greater than the naive principal - payments figure
        assert summary["remaining_balance"] > 50000.0 - 3450.0

    def test_analysis_interest_split_matches_schedule(self, db_session, seed_liabilities):
        """Verify interest_paid + interest_remaining equals total schedule interest."""
        service = LiabilitiesService(db_session)
        car_loan = seed_liabilities["liabilities"][0]
        analysis = service.get_liability_analysis(car_loan.id)
        summary = analysis["summary"]

        total_schedule_interest = sum(
            e["interest_portion"] for e in analysis["schedule"]
        )

        # interest_paid + interest_remaining == total schedule interest
        assert abs(
            (summary["interest_paid"] + summary["interest_remaining"])
            - total_schedule_interest
        ) < 0.01

    def test_analysis_interest_paid_from_actual_payments(self, db_session, seed_liabilities):
        """Verify interest_paid is based on first N schedule entries matching payment count."""
        service = LiabilitiesService(db_session)
        car_loan = seed_liabilities["liabilities"][0]
        analysis = service.get_liability_analysis(car_loan.id)
        summary = analysis["summary"]
        schedule = analysis["schedule"]

        # 3 payments made → interest_paid = sum of first 3 schedule interest portions
        expected_interest_paid = sum(
            e["interest_portion"] for e in schedule[:3]
        )
        # ≈ 187.50 + 183.93 + 180.34 = 551.77
        assert abs(summary["interest_paid"] - expected_interest_paid) < 0.01
        assert abs(summary["interest_paid"] - 551.77) < 1.0

    def test_analysis_interest_remaining_from_future_schedule(self, db_session, seed_liabilities):
        """Verify interest_remaining is sum of schedule entries after payments made."""
        service = LiabilitiesService(db_session)
        car_loan = seed_liabilities["liabilities"][0]
        analysis = service.get_liability_analysis(car_loan.id)
        summary = analysis["summary"]
        schedule = analysis["schedule"]

        # Remaining = sum of entries 4..48
        expected_remaining = sum(
            e["interest_portion"] for e in schedule[3:]
        )
        assert abs(summary["interest_remaining"] - expected_remaining) < 0.01
        assert abs(summary["interest_remaining"] - 4176.60) < 1.0

    def test_get_liability_transactions(self, db_session, seed_liabilities):
        """Verify get_liability_transactions returns 4 matched transactions with disbursement first."""
        service = LiabilitiesService(db_session)
        car_loan = seed_liabilities["liabilities"][0]
        transactions = service.get_liability_transactions(car_loan.id)

        assert len(transactions) == 4

        # First transaction is the disbursement (positive amount)
        first = transactions[0]
        assert first["amount"] > 0
        assert first["tag"] == "Car Loan"
        assert first["category"] == "Liabilities"

    def test_detect_tag_transactions_with_receipt(self, db_session, seed_liabilities):
        """Verify detect_tag_transactions finds receipt and payments for an existing tag."""
        service = LiabilitiesService(db_session)
        result = service.detect_tag_transactions("Car Loan")

        assert result["has_receipt"] is True
        assert result["receipt"] is not None
        assert result["receipt"]["amount"] == 50000.0
        assert result["receipt"]["date"] == "2023-06-01"
        assert len(result["payments"]) == 3

    def test_detect_tag_transactions_no_match(self, db_session, seed_liabilities):
        """Verify detect_tag_transactions returns empty when tag has no transactions."""
        service = LiabilitiesService(db_session)
        result = service.detect_tag_transactions("Nonexistent Tag")

        assert result["has_receipt"] is False
        assert result["receipt"] is None
        assert len(result["payments"]) == 0

    def test_detect_tag_transactions_payments_only(self, db_session, seed_liabilities):
        """Verify detect_tag_transactions returns no receipt when only payments exist."""
        from backend.models.transaction import BankTransaction

        # Add payments-only tag (no positive disbursement)
        txn = BankTransaction(
            id="bank_orphan_payment",
            date="2024-01-01",
            provider="leumi",
            account_name="Checking",
            description="Orphan Payment",
            amount=-500.0,
            category="Liabilities",
            tag="Orphan Loan",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        db_session.add(txn)
        db_session.commit()

        service = LiabilitiesService(db_session)
        result = service.detect_tag_transactions("Orphan Loan")

        assert result["has_receipt"] is False
        assert result["receipt"] is None
        assert len(result["payments"]) == 1

    @patch("backend.services.liabilities_service.date", _FakeDate)
    def test_generate_missing_transactions(self, db_session, seed_liabilities):
        """Verify generate_missing_transactions creates entries for months without payments."""
        # Car Loan: start 2023-06-01, payments exist for Jul/Aug/Sep 2023
        # _FakeDate.today() returns 2023-12-15 so months Oct/Nov/Dec should be generated
        _FakeDate._today = date(2023, 12, 15)

        service = LiabilitiesService(db_session)
        car_loan = seed_liabilities["liabilities"][0]

        created = service.generate_missing_transactions(car_loan.id)
        assert created == 3  # Oct, Nov, Dec

        # Verify transactions were inserted
        gen_txns = db_session.execute(
            select(LiabilityTransaction).where(
                LiabilityTransaction.liability_id == car_loan.id
            )
        ).scalars().all()
        assert len(gen_txns) == 3
        assert all(t.amount < 0 for t in gen_txns)
        assert {t.payment_number for t in gen_txns} == {4, 5, 6}

    @patch("backend.services.liabilities_service.date", _FakeDate)
    def test_generate_missing_transactions_idempotent(self, db_session, seed_liabilities):
        """Verify calling generate twice does not create duplicate transactions."""
        _FakeDate._today = date(2023, 12, 15)

        service = LiabilitiesService(db_session)
        car_loan = seed_liabilities["liabilities"][0]

        first_run = service.generate_missing_transactions(car_loan.id)
        second_run = service.generate_missing_transactions(car_loan.id)

        assert first_run == 3
        assert second_run == 0

    @patch("backend.services.liabilities_service.date", _FakeDate)
    def test_get_liability_transactions_includes_generated(self, db_session, seed_liabilities):
        """Verify get_liability_transactions merges real and generated transactions."""
        _FakeDate._today = date(2023, 11, 15)

        service = LiabilitiesService(db_session)
        car_loan = seed_liabilities["liabilities"][0]

        # Generate 2 missing months (Oct, Nov)
        service.generate_missing_transactions(car_loan.id)

        transactions = service.get_liability_transactions(car_loan.id)
        # 4 real (1 disbursement + 3 payments) + 2 generated
        assert len(transactions) == 6

        # Verify generated ones have the liability_transactions source
        generated = [t for t in transactions if t.get("source") == "liability_transactions"]
        assert len(generated) == 2


class TestAmortizationStrategies:
    """Tests for the equal-principal and balloon amortization methods."""

    def test_equal_principal_constant_principal_portion(self):
        """Verify equal-principal schedules keep a constant principal portion with declining interest."""
        schedule = LiabilitiesService.calculate_amortization_schedule(
            principal=12000.0,
            annual_rate=6.0,
            term_months=12,
            start_date=date(2024, 1, 1),
            amortization_method="equal_principal",
        )

        assert len(schedule) == 12
        assert all(abs(e["principal_portion"] - 1000.0) < 0.01 for e in schedule)
        # First interest: 12000 * 0.5% = 60; declines every month
        assert abs(schedule[0]["interest_portion"] - 60.0) < 0.01
        assert schedule[0]["interest_portion"] > schedule[1]["interest_portion"]
        # Payments decline over time; balance amortizes to zero
        assert schedule[0]["payment"] > schedule[-1]["payment"]
        assert abs(schedule[-1]["remaining_balance"]) < 0.01

    def test_balloon_interest_only_until_final_payment(self):
        """Verify balloon schedules pay interest only, with principal due at maturity."""
        schedule = LiabilitiesService.calculate_amortization_schedule(
            principal=12000.0,
            annual_rate=6.0,
            term_months=12,
            start_date=date(2024, 1, 1),
            amortization_method="balloon",
        )

        assert len(schedule) == 12
        # All but the last: interest only, balance untouched
        for entry in schedule[:-1]:
            assert entry["principal_portion"] == 0.0
            assert abs(entry["payment"] - 60.0) < 0.01
            assert abs(entry["remaining_balance"] - 12000.0) < 0.01
        # Final payment repays the full principal plus its interest
        assert abs(schedule[-1]["principal_portion"] - 12000.0) < 0.01
        assert abs(schedule[-1]["payment"] - 12060.0) < 0.01
        assert abs(schedule[-1]["remaining_balance"]) < 0.01

    def test_shpitzer_reamortizes_on_rate_step(self):
        """Verify a rate hike mid-loan raises the Shpitzer payment from that month on."""
        rate_steps = [
            {"date": "2024-01-01", "value": 3.0},
            {"date": "2024-07-15", "value": 6.0},
        ]
        schedule = LiabilitiesService.calculate_amortization_schedule(
            principal=100000.0,
            annual_rate=3.0,
            term_months=24,
            start_date=date(2024, 1, 1),
            amortization_method="shpitzer",
            rate_steps=rate_steps,
        )

        # Rate applies from the first payment whose interest period starts
        # on/after the step: payment #8 (period Aug 1 → Sep 1) is the first
        # fully priced at 6% (the Jul 15 step lands mid-period of #7).
        assert all(e["annual_rate"] == 3.0 for e in schedule[:7])
        assert all(e["annual_rate"] == 6.0 for e in schedule[7:])
        # Payment is constant within each rate regime and jumps at the step
        assert abs(schedule[0]["payment"] - schedule[6]["payment"]) < 0.01
        assert schedule[7]["payment"] > schedule[6]["payment"]
        assert abs(schedule[7]["payment"] - schedule[-1]["payment"]) < 0.02
        # Still amortizes to zero
        assert abs(schedule[-1]["remaining_balance"]) < 0.01

    def test_flat_rate_ignores_missing_steps(self):
        """Verify passing no rate_steps produces the classic flat-rate annuity."""
        flat = LiabilitiesService.calculate_amortization_schedule(
            principal=12000.0,
            annual_rate=6.0,
            term_months=12,
            start_date=date(2024, 1, 1),
        )
        stepped = LiabilitiesService.calculate_amortization_schedule(
            principal=12000.0,
            annual_rate=0.0,
            term_months=12,
            start_date=date(2024, 1, 1),
            rate_steps=[{"date": "2024-01-01", "value": 6.0}],
        )
        for a, b in zip(flat, stepped):
            assert abs(a["payment"] - b["payment"]) < 0.01
            assert abs(a["remaining_balance"] - b["remaining_balance"]) < 0.01


class TestPrimeBasedLoans:
    """Tests for prime-linked and variable loan types backed by the rate series."""

    @staticmethod
    def _seed_rates(db_session, points):
        """Insert BoI rate points directly into the series table."""
        from backend.repositories.interest_rates_repository import (
            InterestRatesRepository,
        )

        InterestRatesRepository(db_session).upsert_points(
            "boi_rate", points, source="seed"
        )

    def test_create_prime_linked_requires_spread(self, db_session):
        """Verify creating a prime-linked loan without a spread raises ValidationException."""
        import pytest

        from backend.errors import ValidationException

        service = LiabilitiesService(db_session)
        with pytest.raises(ValidationException):
            service.create_liability(
                name="Mortgage Prime",
                tag="Mortgage",
                principal_amount=500000.0,
                term_months=240,
                start_date="2024-01-01",
                loan_type="prime_linked",
            )

    def test_create_variable_requires_reset_months(self, db_session):
        """Verify creating a variable loan without reset months raises ValidationException."""
        import pytest

        from backend.errors import ValidationException

        service = LiabilitiesService(db_session)
        with pytest.raises(ValidationException):
            service.create_liability(
                name="Variable Loan",
                tag="Mortgage",
                principal_amount=100000.0,
                term_months=120,
                start_date="2024-01-01",
                loan_type="variable_unlinked",
                rate_spread=1.0,
            )

    def test_create_fixed_requires_interest_rate(self, db_session):
        """Verify creating a fixed loan without a rate raises ValidationException."""
        import pytest

        from backend.errors import ValidationException

        service = LiabilitiesService(db_session)
        with pytest.raises(ValidationException):
            service.create_liability(
                name="Fixed Loan",
                tag="Car Loan",
                principal_amount=50000.0,
                term_months=48,
                start_date="2024-01-01",
            )

    def test_prime_linked_derives_rate_and_tracks_steps(self, db_session):
        """Verify a prime-linked loan derives its rate from prime + spread and follows rate changes."""
        self._seed_rates(
            db_session,
            [
                {"date": "2023-01-01", "value": 3.0},   # prime 4.5
                {"date": "2024-06-10", "value": 4.0},   # prime 5.5
            ],
        )
        service = LiabilitiesService(db_session)
        service.create_liability(
            name="Prime Mortgage",
            tag="Mortgage",
            principal_amount=100000.0,
            term_months=24,
            start_date="2024-01-01",
            loan_type="prime_linked",
            rate_spread=-0.5,
        )

        records = service.get_all_liabilities()
        record = records[0]
        # Derived creation rate: prime at start (4.5) - 0.5 = 4.0
        assert abs(record["interest_rate"] - 4.0) < 0.001
        assert record["loan_type"] == "prime_linked"

        analysis = service.get_liability_analysis(record["id"])
        schedule = analysis["schedule"]
        # Payments before the June 2024 hike run at 4.0%, after at 5.0%
        assert schedule[0]["annual_rate"] == 4.0
        assert schedule[-1]["annual_rate"] == 5.0
        rates = {e["annual_rate"] for e in schedule}
        assert rates == {4.0, 5.0}

    def test_variable_rate_locks_between_resets(self, db_session):
        """Verify a variable loan only picks up prime changes at its reset dates."""
        self._seed_rates(
            db_session,
            [
                {"date": "2023-01-01", "value": 3.0},   # prime 4.5
                {"date": "2024-03-10", "value": 4.5},   # prime 6.0 (mid first year)
            ],
        )
        service = LiabilitiesService(db_session)
        service.create_liability(
            name="Variable Loan",
            tag="Mortgage",
            principal_amount=100000.0,
            term_months=24,
            start_date="2024-01-01",
            loan_type="variable_unlinked",
            rate_spread=0.5,
            rate_reset_months=12,
        )

        record = service.get_all_liabilities()[0]
        analysis = service.get_liability_analysis(record["id"])
        schedule = analysis["schedule"]

        # Year 1 locked at origination rate (prime 4.5 + 0.5 = 5.0) even
        # though prime rose mid-year; year 2 resets to 6.0 + 0.5 = 6.5.
        assert all(e["annual_rate"] == 5.0 for e in schedule[:12])
        assert all(e["annual_rate"] == 6.5 for e in schedule[12:])

    def test_prime_linked_falls_back_to_flat_rate_without_series(self, db_session):
        """Verify a prime-linked loan with an empty rate series falls back to its stored rate."""
        from unittest.mock import patch as mock_patch

        service = LiabilitiesService(db_session)
        # Avoid the bundled seed so the series is genuinely empty
        with mock_patch.object(service.rates_service, "ensure_seeded"):
            service.create_liability(
                name="Prime No Series",
                tag="Mortgage",
                principal_amount=100000.0,
                term_months=12,
                start_date="2024-01-01",
                loan_type="prime_linked",
                rate_spread=0.0,
                interest_rate=5.0,
            )
            record = service.get_all_liabilities()[0]
            # Flat fallback: every entry runs at the stored 5.0%
            analysis = service.get_liability_analysis(record["id"])
            assert all(e["annual_rate"] == 5.0 for e in analysis["schedule"])
