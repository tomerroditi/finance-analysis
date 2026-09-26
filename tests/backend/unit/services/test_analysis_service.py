"""Tests for AnalysisService functionality."""

from datetime import date

import pandas as pd
import pytest

from backend.constants.tables import Tables
from backend.models.transaction import BankTransaction, CreditCardTransaction
from backend.services.analysis import AnalysisService
from backend.services.pending_refunds_service import PendingRefundsService
from backend.services.recurring_service import RecurringService
from backend.services.transaction_classification import income_mask, investment_mask


def _months_ago(n: int, day: int = 10) -> str:
    """A YYYY-MM-DD string ``n`` months back, on a fixed day."""
    d = (pd.Timestamp.today().normalize() - pd.DateOffset(months=n)).replace(day=day)
    return d.strftime("%Y-%m-%d")


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
        """Verify overview returns zero-valued result on empty database.

        ``_get_base_transactions`` returns an empty DataFrame with the
        canonical transaction columns when no source has rows, so the
        downstream ``df["date"]`` / aggregation calls work cleanly.
        ``latest_data_date`` is coerced to ``None`` so the response is
        JSON-serialisable.
        """
        service = AnalysisService(db_session)
        result = service.get_overview()

        assert result["latest_data_date"] is None
        assert result["total_income"] == 0
        assert result["total_expenses"] == 0
        assert result["total_investments"] == 0
        assert result["net_balance_change"] == 0


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

    def test_cc_only_month_appears_with_zeros(self, db_session):
        """A month with only credit-card rows still appears, valued at zero.

        The month index is built before the cashflow source exclusion, so a
        CC-only month must not vanish from the series (regression guard for
        the vectorized implementation).
        """
        db_session.add(
            CreditCardTransaction(
                id="cc-only-1",
                date="2030-06-15",
                provider="isracard",
                account_name="cc",
                description="cc only month",
                amount=-500.0,
                category="Food",
                tag="Groceries",
                source="credit_card_transactions",
                type="normal",
                status="completed",
            )
        )
        db_session.commit()

        service = AnalysisService(db_session)
        result = service.get_income_expenses_over_time()

        june = next((r for r in result if r["month"] == "2030-06"), None)
        assert june is not None
        assert june["income"] == 0.0
        assert june["investments"] == 0.0
        assert june["expenses"] == 0.0

    def test_get_net_balance_over_time_empty(self, db_session):
        """Verify empty database returns empty list."""
        service = AnalysisService(db_session)

        result = service.get_net_balance_over_time()
        assert result == []


class TestAnalysisServiceNetWorthOverTime:
    """Tests for net worth over time including cash balance tracking."""

    def test_get_net_worth_over_time_structure(self, db_session, seed_base_transactions):
        """Verify an anchor month plus one snapshot per month, each with all keys."""
        service = AnalysisService(db_session)
        result = service.get_net_worth_over_time()

        assert [r["month"] for r in result] == ["2023-12", "2024-01", "2024-02", "2024-03"]
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

    def test_get_net_worth_over_time_net_worth_equals_bank_plus_investments_plus_cash(
        self, db_session, seed_base_transactions
    ):
        """Verify net_worth = bank_balance + investment_value + cash for each month."""
        service = AnalysisService(db_session)
        result = service.get_net_worth_over_time()

        for entry in result:
            assert entry["net_worth"] == pytest.approx(
                entry["bank_balance"] + entry["investment_value"] + entry["cash"]
            )

    def test_get_net_worth_over_time_cash_does_not_leak_into_bank_balance(
        self, db_session, seed_base_transactions
    ):
        """Verify bank_balance reflects only bank-side flows, not cash spending.

        seed_base_transactions has no investments and no bank-balance prior
        wealth seeded, so prior_wealth_total is 0 and bank_balance at any
        month-end must equal the cumulative sum of *bank-only* transactions
        up to that month-end. Cash transactions belong in the cash line, not
        bundled into bank_balance.
        """
        from backend.repositories.transactions import TransactionsRepository

        repo = TransactionsRepository(db_session)
        bank_only = repo.get_cashflow_transactions()
        bank_only["date_parsed"] = pd.to_datetime(bank_only["date"])
        bank_only = bank_only[bank_only["source"] != Tables.CASH.value]

        service = AnalysisService(db_session)
        result = service.get_net_worth_over_time()

        for entry in result[1:]:  # skip anchor
            month_end = (
                pd.to_datetime(entry["month"] + "-01") + pd.offsets.MonthEnd(0)
            )
            expected = float(
                bank_only.loc[bank_only["date_parsed"] <= month_end, "amount"].sum()
            )
            assert entry["bank_balance"] == pytest.approx(expected), (
                f"bank_balance for {entry['month']} should be {expected} "
                f"(bank+inv cumulative only) but was {entry['bank_balance']} — "
                f"cash leaked in"
            )


class TestAnalysisServiceIncomeExpenses:
    """Tests for income/expense classification logic."""

    def test_get_income_and_expenses(self, db_session, seed_base_transactions):
        """Verify income vs expense calculation via direct method call."""
        service = AnalysisService(db_session)

        # Call get_income_investments_and_expenses directly with the full transactions df
        df = service.repo.get_table()
        income, _investments, expenses = service.get_income_investments_and_expenses(df)

        # Income from bank+cash only (CC excluded): Salary 24700 + Other Income 3500
        assert income == 28200.0

        # Expenses from bank+cash only: Home/Rent 9000 + Coffee 45 + Parking 30
        assert expenses == 9075.0

    def test_income_mask_includes_salary(self, db_session, seed_base_transactions):
        """Verify Salary category counted as income by the income mask."""
        service = AnalysisService(db_session)
        df = service.repo.get_table()
        df = df[df["source"] != "credit_card_transactions"]

        mask = income_mask(df)
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

        mask = income_mask(df)
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

    def test_get_sankey_data_excludes_ignore_category(self, db_session):
        """Verify an unbalanced Ignore transfer is not a Sankey flow.

        Ignore marks internal transfers and CC bill summaries. Its legs only
        cancel when both are tracked, so any residual must be dropped rather
        than surfacing as a phantom expense that skews Wealth Growth.
        """
        from backend.models.transaction import BankTransaction

        for i, (category, amount) in enumerate(
            [("Salary", 10000.0), ("Food", -1200.0), ("Ignore", -5000.0)]
        ):
            db_session.add(
                BankTransaction(
                    id=f"sankey-ignore-{i}", date="2026-03-10", provider="p",
                    account_name="a", description=f"d{i}", amount=amount,
                    category=category, tag=None, source="bank_transactions",
                    type="normal", status="completed",
                )
            )
        db_session.commit()

        result = AnalysisService(db_session).get_sankey_data()
        labels = result["node_labels"]
        assert "Ignore" not in labels
        assert "Refunds: Ignore" not in labels

        flows = {
            (labels[link["source"]], labels[link["target"]]): link["value"]
            for link in result["links"]
        }
        # 10000 income - 1200 real expenses; the 5000 transfer is not spending.
        assert flows[("Total Income", "Wealth Growth")] == 8800.0

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
        # Positive Liabilities with a tag are labeled "Loans / {tag}"
        assert sources["Loans / Mortgage"] == 50000.0
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

