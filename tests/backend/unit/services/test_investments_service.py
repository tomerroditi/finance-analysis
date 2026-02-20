"""Tests for InvestmentsService using real in-memory SQLite database."""

import pytest

from backend.models.investment import Investment as InvestmentModel
from backend.services.investments_service import InvestmentsService


class TestInvestmentsServiceCRUD:
    """Tests for InvestmentsService CRUD operations."""

    def test_create_investment(self, db_session):
        """Verify creating an investment persists it in the database."""
        service = InvestmentsService(db_session)
        service.create_investment(
            category="Investments",
            tag="New Fund",
            type_="etf",
            name="Vanguard Total Market",
            interest_rate=5.0,
            interest_rate_type="variable",
        )

        investments = service.get_all_investments()
        assert len(investments) == 1
        created = investments[0]
        assert created["name"] == "Vanguard Total Market"
        assert created["type"] == "etf"
        assert created["category"] == "Investments"
        assert created["tag"] == "New Fund"
        assert created["interest_rate"] == 5.0

    def test_get_all_investments(self, db_session, seed_investments):
        """Verify listing investments returns dicts and excludes closed by default."""
        service = InvestmentsService(db_session)
        investments = service.get_all_investments(include_closed=False)

        # Only stock_fund is open; bond_fund is closed
        assert len(investments) == 1
        assert investments[0]["name"] == "Migdal S&P 500 Fund"

        # With include_closed=True, both should appear
        all_investments = service.get_all_investments(include_closed=True)
        assert len(all_investments) == 2

    def test_get_investment_by_id(self, db_session, seed_investments):
        """Verify retrieving a single investment by ID returns correct data."""
        service = InvestmentsService(db_session)
        stock_fund = seed_investments["investments"][0]
        result = service.get_investment(stock_fund.id)

        assert result["name"] == "Migdal S&P 500 Fund"
        assert result["type"] == "mutual_fund"
        assert result["interest_rate"] == 7.5
        assert result["is_closed"] == 0

    def test_close_and_reopen(self, db_session, seed_investments):
        """Verify close sets is_closed=1 and reopen restores is_closed=0."""
        service = InvestmentsService(db_session)
        stock_fund = seed_investments["investments"][0]

        # Close the investment
        service.close_investment(stock_fund.id, closed_date="2025-12-31")
        closed = service.get_investment(stock_fund.id)
        assert closed["is_closed"] == 1
        assert closed["closed_date"] == "2025-12-31"

        # Reopen it
        service.reopen_investment(stock_fund.id)
        reopened = service.get_investment(stock_fund.id)
        assert reopened["is_closed"] == 0
        assert reopened["closed_date"] is None

    def test_delete_investment(self, db_session, seed_investments):
        """Verify deletion removes the investment from the database."""
        service = InvestmentsService(db_session)
        stock_fund = seed_investments["investments"][0]

        service.delete_investment(stock_fund.id)

        # Only the bond_fund should remain
        remaining = service.get_all_investments(include_closed=True)
        assert len(remaining) == 1
        assert remaining[0]["name"] == "Psagot Government Bond"


