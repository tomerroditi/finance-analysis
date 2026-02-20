"""Tests for AnalysisService functionality."""

import pytest

from backend.models.transaction import BankTransaction
from backend.services.analysis_service import AnalysisService


class TestAnalysisServiceOverview:
    """Tests for AnalysisService financial overview."""

    def test_get_overview_with_data(self, db_session, seed_base_transactions):
        """Verify overview returns correct totals."""
        service = AnalysisService(db_session)
        result = service.get_overview()

        assert result["total_transactions"] == len(seed_base_transactions)
        assert result["latest_data_date"] is not None

        # Income from bank+cash only (CC excluded): Salary 24700 + Other Income 3500
        assert result["total_income"] == 28200.0

        # Expenses from bank+cash only (CC excluded):
        # Home/Rent 9000 + Food/Coffee 45 + Transport/Parking 30
        # Ignore transactions cancel out (net 0 expense)
        assert result["total_expenses"] == 9075.0

        assert result["net_balance_change"] == 28200.0 - 9075.0

    def test_get_overview_with_date_filter(self, db_session, seed_base_transactions):
        """Verify overview respects date range filters."""
        service = AnalysisService(db_session)

        # Filter to January 2024 only
        result = service.get_overview(
            start_date="2024-01-01", end_date="2024-01-31"
        )

        # Jan bank+cash income: 8000 (Salary)
        assert result["total_income"] == 8000.0

        # Jan bank+cash expenses: Home/Rent 3000 + Ignore(net 0) + Coffee 15 + Parking 10
        assert result["total_expenses"] == 3025.0

        # latest_data_date is always from full dataset (before filtering)
        assert result["latest_data_date"] == "2024-03-25"

    def test_get_overview_empty_db(self, db_session):
        """Verify overview raises KeyError on empty database (no columns in empty DataFrame)."""
        service = AnalysisService(db_session)

        with pytest.raises(KeyError):
            service.get_overview()


class TestAnalysisServiceTimeSeries:
    """Tests for AnalysisService time series data."""

    def test_get_income_expenses_over_time(self, db_session, seed_base_transactions):
        """Verify monthly income/expense breakdown."""
        service = AnalysisService(db_session)
        result = service.get_income_expenses_over_time()

        assert len(result) == 3
        months = [r["month"] for r in result]
        assert months == ["2024-01", "2024-02", "2024-03"]

        # January: income = 8000, expenses = 3025
        jan = result[0]
        assert jan["income"] == 8000.0
        assert jan["expenses"] == 3025.0

        # February: income = 8500 + 3500 = 12000, expenses = 3030
        feb = result[1]
        assert feb["income"] == 12000.0
        assert feb["expenses"] == 3030.0

        # March: income = 8200, expenses = 3020
        mar = result[2]
        assert mar["income"] == 8200.0
        assert mar["expenses"] == 3020.0

    def test_get_income_expenses_over_time_date_filter(
        self, db_session, seed_base_transactions
    ):
        """Verify date filtering on time series."""
        service = AnalysisService(db_session)
        result = service.get_income_expenses_over_time(
            start_date="2024-02-01", end_date="2024-02-28"
        )

        assert len(result) == 1
        assert result[0]["month"] == "2024-02"
        assert result[0]["income"] == 12000.0
        assert result[0]["expenses"] == 3030.0

    def test_get_net_balance_over_time(self, db_session, seed_base_transactions):
        """Verify cumulative balance calculation."""
        service = AnalysisService(db_session)
        result = service.get_net_balance_over_time()

        assert len(result) == 3

        # Jan bank+cash: 8000 - 3000 - 500 + 500 - 15 - 10 = 4975
        jan = result[0]
        assert jan["month"] == "2024-01"
        assert jan["net_change"] == 4975.0
        assert jan["cumulative_balance"] == 4975.0

        # Feb bank+cash: 8500 - 3000 - 18 - 12 + 3500 = 8970
        feb = result[1]
        assert feb["month"] == "2024-02"
        assert feb["net_change"] == 8970.0
        assert feb["cumulative_balance"] == 4975.0 + 8970.0

        # Mar bank+cash: 8200 - 3000 - 700 + 700 - 12 - 8 = 5180
        mar = result[2]
        assert mar["month"] == "2024-03"
        assert mar["net_change"] == 5180.0
        assert mar["cumulative_balance"] == 4975.0 + 8970.0 + 5180.0

    def test_get_net_balance_over_time_excludes_cc(
        self, db_session, seed_base_transactions
    ):
        """Verify credit card transactions excluded from balance (only bank source used)."""
        service = AnalysisService(db_session)
        result = service.get_net_balance_over_time()

        # Total net change across all months should equal sum of all bank+cash amounts
        # (CC transactions are excluded)
        total_net = sum(r["net_change"] for r in result)

        # Sum of all bank+cash amounts in seed data:
        # Jan: 8000 - 3000 - 500 + 500 - 15 - 10 = 4975
        # Feb: 8500 - 3000 - 18 - 12 + 3500 = 8970
        # Mar: 8200 - 3000 - 700 + 700 - 12 - 8 = 5180
        expected_total = 4975.0 + 8970.0 + 5180.0
        assert total_net == expected_total

        # Verify CC amounts are NOT included (total CC = -1380 across all months)
        # If CC were included, total would differ
        cc_total = -(150 + 80 + 60 + 40 + 250 + 180 + 120 + 55 + 45 + 200 + 95 + 70 + 35)
        assert total_net != expected_total + cc_total

    def test_get_net_balance_over_time_empty(self, db_session):
        """Verify empty database raises KeyError (no columns in empty DataFrame)."""
        service = AnalysisService(db_session)

        with pytest.raises(KeyError):
            service.get_net_balance_over_time()