class TestIncomeMaskPositiveLiabilities:
    """Tests for income_mask handling of positive liabilities (loan receipts)."""

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
        mask = income_mask(df)

        income_rows = df[mask]
        assert len(income_rows) == 1
        assert income_rows.iloc[0]["amount"] == 50000.0


class TestInvestmentMask:
    """Tests for investment_mask identifying investment transactions."""

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
        mask = investment_mask(df)

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
        mask = investment_mask(df)

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


class TestAnalysisServiceEmptyDatabaseSafety:
    """Tests guaranteeing analysis endpoints don't crash on a fresh empty database."""

    def test_get_income_expenses_over_time_empty_db(self, db_session):
        """Verify empty database returns an empty list rather than raising KeyError."""
        service = AnalysisService(db_session)
        result = service.get_income_expenses_over_time()
        assert result == []

    def test_get_income_expenses_over_time_empty_db_with_flags(self, db_session):
        """Verify empty database is handled when toggle flags are passed."""
        service = AnalysisService(db_session)
        result = service.get_income_expenses_over_time(
            exclude_projects=True, exclude_liabilities=True, exclude_refunds=True
        )
        assert result == []

    def test_get_debt_payments_over_time_empty_db(self, db_session):
        """Verify empty database returns an empty list rather than raising KeyError."""
        service = AnalysisService(db_session)
        result = service.get_debt_payments_over_time()
        assert result == []


class TestMonthlyExpenses:
    """Tests for get_monthly_expenses aggregation and rolling averages."""

    def test_get_monthly_expenses_returns_months_and_averages(
        self, db_session, seed_base_transactions
    ):
        """Verify months come back chronologically with non-negative expenses and float averages."""
        service = AnalysisService(db_session)
        result = service.get_monthly_expenses()

        assert "months" in result
        assert "avg_3_months" in result
        assert "avg_6_months" in result
        assert "avg_12_months" in result
        assert len(result["months"]) > 0
        assert all(isinstance(result[k], float) for k in ("avg_3_months", "avg_6_months", "avg_12_months"))

        months = [entry["month"] for entry in result["months"]]
        assert months == sorted(months)
        for entry in result["months"]:
            assert entry["expenses"] >= 0

    def test_get_monthly_expenses_empty_db(self, db_session):
        """Verify empty database returns zero averages."""
        service = AnalysisService(db_session)
        result = service.get_monthly_expenses()

        assert result["months"] == []
        assert result["avg_3_months"] == 0.0
        assert result["avg_6_months"] == 0.0
        assert result["avg_12_months"] == 0.0

class TestCashFlowForecast:
    """Tests for AnalysisService.get_cash_flow_forecast."""

    def test_forecast_empty_db(self, db_session):
        """Verify forecast returns a zero-valued, well-shaped result on empty DB."""
        service = AnalysisService(db_session)
        result = service.get_cash_flow_forecast()

        assert result["actual_income"] == 0
        assert result["actual_expenses"] == 0
        assert result["expected_income"] == 0
        assert result["expected_expenses"] == 0
        assert result["safe_to_spend"] == 0
        assert result["current_bank_balance"] == 0
        assert result["projected_end_balance"] == result["current_bank_balance"]
        # daily trajectory always spans the full month
        assert len(result["daily"]) == result["days_in_month"]

    def test_forecast_shape_with_data(self, db_session, seed_base_transactions):
        """Verify forecast exposes all documented keys and a full daily series."""
        service = AnalysisService(db_session)
        result = service.get_cash_flow_forecast()

        for key in (
            "month", "days_in_month", "day_of_month", "days_remaining",
            "actual_income", "actual_expenses", "expected_income",
            "expected_expenses", "projected_net", "current_bank_balance",
            "projected_end_balance", "safe_to_spend", "safe_to_spend_daily",
            "avg_monthly_income", "avg_monthly_expenses", "committed_remaining",
            "daily",
        ):
            assert key in result

        assert result["days_in_month"] == len(result["daily"])
        # safe_to_spend is never negative
        assert result["safe_to_spend"] >= 0
        # exactly the elapsed days carry an actual balance, the rest projected
        actual = [d for d in result["daily"] if d["actual_balance"] is not None]
        assert len(actual) == result["day_of_month"]

    def test_forecast_subtracts_upcoming_recurring(self, db_session):
        """A subscription due later this month feeds committed_remaining and
        keeps safe_to_spend at or below income-minus-spent."""
        import pytest

        from backend.models.transaction import CreditCardTransaction

        today = pd.Timestamp.today().normalize()
        month_end = today + pd.offsets.MonthEnd(0)
        if today >= month_end:
            pytest.skip("run on the last day of the month — no remaining days")

        # Place 4 monthly charges so the next expected charge lands tomorrow,
        # inside the remaining days of the current month.
        next_due = today + pd.Timedelta(days=1)
        for k in range(1, 5):
            d = (next_due - pd.Timedelta(days=30 * k)).strftime("%Y-%m-%d")
            db_session.add(
                CreditCardTransaction(
                    id=f"sub-{k}",
                    date=d,
                    provider="visa",
                    account_name="card",
                    description="NETFLIX.COM",
                    amount=-45.0,
                    category="Streaming",
                    source=Tables.CREDIT_CARD.value,
                )
            )
        db_session.commit()

        # The forecast acts only on confirmed charges, so a detection nobody
        # has ruled on commits nothing.
        from backend.services.recurring_service import RecurringService

        recurring = RecurringService(db_session)
        assert AnalysisService(db_session).get_cash_flow_forecast()[
            "committed_remaining"
        ] == 0.0

        key = recurring.get_recurring()["items"][0]["normalized"]
        recurring.set_decisions([{"normalized": key, "decision": "confirmed"}])

        result = AnalysisService(db_session).get_cash_flow_forecast()
        assert result["committed_remaining"] >= 45.0
        assert result["safe_to_spend"] <= max(
            0.0, result["expected_income"] - result["actual_expenses"]
        )