class TestInvestmentsServiceCalculations:
    """Tests for InvestmentsService calculation and analysis methods."""

    def test_calculate_current_balance(self, db_session, seed_investments):
        """Verify balance = -(sum of transactions) for an open investment.

        Stock fund has transactions: -10000 + -2000 = -12000
        Balance = -(-12000) = 12000
        """
        service = InvestmentsService(db_session)
        stock_fund = seed_investments["investments"][0]

        balance = service.calculate_current_balance(stock_fund.id)
        assert balance == 12000.0

    def test_calculate_profit_loss(self, db_session, seed_investments):
        """Verify deposits, withdrawals, and ROI calculation for the bond fund.

        Bond fund (closed):
        - Deposits: abs(-5000) = 5000
        - Withdrawals: 5160
        - Profit = 5160 - 5000 = 160
        - ROI = ((5160 / 5000) - 1) * 100 = 3.2%
        """
        service = InvestmentsService(db_session)
        bond_fund = seed_investments["investments"][1]

        metrics = service.calculate_profit_loss(bond_fund.id)

        assert metrics["total_deposits"] == 5000.0
        assert metrics["total_withdrawals"] == 5160.0
        assert metrics["current_balance"] == 0.0  # closed investment
        assert metrics["absolute_profit_loss"] == pytest.approx(160.0)
        assert metrics["roi_percentage"] == pytest.approx(3.2)
        assert metrics["first_transaction_date"] == "2023-01-10"

    def test_calculate_balance_over_time(self, db_session, seed_investments):
        """Verify daily balance series returns correct balances at key dates."""
        service = InvestmentsService(db_session)
        stock_fund = seed_investments["investments"][0]

        history = service.calculate_balance_over_time(
            stock_fund.id,
            start_date="2023-06-14",
            end_date="2024-01-16",
        )

        assert len(history) > 0

        # Build a lookup for easy assertion
        balance_by_date = {entry["date"]: entry["balance"] for entry in history}

        # Before first deposit: balance should be 0
        assert balance_by_date["2023-06-14"] == 0.0

        # On first deposit date (-10000): balance = 10000
        assert balance_by_date["2023-06-15"] == 10000.0

        # After second deposit (-2000 on 2024-01-15): balance = 12000
        assert balance_by_date["2024-01-15"] == 12000.0
        assert balance_by_date["2024-01-16"] == 12000.0

    def test_get_portfolio_overview(self, db_session, seed_investments):
        """Verify portfolio totals and allocation for open investments only."""
        service = InvestmentsService(db_session)

        overview = service.get_portfolio_overview()

        # Only stock_fund is open with balance 12000
        assert overview["total_value"] == 12000.0

        # total_deposits for stock fund = 12000, total_withdrawals = 0
        # total_profit = 12000 - (12000 - 0) = 0
        assert overview["total_profit"] == 0.0

        # ROI = ((12000 / 12000) - 1) * 100 = 0%
        assert overview["portfolio_roi"] == pytest.approx(0.0)

        # Allocation should contain one entry for the stock fund
        assert len(overview["allocation"]) == 1
        assert overview["allocation"][0]["name"] == "Migdal S&P 500 Fund"
        assert overview["allocation"][0]["balance"] == 12000.0
        assert overview["allocation"][0]["type"] == "mutual_fund"

    def test_get_portfolio_overview_empty(self, db_session):
        """Verify empty portfolio returns zeros and empty allocation."""
        service = InvestmentsService(db_session)

        overview = service.get_portfolio_overview()

        assert overview["total_value"] == 0.0
        assert overview["total_profit"] == 0.0
        assert overview["portfolio_roi"] == 0.0
        assert overview["allocation"] == []


class TestInvestmentsServicePriorWealth:
    """Tests for prior wealth calculation and storage."""

    def test_recalculate_prior_wealth_sums_transactions(self, db_session, seed_investments):
        """Verify recalculate_prior_wealth stores -(sum of all txns) on Investment."""
        service = InvestmentsService(db_session)
        stock_fund = seed_investments["investments"][0]

        # stock_fund txns: -10000, -2000 → prior_wealth = -(-12000) = 12000
        service.recalculate_prior_wealth(stock_fund.id)

        db_session.refresh(stock_fund)
        assert stock_fund.prior_wealth_amount == pytest.approx(12000.0)

    def test_recalculate_prior_wealth_handles_no_transactions(self, db_session):
        """Verify prior_wealth_amount is 0 when investment has no transactions."""
        inv = InvestmentModel(
            category="Investments",
            tag="Empty Fund",
            type="etf",
            name="Empty",
            created_date="2024-01-01",
        )
        db_session.add(inv)
        db_session.commit()
        db_session.refresh(inv)

        service = InvestmentsService(db_session)
        service.recalculate_prior_wealth(inv.id)

        db_session.refresh(inv)
        assert inv.prior_wealth_amount == 0.0

    def test_get_total_prior_wealth_sums_open_investments(self, db_session, seed_investments):
        """Verify get_total_prior_wealth sums prior_wealth_amount for non-closed investments only."""
        stock_fund, bond_fund = seed_investments["investments"]
        stock_fund.prior_wealth_amount = 12000.0   # open
        bond_fund.prior_wealth_amount = -160.0     # closed — should be excluded
        db_session.commit()

        service = InvestmentsService(db_session)
        total = service.get_total_prior_wealth()

        assert total == pytest.approx(12000.0)

    def test_get_total_prior_wealth_returns_zero_when_empty(self, db_session):
        """Verify get_total_prior_wealth returns 0.0 when no open investments exist."""
        service = InvestmentsService(db_session)
        assert service.get_total_prior_wealth() == 0.0