class TestAnalysisServiceCategories:
    """Tests for AnalysisService category breakdown."""

    def test_get_expenses_by_category(self, db_session, seed_base_transactions):
        """Verify category grouping with expenses and refunds separated."""
        service = AnalysisService(db_session)
        result = service.get_expenses_by_category()

        assert "expenses" in result
        assert "refunds" in result

        # Build lookup for expenses
        expense_map = {e["category"]: e["amount"] for e in result["expenses"]}

        # Food: CC(-150-80-180-120-200-95) + Cash(-15-18-12) = -870
        assert expense_map["Food"] == 870.0

        # Transport: CC(-60-55-70) + Cash(-10-12-8) = -215
        assert expense_map["Transport"] == 215.0

        # Entertainment: CC(-40-45-35) = -120
        assert expense_map["Entertainment"] == 120.0

        # Home: Bank(-3000*3) = -9000
        assert expense_map["Home"] == 9000.0

        # Other: CC(-250) = -250
        assert expense_map["Other"] == 250.0

    def test_get_expenses_by_category_excludes_non_expenses(
        self, db_session, seed_base_transactions
    ):
        """Verify Salary, Ignore, Investments excluded from expense breakdown."""
        service = AnalysisService(db_session)
        result = service.get_expenses_by_category()

        expense_categories = {e["category"] for e in result["expenses"]}
        refund_categories = {r["category"] for r in result["refunds"]}
        all_categories = expense_categories | refund_categories

        # Non-expense categories must be excluded
        assert "Salary" not in all_categories
        assert "Ignore" not in all_categories
        assert "Investments" not in all_categories
        assert "Other Income" not in all_categories
        assert "Liabilities" not in all_categories

    def test_get_expenses_by_category_empty(self, db_session):
        """Verify empty result for no data."""
        service = AnalysisService(db_session)
        result = service.get_expenses_by_category()

        # When empty, service returns []
        assert result == []