class TestAnalysisServiceIncomeBySourceAggregate:
    """Tests for get_income_by_source (date-range aggregate)."""

    def _seed(self, db_session):
        """Seed three months of income across two sources + one CC + prior wealth."""
        records = [
            BankTransaction(
                id="agg_sal_jan", date="2024-01-15", provider="hapoalim",
                account_name="Checking", description="Salary Jan",
                amount=8000.0, category="Salary", tag=None,
                source="bank_transactions", type="normal", status="completed",
            ),
            BankTransaction(
                id="agg_free_jan", date="2024-01-20", provider="leumi",
                account_name="Business", description="Freelance Jan",
                amount=2000.0, category="Other Income", tag="Freelance",
                source="bank_transactions", type="normal", status="completed",
            ),
            BankTransaction(
                id="agg_sal_feb", date="2024-02-15", provider="hapoalim",
                account_name="Checking", description="Salary Feb",
                amount=8500.0, category="Salary", tag=None,
                source="bank_transactions", type="normal", status="completed",
            ),
            BankTransaction(
                id="agg_sal_mar", date="2024-03-15", provider="hapoalim",
                account_name="Checking", description="Salary Mar",
                amount=8200.0, category="Salary", tag=None,
                source="bank_transactions", type="normal", status="completed",
            ),
            # Credit-card income-category row must be EXCLUDED (CC source).
            CreditCardTransaction(
                id="agg_cc", date="2024-02-10", provider="isracard",
                account_name="Visa", description="CC refund",
                amount=999.0, category="Other Income", tag=None,
                source="credit_card_transactions", type="normal", status="completed",
            ),
            # Prior Wealth must be EXCLUDED.
            BankTransaction(
                id="agg_pw", date="2024-01-01", provider="hapoalim",
                account_name="Checking", description="Opening balance",
                amount=50000.0, category="Salary", tag="Prior Wealth",
                source="bank_transactions", type="normal", status="completed",
            ),
        ]
        db_session.add_all(records)
        db_session.commit()

    def test_all_time_aggregates_and_sorts_by_amount(self, db_session):
        """All-time: sources summed across months, sorted desc, with shares + total."""
        self._seed(db_session)
        result = AnalysisService(db_session).get_income_by_source()

        assert result["start"] is None
        assert result["end"] is None
        # Salary 8000+8500+8200 = 24700; Freelance 2000. CC + Prior Wealth excluded.
        assert result["total"] == 26700.0
        labels = [s["label"] for s in result["sources"]]
        assert labels == ["Salary", "Other Income / Freelance"]  # sorted desc
        assert result["sources"][0]["amount"] == 24700.0
        assert result["sources"][1]["amount"] == 2000.0
        assert result["sources"][0]["share"] == round(24700.0 / 26700.0, 4)

    def test_date_range_is_inclusive_on_both_edges(self, db_session):
        """A window covering only Jan keeps Jan rows, drops Feb/Mar."""
        self._seed(db_session)
        result = AnalysisService(db_session).get_income_by_source(
            start=date(2024, 1, 1), end=date(2024, 1, 31)
        )
        assert result["start"] == "2024-01-01"
        assert result["end"] == "2024-01-31"
        assert result["total"] == 10000.0  # Salary 8000 + Freelance 2000
        labels = {s["label"] for s in result["sources"]}
        assert labels == {"Salary", "Other Income / Freelance"}

    def test_empty_window_returns_zero(self, db_session):
        """A window with no income returns empty sources and zero total."""
        self._seed(db_session)
        result = AnalysisService(db_session).get_income_by_source(
            start=date(2025, 1, 1), end=date(2025, 12, 31)
        )
        assert result["sources"] == []
        assert result["total"] == 0.0

    def test_empty_db_does_not_raise(self, db_session):
        """Empty DB returns a zero result (regression: no KeyError on fresh install)."""
        result = AnalysisService(db_session).get_income_by_source()
        assert result == {"sources": [], "total": 0.0, "start": None, "end": None}

    def test_one_sided_windows_filter_independently(self, db_session):
        """A start-only window and an end-only window each filter on their own edge."""

        self._seed(db_session)
        service = AnalysisService(db_session)

        # start-only: drop Jan, keep Feb (8500) + Mar (8200) Salary.
        start_only = service.get_income_by_source(start=date(2024, 2, 1))
        assert start_only["start"] == "2024-02-01"
        assert start_only["end"] is None
        assert start_only["total"] == 16700.0
        assert [s["label"] for s in start_only["sources"]] == ["Salary"]

        # end-only: keep only Jan Salary (8000) + Freelance (2000).
        end_only = service.get_income_by_source(end=date(2024, 1, 31))
        assert end_only["start"] is None
        assert end_only["end"] == "2024-01-31"
        assert end_only["total"] == 10000.0
        assert {s["label"] for s in end_only["sources"]} == {
            "Salary",
            "Other Income / Freelance",
        }
        # Shares of a complete breakdown sum to ~1.
        assert round(sum(s["share"] for s in end_only["sources"]), 4) == 1.0


class TestMonthlyExpenseAveragesExcludePartialMonth:
    """Trend baselines average complete months only."""

    def test_avg_3_months_ignores_running_month(self, db_session):
        """Three complete 3,000 months average to 3,000, not a diluted figure.

        Including the running month divided a few days of spend by a full
        month, dragging the cash-flow forecast's expense baseline down while
        its income baseline already excluded that month.
        """
        import pandas as pd

        from backend.models.transaction import BankTransaction

        today = pd.Timestamp.today().normalize()
        rows = []
        for index, offset in enumerate((1, 2, 3)):
            month = (today - pd.DateOffset(months=offset)).replace(day=15)
            rows.append(
                BankTransaction(
                    id=f"avg{index}", date=month.strftime("%Y-%m-%d"),
                    provider="p", account_name="a", description="d",
                    amount=-3000.0, category="Food", tag=None,
                    source="bank_transactions", type="normal",
                    status="completed",
                )
            )
        rows.append(
            BankTransaction(
                id="avg-partial", date=today.replace(day=1).strftime("%Y-%m-%d"),
                provider="p", account_name="a", description="partial",
                amount=-100.0, category="Food", tag=None,
                source="bank_transactions", type="normal", status="completed",
            )
        )
        db_session.add_all(rows)
        db_session.commit()

        result = AnalysisService(db_session).get_monthly_expenses()
        assert result["avg_3_months"] == 3000.0


class TestAvgMonthlySalary:
    """Tests for ``get_avg_monthly_salary`` (the retirement auto-fill default)."""

    def test_averages_per_month_salary_totals(self, db_session, seed_base_transactions):
        """The three seeded salary months average to their mean."""
        service = AnalysisService(db_session)
        assert service.get_avg_monthly_salary() == pytest.approx((8000 + 8500 + 8200) / 3)

    def test_window_keeps_only_the_most_recent_months(self, db_session, seed_base_transactions):
        """``months`` limits the average to the latest N salary months."""
        service = AnalysisService(db_session)
        assert service.get_avg_monthly_salary(months=2) == pytest.approx((8500 + 8200) / 2)
        assert service.get_avg_monthly_salary(months=1) == pytest.approx(8200)

    def test_two_salary_lines_in_one_month_are_summed_first(self, db_session):
        """Averaging happens over per-month totals, not individual transactions."""
        for i, (d, amt) in enumerate([("2024-01-01", 5000.0), ("2024-01-15", 3000.0), ("2024-02-01", 6000.0)]):
            db_session.add(
                BankTransaction(
                    id=f"sal_{i}", date=d, provider="leumi", account_name="Checking",
                    description="Salary", amount=amt, category="Salary", source="bank_transactions",
                )
            )
        db_session.commit()

        assert AnalysisService(db_session).get_avg_monthly_salary() == pytest.approx(7000.0)

    def test_none_when_no_transactions(self, db_session):
        """An empty database has no salary to average."""
        assert AnalysisService(db_session).get_avg_monthly_salary() is None

    def test_none_when_no_salary_category(self, db_session):
        """Income that is not in the Salary category does not count."""
        db_session.add(
            BankTransaction(
                id="other_income", date="2024-01-01", provider="leumi", account_name="Checking",
                description="Gift", amount=1000.0, category="Other Income", source="bank_transactions",
            )
        )
        db_session.commit()

        assert AnalysisService(db_session).get_avg_monthly_salary() is None


