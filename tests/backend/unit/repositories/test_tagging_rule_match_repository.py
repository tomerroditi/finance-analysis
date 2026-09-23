"""
Tests for the tagging-rule condition compiler and TaggingRuleMatchRepository.
"""

import pytest

from backend.models.transaction import BankTransaction, CreditCardTransaction
from backend.repositories.tagging_rule_match_repository import (
    TaggingRuleMatchRepository,
    build_filter,
    model_column,
)


def _condition(field: str, operator: str, value) -> dict:
    """Build a single CONDITION node."""
    return {"type": "CONDITION", "field": field, "operator": operator, "value": value}


def _contains(value: str) -> dict:
    """Build a ``description contains value`` condition."""
    return _condition("description", "contains", value)


class TestBuildFilter:
    """Tests for build_filter handling nested condition trees."""

    def _compile(self, filter_expr):
        """Compile a SQLAlchemy filter to a readable SQL string."""
        return str(filter_expr.compile(compile_kwargs={"literal_binds": True}))

    def test_empty_subconditions_matches_nothing(self, db_session):
        """An empty AND/OR group fails closed: it matches no transaction."""
        db_session.add(
            CreditCardTransaction(
                id="e1", date="2024-01-01", description="anything", amount=-10.0,
                account_name="Card1", provider="Visa",
                source="credit_card_transactions",
            )
        )
        db_session.commit()
        conditions = {"type": "AND", "subconditions": []}

        assert build_filter(conditions, CreditCardTransaction) is False
        repo = TaggingRuleMatchRepository(db_session)
        preview = repo.preview(
            "credit_card_transactions", {"type": "OR", "subconditions": []}
        )
        assert preview.empty

    def test_unknown_type_returns_false(self):
        """Verify unknown condition type matches nothing."""
        result = build_filter({"type": "UNKNOWN"}, CreditCardTransaction)

        assert result is False

    def test_deeply_nested_conditions(self):
        """Verify deeply nested AND(OR(CONDITION, CONDITION), CONDITION) works."""
        conditions = {
            "type": "AND",
            "subconditions": [
                {
                    "type": "OR",
                    "subconditions": [_contains("food"), _contains("grocery")],
                },
                _condition("amount", "lt", -20),
            ],
        }
        result = build_filter(conditions, CreditCardTransaction)
        compiled = self._compile(result)

        assert "AND" in compiled
        assert "OR" in compiled
        assert "%food%" in compiled
        assert "%grocery%" in compiled


class TestModelColumn:
    """Tests for model_column mapping field names to ORM columns."""

    @pytest.mark.parametrize(
        "field, model, expected",
        [
            ("description", CreditCardTransaction, "description"),
            ("amount", CreditCardTransaction, "amount"),
            ("provider", BankTransaction, "provider"),
            ("account_name", BankTransaction, "account_name"),
            ("service", CreditCardTransaction, None),
        ],
    )
    def test_field_maps_to_its_model_column(self, field, model, expected):
        """Each real field maps to the same-named column; ``service`` maps to None.

        ``service`` is a pseudo-field handled by table selection, so it has no
        column of its own.
        """
        col = model_column(field, model)

        assert (col.key if col is not None else None) == expected
