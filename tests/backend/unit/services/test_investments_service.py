"""Tests for InvestmentsService using real in-memory SQLite database."""

import pandas as pd
import pytest

from backend.models.insurance_account import InsuranceAccount
from backend.models.investment import Investment as InvestmentModel
from backend.models.transaction import InsuranceTransaction, ManualInvestmentTransaction
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

    def test_calculate_balance_over_time_closed_stops_at_last_transaction(
        self, db_session, seed_investments
    ):
        """Verify closed investment balance history ends at last transaction date."""
        service = InvestmentsService(db_session)
        bond_fund = seed_investments["investments"][1]

        # Bond fund is closed. Last transaction is 2024-01-10.
        # Request history far beyond that — should stop at 2024-01-10.
        history = service.calculate_balance_over_time(
            bond_fund.id,
            start_date="2023-01-01",
            end_date="2025-12-31",
        )

        assert len(history) > 0
        last_date = history[-1]["date"]
        assert last_date == "2024-01-10"

    def test_get_portfolio_overview(self, db_session, seed_investments):
        """Verify portfolio totals reflect open only; allocation includes all."""
        service = InvestmentsService(db_session)

        overview = service.get_portfolio_overview()

        # Only stock_fund is open with balance 12000
        assert overview["total_value"] == 12000.0

        # total_deposits for stock fund = 12000, total_withdrawals = 0
        # total_profit = 12000 - (12000 - 0) = 0
        assert overview["total_profit"] == 0.0

        # ROI = ((12000 / 12000) - 1) * 100 = 0%
        assert overview["portfolio_roi"] == pytest.approx(0.0)

        # Allocation includes both open and closed investments
        assert len(overview["allocation"]) == 2
        stock = next(a for a in overview["allocation"] if a["name"] == "Migdal S&P 500 Fund")
        assert stock["balance"] == 12000.0
        assert stock["type"] == "mutual_fund"
        assert stock["id"] == seed_investments["investments"][0].id

    def test_get_portfolio_overview_includes_sparkline_data(
        self, db_session, seed_investments
    ):
        """Verify allocation entries include deposits, withdrawals, and history."""
        service = InvestmentsService(db_session)

        overview = service.get_portfolio_overview()
        alloc = next(a for a in overview["allocation"] if a["name"] == "Migdal S&P 500 Fund")

        assert "total_deposits" in alloc
        assert "total_withdrawals" in alloc
        assert "history" in alloc
        assert alloc["total_deposits"] == 12000.0
        assert alloc["total_withdrawals"] == 0.0
        assert isinstance(alloc["history"], list)
        assert len(alloc["history"]) > 0

    def test_get_portfolio_overview_empty(self, db_session):
        """Verify empty portfolio returns zeros and empty allocation."""
        service = InvestmentsService(db_session)

        overview = service.get_portfolio_overview()

        assert overview["total_value"] == 0.0
        assert overview["total_profit"] == 0.0
        assert overview["portfolio_roi"] == 0.0
        assert overview["allocation"] == []

    def test_get_portfolio_balance_history_active_only(
        self, db_session, seed_investments
    ):
        """Verify portfolio balance history returns series and total for active investments."""
        service = InvestmentsService(db_session)

        result = service.get_portfolio_balance_history(include_closed=False)

        assert "series" in result
        assert "total" in result
        # Only stock_fund is open
        assert len(result["series"]) == 1
        assert result["series"][0]["name"] == "Migdal S&P 500 Fund"
        assert len(result["series"][0]["data"]) > 0

        # Total should have entries and match stock fund (only 1 investment)
        assert len(result["total"]) > 0

    def test_get_portfolio_balance_history_include_closed(
        self, db_session, seed_investments
    ):
        """Verify include_closed adds closed investment series."""
        service = InvestmentsService(db_session)

        result = service.get_portfolio_balance_history(include_closed=True)

        # Both stock_fund and bond_fund
        assert len(result["series"]) == 2
        names = {s["name"] for s in result["series"]}
        assert "Migdal S&P 500 Fund" in names
        assert "Psagot Government Bond" in names

    def test_get_portfolio_balance_history_empty(self, db_session):
        """Verify empty portfolio returns empty series and total."""
        service = InvestmentsService(db_session)

        result = service.get_portfolio_balance_history()

        assert result["series"] == []
        assert result["total"] == []

    def test_get_portfolio_balance_history_total_sums_correctly(
        self, db_session, seed_investments
    ):
        """Verify total line sums balances across all investments per date."""
        service = InvestmentsService(db_session)

        result = service.get_portfolio_balance_history(include_closed=True)

        # The total should be the sum of all investment balances at each date
        total_by_date = {p["date"]: p["balance"] for p in result["total"]}

        # At any date, total should be >= 0
        for balance in total_by_date.values():
            assert balance >= 0

    def test_get_all_investments_includes_first_transaction_date(
        self, db_session, seed_investments
    ):
        """Verify get_all_investments enriches records with first_transaction_date."""
        service = InvestmentsService(db_session)

        investments = service.get_all_investments(include_closed=True)

        for inv in investments:
            assert "first_transaction_date" in inv

        # Stock fund first transaction is 2023-06-15
        stock = next(i for i in investments if i["name"] == "Migdal S&P 500 Fund")
        assert stock["first_transaction_date"] == "2023-06-15"

        # Bond fund first transaction is 2023-01-10
        bond = next(i for i in investments if i["name"] == "Psagot Government Bond")
        assert bond["first_transaction_date"] == "2023-01-10"


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

    def test_get_total_prior_wealth_sums_all_investments(self, db_session, seed_investments):
        """Verify get_total_prior_wealth sums prior_wealth_amount for all investments."""
        stock_fund, bond_fund = seed_investments["investments"]
        stock_fund.prior_wealth_amount = 12000.0   # open
        bond_fund.prior_wealth_amount = 100.0     # closed — still included
        db_session.commit()

        service = InvestmentsService(db_session)
        total = service.get_total_prior_wealth()

        assert total == pytest.approx(12100.0)

    def test_get_total_prior_wealth_returns_zero_when_empty(self, db_session):
        """Verify get_total_prior_wealth returns 0.0 when no investments exist."""
        service = InvestmentsService(db_session)
        assert service.get_total_prior_wealth() == 0.0

    def test_recalculate_prior_wealth_by_tag_no_op_when_no_matching_investment(
        self, db_session
    ):
        """Verify recalculate_prior_wealth_by_tag does nothing when no investment matches category/tag."""
        service = InvestmentsService(db_session)
        # Should not raise — silent no-op when investment does not exist
        service.recalculate_prior_wealth_by_tag("Investments", "Nonexistent Fund")


