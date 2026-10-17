"""Tests for the split-origin breakdown the income and expense charts draw."""

from backend.models.transaction import BankTransaction
from backend.services.analysis import AnalysisService
from backend.services.transactions_service import TransactionsService


def _bank(db_session, txn_id: str, amount: float, category: str, tag: str | None):
    """Insert one bank transaction dated 2024-04-10 and return its unique_id."""
    row = BankTransaction(
        id=txn_id, date="2024-04-10", provider="hapoalim",
        account_name="Checking", description=txn_id, amount=amount,
        category=category, tag=tag, source="bank_transactions",
        type="normal", status="completed",
    )
    db_session.add(row)
    db_session.commit()
    return row.unique_id


class TestIncomeSplitOrigins:
    """Income parts split away from their parent's tag."""

    def test_part_tagged_apart_is_traced_to_its_parent(self, db_session):
        """A part moved to Salary reports the Bit transfer it came from."""
        uid = _bank(db_session, "bit", 3000.0, "Other Income", "Bit")
        TransactionsService(db_session).split_transaction(
            uid, "bank_transactions",
            [
                {"amount": 1000.0, "category": "Salary", "tag": "Bonus"},
                {"amount": 2000.0, "category": "Other Income", "tag": "Bit"},
            ],
        )

        [month] = AnalysisService(db_session).get_income_by_source_over_time()

        assert month["sources"] == {
            "Salary / Bonus": 1000.0, "Other Income / Bit": 2000.0,
        }
        assert month["split_from"] == {"Salary / Bonus": {"Other Income / Bit": 1000.0}}

    def test_unsplit_income_has_no_origins(self, db_session):
        """Without splits the breakdown carries an empty origin map."""
        _bank(db_session, "pay", 8000.0, "Salary", None)

        [month] = AnalysisService(db_session).get_income_by_source_over_time()

        assert month["split_from"] == {}


class TestExpenseSplitOrigins:
    """Expense parts split away from their parent's category."""

    def test_part_in_another_category_is_traced_to_its_parent(self, db_session):
        """A supermarket bill split into Household reports Food as its origin."""
        uid = _bank(db_session, "shufersal", -500.0, "Food", "Groceries")
        TransactionsService(db_session).split_transaction(
            uid, "bank_transactions",
            [
                {"amount": -200.0, "category": "Household", "tag": "Cleaning"},
                {"amount": -300.0, "category": "Food", "tag": "Groceries"},
            ],
        )

        [month] = AnalysisService(db_session).get_expenses_by_category_over_time()

        assert month["categories"] == {"Household": 200.0, "Food": 300.0}
        assert month["split_from"] == {"Household": {"Food": 200.0}}

    def test_part_keeping_its_category_is_not_an_origin(self, db_session):
        """Splitting into two tags of one category moves nothing between bars."""
        uid = _bank(db_session, "market", -400.0, "Food", "Groceries")
        TransactionsService(db_session).split_transaction(
            uid, "bank_transactions",
            [
                {"amount": -100.0, "category": "Food", "tag": "Snacks"},
                {"amount": -300.0, "category": "Food", "tag": "Groceries"},
            ],
        )

        [month] = AnalysisService(db_session).get_expenses_by_category_over_time()

        assert month["split_from"] == {}
