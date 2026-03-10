"""Tests for AnalysisService functionality."""

import pytest

from backend.models.transaction import BankTransaction, CreditCardTransaction
from backend.services.analysis_service import AnalysisService
from backend.services.investments_service import InvestmentsService


class TestAnalysisServiceOverview:
    """Tests for AnalysisService financial overview."""

    def test_get_overview_with_data(self, db_session, seed_base_transactions):
        """Verify overview returns correct totals."""
        service = AnalysisService(db_session)
        result = service.get_overview()

        assert result["latest_data_date"] is not None

        # Income from bank+cash only (CC excluded): Salary 24700 + Other Income 3500
        assert result["total_income"] == 28200.0

        # Expenses from bank+cash only (CC excluded):
        # Home/Rent 9000 + Food/Coffee 45 + Transport/Parking 30
        # Ignore transactions cancel out (net 0 expense)
        assert result["total_expenses"] == 9075.0

        assert result["net_balance_change"] == 28200.0 - 9075.0

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

    def test_get_net_balance_over_time(self, db_session, seed_base_transactions):
        """Verify cumulative balance calculation."""
        service = AnalysisService(db_session)
        result = service.get_net_balance_over_time()

        assert len(result) == 4

        # anchor point before first month (cumulative balance = prior wealth = 0 - cash prior wealth is being ignored atm, we should add it in the future)
        anchor = result[0]
        assert anchor["month"] == "2023-12"
        assert anchor["net_change"] == 0.0
        assert anchor["cumulative_balance"] == 0

        # Jan bank+cash: 8000 - 3000 - 500 + 500 - 15 - 10 = 4975
        jan = result[1]
        assert jan["month"] == "2024-01"
        assert jan["net_change"] == 4975.0
        assert jan["cumulative_balance"] == 4975.0

        # Feb bank+cash: 8500 - 3000 - 18 - 12 + 3500 = 8970
        feb = result[2]
        assert feb["month"] == "2024-02"
        assert feb["net_change"] == 8970.0
        assert feb["cumulative_balance"] == 4975.0 + 8970.0

        # Mar bank+cash: 8200 - 3000 - 700 + 700 - 12 - 8 = 5180
        mar = result[3]
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
        """Verify empty database returns empty list."""
        service = AnalysisService(db_session)

        result = service.get_net_balance_over_time()
        assert result == []


