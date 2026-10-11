"""Tests for the cash-flow counting basis and the breakdowns that use it."""

from datetime import date

import pandas as pd

from backend.models.transaction import BankTransaction, CreditCardTransaction
from backend.services.analysis import AnalysisService
from backend.services.cash_flow_basis import (
    REFUNDS_SOURCE_LABEL,
    date_cards_by_billing,
    refund_mask,
)
from backend.services.pending_refunds_service import PendingRefundsService
from tests.backend.unit.services.savings_goal_helpers import create_project

_TODAY = date(2026, 10, 11)


def _cards(rows: list[dict]) -> pd.DataFrame:
    """A frame of card rows, with defaults for what a test does not care about."""
    base = {
        "source": "credit_card_transactions",
        "provider": "isracard",
        "account_name": "Card",
        "amount": -100.0,
        "category": "Food",
        "billing_date": None,
    }
    return pd.DataFrame([{**base, **row} for row in rows])


class TestDateCardsByBilling:
    """Card rows move to the day they were charged; nothing else moves."""

    def test_a_reported_billing_date_wins(self):
        """The card's own charge day is used as is."""
        df = _cards([{"date": "2026-08-20", "billing_date": "2026-09-02"}])

        assert date_cards_by_billing(df, _TODAY)["date"].tolist() == ["2026-09-02"]

    def test_a_missing_one_takes_the_card_s_usual_day_next_month(self):
        """An old row is estimated from its card's other rows."""
        df = _cards([
            {"date": "2026-07-03", "billing_date": "2026-08-02"},
            {"date": "2026-08-25", "billing_date": "2026-09-02"},
            {"date": "2026-06-14"},
        ])

        assert date_cards_by_billing(df, _TODAY)["date"].tolist()[2] == "2026-07-02"

    def test_a_card_with_no_reported_day_bills_on_the_10th(self):
        """With nothing to learn from, the common Israeli billing day is assumed."""
        df = _cards([{"date": "2026-05-14"}])

        assert date_cards_by_billing(df, _TODAY)["date"].tolist() == ["2026-06-10"]

    def test_a_10th_card_bills_early_purchases_the_same_month(self):
        """Its cycle closes two days before the 10th: the 5th is on that bill."""
        df = _cards([
            {"date": "2026-05-05"},
            {"date": "2026-05-09"},
        ])

        assert date_cards_by_billing(df, _TODAY)["date"].tolist() == [
            "2026-05-10",
            "2026-06-10",
        ]

    def test_a_bill_on_a_weekend_is_charged_on_sunday(self):
        """Friday 10 July 2026 is charged on Sunday the 12th."""
        df = _cards([{"date": "2026-06-14"}])

        assert date_cards_by_billing(df, _TODAY)["date"].tolist() == ["2026-07-12"]

    def test_a_holiday_and_the_weekend_after_it_push_the_bill_on(self):
        """Yom Kippur on 2 Oct 2025, then Friday and Saturday: Sunday the 5th."""
        df = _cards([
            {"date": "2025-07-03", "billing_date": "2025-08-03"},
            {"date": "2025-09-14"},
        ])

        assert date_cards_by_billing(df, _TODAY)["date"].tolist()[1] == "2025-10-05"

    def test_each_card_keeps_its_own_day(self):
        """Two cards behind one login can bill on different days."""
        df = _cards([
            {"date": "2026-07-03", "billing_date": "2026-08-02", "account_number": "1"},
            {"date": "2026-07-03", "billing_date": "2026-08-10", "account_number": "2"},
            {"date": "2026-05-14", "account_number": "1"},
            {"date": "2026-05-14", "account_number": "2"},
        ])

        dates = date_cards_by_billing(df, _TODAY)["date"].tolist()
        assert dates[2:] == ["2026-06-02", "2026-06-10"]

    def test_a_charge_still_to_come_is_dropped(self):
        """Money the card has not taken from the bank yet has not moved."""
        df = _cards([
            {"date": "2026-10-05", "billing_date": "2026-11-02"},
            {"date": "2026-09-05", "billing_date": "2026-10-02"},
        ])

        assert date_cards_by_billing(df, _TODAY)["date"].tolist() == ["2026-10-02"]

    def test_bank_rows_are_untouched(self):
        """Only card rows have a billing day."""
        df = pd.DataFrame([{
            "source": "bank_transactions", "date": "2026-10-20",
            "provider": "hapoalim", "account_name": "Main", "amount": -5.0,
            "category": "Food",
        }])

        assert date_cards_by_billing(df, _TODAY)["date"].tolist() == ["2026-10-20"]


