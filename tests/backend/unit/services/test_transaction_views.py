"""Tests for the bank and spending views of the household's transactions."""

import pytest

from backend.constants.categories import PRIOR_WEALTH_TAG
from backend.models.transaction import (
    BankTransaction,
    CreditCardTransaction,
    InsuranceTransaction,
)
from backend.repositories.budget_repository import BudgetRepository
from backend.services.pending_refunds_service import PendingRefundsService
from backend.services.transaction_views import TransactionViews

_MODELS = {
    "bank_transactions": BankTransaction,
    "credit_card_transactions": CreditCardTransaction,
    "insurance_transactions": InsuranceTransaction,
}


def _add(db_session, source, amount, category, date="2026-03-10", tag=None, id_=None):
    """Insert one transaction into ``source``'s table and return its unique_id."""
    row = _MODELS[source](
        id=id_ or f"{source}-{category}-{amount}-{date}",
        date=date,
        provider="leumi",
        account_name="Main",
        description=category,
        amount=amount,
        category=category,
        tag=tag,
        source=source,
    )
    db_session.add(row)
    db_session.commit()
    return row.unique_id


def _descriptions(frame):
    """Return the sorted ``category`` values of a view frame."""
    return sorted(frame["category"].tolist())


class TestCardPurchasesAndBills:
    """Each view counts a card purchase exactly once."""

    @pytest.fixture
    def card_month(self, db_session):
        """A 300 card purchase and the 300 bank debit that paid its statement."""
        _add(db_session, "credit_card_transactions", -300.0, "Groceries")
        _add(db_session, "bank_transactions", -300.0, "Credit Cards")

    def test_bank_view_counts_the_statement_not_the_purchase(self, db_session, card_month):
        """Verify the bank view sees the bill as the expense and no card rows."""
        view = TransactionViews(db_session).bank()

        assert _descriptions(view.expenses) == ["Credit Cards"]
        assert view.expenses["amount"].sum() == -300.0

    def test_spending_view_counts_the_purchase_not_the_statement(
        self, db_session, card_month
    ):
        """Verify the spending view sees the purchase and leaves the bill out."""
        view = TransactionViews(db_session).spending()

        assert _descriptions(view.expenses) == ["Groceries"]
        assert view.expenses["amount"].sum() == -300.0


class TestRowsNoViewKeeps:
    """Insurance deposits, prior wealth and Ignore are never spending."""

    @pytest.mark.parametrize("view_name", ["bank", "spending"])
    def test_insurance_deposits_are_left_out(self, db_session, view_name):
        """Verify an insurance deposit is in neither view."""
        _add(db_session, "insurance_transactions", -500.0, "Insurance")

        view = getattr(TransactionViews(db_session), view_name)()

        assert view.rows.empty

    @pytest.mark.parametrize("view_name", ["bank", "spending"])
    def test_prior_wealth_rows_are_left_out(self, db_session, view_name):
        """Verify an opening balance is not counted as income."""
        _add(db_session, "bank_transactions", 15000.0, "Other Income", tag=PRIOR_WEALTH_TAG)
        _add(db_session, "bank_transactions", 4000.0, "Other Income")

        view = getattr(TransactionViews(db_session), view_name)()

        assert view.income["amount"].tolist() == [4000.0]

    def test_spending_view_leaves_ignore_out(self, db_session):
        """Verify an internal transfer is neither income nor spending."""
        _add(db_session, "bank_transactions", -1000.0, "Ignore", id_="out")
        _add(db_session, "bank_transactions", 1000.0, "Ignore", id_="in")

        assert TransactionViews(db_session).spending().rows.empty


class TestClassification:
    """Every kept row is exactly one of income, expense or investment."""

    @pytest.mark.parametrize("view_name", ["bank", "spending"])
    def test_liabilities_split_by_sign(self, db_session, view_name):
        """Verify a loan receipt is income and a debt payment is an expense."""
        _add(db_session, "bank_transactions", 20000.0, "Liabilities", tag="Car loan")
        _add(db_session, "bank_transactions", -800.0, "Liabilities", tag="Car loan")

        view = getattr(TransactionViews(db_session), view_name)()

        assert view.income["amount"].tolist() == [20000.0]
        assert view.expenses["amount"].tolist() == [-800.0]

    @pytest.mark.parametrize("view_name", ["bank", "spending"])
    def test_kinds_are_disjoint(self, db_session, view_name):
        """Verify income, expense and investment rows partition the view."""
        _add(db_session, "bank_transactions", 9000.0, "Salary")
        _add(db_session, "bank_transactions", -2000.0, "Investments")
        _add(db_session, "bank_transactions", -120.0, "Restaurants")

        view = getattr(TransactionViews(db_session), view_name)()

        assert view.income["amount"].tolist() == [9000.0]
        assert view.investments["amount"].tolist() == [-2000.0]
        assert view.expenses["amount"].tolist() == [-120.0]
        assert len(view.rows) == 3


