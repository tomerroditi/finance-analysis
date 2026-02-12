"""
Tests for TaggingRulesService.
"""

from datetime import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.errors import BadRequestException
from backend.models.tagging_rules import TaggingRule
from backend.constants.tables import Tables
from backend.repositories.tagging_rules_repository import TaggingRulesRepository
from backend.services.tagging_rules_service import TaggingRulesService


class TestTaggingRulesService:
    """Tests for TaggingRulesService functionality."""

    @pytest.fixture
    def service(self, db_session):
        return TaggingRulesService(db_session)

    @pytest.fixture
    def setup_transactions(self, db_session):
        """Setup sample transactions for conflict tests."""
        # Insert a credit card transaction
        db_session.execute(
            text(f"""
            INSERT INTO {Tables.CREDIT_CARD.value} 
            (id, date, amount, description, original_description, account_name, provider, service)
            VALUES 
            (100, '2023-01-01', -50.0, 'GitHub Subscription', 'GitHub', 'MyCard', 'Visa', 'credit_card')
            """)
        )
        # Insert a bank transaction
        db_session.execute(
            text(f"""
            INSERT INTO {Tables.BANK.value}
            (id, date, amount, description, original_description, account_name, provider, service)
            VALUES
            (200, '2023-01-02', -100.0, 'AWS Bill', 'AWS', 'MyBank', 'Bank', 'bank')
            """)
        )
        db_session.commit()

    def test_validate_rule_integrity_valid(self, service):
        """Test valid conditions pass integrity check."""
        conditions = {
            "type": "AND",
            "subconditions": [
                {
                    "type": "CONDITION",
                    "field": "description",
                    "operator": "contains",
                    "value": "GitHub",
                },
                {
                    "type": "CONDITION",
                    "field": "amount",
                    "operator": "lt",
                    "value": -10,
                },
            ],
        }
        service.validate_rule_integrity(conditions)

    def test_validate_rule_integrity_invalid_operator(self, service):
        """Test numeric operator on text field fails."""
        conditions = {
            "type": "CONDITION",
            "field": "description",
            "operator": "gt",
            "value": 100,
        }
        with pytest.raises(BadRequestException):
            service.validate_rule_integrity(conditions)

    def test_validate_rule_integrity_invalid_type(self, service):
        """Test text value on numeric field fails."""
        conditions = {
            "type": "CONDITION",
            "field": "amount",
            "operator": "lt",
            "value": "not_a_number",
        }
        with pytest.raises(BadRequestException):
            service.validate_rule_integrity(conditions)

    def test_check_conflicts_no_conflict(self, service, setup_transactions):
        """Test adding a non-conflicting rule."""
        conditions = {
            "type": "CONDITION",
            "field": "description",
            "operator": "contains",
            "value": "Azure",
        }
        # Transaction is AWS, so Azure should not match, so no conflict check needed really
        # But let's add a rule that MATCHES AWS first

        # Add rule 1: "AWS" -> "Cloud"
        service.add_rule(
            "AWS Rule",
            {
                "type": "CONDITION",
                "field": "description",
                "operator": "contains",
                "value": "AWS",
            },
            "Cloud",
            "Hosting",
        )

        # Add rule 2: "GitHub" -> "Software" (Matches different tx)
        service.check_conflicts(
            {
                "type": "CONDITION",
                "field": "description",
                "operator": "contains",
                "value": "GitHub",
            },
            "Software",
            "Dev",
        )
        # Should pass

    def test_check_conflicts_detected(self, service, setup_transactions):
        """Test adding a conflicting rule raises error."""
        # Add Rule A: "GitHub" -> "Software"
        service.add_rule(
            "Rule A",
            {
                "type": "CONDITION",
                "field": "description",
                "operator": "contains",
                "value": "GitHub",
            },
            "Software",
            "Dev",
        )

        # Try Adding Rule B: "GitHub" -> "Entertainment" (Same tx, different tag)
        with pytest.raises(BadRequestException, match="Conflict detected"):
            service.check_conflicts(
                {
                    "type": "CONDITION",
                    "field": "amount",
                    "operator": "lt",
                    "value": -10,
                },
                "Entertainment",
                "Fun",
            )
            # Note: logic: github tx is -50, so "amount < -10" ALSO matches it.
            # So Rule B matches the SAME transaction as Rule A.
            # Different tags ("Software/Dev" vs "Entertainment/Fun") -> Conflict!

    def test_check_conflicts_same_tag_allowed(self, service, setup_transactions):
        """Test overlapping rule with SAME tag is allowed."""
        # Add Rule A: "GitHub" -> "Software"
        service.add_rule(
            "Rule A",
            {
                "type": "CONDITION",
                "field": "description",
                "operator": "contains",
                "value": "GitHub",
            },
            "Software",
            "Dev",
        )

        # Add Rule B: Matches same tx, but assigns SAME tag
        service.check_conflicts(
            {"type": "CONDITION", "field": "amount", "operator": "lt", "value": -10},
            "Software",
            "Dev",
        )
        # Should pass (redundant but safe)

    def test_update_conflicts_excluding_self(self, service, setup_transactions):
        """Test updating a rule checks conflicts but ignores itself."""
        # Rule A: matches GitHub -> Software
        id_a, _ = service.add_rule(
            "Rule A",
            {
                "type": "CONDITION",
                "field": "description",
                "operator": "contains",
                "value": "GitHub",
            },
            "Software",
            "Dev",
        )

        # Update Rule A: still matches GitHub, diff tag?
        # No, updating Rule A to "Entertainment" is allowed if no OTHER rule claims it.

        # But if we have Rule B matches nothing yet...

        # Let's say Rule B matches "AWS" -> "Cloud"
        id_b, _ = service.add_rule(
            "Rule B",
            {
                "type": "CONDITION",
                "field": "description",
                "operator": "contains",
                "value": "AWS",
            },
            "Technology",
            "Cloud",
        )

        # Update Rule B to match "GitHub" -> "Cloud"
        # This should conflict with Rule A (which claims GitHub as "Software")
        with pytest.raises(BadRequestException, match="Conflict detected"):
            service.update_rule(
                id_b,
                conditions={
                    "type": "CONDITION",
                    "field": "description",
                    "operator": "contains",
                    "value": "GitHub",
                },
            )

    def test_recursive_conditions_sql(self, service):
        """Test SQL generation for recursive conditions."""
        conditions = {
            "type": "OR",
            "subconditions": [
                {
                    "type": "CONDITION",
                    "field": "description",
                    "operator": "contains",
                    "value": "A",
                },
                {
                    "type": "AND",
                    "subconditions": [
                        {
                            "type": "CONDITION",
                            "field": "amount",
                            "operator": "lt",
                            "value": 0,
                        },
                        {
                            "type": "CONDITION",
                            "field": "provider",
                            "operator": "equals",
                            "value": "Visa",
                        },
                    ],
                },
            ],
        }
        where, params = service._build_recursive_where_clause(conditions)

        assert "description LIKE :p_0_description" in where
        assert "amount < :p_1_0_amount" in where
        assert "provider = :p_1_1_provider" in where
        assert " OR " in where
        assert " AND " in where
        assert " OR " in where
        assert " AND " in where