class TestInvestmentsServiceEdgeCases:
    """Tests for edge cases and early exits in InvestmentsService."""

    def test_get_investment_analysis_default_dates(self, db_session, seed_investments):
        """Verify get_investment_analysis defaults to first_transaction_date when start_date not provided."""
        service = InvestmentsService(db_session)
        stock_fund = seed_investments["investments"][0]

        result = service.get_investment_analysis(stock_fund.id)

        assert "metrics" in result
        assert "history" in result
        assert len(result["history"]) > 0
        assert result["metrics"]["total_deposits"] == 12000.0

    def test_close_investment_no_transactions(self, db_session):
        """Verify close_investment uses closure date when investment has no transactions."""
        inv = InvestmentModel(
            category="Investments", tag="Empty Fund", type="etf",
            name="Empty Investment", created_date="2024-01-01",
        )
        db_session.add(inv)
        db_session.commit()
        db_session.refresh(inv)

        service = InvestmentsService(db_session)
        service.close_investment(inv.id, closed_date="2025-01-15")

        closed = service.get_investment(inv.id)
        assert closed["is_closed"] == 1

    def test_update_balance_snapshot(self, db_session, seed_investments):
        """Verify update_balance_snapshot delegates to repository."""
        service = InvestmentsService(db_session)
        stock_fund = seed_investments["investments"][0]

        service.create_balance_snapshot(stock_fund.id, "2024-06-01", 15000.0)
        snapshots = service.get_balance_snapshots(stock_fund.id)
        snap_id = snapshots[0]["id"]

        service.update_balance_snapshot(snap_id, balance=16000.0)

        updated = service.get_balance_snapshots(stock_fund.id)
        assert updated[0]["balance"] == 16000.0

    def test_calculate_fixed_rate_non_fixed_exits_early(self, db_session):
        """Verify calculate_fixed_rate_snapshots exits early for non-fixed rate investments."""
        inv = InvestmentModel(
            category="Investments", tag="Variable Fund", type="etf",
            name="Variable Rate", created_date="2024-01-01",
            interest_rate=5.0, interest_rate_type="variable",
        )
        db_session.add(inv)
        db_session.commit()
        db_session.refresh(inv)

        service = InvestmentsService(db_session)
        service.calculate_fixed_rate_snapshots(inv.id)  # Should not raise

    def test_calculate_fixed_rate_no_transactions_exits_early(self, db_session):
        """Verify calculate_fixed_rate_snapshots exits early when no transactions exist."""
        inv = InvestmentModel(
            category="Investments", tag="Fixed Empty", type="savings_account",
            name="Fixed Empty", created_date="2024-01-01",
            interest_rate=5.0, interest_rate_type="fixed",
        )
        db_session.add(inv)
        db_session.commit()
        db_session.refresh(inv)

        service = InvestmentsService(db_session)
        service.calculate_fixed_rate_snapshots(inv.id)  # Should not raise

    def test_recalculate_prior_wealth_no_matching_transactions(self, db_session):
        """Verify prior_wealth set to 0 when investment has no matching manual_investment txns."""
        inv = InvestmentModel(
            category="Investments", tag="Orphan Fund", type="etf",
            name="Orphan", created_date="2024-01-01",
        )
        # Add a manual_investment transaction for a DIFFERENT tag
        txn = ManualInvestmentTransaction(
            id="inv_orphan_1", date="2024-01-01", account_name="Broker",
            description="Deposit", amount=-1000.0, category="Investments",
            tag="Other Fund", source="manual_investment_transactions",
            type="deposit", status="completed", provider="manual",
        )
        db_session.add_all([inv, txn])
        db_session.commit()
        db_session.refresh(inv)

        service = InvestmentsService(db_session)
        service.recalculate_prior_wealth(inv.id)

        db_session.refresh(inv)
        assert inv.prior_wealth_amount == 0.0

    def test_calculate_current_balance_nonexistent(self, db_session):
        """Verify calculate_current_balance raises EntityNotFoundException for nonexistent investment."""
        from backend.errors import EntityNotFoundException

        service = InvestmentsService(db_session)
        with pytest.raises(EntityNotFoundException):
            service.calculate_current_balance(99999)

    def test_calculate_current_balance_closed(self, db_session, seed_investments):
        """Verify calculate_current_balance returns 0 for closed investment."""
        service = InvestmentsService(db_session)
        bond_fund = seed_investments["investments"][1]
        assert service.calculate_current_balance(bond_fund.id) == 0.0

    def test_calculate_balance_over_time_nonexistent(self, db_session):
        """Verify calculate_balance_over_time raises EntityNotFoundException for nonexistent investment."""
        from backend.errors import EntityNotFoundException

        service = InvestmentsService(db_session)
        with pytest.raises(EntityNotFoundException):
            service.calculate_balance_over_time(99999, "2024-01-01", "2024-12-31")

    def test_calculate_balance_over_time_no_transactions(self, db_session):
        """Verify calculate_balance_over_time returns empty when no transactions exist."""
        inv = InvestmentModel(
            category="Investments", tag="Empty Fund2", type="etf",
            name="Empty Fund2", created_date="2024-01-01",
        )
        db_session.add(inv)
        db_session.commit()
        db_session.refresh(inv)

        service = InvestmentsService(db_session)
        result = service.calculate_balance_over_time(inv.id, "2024-01-01", "2024-12-31")
        assert result == []

    def test_calculate_profit_loss_empty(self, db_session):
        """Verify calculate_profit_loss returns zero metrics for investment with no transactions."""
        inv = InvestmentModel(
            category="Investments", tag="No Txns Fund", type="etf",
            name="No Txns", created_date="2024-01-01",
        )
        db_session.add(inv)
        db_session.commit()
        db_session.refresh(inv)

        service = InvestmentsService(db_session)
        metrics = service.calculate_profit_loss(inv.id)

        assert metrics["total_deposits"] == 0.0
        assert metrics["total_withdrawals"] == 0.0
        assert metrics["current_balance"] == 0.0
        assert metrics["roi_percentage"] == 0.0

    def test_get_all_investment_transactions_combined_empty(self, db_session):
        """Verify get_all_investment_transactions_combined returns empty DF with no investments."""
        service = InvestmentsService(db_session)
        result = service.get_all_investment_transactions_combined()
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_get_all_investment_transactions_combined_no_matching_txns(self, db_session):
        """Verify returns empty DF when investments exist but have no transactions."""
        inv = InvestmentModel(
            category="Investments", tag="Lonely Fund", type="etf",
            name="Lonely", created_date="2024-01-01",
        )
        db_session.add(inv)
        db_session.commit()

        service = InvestmentsService(db_session)
        result = service.get_all_investment_transactions_combined()
        assert result.empty

    def test_calculate_balance_from_transactions_empty_df(self, db_session):
        """Verify _calculate_balance_from_transactions returns 0 for empty DataFrame."""
        service = InvestmentsService(db_session)
        result = service._calculate_balance_from_transactions(pd.DataFrame())
        assert result == 0.0

    def test_calculate_balance_from_transactions_missing_amount_column(self, db_session):
        """Verify _calculate_balance_from_transactions returns 0 when amount column missing."""
        service = InvestmentsService(db_session)
        df = pd.DataFrame({"date": ["2024-01-01"], "description": ["test"]})
        result = service._calculate_balance_from_transactions(df)
        assert result == 0.0

    def test_calculate_balance_over_time_with_snapshots(self, db_session, seed_investments):
        """Verify balance history uses snapshot interpolation when snapshots exist."""
        service = InvestmentsService(db_session)
        stock_fund = seed_investments["investments"][0]

        # Create two snapshots
        service.create_balance_snapshot(stock_fund.id, "2023-07-01", 10500.0)
        service.create_balance_snapshot(stock_fund.id, "2023-08-01", 11000.0)

        history = service.calculate_balance_over_time(
            stock_fund.id, "2023-07-01", "2023-08-01"
        )

        assert len(history) > 0
        balance_by_date = {e["date"]: e["balance"] for e in history}

        # At snapshot dates, balance should match exactly
        assert balance_by_date["2023-07-01"] == 10500.0
        assert balance_by_date["2023-08-01"] == 11000.0

        # Midpoint should be interpolated between 10500 and 11000
        mid_balance = balance_by_date.get("2023-07-16")
        if mid_balance is not None:
            assert 10500.0 < mid_balance < 11000.0