class TestAnalysisServiceNetWorthOverTime:
    """Tests for net worth over time including cash balance tracking."""

    def test_get_net_worth_over_time_structure(self, db_session, seed_base_transactions):
        """Verify each snapshot has all required keys including cash."""
        service = AnalysisService(db_session)
        result = service.get_net_worth_over_time()

        assert len(result) == 4  # anchor + 3 months
        for entry in result:
            assert "month" in entry
            assert "bank_balance" in entry
            assert "investment_value" in entry
            assert "cash" in entry
            assert "net_worth" in entry

    def test_get_net_worth_over_time_cash_values(self, db_session, seed_base_transactions):
        """Verify cash balance is tracked cumulatively from cash transactions."""
        service = AnalysisService(db_session)
        result = service.get_net_worth_over_time()

        # No cash_balances records seeded -> cash_prior_wealth = 0
        # Cash txns: Jan(-15-10=-25), Feb(-18-12=-30), Mar(-12-8=-20)
        anchor = result[0]
        assert anchor["cash"] == 0.0

        jan = result[1]
        assert jan["cash"] == -25.0  # cumulative: -25

        feb = result[2]
        assert feb["cash"] == -55.0  # cumulative: -25 + -30

        mar = result[3]
        assert mar["cash"] == -75.0  # cumulative: -25 + -30 + -20

    def test_get_net_worth_over_time_empty(self, db_session):
        """Verify empty database returns empty list."""
        service = AnalysisService(db_session)
        result = service.get_net_worth_over_time()
        assert result == []

    def test_get_net_worth_over_time_months(self, db_session, seed_base_transactions):
        """Verify correct months returned with anchor point."""
        service = AnalysisService(db_session)
        result = service.get_net_worth_over_time()

        months = [r["month"] for r in result]
        assert months == ["2023-12", "2024-01", "2024-02", "2024-03"]

    def test_get_net_worth_over_time_net_worth_equals_bank_plus_investments(
        self, db_session, seed_base_transactions
    ):
        """Verify net_worth = bank_balance + investment_value for each month."""
        service = AnalysisService(db_session)
        result = service.get_net_worth_over_time()

        for entry in result:
            assert entry["net_worth"] == pytest.approx(
                entry["bank_balance"] + entry["investment_value"]
            )


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

        # Call get_income_investments_and_expenses directly with the full transactions df
        df = service.repo.get_table()
        income, investments, expenses = service.get_income_investments_and_expenses(df)

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
        self, db_session, seed_base_transactions, seed_prior_wealth_transactions, seed_investments
    ):
        """Verify Prior Wealth node included from bank balances and open investments."""
        service = AnalysisService(db_session)
        result = service.get_sankey_data()

        # Prior Wealth should appear as a node
        assert "Prior Wealth" in result["nodes"]

        # Find the Prior Wealth link
        pw_node_idx = result["node_labels"].index("Prior Wealth")
        pw_links = [link for link in result["links"] if link["source"] == pw_node_idx]
        assert len(pw_links) == 1

        # Prior Wealth value = cash_pw (5000) + bank balances (20000 + 15000) + all investments (12000 + -160)
        assert pw_links[0]["value"] == 51840.0

    def test_get_sankey_data_empty(self, db_session):
        """Verify empty nodes/links for no data."""
        service = AnalysisService(db_session)
        result = service.get_sankey_data()

        assert result["nodes"] == []
        assert result["links"] == []

    def test_get_sankey_data_unknown_cc_gap(self, db_session):
        """Verify Unknown destination appears when bank CC payments exceed itemized CC total."""
        # Bank CC bill payment: 500
        bank_cc = BankTransaction(
            id="bank_cc_1",
            date="2024-01-10",
            provider="hapoalim",
            account_name="Checking",
            description="Credit Card Payment - Isracard",
            amount=-500.0,
            category="Credit Cards",
            tag=None,
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        # Itemized CC transactions: 150 + 200 = 350
        cc_txn_1 = CreditCardTransaction(
            id="cc_gap_1",
            date="2024-01-05",
            provider="isracard",
            account_name="Isracard",
            description="Grocery Store",
            amount=-150.0,
            category="Food",
            tag="Groceries",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        )
        cc_txn_2 = CreditCardTransaction(
            id="cc_gap_2",
            date="2024-01-08",
            provider="isracard",
            account_name="Isracard",
            description="Gas Station",
            amount=-200.0,
            category="Transport",
            tag="Gas",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        )
        # Also add a salary so the diagram has income
        salary = BankTransaction(
            id="bank_salary_gap",
            date="2024-01-01",
            provider="hapoalim",
            account_name="Checking",
            description="Salary",
            amount=8000.0,
            category="Salary",
            tag=None,
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        db_session.add_all([bank_cc, cc_txn_1, cc_txn_2, salary])
        db_session.commit()

        service = AnalysisService(db_session)
        result = service.get_sankey_data()

        # Gap = 500 - 350 = 150 → should appear as Unknown
        assert "Unknown" in result["nodes"]
        unknown_idx = result["node_labels"].index("Unknown")
        unknown_links = [
            link for link in result["links"] if link["target"] == unknown_idx
        ]
        assert len(unknown_links) == 1
        assert unknown_links[0]["value"] == 150.0

    def test_get_sankey_data_no_unknown_when_no_gap(self, db_session):
        """Verify Unknown does not appear when bank CC payments equal itemized CC total."""
        bank_cc = BankTransaction(
            id="bank_cc_no_gap",
            date="2024-01-10",
            provider="hapoalim",
            account_name="Checking",
            description="Credit Card Payment",
            amount=-300.0,
            category="Credit Cards",
            tag=None,
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        cc_txn = CreditCardTransaction(
            id="cc_no_gap_1",
            date="2024-01-05",
            provider="isracard",
            account_name="Isracard",
            description="Grocery Store",
            amount=-300.0,
            category="Food",
            tag="Groceries",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        )
        salary = BankTransaction(
            id="bank_salary_no_gap",
            date="2024-01-01",
            provider="hapoalim",
            account_name="Checking",
            description="Salary",
            amount=8000.0,
            category="Salary",
            tag=None,
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        db_session.add_all([bank_cc, cc_txn, salary])
        db_session.commit()

        service = AnalysisService(db_session)
        result = service.get_sankey_data()

        assert "Unknown" not in result["nodes"]

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
    """Tests for investment prior wealth aggregation."""

    def test_get_investment_prior_wealth_total_sums_all_investments(
        self, db_session, seed_investments
    ):
        """Verify get_total_prior_wealth sums prior_wealth_amount for all investments."""
        stock_fund, bond_fund = seed_investments["investments"]
        stock_fund.prior_wealth_amount = 12000.0
        bond_fund.prior_wealth_amount = -160.0   # closed, still included
        db_session.commit()

        service = InvestmentsService(db_session)
        total = service.get_total_prior_wealth()

        assert total == pytest.approx(11840.0)

    def test_get_investment_prior_wealth_total_returns_zero_with_no_investments(
        self, db_session
    ):
        """Verify get_total_prior_wealth returns 0.0 when no investments exist."""
        service = InvestmentsService(db_session)
        assert service.get_total_prior_wealth() == 0.0


class TestAnalysisServiceIncomeBySource:
    """Tests for income breakdown by source over time."""

    def test_get_income_by_source_over_time(self, db_session, seed_base_transactions):
        """Verify monthly income is broken down by category+tag source."""
        service = AnalysisService(db_session)
        result = service.get_income_by_source_over_time()

        assert len(result) == 3
        months = [r["month"] for r in result]
        assert months == ["2024-01", "2024-02", "2024-03"]

        # January: only Salary 8000
        jan = result[0]
        assert jan["sources"] == {"Salary": 8000.0}
        assert jan["total"] == 8000.0

        # February: Salary 8500 + Other Income 3500
        feb = result[1]
        assert feb["sources"] == {"Salary": 8500.0, "Other Income": 3500.0}
        assert feb["total"] == 12000.0

        # March: only Salary 8200
        mar = result[2]
        assert mar["sources"] == {"Salary": 8200.0}
        assert mar["total"] == 8200.0

    def test_get_income_by_source_over_time_with_tags(self, db_session):
        """Verify category/tag combo labels when tags exist on income transactions."""
        records = [
            BankTransaction(
                id="bank_tag_1", date="2024-04-01", provider="hapoalim",
                account_name="Checking", description="Salary April",
                amount=8000.0, category="Salary", tag=None,
                source="bank_transactions", type="normal", status="completed",
            ),
            BankTransaction(
                id="bank_tag_2", date="2024-04-10", provider="leumi",
                account_name="Business", description="Freelance Project A",
                amount=2000.0, category="Other Income", tag="Freelance",
                source="bank_transactions", type="normal", status="completed",
            ),
            BankTransaction(
                id="bank_tag_3", date="2024-04-15", provider="leumi",
                account_name="Business", description="Dividend Payment",
                amount=500.0, category="Other Income", tag="Dividends",
                source="bank_transactions", type="normal", status="completed",
            ),
            BankTransaction(
                id="bank_tag_4", date="2024-04-20", provider="leumi",
                account_name="Business", description="Misc Income",
                amount=300.0, category="Other Income", tag=None,
                source="bank_transactions", type="normal", status="completed",
            ),
        ]
        db_session.add_all(records)
        db_session.commit()

        service = AnalysisService(db_session)
        result = service.get_income_by_source_over_time()

        assert len(result) == 1
        sources = result[0]["sources"]
        # Salary has no tag variants -> just "Salary"
        assert sources["Salary"] == 8000.0
        # Other Income with tags -> "Other Income / Tag"
        assert sources["Other Income / Freelance"] == 2000.0
        assert sources["Other Income / Dividends"] == 500.0
        # Other Income with no tag -> just "Other Income"
        assert sources["Other Income"] == 300.0
        assert result[0]["total"] == 10800.0

    def test_get_income_by_source_over_time_includes_positive_liabilities(self, db_session):
        """Verify positive Liabilities (loans received) counted as income source."""
        records = [
            BankTransaction(
                id="bank_loan_inc", date="2024-05-01", provider="hapoalim",
                account_name="Checking", description="Loan Disbursement",
                amount=50000.0, category="Liabilities", tag="Mortgage",
                source="bank_transactions", type="normal", status="completed",
            ),
            BankTransaction(
                id="bank_sal_inc", date="2024-05-01", provider="hapoalim",
                account_name="Checking", description="Salary May",
                amount=8000.0, category="Salary", tag=None,
                source="bank_transactions", type="normal", status="completed",
            ),
        ]
        db_session.add_all(records)
        db_session.commit()

        service = AnalysisService(db_session)
        result = service.get_income_by_source_over_time()

        assert len(result) == 1
        sources = result[0]["sources"]
        assert sources["Loans"] == 50000.0
        assert sources["Salary"] == 8000.0

    def test_get_income_by_source_over_time_excludes_prior_wealth(
        self, db_session, seed_base_transactions, seed_prior_wealth_transactions
    ):
        """Verify Prior Wealth tagged transactions are excluded from income sources."""
        service = AnalysisService(db_session)
        result = service.get_income_by_source_over_time()

        # Prior Wealth should not appear as a source label
        for month_data in result:
            for source_label in month_data["sources"]:
                assert "Prior Wealth" not in source_label

    def test_get_income_by_source_over_time_empty(self, db_session):
        """Verify empty database returns empty list."""
        service = AnalysisService(db_session)
        result = service.get_income_by_source_over_time()
        assert result == []

    def test_get_income_by_source_over_time_excludes_cc(
        self, db_session, seed_base_transactions
    ):
        """Verify credit card transactions are excluded from income calculation."""
        service = AnalysisService(db_session)
        result = service.get_income_by_source_over_time()

        # All income should come from bank/cash sources only
        # CC transactions have no income categories in seed data, but verify
        # the method filters them out by checking totals match expected
        total_income = sum(r["total"] for r in result)
        assert total_income == 8000.0 + 12000.0 + 8200.0  # 28200


class TestIncomeMaskPositiveLiabilities:
    """Tests for _get_income_mask handling of positive liabilities (loan receipts)."""

    def test_positive_liabilities_classified_as_income(self, db_session):
        """Verify positive Liabilities amount is classified as income by the mask."""
        loan = BankTransaction(
            id="bank_loan_mask_1",
            date="2024-06-01",
            provider="hapoalim",
            account_name="Checking",
            description="Loan Disbursement",
            amount=25000.0,
            category="Liabilities",
            tag="Mortgage",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        db_session.add(loan)
        db_session.commit()

        service = AnalysisService(db_session)
        df = service.repo.get_table()
        mask = service._get_income_mask(df)

        income_rows = df[mask]
        assert len(income_rows) == 1
        assert income_rows.iloc[0]["category"] == "Liabilities"
        assert income_rows.iloc[0]["amount"] == 25000.0

    def test_negative_liabilities_not_classified_as_income(self, db_session):
        """Verify negative Liabilities (debt payments) are NOT classified as income."""
        debt_payment = BankTransaction(
            id="bank_debt_1",
            date="2024-06-01",
            provider="hapoalim",
            account_name="Checking",
            description="Mortgage Payment",
            amount=-2000.0,
            category="Liabilities",
            tag="Mortgage",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        db_session.add(debt_payment)
        db_session.commit()

        service = AnalysisService(db_session)
        df = service.repo.get_table()
        mask = service._get_income_mask(df)

        income_rows = df[mask]
        assert income_rows.empty

    def test_mixed_liabilities_only_positive_is_income(self, db_session):
        """Verify only positive Liabilities rows are income when mixed with negative."""
        records = [
            BankTransaction(
                id="bank_loan_mix_1",
                date="2024-06-01",
                provider="hapoalim",
                account_name="Checking",
                description="Loan Received",
                amount=50000.0,
                category="Liabilities",
                tag="Personal Loan",
                source="bank_transactions",
                type="normal",
                status="completed",
            ),
            BankTransaction(
                id="bank_debt_mix_1",
                date="2024-06-15",
                provider="hapoalim",
                account_name="Checking",
                description="Loan Repayment",
                amount=-3000.0,
                category="Liabilities",
                tag="Personal Loan",
                source="bank_transactions",
                type="normal",
                status="completed",
            ),
        ]
        db_session.add_all(records)
        db_session.commit()

        service = AnalysisService(db_session)
        df = service.repo.get_table()
        mask = service._get_income_mask(df)

        income_rows = df[mask]
        assert len(income_rows) == 1
        assert income_rows.iloc[0]["amount"] == 50000.0


class TestInvestmentMask:
    """Tests for _get_investment_mask identifying investment transactions."""

    def test_investment_category_classified_as_investment(self, db_session):
        """Verify Investments category transactions are identified by the mask."""
        inv_txn = BankTransaction(
            id="bank_inv_mask_1",
            date="2024-06-01",
            provider="hapoalim",
            account_name="Checking",
            description="Investment Deposit",
            amount=-5000.0,
            category="Investments",
            tag="Stock Fund",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        db_session.add(inv_txn)
        db_session.commit()

        service = AnalysisService(db_session)
        df = service.repo.get_table()
        mask = service._get_investment_mask(df)

        investment_rows = df[mask]
        assert len(investment_rows) == 1
        assert investment_rows.iloc[0]["category"] == "Investments"

    def test_non_investment_category_not_classified(self, db_session):
        """Verify non-investment categories are excluded by the investment mask."""
        records = [
            BankTransaction(
                id="bank_salary_mask",
                date="2024-06-01",
                provider="hapoalim",
                account_name="Checking",
                description="Salary",
                amount=8000.0,
                category="Salary",
                tag=None,
                source="bank_transactions",
                type="normal",
                status="completed",
            ),
            BankTransaction(
                id="bank_food_mask",
                date="2024-06-02",
                provider="hapoalim",
                account_name="Checking",
                description="Grocery",
                amount=-200.0,
                category="Food",
                tag="Groceries",
                source="bank_transactions",
                type="normal",
                status="completed",
            ),
        ]
        db_session.add_all(records)
        db_session.commit()

        service = AnalysisService(db_session)
        df = service.repo.get_table()
        mask = service._get_investment_mask(df)

        investment_rows = df[mask]
        assert investment_rows.empty

    def test_investment_mask_with_mixed_categories(self, db_session):
        """Verify investment mask correctly picks only Investments from mixed data."""
        records = [
            BankTransaction(
                id="bank_inv_mixed_1",
                date="2024-06-01",
                provider="hapoalim",
                account_name="Checking",
                description="Fund Deposit",
                amount=-10000.0,
                category="Investments",
                tag="Stock Fund",
                source="bank_transactions",
                type="normal",
                status="completed",
            ),
            BankTransaction(
                id="bank_sal_mixed_1",
                date="2024-06-01",
                provider="hapoalim",
                account_name="Checking",
                description="Salary",
                amount=8000.0,
                category="Salary",
                tag=None,
                source="bank_transactions",
                type="normal",
                status="completed",
            ),
            BankTransaction(
                id="bank_liab_mixed_1",
                date="2024-06-01",
                provider="hapoalim",
                account_name="Checking",
                description="Loan",
                amount=20000.0,
                category="Liabilities",
                tag="Mortgage",
                source="bank_transactions",
                type="normal",
                status="completed",
            ),
        ]
        db_session.add_all(records)
        db_session.commit()

        service = AnalysisService(db_session)
        df = service.repo.get_table()
        mask = service._get_investment_mask(df)

        investment_rows = df[mask]
        assert len(investment_rows) == 1
        assert investment_rows.iloc[0]["amount"] == -10000.0


class TestIncomeBySourceEarlyExits:
    """Tests for get_income_by_source_over_time early exit paths."""

    def test_returns_empty_when_only_cashflow_excluded_sources(self, db_session):
        """Verify early exit when all transactions are from excluded sources (CC/insurance)."""
        cc_income = CreditCardTransaction(
            id="cc_income_only",
            date="2024-06-01",
            provider="isracard",
            account_name="Main Card",
            description="Refund",
            amount=500.0,
            category="Other Income",
            tag=None,
            source="credit_card_transactions",
            type="normal",
            status="completed",
        )
        db_session.add(cc_income)
        db_session.commit()

        service = AnalysisService(db_session)
        result = service.get_income_by_source_over_time()

        assert result == []

    def test_returns_empty_when_only_prior_wealth_income(self, db_session):
        """Verify early exit when all income after filtering is tagged Prior Wealth."""
        pw_txn = BankTransaction(
            id="bank_pw_only",
            date="2024-06-01",
            provider="hapoalim",
            account_name="Checking",
            description="Prior Wealth Entry",
            amount=10000.0,
            category="Other Income",
            tag="Prior Wealth",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        db_session.add(pw_txn)
        db_session.commit()

        service = AnalysisService(db_session)
        result = service.get_income_by_source_over_time()

        assert result == []

    def test_returns_empty_when_only_expense_transactions(self, db_session):
        """Verify early exit when data exists but no income transactions after filtering."""
        expense = BankTransaction(
            id="bank_expense_only",
            date="2024-06-01",
            provider="hapoalim",
            account_name="Checking",
            description="Rent",
            amount=-3000.0,
            category="Home",
            tag="Rent",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        db_session.add(expense)
        db_session.commit()

        service = AnalysisService(db_session)
        result = service.get_income_by_source_over_time()

        assert result == []


class TestNetWorthEmptyEarlyExit:
    """Tests for get_net_worth_over_time empty data early exit."""

    def test_returns_empty_when_only_cc_transactions(self, db_session):
        """Verify early exit when all transactions are excluded (CC only)."""
        cc_txn = CreditCardTransaction(
            id="cc_nw_only",
            date="2024-06-01",
            provider="isracard",
            account_name="Main Card",
            description="Purchase",
            amount=-100.0,
            category="Food",
            tag="Groceries",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        )
        db_session.add(cc_txn)
        db_session.commit()

        service = AnalysisService(db_session)
        result = service.get_net_worth_over_time()

        assert result == []


class TestMonthlyExpenses:
    """Tests for get_monthly_expenses aggregation and rolling averages."""

    def test_get_monthly_expenses_returns_months_and_averages(
        self, db_session, seed_base_transactions
    ):
        """Verify monthly expenses returns correct structure with months list and averages."""
        service = AnalysisService(db_session)
        result = service.get_monthly_expenses()

        assert "months" in result
        assert "avg_3_months" in result
        assert "avg_6_months" in result
        assert "avg_12_months" in result
        assert len(result["months"]) > 0

        for entry in result["months"]:
            assert "month" in entry
            assert "expenses" in entry
            assert entry["expenses"] >= 0

    def test_get_monthly_expenses_empty_db(self, db_session):
        """Verify empty database returns zero averages."""
        service = AnalysisService(db_session)
        result = service.get_monthly_expenses()

        assert result["months"] == []
        assert result["avg_3_months"] == 0.0
        assert result["avg_6_months"] == 0.0
        assert result["avg_12_months"] == 0.0

    def test_get_monthly_expenses_months_ordered_chronologically(
        self, db_session, seed_base_transactions
    ):
        """Verify monthly expense entries are sorted by month ascending."""
        service = AnalysisService(db_session)
        result = service.get_monthly_expenses()

        months = [entry["month"] for entry in result["months"]]
        assert months == sorted(months)

    def test_get_monthly_expenses_amounts_are_positive(
        self, db_session, seed_base_transactions
    ):
        """Verify expense amounts are positive (negated from raw negative convention)."""
        service = AnalysisService(db_session)
        result = service.get_monthly_expenses()

        for entry in result["months"]:
            assert entry["expenses"] >= 0

    def test_get_monthly_expenses_averages_are_floats(
        self, db_session, seed_base_transactions
    ):
        """Verify rolling averages are numeric float values."""
        service = AnalysisService(db_session)
        result = service.get_monthly_expenses()

        assert isinstance(result["avg_3_months"], float)
        assert isinstance(result["avg_6_months"], float)
        assert isinstance(result["avg_12_months"], float)