class TestDebtPaymentsOverTime:
    """Tests for ``get_debt_payments_over_time`` with real liability transactions."""

    def test_groups_negative_liability_payments_by_month_and_tag(self, db_session, seed_liabilities):
        """Each payment month reports its positive total and a per-tag breakdown."""
        result = AnalysisService(db_session).get_debt_payments_over_time()

        assert [r["month"] for r in result] == ["2023-07", "2023-08", "2023-09"]
        assert all(r["amount"] == 1150.0 for r in result)
        assert all(r["tags"] == {"Car Loan": 1150.0} for r in result)

    def test_untagged_payments_fall_under_uncategorized(self, db_session):
        """A Liabilities payment without a tag is bucketed as ``Uncategorized``."""
        db_session.add(
            BankTransaction(
                id="untagged_debt", date="2024-03-05", provider="leumi", account_name="Checking",
                description="Loan", amount=-400.0, category="Liabilities", tag=None,
                source="bank_transactions",
            )
        )
        db_session.commit()

        result = AnalysisService(db_session).get_debt_payments_over_time()

        assert result == [{"month": "2024-03", "amount": 400.0, "tags": {"Uncategorized": 400.0}}]

    def test_credit_card_liability_rows_are_excluded(self, db_session):
        """CC-sourced rows are outside the cashflow view and never counted."""
        db_session.add(
            CreditCardTransaction(
                id="cc_debt", date="2024-03-05", provider="visa", account_name="Card",
                description="Loan via card", amount=-400.0, category="Liabilities", tag="X",
                source="credit_card_transactions",
            )
        )
        db_session.commit()

        assert AnalysisService(db_session).get_debt_payments_over_time() == []


class TestIncomeExpensesOverTimeFlags:
    """Tests for the exclusion flags on ``get_income_expenses_over_time``."""

    @staticmethod
    def _month(result, month):
        return next(r for r in result if r["month"] == month)

    def test_exclude_liabilities_drops_debt_from_both_sides(self, db_session, seed_liabilities):
        """Debt payments are expenses and loan receipts are income unless liabilities are excluded."""
        service = AnalysisService(db_session)

        default = service.get_income_expenses_over_time()
        excluded = service.get_income_expenses_over_time(exclude_liabilities=True)

        assert self._month(default, "2023-07")["expenses"] == 1150.0
        assert self._month(default, "2023-06")["income"] == 50000.0
        # Months that held nothing but liability rows disappear altogether.
        assert {r["month"] for r in excluded} == {"2024-01", "2024-02", "2024-03"}
        assert self._month(excluded, "2024-01") == self._month(default, "2024-01")

    def test_exclude_refunds_ignores_positive_expense_and_negative_income_rows(self, db_session):
        """Refunds (positive expense rows) and income reversals are dropped when flagged."""
        rows = [
            ("rent", "2024-01-03", -3000.0, "Home", "Rent"),
            ("refund", "2024-01-20", 200.0, "Home", "Rent"),
            ("salary", "2024-01-01", 8000.0, "Salary", None),
            ("reversal", "2024-01-21", -300.0, "Salary", None),
        ]
        for id_, d, amount, category, tag in rows:
            db_session.add(
                BankTransaction(
                    id=id_, date=d, provider="leumi", account_name="Checking", description=id_,
                    amount=amount, category=category, tag=tag, source="bank_transactions",
                )
            )
        db_session.commit()
        service = AnalysisService(db_session)

        default = self._month(service.get_income_expenses_over_time(), "2024-01")
        strict = self._month(service.get_income_expenses_over_time(exclude_refunds=True), "2024-01")

        assert (default["income"], default["expenses"]) == (7700.0, 2800.0)
        assert (strict["income"], strict["expenses"]) == (8000.0, 3000.0)

    def test_exclude_projects_removes_project_category_spend(self, db_session, seed_project_transactions):
        """Rows whose category is a project budget name vanish when ``exclude_projects`` is set."""
        service = AnalysisService(db_session)

        default = self._month(service.get_income_expenses_over_time(), "2024-02")
        no_projects = service.get_income_expenses_over_time(exclude_projects=True)

        # The 15,000 Wedding bank transfer in February is project spend.
        assert default["expenses"] >= 15000.0
        feb = next((r for r in no_projects if r["month"] == "2024-02"), None)
        assert feb is None or feb["expenses"] == default["expenses"] - 15000.0

    def test_exclude_projects_is_a_no_op_without_project_budgets(self, db_session, seed_base_transactions):
        """With no project rules the flag changes nothing."""
        service = AnalysisService(db_session)
        assert service.get_income_expenses_over_time(exclude_projects=True) == service.get_income_expenses_over_time()


class TestMonthlyExpensesWithProjects:
    """Tests for ``get_monthly_expenses(include_projects=True)``."""

    def test_project_expenses_are_reported_separately_per_month(
        self, db_session, seed_base_transactions, seed_project_transactions
    ):
        """Each month carries a ``project_expenses`` figure alongside regular expenses."""
        result = AnalysisService(db_session).get_monthly_expenses(include_projects=True)

        by_month = {m["month"]: m for m in result["months"]}
        assert all("project_expenses" in m for m in result["months"])
        # Jan: Wedding 5,000 + Renovation 3,200. Feb: Wedding 800 + 15,000,
        # Renovation 8,000 + 1,500. Project spend is never folded into the
        # regular ``expenses`` figure.
        assert by_month["2024-01"]["project_expenses"] == 8200.0
        assert by_month["2024-02"]["project_expenses"] == 25300.0
        assert by_month["2024-01"]["expenses"] < 5000.0

    def test_only_project_spend_yields_no_months(self, db_session, seed_project_transactions):
        """Project-only data has no regular expenses, so the trend is empty even with the flag."""
        result = AnalysisService(db_session).get_monthly_expenses(include_projects=True)
        assert result == {"months": [], "avg_3_months": 0.0, "avg_6_months": 0.0, "avg_12_months": 0.0}

    def test_without_flag_project_key_is_absent(self, db_session, seed_base_transactions, seed_project_transactions):
        """The default shape stays unchanged for callers that do not ask for projects."""
        result = AnalysisService(db_session).get_monthly_expenses()
        assert result["months"] and all("project_expenses" not in m for m in result["months"])

    def test_flag_without_project_budgets_reports_zero(self, db_session, seed_base_transactions):
        """When no project rules exist every month reports zero project spend."""
        result = AnalysisService(db_session).get_monthly_expenses(include_projects=True)
        assert result["months"] and all(m["project_expenses"] == 0.0 for m in result["months"])