class TestRefundNetting:
    """A refund matched to its purchase is one event, whatever the months."""

    def _purchase_and_refund(self, db_session):
        """A 1,000 March purchase refunded 1,000 in May, linked."""
        purchase = _add(db_session, "bank_transactions", -1000.0, "Electronics")
        refund = _add(
            db_session, "bank_transactions", 1000.0, "Electronics", date="2026-05-02"
        )
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund(
            source_type="transaction",
            source_id=purchase,
            source_table="banks",
            expected_amount=1000.0,
        )
        service.link_refund(
            pending_refund_id=pending["id"],
            refund_transaction_id=refund,
            refund_source="banks",
            amount=1000.0,
        )

    @pytest.mark.parametrize("view_name", ["bank", "spending"])
    def test_matched_refund_cancels_both_sides(self, db_session, view_name):
        """Verify neither month shows the purchase or the refund."""
        self._purchase_and_refund(db_session)

        monthly = getattr(TransactionViews(db_session), view_name)().monthly()

        assert monthly["expenses"].abs().sum() == 0.0
        assert monthly["income"].sum() == 0.0

    def test_card_purchase_refunded_to_the_bank(self, db_session):
        """Verify each view nets only a pair it sees both halves of.

        The bank view has the 300 statement that paid the card purchase but
        not the purchase itself, so the refund stays money back against the
        bill; the spending view has the purchase and nets the pair to nothing.
        """
        purchase = _add(db_session, "credit_card_transactions", -300.0, "Shopping")
        _add(db_session, "bank_transactions", -300.0, "Credit Cards")
        refund = _add(
            db_session, "bank_transactions", 300.0, "Shopping", date="2026-04-02"
        )
        service = PendingRefundsService(db_session)
        pending = service.mark_as_pending_refund(
            source_type="transaction",
            source_id=purchase,
            source_table="credit_cards",
            expected_amount=300.0,
        )
        service.link_refund(
            pending_refund_id=pending["id"],
            refund_transaction_id=refund,
            refund_source="banks",
            amount=300.0,
        )
        views = TransactionViews(db_session)

        assert views.bank().totals()["expenses"] == 0.0
        assert views.spending().totals()["expenses"] == 0.0

    def test_purchase_awaiting_its_refund_is_dropped_only_on_request(self, db_session):
        """Verify the pending-refunds option decides what an open expectation costs."""
        purchase = _add(db_session, "bank_transactions", -400.0, "Electronics")
        PendingRefundsService(db_session).mark_as_pending_refund(
            source_type="transaction",
            source_id=purchase,
            source_table="banks",
            expected_amount=400.0,
        )
        views = TransactionViews(db_session)

        assert views.bank(exclude_pending_refunds=False).expenses["amount"].sum() == -400.0
        assert views.bank(exclude_pending_refunds=True).expenses["amount"].sum() == 0.0


class TestOptions:
    """Project and liability exclusion leave whole rows out."""

    def test_exclude_projects_drops_project_categories(self, db_session, monkeypatch):
        """Verify a project-budget category is left out on request only."""
        monkeypatch.setattr(
            BudgetRepository, "read_project_category_names", lambda self: ["Wedding"]
        )
        _add(db_session, "bank_transactions", -5000.0, "Wedding")
        _add(db_session, "bank_transactions", -100.0, "Groceries")
        views = TransactionViews(db_session)

        assert _descriptions(views.spending().expenses) == ["Groceries", "Wedding"]
        assert _descriptions(views.spending(exclude_projects=True).expenses) == [
            "Groceries"
        ]

    def test_exclude_liabilities_drops_loans_and_payments(self, db_session):
        """Verify both halves of a loan go when liabilities are excluded."""
        _add(db_session, "bank_transactions", 20000.0, "Liabilities")
        _add(db_session, "bank_transactions", -800.0, "Liabilities")

        assert TransactionViews(db_session).bank(exclude_liabilities=True).rows.empty


class TestMonthly:
    """Per-month totals as the cards draw them."""

    def test_signs_and_every_month(self, db_session):
        """Verify card-only months read zero on the bank view and signs are positive."""
        _add(db_session, "bank_transactions", 9000.0, "Salary", date="2026-01-05")
        _add(db_session, "bank_transactions", -2000.0, "Investments", date="2026-01-06")
        _add(db_session, "bank_transactions", -3000.0, "Rent", date="2026-01-07")
        _add(db_session, "credit_card_transactions", -50.0, "Coffee", date="2026-02-03")

        monthly = TransactionViews(db_session).bank().monthly()

        assert monthly.index.tolist() == ["2026-01", "2026-02"]
        assert monthly.loc["2026-01"].to_dict() == {
            "income": 9000.0,
            "expenses": 3000.0,
            "investments": 2000.0,
        }
        assert monthly.loc["2026-02"].to_dict() == {
            "income": 0.0,
            "expenses": 0.0,
            "investments": 0.0,
        }

    @pytest.mark.parametrize("view_name", ["bank", "spending"])
    def test_empty_database(self, db_session, view_name):
        """Verify a fresh install yields an empty view rather than an error."""
        view = getattr(TransactionViews(db_session), view_name)()

        assert view.rows.empty
        assert view.months == []
        assert view.monthly().empty
