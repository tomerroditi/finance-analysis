"""Tests for card billing days, their history, and the account paying each card."""

from datetime import date

import pandas as pd

from backend.models.transaction import BankTransaction, CreditCardTransaction
from backend.services.card_billing import (
    BillingSchedule,
    charge_date,
    is_business_day,
    issuer_key,
    nominal_billing_day,
)
from backend.services.card_billing_service import CardBillingService

ISRACARD_BILL = "חיוב מ-ישראכרט-דיירקט"
MAX_BILL = "מקס איט פיננסים"


class TestBusinessDays:
    """Banks charge on business days only."""

    def test_weekends_and_holidays_are_closed(self):
        """Friday, Saturday and Yom Kippur are closed; a Sunday is open."""
        assert not is_business_day(date(2026, 7, 10))
        assert not is_business_day(date(2026, 7, 11))
        assert not is_business_day(date(2025, 10, 2))
        assert is_business_day(date(2026, 7, 12))

    def test_a_short_month_bills_on_its_last_day(self):
        """A 31st-of-the-month card bills on 30 April."""
        assert charge_date(31, pd.Period("2026-04", "M")) == date(2026, 4, 30)


class TestNominalBillingDay:
    """A charge date is read back to the day the card meant."""

    def test_a_usual_day_is_itself(self):
        """A bill on the 10th is a 10th card."""
        assert nominal_billing_day(date(2026, 6, 10)) == 10

    def test_a_shifted_bill_is_read_back_past_closed_days(self):
        """Sunday the 12th after a Friday 10th is a 10th card."""
        assert nominal_billing_day(date(2026, 7, 12)) == 10

    def test_an_open_day_before_it_means_its_own_day(self):
        """Thursday 3 Sept 2026 with an open 2nd is a 3rd card."""
        assert nominal_billing_day(date(2026, 9, 3)) == 3

    def test_a_bank_posting_a_day_late_is_allowed(self):
        """The bank's record of the same bill may trail it by a day."""
        assert nominal_billing_day(date(2026, 9, 3), posting_lag=1) == 2


class TestIssuerKey:
    """Every spelling of one issuer's bills lands on one key."""

    def test_spellings_agree(self):
        """Prefix, dashes, card digits and reversed Hebrew fold together."""
        spellings = [
            ISRACARD_BILL,
            ISRACARD_BILL.removeprefix("חיוב מ-"),
            ISRACARD_BILL.replace("-", ""),
            "חיוב מ-" + ISRACARD_BILL.removeprefix("חיוב מ-")[::-1],
            "130099981560 " + ISRACARD_BILL.removeprefix("חיוב מ-"),
        ]
        assert len({issuer_key(s) for s in spellings}) == 1

    def test_final_letters_fold(self):
        """A reversed final mem matches its regular form."""
        assert issuer_key(MAX_BILL) == issuer_key(MAX_BILL[::-1])


def _frame(rows: list[dict]) -> pd.DataFrame:
    """Card and bill rows with defaults."""
    base = {
        "provider": "isracard",
        "account_name": "Card",
        "account_number": "1111",
        "source": "credit_card_transactions",
        "category": "Food",
        "description": "shop",
        "billing_date": None,
    }
    return pd.DataFrame([{**base, **row} for row in rows])


class TestScheduleHistory:
    """A card's billing day is kept month by month, as it reported it."""

    def test_a_change_of_billing_day_is_kept(self):
        """A card that moved from the 10th to the 2nd shows both runs."""
        df = _frame([
            {"date": "2026-01-05", "amount": -10.0, "billing_date": "2026-02-10"},
            {"date": "2026-02-05", "amount": -10.0, "billing_date": "2026-03-10"},
            {"date": "2026-03-05", "amount": -10.0, "billing_date": "2026-04-02"},
        ])
        schedule = BillingSchedule.from_frame(df)
        key = ("isracard", "Card", "1111")

        assert schedule.changes(key) == [
            {"day": 10, "from": "2026-02", "to": "2026-03"},
            {"day": 2, "from": "2026-04", "to": "2026-04"},
        ]
        assert schedule.day_for(key, pd.Period("2026-01", "M")) == (10, "reported")
        assert schedule.day_for(key, pd.Period("2026-08", "M")) == (2, "reported")


def _bills_and_card(card_amounts: list[float], bill_amounts: list[float]) -> pd.DataFrame:
    """Months of one card's purchases and one bank stream's bills."""
    rows = []
    for i, (spent, billed) in enumerate(zip(card_amounts, bill_amounts, strict=True)):
        rows.append({"date": f"2026-0{i + 1}-15", "amount": spent})
        rows.append({
            "date": f"2026-0{i + 2}-03",
            "amount": billed,
            "source": "bank_transactions",
            "category": "Credit Cards",
            "provider": "onezero",
            "account_name": "Main",
            "description": ISRACARD_BILL,
            "account_number": None,
        })
    return _frame(rows)


class TestPaidFrom:
    """A card is paired with the bank stream its totals follow."""

    def test_matching_totals_name_the_paying_account(self):
        """Bills within a quarter of the card's totals pair them."""
        df = _bills_and_card([-1000, -2000, -1500, -800], [-1010, -1990, -1480, -805])
        schedule = BillingSchedule.from_frame(df)
        key = ("isracard", "Card", "1111")

        assert schedule.paid_from[key][:2] == ("onezero", "Main")
        assert schedule.day_for(key, pd.Period("2026-08", "M")) == (2, "bills")

    def test_unrelated_bills_name_nobody(self):
        """Totals that do not follow the card leave it unpaired."""
        df = _bills_and_card([-1000, -2000, -1500, -800], [-5000, -90, -7000, -20])

        assert BillingSchedule.from_frame(df).paid_from == {}


class TestCardBillingService:
    """The per-login view the Data Sources page shows."""

    def test_lists_each_card_with_its_day_and_payer(self, db_session):
        """A reported billing date and matching bills both surface."""
        for month in range(1, 5):
            db_session.add(CreditCardTransaction(
                id=f"p{month}", date=f"2026-0{month}-15", provider="max",
                account_name="Visa", account_number="9999", amount=-500.0 * month,
                category="Food", source="credit_card_transactions",
                billing_date=f"2026-0{month + 1}-02" if month == 4 else None,
            ))
            db_session.add(BankTransaction(
                id=f"b{month}", date=f"2026-0{month + 1}-02", provider="leumi",
                account_name="Checking", amount=-500.0 * month, category="Credit Cards",
                description=MAX_BILL, source="bank_transactions",
            ))
        db_session.commit()

        result = CardBillingService(db_session).get_all(today=date(2026, 6, 20))

        assert result == [{
            "provider": "max",
            "account_name": "Visa",
            "cards": [{
                "account_number": "9999",
                "billing_day": 2,
                "billing_day_source": "reported",
                "next_billing_date": "2026-07-02",
                "changes": [{"day": 2, "from": "2026-05", "to": "2026-05"}],
                "paid_from": {"provider": "leumi", "account_name": "Checking"},
            }],
        }]

    def test_an_old_card_is_left_out(self, db_session):
        """A card unused for half a year is no longer listed."""
        db_session.add(CreditCardTransaction(
            id="old", date="2025-01-15", provider="max", account_name="Visa",
            account_number="1", amount=-5.0, source="credit_card_transactions",
        ))
        db_session.commit()

        assert CardBillingService(db_session).get_all(today=date(2026, 6, 20)) == []