class TestRefundNettingAcrossMonths:
    """A matched refund cancels its purchase whatever months the two fell in."""

    @staticmethod
    def _month(result, month):
        return next((r for r in result if r["month"] == month), None)

    @staticmethod
    def _seed(db_session, rows):
        """Insert ``(id, date, amount, category, tag)`` bank rows."""
        for id_, d, amount, category, tag in rows:
            db_session.add(
                BankTransaction(
                    id=id_, date=d, provider="leumi", account_name="Checking",
                    description=id_, amount=amount, category=category, tag=tag,
                    source="bank_transactions",
                )
            )
        db_session.commit()

    def _link(self, db_session, purchase_uid, refund_uid, expected, amount):
        """Mark ``purchase_uid`` as awaiting ``expected`` and match ``amount`` to ``refund_uid``."""
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund(
            source_type="transaction", source_id=purchase_uid,
            source_table="banks", expected_amount=expected,
        )
        service.link_refund(
            pending_refund_id=pending["id"], refund_transaction_id=refund_uid,
            refund_source="banks", amount=amount,
        )
        return pending

    def _uids(self, db_session):
        """Map seeded row ids to the auto-increment unique_ids they landed on."""
        rows = db_session.query(BankTransaction).all()
        return {r.id: r.unique_id for r in rows}

    def test_resolved_refund_removes_both_sides_in_their_own_months(self, db_session):
        """A January purchase repaid in March leaves neither month changed."""
        self._seed(db_session, [
            ("rent", "2024-01-03", -3000.0, "Home", "Rent"),
            ("tv", "2024-01-10", -1000.0, "Electronics", None),
            ("tv-refund", "2024-03-14", 1000.0, "Electronics", None),
        ])
        uids = self._uids(db_session)
        self._link(db_session, uids["tv"], uids["tv-refund"], 1000.0, 1000.0)

        result = AnalysisService(db_session).get_income_expenses_over_time()

        # January keeps only the rent: the refunded TV never cost anything.
        assert self._month(result, "2024-01")["expenses"] == 3000.0
        # March neither gains income nor shows a negative expense.
        march = self._month(result, "2024-03")
        assert march is None or (march["expenses"], march["income"]) == (0.0, 0.0)

    def test_partial_refund_leaves_only_the_unrecovered_part(self, db_session):
        """300 back on a 1,000 purchase nets 300, not the whole row."""
        self._seed(db_session, [
            ("tv", "2024-01-10", -1000.0, "Electronics", None),
            ("part-refund", "2024-02-14", 300.0, "Electronics", None),
        ])
        uids = self._uids(db_session)
        self._link(db_session, uids["tv"], uids["part-refund"], 300.0, 300.0)

        service = AnalysisService(db_session)
        # With the expectation fully matched there is nothing outstanding, so
        # both views agree: 700 of real spend stays.
        for exclude in (True, False):
            result = service.get_income_expenses_over_time(
                exclude_pending_refunds=exclude
            )
            assert self._month(result, "2024-01")["expenses"] == 700.0
            feb = self._month(result, "2024-02")
            assert feb is None or feb["income"] == 0.0

    def test_open_expectation_follows_the_toggle(self, db_session):
        """An unmatched expectation is hidden only when pending refunds are excluded."""
        self._seed(db_session, [
            ("loan-to-friend", "2024-01-10", -800.0, "Other", None),
        ])
        uids = self._uids(db_session)
        PendingRefundsService(db_session).mark_as_pending_refund(
            source_type="transaction", source_id=uids["loan-to-friend"],
            source_table="banks", expected_amount=800.0,
        )
        service = AnalysisService(db_session)

        excluded = service.get_income_expenses_over_time(exclude_pending_refunds=True)
        included = service.get_income_expenses_over_time(exclude_pending_refunds=False)

        jan = self._month(excluded, "2024-01")
        assert jan is None or jan["expenses"] == 0.0
        assert self._month(included, "2024-01")["expenses"] == 800.0

    def test_closed_remainder_stays_an_expense_either_way(self, db_session):
        """Money the user gave up recovering is spend, whatever the toggle says."""
        self._seed(db_session, [
            ("deposit", "2024-01-10", -500.0, "Other", None),
        ])
        uids = self._uids(db_session)
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund(
            source_type="transaction", source_id=uids["deposit"],
            source_table="banks", expected_amount=500.0,
        )
        service.close_pending_refund(pending["id"])
        analysis = AnalysisService(db_session)

        for exclude in (True, False):
            result = analysis.get_income_expenses_over_time(
                exclude_pending_refunds=exclude
            )
            assert self._month(result, "2024-01")["expenses"] == 500.0

    def test_refund_nets_against_its_purchases_category_not_its_own(self, db_session):
        """The breakdown credits the category that was charged, not the refund's."""
        self._seed(db_session, [
            ("tv", "2024-01-10", -1000.0, "Electronics", None),
            ("tv-refund", "2024-03-14", 1000.0, "Uncategorized Refunds", None),
        ])
        uids = self._uids(db_session)
        self._link(db_session, uids["tv"], uids["tv-refund"], 1000.0, 1000.0)

        result = AnalysisService(db_session).get_expenses_by_category_over_time()

        jan = self._month(result, "2024-01")
        assert jan is None or "Electronics" not in jan["categories"]
        # The refund's own category never receives the money either.
        for row in result:
            assert "Uncategorized Refunds" not in row["categories"]

    def test_sankey_stops_flowing_a_repaid_charge_out_and_back(self, db_session):
        """A netted purchase is neither an expense destination nor a Refunds source."""
        self._seed(db_session, [
            ("salary", "2024-01-01", 9000.0, "Salary", None),
            ("tv", "2024-01-10", -1000.0, "Electronics", None),
            ("tv-refund", "2024-03-14", 1000.0, "Electronics", None),
        ])
        uids = self._uids(db_session)
        self._link(db_session, uids["tv"], uids["tv-refund"], 1000.0, 1000.0)

        nodes = AnalysisService(db_session).get_sankey_data()["nodes"]

        assert "Electronics" not in nodes
        assert not any(n.startswith("Refunds:") for n in nodes)

    def test_sankey_unknown_gap_is_measured_before_netting(self, db_session):
        """Netting must not invent untracked card spend out of a refund."""
        # A card purchase repaid into the bank: the bill still covered the
        # full charge, so the itemized detail is complete and there is no gap.
        db_session.add(
            CreditCardTransaction(
                id="cc-tv", date="2024-01-10", provider="max", account_name="Visa",
                description="tv", amount=-1000.0, category="Electronics",
                source="credit_card_transactions",
            )
        )
        self._seed(db_session, [
            ("cc-bill", "2024-02-02", -1000.0, "Credit Cards", None),
            ("tv-refund", "2024-03-14", 1000.0, "Electronics", None),
        ])
        db_session.commit()
        cc_uid = db_session.query(CreditCardTransaction).one().unique_id
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund(
            source_type="transaction", source_id=cc_uid,
            source_table="credit_cards", expected_amount=1000.0,
        )
        service.link_refund(
            pending_refund_id=pending["id"],
            refund_transaction_id=self._uids(db_session)["tv-refund"],
            refund_source="banks", amount=1000.0,
        )

        nodes = AnalysisService(db_session).get_sankey_data()["nodes"]

        assert "Unknown" not in nodes

    def test_matched_refund_is_not_counted_as_income(self, db_session):
        """A repayment landing in an income category is money back, not earnings."""
        self._seed(db_session, [
            ("salary", "2024-03-01", 8000.0, "Salary", None),
            ("work-expense", "2024-01-10", -600.0, "Other", None),
            ("reimbursement", "2024-03-05", 600.0, "Other Income", None),
        ])
        uids = self._uids(db_session)
        self._link(db_session, uids["work-expense"], uids["reimbursement"], 600.0, 600.0)

        service = AnalysisService(db_session)
        over_time = service.get_income_expenses_over_time()
        by_source = service.get_income_by_source_over_time()

        assert self._month(over_time, "2024-03")["income"] == 8000.0
        march_sources = self._month(by_source, "2024-03")["sources"]
        assert sum(march_sources.values()) == 8000.0
        assert not any("Other Income" in label for label in march_sources)