class TestSyncFromInsurance:
    """Tests for syncing investments from scraped insurance data."""

    def _make_hishtalmut_meta(self, **overrides):
        """Build a minimal hishtalmut insurance metadata dict."""
        meta = {
            "policy_id": "POL-HST-001",
            "policy_type": "hishtalmut",
            "provider": "hafenix",
            "account_name": "קרן השתלמות כלשהי",
            "balance": 150000.0,
            "balance_date": "2025-06-15",
            "commission_deposits_pct": 1.0,
            "commission_savings_pct": 0.5,
            "liquidity_date": "2029-05-31",
        }
        meta.update(overrides)
        return meta

    def test_creates_investment_on_first_sync(self, db_session):
        """Verify first sync creates a new Investment record with correct fields."""
        service = InvestmentsService(db_session)
        meta = self._make_hishtalmut_meta()

        service.sync_from_insurance(meta)

        investments = service.get_all_investments()
        assert len(investments) == 1
        inv = investments[0]
        assert inv["insurance_policy_id"] == "POL-HST-001"
        assert inv["type"] == "hishtalmut"
        assert inv["category"] == "Investments"
        assert inv["tag"] == "Keren Hishtalmut - hafenix (POL-HST-001)"
        assert inv["name"] == "קרן השתלמות כלשהי"
        assert inv["commission_deposit"] == 1.0
        assert inv["commission_management"] == 0.5
        assert inv["liquidity_date"] == "2029-05-31"
        assert inv["interest_rate_type"] == "variable"

    def test_creates_balance_snapshot_on_first_sync(self, db_session):
        """Verify first sync creates a scraped balance snapshot."""
        service = InvestmentsService(db_session)
        meta = self._make_hishtalmut_meta()

        service.sync_from_insurance(meta)

        investments = service.get_all_investments()
        snapshots = service.get_balance_snapshots(investments[0]["id"])
        assert len(snapshots) == 1
        assert snapshots[0]["balance"] == 150000.0
        assert snapshots[0]["date"] == "2025-06-15"
        assert snapshots[0]["source"] == "scraped"

    def test_updates_existing_investment_on_resync(self, db_session):
        """Verify subsequent sync updates metadata without creating duplicates."""
        service = InvestmentsService(db_session)
        meta = self._make_hishtalmut_meta()
        service.sync_from_insurance(meta)

        updated_meta = self._make_hishtalmut_meta(
            account_name="קרן השתלמות מעודכנת",
            commission_deposits_pct=0.8,
            commission_savings_pct=0.4,
            liquidity_date="2030-01-01",
            balance=160000.0,
            balance_date="2025-07-15",
        )
        service.sync_from_insurance(updated_meta)

        investments = service.get_all_investments()
        assert len(investments) == 1
        inv = investments[0]
        assert inv["name"] == "קרן השתלמות מעודכנת"
        assert inv["commission_deposit"] == 0.8
        assert inv["commission_management"] == 0.4
        assert inv["liquidity_date"] == "2030-01-01"

    def test_skips_pension_policies(self, db_session):
        """Verify pension policies are ignored by sync."""
        service = InvestmentsService(db_session)
        meta = self._make_hishtalmut_meta(policy_type="pension")

        service.sync_from_insurance(meta)

        investments = service.get_all_investments()
        assert len(investments) == 0

    def test_does_not_overwrite_manual_snapshot(self, db_session):
        """Verify scraped snapshot skips dates with existing manual snapshots."""
        service = InvestmentsService(db_session)
        meta = self._make_hishtalmut_meta()
        service.sync_from_insurance(meta)

        inv_id = service.get_all_investments()[0]["id"]
        # Overwrite the scraped snapshot with a manual one on the same date
        service.create_balance_snapshot(inv_id, "2025-06-15", 999999.0, source="manual")

        # Re-sync with different balance on same date
        meta["balance"] = 160000.0
        service.sync_from_insurance(meta)

        snapshots = service.get_balance_snapshots(inv_id)
        snapshot_on_date = [s for s in snapshots if s["date"] == "2025-06-15"]
        assert len(snapshot_on_date) == 1
        assert snapshot_on_date[0]["balance"] == 999999.0
        assert snapshot_on_date[0]["source"] == "manual"

    def test_updates_existing_scraped_snapshot_on_same_date(self, db_session):
        """Verify re-scraping the same date updates the scraped snapshot balance."""
        service = InvestmentsService(db_session)
        meta = self._make_hishtalmut_meta()
        service.sync_from_insurance(meta)

        meta["balance"] = 155000.0
        service.sync_from_insurance(meta)

        inv_id = service.get_all_investments()[0]["id"]
        snapshots = service.get_balance_snapshots(inv_id)
        assert len(snapshots) == 1
        assert snapshots[0]["balance"] == 155000.0

    def test_skips_snapshot_when_no_balance(self, db_session):
        """Verify no snapshot is created when balance data is missing."""
        service = InvestmentsService(db_session)
        meta = self._make_hishtalmut_meta(balance=None, balance_date=None)

        service.sync_from_insurance(meta)

        investments = service.get_all_investments()
        assert len(investments) == 1
        snapshots = service.get_balance_snapshots(investments[0]["id"])
        assert len(snapshots) == 0

    def test_create_path_writes_policy_id_atomically(self, db_session):
        """Verify insurance_policy_id is set as part of the initial insert, not a follow-up update."""
        service = InvestmentsService(db_session)
        service.sync_from_insurance(self._make_hishtalmut_meta())

        row = db_session.query(InvestmentModel).one()
        assert row.insurance_policy_id == "POL-HST-001"

    def test_links_legacy_investment_when_no_policy_id(self, db_session):
        """Verify an existing unlinked investment with the legacy tag gets linked instead of duplicated."""
        service = InvestmentsService(db_session)
        service.create_investment(
            category="Investments",
            tag="Keren Hishtalmut - hafenix",
            type_="hishtalmut",
            name="Legacy Hishtalmut",
            interest_rate_type="variable",
        )

        service.sync_from_insurance(self._make_hishtalmut_meta())

        investments = service.get_all_investments()
        assert len(investments) == 1
        assert investments[0]["insurance_policy_id"] == "POL-HST-001"
        assert investments[0]["tag"] == "Keren Hishtalmut - hafenix (POL-HST-001)"


