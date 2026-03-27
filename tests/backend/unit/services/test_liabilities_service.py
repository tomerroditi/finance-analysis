"""Tests for LiabilitiesService using real in-memory SQLite database."""

import pytest
from datetime import date

from backend.services.liabilities_service import LiabilitiesService


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
        # Remaining balance is from schedule entry after 3 payments
        expected_balance = analysis["schedule"][3]["remaining_balance"]
        assert abs(summary["remaining_balance"] - expected_balance) < 0.01

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