class TestExpenseBreakdownFilters:
    """``get_expenses_by_category_over_time`` filters, and what they guarantee.

    The Income & Expenses card totals these very rows rather than reading a
    separate totals endpoint, so a filter that cannot reach part of the data
    is not a cosmetic gap — it is the card showing two different answers for
    the same money. See ``.claude/rules/kpi_calculations.md``.
    """

    @staticmethod
    def _total(rows) -> float:
        return round(sum(sum(r["categories"].values()) for r in rows), 2)

    def test_project_categories_are_dropped_including_spend_put_on_a_card(
        self, db_session, seed_base_transactions, seed_project_transactions
    ):
        """The projects filter reaches project spend paid by credit card.

        This is why the card reads the itemized breakdown: on the bank-side
        view a card purchase is folded into a bill row categorised
        ``Credit Cards``, so no category filter can ever see it. The Wedding
        rows in the fixture are credit-card transactions precisely so this
        test fails if the filter is ever moved back onto a bill-based series.
        """
        service = AnalysisService(db_session)

        kept = service.get_expenses_by_category_over_time()
        dropped = service.get_expenses_by_category_over_time(exclude_projects=True)

        assert any("Wedding" in r["categories"] for r in kept)
        assert all("Wedding" not in r["categories"] for r in dropped)
        assert all("Renovation" not in r["categories"] for r in dropped)
        assert self._total(dropped) < self._total(kept)

    def test_debt_payments_leave_the_breakdown_with_their_loan_name(
        self, db_session
    ):
        """The liabilities filter drops debt payments, which carry the loan's tag."""
        db_session.add_all([
            BankTransaction(
                id="dbt_mortgage", date="2024-01-05", provider="leumi",
                account_name="Checking", description="Mortgage",
                amount=-4000.0, category="Liabilities", tag="Mortgage",
                source="bank_transactions",
            ),
            BankTransaction(
                id="dbt_food", date="2024-01-06", provider="leumi",
                account_name="Checking", description="Groceries",
                amount=-300.0, category="Food", tag=None,
                source="bank_transactions",
            ),
        ])
        db_session.commit()
        service = AnalysisService(db_session)

        with_debt = service.get_expenses_by_category_over_time()
        without = service.get_expenses_by_category_over_time(exclude_liabilities=True)

        assert with_debt[0]["categories"]["Mortgage"] == 4000.0
        assert "Mortgage" not in without[0]["categories"]
        assert without[0]["categories"]["Food"] == 300.0

    def test_loan_receipts_leave_the_income_breakdown_with_the_same_switch(
        self, db_session
    ):
        """Excluding debt drops the loan's money in as well as its payments out.

        Taking the payments out of the outflow while leaving the money the
        loan paid in as income would report the household as having saved the
        whole loan.
        """
        db_session.add_all([
            BankTransaction(
                id="loan_in", date="2024-01-02", provider="leumi",
                account_name="Checking", description="Mortgage drawdown",
                amount=900000.0, category="Liabilities", tag="Mortgage",
                source="bank_transactions",
            ),
            BankTransaction(
                id="loan_salary", date="2024-01-03", provider="leumi",
                account_name="Checking", description="Salary",
                amount=10000.0, category="Salary", tag=None,
                source="bank_transactions",
            ),
        ])
        db_session.commit()
        service = AnalysisService(db_session)

        with_loan = service.get_income_by_source_over_time()
        without = service.get_income_by_source_over_time(exclude_liabilities=True)

        assert any("Loans / Mortgage" in r["sources"] for r in with_loan)
        assert all(
            not any(label.startswith("Loans") for label in r["sources"])
            for r in without
        )
        assert without[0]["sources"]["Salary"] == 10000.0

    def test_an_unmatched_refund_can_leave_a_category_in_credit(self, db_session):
        """A refund with no purchase to match nets against the category it lands in.

        The month total is what the card's ledger shows, so a category left in
        credit has to survive into the payload: dropping it would report a
        month as having spent money that came back.
        """
        db_session.add_all([
            BankTransaction(
                id="ref_buy", date="2024-01-05", provider="leumi",
                account_name="Checking", description="Jacket",
                amount=-200.0, category="Shopping", tag=None,
                source="bank_transactions",
            ),
            BankTransaction(
                id="ref_back", date="2024-01-20", provider="leumi",
                account_name="Checking", description="Jacket returned",
                amount=500.0, category="Shopping", tag=None,
                source="bank_transactions",
            ),
        ])
        db_session.commit()

        rows = AnalysisService(db_session).get_expenses_by_category_over_time()

        assert rows[0]["categories"]["Shopping"] == -300.0

    def test_both_filters_on_reproduces_the_budget_views_expense_figure(
        self, db_session, seed_base_transactions, seed_project_transactions
    ):
        """One definition, two switches — the envelope view is a position on it.

        With projects and debt both excluded the breakdown must agree, month by
        month, with ``get_monthly_expenses`` (which the Budget page uses). That
        equality is what makes the card's chips a view of one number rather
        than a fourth definition of "expenses".
        """
        service = AnalysisService(db_session)

        breakdown = service.get_expenses_by_category_over_time(
            exclude_projects=True, exclude_liabilities=True
        )
        budget = service.get_monthly_expenses()

        by_month = {r["month"]: round(sum(r["categories"].values()), 2) for r in breakdown}
        for month in budget["months"]:
            assert by_month.get(month["month"], 0.0) == round(month["expenses"], 2)