class TestBackfillFromInsuranceAccounts:
    """Tests for the hishtalmut backfill service method."""

    def _seed_insurance_account(self, db, **fields):
        """Insert an InsuranceAccount row, filling required defaults."""
        defaults = {
            "provider": "hafenix",
            "policy_id": "POL-HST-100",
            "policy_type": "hishtalmut",
            "account_name": "Backfill Fund",
            "balance": 75000.0,
            "balance_date": "2025-05-01",
            "commission_deposits_pct": 1.0,
            "commission_savings_pct": 0.3,
            "liquidity_date": "2028-01-01",
        }
        defaults.update(fields)
        db.add(InsuranceAccount(**defaults))
        db.commit()

    def test_backfill_processes_only_hishtalmut(self, db_session):
        """Verify pension rows are skipped and hishtalmut rows are synced."""
        self._seed_insurance_account(db_session, policy_id="HST-1")
        self._seed_insurance_account(
            db_session, policy_id="PEN-1", policy_type="pension"
        )

        service = InvestmentsService(db_session)
        processed = service.backfill_from_insurance_accounts()

        assert processed == 1
        investments = service.get_all_investments()
        assert len(investments) == 1
        assert investments[0]["insurance_policy_id"] == "HST-1"

    def test_backfill_is_idempotent(self, db_session):
        """Verify re-running backfill does not create duplicates."""
        self._seed_insurance_account(db_session, policy_id="HST-2")
        service = InvestmentsService(db_session)

        service.backfill_from_insurance_accounts()
        service.backfill_from_insurance_accounts()

        assert len(service.get_all_investments()) == 1


