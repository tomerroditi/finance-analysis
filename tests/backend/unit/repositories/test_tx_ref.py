"""Tests for ``TxRef``, the parsed transaction identity."""

import pytest

from backend.errors import ValidationException
from backend.repositories.transactions import TxRef, transaction_table


class TestTransactionTable:
    """``transaction_table`` maps every spelling of a table to one name."""

    @pytest.mark.parametrize(
        "source, table",
        [
            ("bank_transactions", "bank_transactions"),
            ("banks", "bank_transactions"),
            ("credit_cards", "credit_card_transactions"),
            ("cash", "cash_transactions"),
            ("manual_investments", "manual_investment_transactions"),
            ("insurances", "insurance_transactions"),
        ],
    )
    def test_resolves_table_and_service_names(self, source, table):
        """A table name passes through; a service name maps to its table."""
        assert transaction_table(source) == table

    @pytest.mark.parametrize("source", ["nonsense", "", None, 3, "Banks"])
    def test_unknown_source_raises(self, source):
        """Anything that names no table is one ValidationException."""
        with pytest.raises(ValidationException, match="Invalid source"):
            transaction_table(source)


class TestTxRefParse:
    """``TxRef.parse`` validates both halves of a transaction's identity."""

    @pytest.mark.parametrize("unique_id", [7, "7", 7.0])
    def test_parses_integral_ids(self, unique_id):
        """Ints, integer strings and integral floats all become the int."""
        assert TxRef.parse("cash", unique_id) == TxRef("cash_transactions", 7)

    @pytest.mark.parametrize("unique_id", ["abc", "", None, 7.5, True, [7]])
    def test_non_integer_id_raises(self, unique_id):
        """A bad id is the same ValidationException whatever its type."""
        with pytest.raises(ValidationException, match="Invalid transaction id"):
            TxRef.parse("banks", unique_id)

    def test_source_is_checked_before_id(self):
        """With both halves bad, the source is what gets reported."""
        with pytest.raises(ValidationException, match="Invalid source"):
            TxRef.parse("nonsense", "abc")