class TestForecastIncomeComesFromRecurringStreams:
    """The income half of get_cash_flow_forecast."""

    def _salary(self, db_session, amount=12000.0, day=10, months=6, skip_current=True):
        """A salary paid on ``day`` of each of the last ``months`` months."""
        anchor = pd.Timestamp.today().normalize().replace(day=day)
        start = 1 if skip_current else 0
        for n in range(start, months + start):
            db_session.add(
                BankTransaction(
                    id=f"sal-{n}",
                    date=(anchor - pd.DateOffset(months=n)).strftime("%Y-%m-%d"),
                    provider="leumi",
                    account_name="Checking",
                    description="MONTHLY SALARY",
                    amount=amount,
                    category="Salary",
                    source=Tables.BANK.value,
                )
            )
        db_session.commit()

    def test_a_windfall_does_not_become_next_month_s_income(self, db_session):
        """A one-off deposit three months ago must not be projected as income.

        This is the bug the recurring basis exists for: an averaged baseline
        carried a single 400k month into the next three forecasts, which told
        a household on a 12k salary it was on track to save six figures.
        """
        self._salary(db_session, day=1, skip_current=False)
        db_session.add(
            BankTransaction(
                id="windfall",
                date=_months_ago(2),
                provider="leumi",
                account_name="Checking",
                description="INHERITANCE",
                amount=400000.0,
                category="Other Income",
                source=Tables.BANK.value,
            )
        )
        db_session.commit()

        result = AnalysisService(db_session).get_cash_flow_forecast()

        assert result["income_basis"] == "recurring"
        assert result["expected_income"] < 40000.0
        assert result["projected_net"] < 40000.0

    def test_a_salary_not_yet_paid_is_added_to_what_is_in_hand(self, db_session):
        """Early in the month the forecast still expects the salary to land."""
        import pytest

        today = pd.Timestamp.today().normalize()
        if today.day >= today.days_in_month:
            pytest.skip("run on the last day of the month — no day left to pay on")
        # Anchor pay day just ahead of today, whenever the suite runs.
        self._salary(db_session, day=today.day + 1)

        result = AnalysisService(db_session).get_cash_flow_forecast()

        assert result["recurring_income_due"] == 12000.0
        assert result["expected_income"] == pytest.approx(
            result["actual_income"] + 12000.0
        )

    def test_no_stream_falls_back_to_a_median_not_a_mean(self, db_session):
        """With nothing recurring to lean on, one freak month must not set the
        baseline — the median of the complete months does."""
        payers = ["ALPHA LTD", "BETA GMBH", "GAMMA INC", "DELTA CO"]
        amounts = [5000.0, 5000.0, 400000.0, 5000.0]
        for n, (payer, amount) in enumerate(zip(payers, amounts), start=1):
            db_session.add(
                BankTransaction(
                    id=f"odd-{n}",
                    date=_months_ago(n),
                    provider="leumi",
                    account_name="Checking",
                    description=payer,
                    amount=amount,
                    category="Other Income",
                    source=Tables.BANK.value,
                )
            )
        db_session.commit()

        result = AnalysisService(db_session).get_cash_flow_forecast()

        assert result["income_basis"] == "trend"
        assert result["avg_monthly_income"] == 5000.0

    def test_a_salary_already_banked_keeps_the_recurring_basis(self, db_session):
        """A stream that has paid owes nothing and is still the evidence.

        If an empty "still due" list flipped the basis back to the trend, the
        forecast would swap to a median the moment the salary landed — and
        immediately hand back the windfall the recurring basis exists to keep
        out.
        """
        import pytest

        today = pd.Timestamp.today().normalize()
        if today.day < 2:
            pytest.skip("run on the 1st — no earlier day to bank the salary on")
        self._salary(db_session, day=1)
        db_session.add(
            BankTransaction(
                id="sal-this-month",
                date=today.replace(day=1).strftime("%Y-%m-%d"),
                provider="leumi",
                account_name="Checking",
                description="MONTHLY SALARY",
                amount=12000.0,
                category="Salary",
                source=Tables.BANK.value,
            )
        )
        db_session.commit()

        result = AnalysisService(db_session).get_cash_flow_forecast()

        assert result["income_basis"] == "recurring"
        assert result["recurring_income_due"] == 0.0
        assert result["expected_income"] == result["actual_income"]

    def test_expected_income_never_dips_below_what_is_already_banked(
        self, db_session
    ):
        """Whatever the basis, money in hand is money in hand."""
        result = AnalysisService(db_session).get_cash_flow_forecast()
        assert result["expected_income"] >= result["actual_income"]