class TestAnalysisServiceIncomeExpenses:
    """Tests for income/expense classification logic."""

    def test_get_income_and_expenses(self, db_session, seed_base_transactions):
        """Verify income vs expense calculation via direct method call."""
        service = AnalysisService(db_session)

        # Call get_income_and_expenses directly with the full transactions df
        df = service.repo.get_table()
        income, expenses = service.get_income_and_expenses(df)

        # Income from bank+cash only (CC excluded): Salary 24700 + Other Income 3500
        assert income == 28200.0

        # Expenses from bank+cash only: Home/Rent 9000 + Coffee 45 + Parking 30
        assert expenses == 9075.0

    def test_income_mask_includes_salary(self, db_session, seed_base_transactions):
        """Verify Salary category counted as income by the income mask."""
        service = AnalysisService(db_session)
        df = service.repo.get_table()
        df = df[df["source"] != "credit_card_transactions"]

        mask = service._get_income_mask(df)
        income_rows = df[mask]

        # Salary rows should be in income
        salary_rows = income_rows[income_rows["category"] == "Salary"]
        assert not salary_rows.empty
        assert salary_rows["amount"].sum() == 24700.0  # 8000 + 8500 + 8200

    def test_income_mask_includes_other_income(
        self, db_session, seed_base_transactions
    ):
        """Verify Other Income category counted as income by the income mask."""
        service = AnalysisService(db_session)
        df = service.repo.get_table()
        df = df[df["source"] != "credit_card_transactions"]

        mask = service._get_income_mask(df)
        income_rows = df[mask]

        # Other Income rows should be in income
        other_income_rows = income_rows[income_rows["category"] == "Other Income"]
        assert not other_income_rows.empty
        assert other_income_rows["amount"].sum() == 3500.0  # Freelance payment

    def test_income_mask_liability_positive_is_income(self, db_session):
        """Verify positive Liabilities amounts (loans received) counted as income."""
        service = AnalysisService(db_session)

        # Insert a positive Liabilities transaction (loan received)
        loan = BankTransaction(
            id="bank_loan_1",
            date="2024-04-01",
            provider="hapoalim",
            account_name="Checking",
            description="Loan Received",
            amount=10000.0,
            category="Liabilities",
            tag="Mortgage",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        db_session.add(loan)
        db_session.commit()

        result = service.get_overview()

        # The positive Liabilities amount should count as income
        assert result["total_income"] == 10000.0
        assert result["total_expenses"] == 0.0


class TestAnalysisServiceSankey:
    """Tests for Sankey diagram data generation."""

    def test_get_sankey_data_structure(self, db_session, seed_base_transactions):
        """Verify Sankey returns nodes and links."""
        service = AnalysisService(db_session)
        result = service.get_sankey_data()

        assert "nodes" in result
        assert "links" in result
        assert "node_labels" in result

        # Should have at least Total Income node plus source/destination nodes
        assert len(result["nodes"]) > 0
        assert "Total Income" in result["nodes"]

        # Every link should have source, target, value, label
        for link in result["links"]:
            assert "source" in link
            assert "target" in link
            assert "value" in link
            assert "label" in link

    def test_get_sankey_data_includes_prior_wealth(
        self, db_session, seed_base_transactions, seed_prior_wealth_transactions
    ):
        """Verify Prior Wealth node included from bank balances."""
        service = AnalysisService(db_session)
        result = service.get_sankey_data()

        # Prior Wealth should appear as a node
        assert "Prior Wealth" in result["nodes"]

        # Find the Prior Wealth link
        pw_node_idx = result["node_labels"].index("Prior Wealth")
        pw_links = [link for link in result["links"] if link["source"] == pw_node_idx]
        assert len(pw_links) == 1

        # Prior Wealth value = cash_pw (5000) + bank balances (20000 + 15000)
        assert pw_links[0]["value"] == 40000.0

    def test_get_sankey_data_empty(self, db_session):
        """Verify empty nodes/links for no data."""
        service = AnalysisService(db_session)
        result = service.get_sankey_data()

        assert result["nodes"] == []
        assert result["links"] == []

    def test_get_sankey_data_excludes_ignore(
        self, db_session, seed_base_transactions
    ):
        """Verify Ignore category excluded from Sankey."""
        service = AnalysisService(db_session)
        result = service.get_sankey_data()

        # "Ignore" should not appear anywhere in nodes
        assert "Ignore" not in result["nodes"]

        # Verify that all nodes are valid (no Ignore-related nodes)
        for node in result["nodes"]:
            assert "Ignore" not in node


class TestAnalysisServiceInvestmentPriorWealth:
    """Tests for investment prior wealth aggregation in AnalysisService."""

    def test_get_investment_prior_wealth_total_sums_open_investments(
        self, db_session, seed_investments
    ):
        """Verify _get_investment_prior_wealth_total sums prior_wealth_amount for open investments."""
        stock_fund, bond_fund = seed_investments["investments"]
        stock_fund.prior_wealth_amount = 12000.0
        bond_fund.prior_wealth_amount = -160.0   # closed, should be excluded
        db_session.commit()

        service = AnalysisService(db_session)
        total = service._get_investment_prior_wealth_total()

        assert total == pytest.approx(12000.0)

    def test_get_investment_prior_wealth_total_returns_zero_with_no_investments(
        self, db_session
    ):
        """Verify _get_investment_prior_wealth_total returns 0.0 when no investments exist."""
        service = AnalysisService(db_session)
        assert service._get_investment_prior_wealth_total() == 0.0