class TestRefundMask:
    """A refund is money back on spending, whatever source it came from."""

    def test_positive_spending_categories_are_refunds(self):
        """Income, loans, investments and transfers are never refunds."""
        df = pd.DataFrame({
            "category": ["Food", None, "Salary", "Liabilities", "Ignore", "Food"],
            "amount": [50.0, 20.0, 9000.0, 1000.0, 300.0, -50.0],
        })

        assert refund_mask(df).tolist() == [True, True, False, False, False, False]


def _month(rows: list[dict], month: str) -> dict | None:
    """The row for ``month``."""
    return next((r for r in rows if r["month"] == month), None)


def _bank(db, id_: str, d: str, amount: float, category: str) -> BankTransaction:
    """Insert one bank row."""
    txn = BankTransaction(
        id=id_, date=d, provider="leumi", account_name="Checking",
        description=id_, amount=amount, category=category,
        source="bank_transactions",
    )
    db.add(txn)
    db.commit()
    return txn


def _card(db, id_: str, d: str, amount: float, category: str, billed: str | None):
    """Insert one card row with the billing date the card reported."""
    txn = CreditCardTransaction(
        id=id_, date=d, provider="max", account_name="Visa", description=id_,
        amount=amount, category=category, source="credit_card_transactions",
        billing_date=billed,
    )
    db.add(txn)
    db.commit()
    return txn


class TestIncomeAndExpensesOnTheCashFlowBasis:
    """The Income & Expenses series, counted as money moved."""

    def test_card_spending_lands_in_the_bill_s_month_with_its_category(
        self, db_session
    ):
        """A January purchase billed in February is February's Food."""
        _card(db_session, "tv", "2024-01-20", -800.0, "Food", "2024-02-02")
        service = AnalysisService(db_session)

        cash = service.get_expenses_by_category_over_time(basis="cash_flow")
        cost = service.get_expenses_by_category_over_time()

        assert _month(cash, "2024-02")["categories"] == {"Food": 800.0}
        assert _month(cash, "2024-01") is None
        assert _month(cost, "2024-01")["categories"] == {"Food": 800.0}

    def test_a_refund_is_income_where_it_landed(self, db_session):
        """A matched refund stays put, as income, and the purchase stays whole."""
        tv = _bank(db_session, "tv", "2024-01-10", -1000.0, "Electronics")
        back = _bank(db_session, "back", "2024-03-14", 1000.0, "Electronics")
        refunds = PendingRefundsService(db_session)
        pending = refunds.mark_as_pending_refund(
            source_type="transaction", source_id=tv.unique_id,
            source_table="banks", expected_amount=1000.0,
        )
        refunds.link_refund(
            pending_refund_id=pending["id"], refund_transaction_id=back.unique_id,
            refund_source="banks", amount=1000.0,
        )
        service = AnalysisService(db_session)

        expenses = service.get_expenses_by_category_over_time(basis="cash_flow")
        income = service.get_income_by_source_over_time(basis="cash_flow")

        assert _month(expenses, "2024-01")["categories"] == {"Electronics": 1000.0}
        assert _month(expenses, "2024-03") is None
        assert _month(income, "2024-03")["sources"] == {REFUNDS_SOURCE_LABEL: 1000.0}

    def test_a_card_refund_is_income_on_the_day_the_card_credited_it(
        self, db_session
    ):
        """Card refunds are income too, on their bill's date."""
        _card(db_session, "back", "2024-01-25", 200.0, "Clothing", "2024-02-10")

        income = AnalysisService(db_session).get_income_by_source_over_time(
            basis="cash_flow"
        )

        assert _month(income, "2024-02")["sources"] == {REFUNDS_SOURCE_LABEL: 200.0}

    def test_the_projects_switch_takes_a_project_s_refunds_too(self, db_session):
        """Leaving a project out leaves out the money it got back."""
        create_project(db_session, "Wedding")
        _bank(db_session, "back", "2024-03-14", 300.0, "Wedding")
        service = AnalysisService(db_session)

        kept = service.get_income_by_source_over_time(basis="cash_flow")
        dropped = service.get_income_by_source_over_time(
            basis="cash_flow", exclude_projects=True
        )

        assert _month(kept, "2024-03")["sources"] == {REFUNDS_SOURCE_LABEL: 300.0}
        assert _month(dropped, "2024-03") is None

    def test_the_net_cost_basis_has_no_refunds_source(self, db_session):
        """The default basis nets refunds into spending, never into income."""
        _bank(db_session, "back", "2024-03-14", 300.0, "Clothing")

        income = AnalysisService(db_session).get_income_by_source_over_time()

        assert _month(income, "2024-03") is None