class TestForecastExpensesUseOneDefinition:
    """The expense half — month-to-date and trend measured the same way."""

    def test_month_to_date_expenses_match_the_budget_page(self, db_session):
        """``actual_expenses`` is itemized spend, not the card bill the bank
        paid this month for last month's shopping."""
        today = pd.Timestamp.today().normalize()
        db_session.add(
            CreditCardTransaction(
                id="bought-this-month",
                date=today.replace(day=1).strftime("%Y-%m-%d"),
                provider="visa",
                account_name="card-1",
                description="GROCERIES",
                amount=-500.0,
                category="Food",
                source=Tables.CREDIT_CARD.value,
            )
        )
        db_session.add(
            BankTransaction(
                id="card-bill",
                date=today.replace(day=1).strftime("%Y-%m-%d"),
                provider="leumi",
                account_name="Checking",
                description="CARD BILL",
                amount=-9000.0,
                category="Credit Cards",
                source=Tables.BANK.value,
            )
        )
        db_session.commit()

        service = AnalysisService(db_session)
        result = service.get_cash_flow_forecast()
        month = today.strftime("%Y-%m")
        budget_figure = next(
            m["expenses"]
            for m in service.get_monthly_expenses()["months"]
            if m["month"] == month
        )

        assert result["actual_expenses"] == budget_figure

    @staticmethod
    def _pin_sync(monkeypatch, *entries):
        """Pin what the scrape audit trail reports, without a keyring."""
        from backend.services import scraping_history_service

        monkeypatch.setattr(
            scraping_history_service.ScrapingHistoryService,
            "get_last_scrape_dates",
            lambda self: list(entries),
        )

    @staticmethod
    def _sync(service, provider, account, date):
        """One `get_last_scrape_dates` entry."""
        return {
            "service": service,
            "provider": provider,
            "account_name": account,
            "last_scrape_date": date,
        }

    def _seed_history(self, db_session, card=-3000.0, bank=-3000.0):
        """Three complete months of spend, split evenly over two accounts.

        Gives the projection both a trend to scale and a share to split it by.
        """
        for n in range(1, 4):
            db_session.add(
                CreditCardTransaction(
                    id=f"hist-card-{n}",
                    date=_months_ago(n),
                    provider="visa",
                    account_name="card-1",
                    description=f"CARD SHOP {n}",
                    amount=card,
                    category="Food",
                    source=Tables.CREDIT_CARD.value,
                )
            )
            db_session.add(
                BankTransaction(
                    id=f"hist-bank-{n}",
                    date=_months_ago(n),
                    provider="leumi",
                    account_name="acct-1",
                    description=f"BANK DEBIT {n}",
                    amount=bank,
                    category="Household",
                    source=Tables.BANK.value,
                )
            )
        db_session.commit()

    @staticmethod
    def _projected(result):
        """What the forecast expects to still be spent this month."""
        return result["expected_expenses"] - result["actual_expenses"]

    @staticmethod
    def _calendar_share(result):
        """The whole-household projection over the days left on the calendar."""
        return (
            result["avg_monthly_expenses"]
            / result["days_in_month"]
            * result["days_remaining"]
        )

    def test_days_no_account_has_synced_are_projected_not_counted_as_zero(
        self, db_session, monkeypatch
    ):
        """A scrape that stopped a week ago is a week of unknown spending, not
        a week of savings."""
        today = pd.Timestamp.today().normalize()
        if today.day < 12:
            pytest.skip("too early in the month to leave a stale gap")

        self._seed_history(db_session)
        stale = today.replace(day=2).isoformat()
        self._pin_sync(
            monkeypatch,
            self._sync("credit_cards", "visa", "card-1", stale),
            self._sync("banks", "leumi", "acct-1", stale),
        )

        result = AnalysisService(db_session).get_cash_flow_forecast()

        assert result["observed_through"] == today.replace(day=2).strftime("%Y-%m-%d")
        assert self._projected(result) > self._calendar_share(result)

    def test_a_quiet_stretch_on_a_current_sync_is_not_unobserved(
        self, db_session, monkeypatch
    ):
        """Days with no transactions are not days with no data.

        Reading the edge off the last transaction could not tell a household
        that spent nothing since the 2nd from accounts that stopped syncing on
        the 2nd, and projected weeks of spending over the quiet one.
        """
        today = pd.Timestamp.today().normalize()
        if today.day < 12:
            pytest.skip("too early in the month for a quiet stretch")

        self._seed_history(db_session)
        # Nothing bought since the 2nd, but every account is synced to today.
        db_session.add(
            CreditCardTransaction(
                id="last-purchase",
                date=today.replace(day=2).strftime("%Y-%m-%d"),
                provider="visa",
                account_name="card-1",
                description="CARD SHOP now",
                amount=-100.0,
                category="Food",
                source=Tables.CREDIT_CARD.value,
            )
        )
        db_session.commit()
        self._pin_sync(
            monkeypatch,
            self._sync("credit_cards", "visa", "card-1", today.isoformat()),
            self._sync("banks", "leumi", "acct-1", today.isoformat()),
        )

        result = AnalysisService(db_session).get_cash_flow_forecast()

        assert result["observed_through"] == today.strftime("%Y-%m-%d")
        assert self._projected(result) == pytest.approx(self._calendar_share(result))

    def test_each_account_is_projected_over_its_own_unsynced_days(
        self, db_session, monkeypatch
    ):
        """Staleness is per account: one card current to today beside a bank
        three weeks behind is two different holes in the month, not one."""
        today = pd.Timestamp.today().normalize()
        if today.day < 12:
            pytest.skip("too early in the month to leave a stale gap")

        self._seed_history(db_session)
        self._pin_sync(
            monkeypatch,
            self._sync("credit_cards", "visa", "card-1", today.isoformat()),
            self._sync("banks", "leumi", "acct-1", today.replace(day=2).isoformat()),
        )

        result = AnalysisService(db_session).get_cash_flow_forecast()
        days_in_month = result["days_in_month"]
        daily = result["avg_monthly_expenses"] / days_in_month

        # The two accounts spent equally over the trend window, so each
        # carries half the daily rate over its own remaining days.
        expected = daily * 0.5 * (days_in_month - today.day) + daily * 0.5 * (
            days_in_month - 2
        )
        assert self._projected(result) == pytest.approx(expected)

    def test_a_fresh_account_s_spending_does_not_cancel_a_stale_one_s_gap(
        self, db_session, monkeypatch
    ):
        """What the card already reported says nothing about the bank.

        Rolling both accounts into one household window and subtracting what
        had already landed in it let one big card purchase swallow the whole
        month's expectation — including the stale bank's direct debits, which
        nothing had reported at all.
        """
        today = pd.Timestamp.today().normalize()
        if today.day < 12:
            pytest.skip("too early in the month to leave a stale gap")

        self._seed_history(db_session)
        db_session.add(
            CreditCardTransaction(
                id="card-blowout",
                date=today.replace(day=10).strftime("%Y-%m-%d"),
                provider="visa",
                account_name="card-1",
                description="CARD BIG SHOP",
                amount=-99000.0,
                category="Food",
                source=Tables.CREDIT_CARD.value,
            )
        )
        db_session.commit()
        self._pin_sync(
            monkeypatch,
            self._sync("credit_cards", "visa", "card-1", today.isoformat()),
            self._sync("banks", "leumi", "acct-1", today.replace(day=2).isoformat()),
        )

        result = AnalysisService(db_session).get_cash_flow_forecast()
        days_in_month = result["days_in_month"]
        daily = result["avg_monthly_expenses"] / days_in_month

        # The bank's half still projects over the 3rd onward, untouched by the
        # card's blowout.
        assert self._projected(result) >= daily * 0.5 * (days_in_month - 2)

    def test_an_account_that_is_not_scraped_at_all_is_never_behind(
        self, db_session, monkeypatch
    ):
        """Cash and manual entries are typed in, so they are current by
        definition — only the scraped card here has a gap to project."""
        today = pd.Timestamp.today().normalize()
        if today.day < 12:
            pytest.skip("too early in the month to leave a stale gap")

        self._seed_history(db_session)
        # The bank has no credential row at all.
        self._pin_sync(
            monkeypatch,
            self._sync("credit_cards", "visa", "card-1", today.replace(day=2).isoformat()),
        )

        result = AnalysisService(db_session).get_cash_flow_forecast()
        days_in_month = result["days_in_month"]
        daily = result["avg_monthly_expenses"] / days_in_month

        expected = daily * 0.5 * (days_in_month - 2) + daily * 0.5 * (
            days_in_month - today.day
        )
        assert self._projected(result) == pytest.approx(expected)

    def test_insurance_never_holds_the_edge_back(self, db_session, monkeypatch):
        """Insurance is scraped but produces no budget transactions, so a
        stale insurance sync says nothing about the month's completeness."""
        today = pd.Timestamp.today().normalize()
        self._seed_history(db_session)
        self._pin_sync(
            monkeypatch,
            self._sync(
                "insurances", "hafenix", "Tomer",
                (today - pd.Timedelta(days=200)).isoformat(),
            ),
            self._sync("credit_cards", "visa", "card-1", today.isoformat()),
            self._sync("banks", "leumi", "acct-1", today.isoformat()),
        )

        result = AnalysisService(db_session).get_cash_flow_forecast()

        assert result["observed_through"] == today.strftime("%Y-%m-%d")
        assert self._projected(result) == pytest.approx(self._calendar_share(result))

    def test_a_never_synced_account_does_not_blank_the_month(
        self, db_session, monkeypatch
    ):
        """An account with no successful scrape contributed nothing to the
        trend baseline either — counting it would project spending no month
        in the history ever contained."""
        today = pd.Timestamp.today().normalize()
        self._seed_history(db_session)
        self._pin_sync(
            monkeypatch,
            self._sync("banks", "leumi", "acct-1", None),
            self._sync("credit_cards", "visa", "card-1", today.isoformat()),
        )

        result = AnalysisService(db_session).get_cash_flow_forecast()

        assert result["observed_through"] == today.strftime("%Y-%m-%d")
        assert self._projected(result) == pytest.approx(self._calendar_share(result))

    def test_nothing_scrapable_means_nothing_stale(self, db_session, monkeypatch):
        """A cash-only household has no sync to be behind on."""
        self._seed_history(db_session)
        self._pin_sync(monkeypatch)

        result = AnalysisService(db_session).get_cash_flow_forecast()

        assert result["observed_through"] is None
        assert self._projected(result) == pytest.approx(self._calendar_share(result))

    def test_a_committed_bill_is_counted_once(self, db_session):
        """A confirmed recurring charge is added at its due date and taken out
        of the daily trend, not smeared across the month on top of itself."""
        import pytest

        today = pd.Timestamp.today().normalize()
        month_end = today + pd.offsets.MonthEnd(0)
        if today >= month_end:
            pytest.skip("run on the last day of the month — no remaining days")

        next_due = today + pd.Timedelta(days=1)
        for k in range(1, 5):
            db_session.add(
                CreditCardTransaction(
                    id=f"rent-{k}",
                    date=(next_due - pd.Timedelta(days=30 * k)).strftime("%Y-%m-%d"),
                    provider="visa",
                    account_name="card-1",
                    description="RENT",
                    amount=-5000.0,
                    category="Household",
                    source=Tables.CREDIT_CARD.value,
                )
            )
        db_session.commit()

        recurring = RecurringService(db_session)
        key = recurring.get_recurring()["items"][0]["normalized"]
        recurring.set_decisions([{"normalized": key, "decision": "confirmed"}])

        result = AnalysisService(db_session).get_cash_flow_forecast()
        projected = result["expected_expenses"] - result["actual_expenses"]

        assert result["committed_remaining"] >= 5000.0
        # The bill is in there once; a trend that still carried it would push
        # the remainder past the bill plus a full month of everything else.
        assert projected <= result["committed_remaining"] + result[
            "avg_monthly_expenses"
        ]