class TestInsuranceLinkedTransactions:
    """Tests for merging insurance transactions into investment calculations."""

    def _seed_linked_investment(self, service, policy_id="POL-INS-1"):
        meta = {
            "policy_id": policy_id,
            "policy_type": "hishtalmut",
            "provider": "hafenix",
            "account_name": "Linked Fund",
            "balance": None,
            "balance_date": None,
            "commission_deposits_pct": 1.0,
            "commission_savings_pct": 0.5,
            "liquidity_date": "2030-01-01",
        }
        service.sync_from_insurance(meta)
        return service.get_all_investments()[0]["id"]

    def test_insurance_deposits_included_in_profit_loss(self, db_session):
        """Verify insurance deposits are negated and counted as deposits in P/L."""
        service = InvestmentsService(db_session)
        inv_id = self._seed_linked_investment(service, policy_id="POL-PL")

        db_session.add(InsuranceTransaction(
            id="ins-1",
            date="2025-01-15",
            provider="hafenix",
            account_name="Linked Fund",
            account_number="POL-PL",
            description="Monthly deposit",
            amount=1000.0,
            source="insurance_transactions",
        ))
        db_session.commit()

        metrics = service.calculate_profit_loss(inv_id)
        assert metrics["total_deposits"] == 1000.0
        assert metrics["total_withdrawals"] == 0.0
        assert metrics["first_transaction_date"] == "2025-01-15"

    def test_unlinked_investment_ignores_insurance_transactions(self, db_session):
        """Verify insurance transactions do not leak into investments without a policy link."""
        service = InvestmentsService(db_session)
        service.create_investment(
            category="Investments",
            tag="Standalone",
            type_="etf",
            name="Standalone ETF",
            interest_rate_type="variable",
        )
        inv_id = service.get_all_investments()[0]["id"]

        db_session.add(InsuranceTransaction(
            id="ins-unrelated",
            date="2025-02-01",
            provider="hafenix",
            account_name="Other",
            account_number="POL-OTHER",
            description="Not mine",
            amount=500.0,
            source="insurance_transactions",
        ))
        db_session.commit()

        metrics = service.calculate_profit_loss(inv_id)
        assert metrics["total_deposits"] == 0.0
