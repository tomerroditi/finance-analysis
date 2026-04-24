"""
Tests for TaggingRulesService.
"""

import pytest
from sqlalchemy import select

from backend.errors import BadRequestException
from backend.models.transaction import BankTransaction, CreditCardTransaction
from backend.services.tagging_rules_service import TaggingRulesService


class TestTaggingRulesService:
    """Tests for TaggingRulesService functionality."""

    @pytest.fixture
    def service(self, db_session):
        return TaggingRulesService(db_session)

    @pytest.fixture
    def setup_transactions(self, db_session):
        """Setup sample transactions for conflict tests."""
        db_session.add(CreditCardTransaction(
            id="cc-100",
            date="2023-01-01",
            amount=-50.0,
            description="GitHub Subscription",
            account_name="MyCard",
            provider="Visa",
            source="credit_card_transactions",
        ))
        db_session.add(BankTransaction(
            id="bank-200",
            date="2023-01-02",
            amount=-100.0,
            description="AWS Bill",
            account_name="MyBank",
            provider="Bank",
            source="bank_transactions",
        ))
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

    def test_check_conflicts_no_false_positive_on_shared_source_id(
        self, service, db_session
    ):
        """Test that transactions sharing the same source id but different
        descriptions are not falsely reported as conflicting.

        Regression: ``check_conflicts`` previously used the non-unique ``id``
        column (source institution id) instead of ``unique_id`` (primary key).
        Multiple distinct transactions can share the same ``id``, which caused
        the overlap query to return false positives.
        """
        # Two distinct bank transactions that share the same source id
        db_session.add(BankTransaction(
            id="710",
            date="2024-01-01",
            amount=-21.90,
            description="Mastercard",
            account_name="Acc",
            provider="Bank",
            source="bank_transactions",
        ))
        db_session.add(BankTransaction(
            id="710",
            date="2024-01-02",
            amount=-6000.0,
            description="ATM Withdrawal",
            account_name="Acc",
            provider="Bank",
            source="bank_transactions",
        ))
        db_session.commit()

        # Rule A: matches the ATM transaction
        service.add_rule(
            "ATM Rule",
            {
                "type": "CONDITION",
                "field": "description",
                "operator": "contains",
                "value": "ATM",
            },
            "Other",
            "ATM",
        )

        # Rule B: matches the Mastercard transaction (different row, same source id)
        # Should NOT conflict — the rules match entirely different transactions.
        service.check_conflicts(
            {
                "type": "AND",
                "subconditions": [
                    {
                        "type": "CONDITION",
                        "field": "description",
                        "operator": "contains",
                        "value": "Mastercard",
                    },
                    {
                        "type": "CONDITION",
                        "field": "amount",
                        "operator": "equals",
                        "value": -21.90,
                    },
                ],
            },
            "Subscriptions",
            "Streaming",
        )

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

    def test_recursive_conditions_filter(self, service):
        """Test SQLAlchemy filter generation for recursive conditions."""
        from backend.models.transaction import CreditCardTransaction

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
        filter_expr = service._build_recursive_filter(conditions, CreditCardTransaction)
        compiled = str(filter_expr.compile(compile_kwargs={"literal_binds": True}))

        assert "LIKE" in compiled
        assert "OR" in compiled
        assert "AND" in compiled


class TestBuildSingleFilter:
    """Tests for _build_single_filter generating correct SQLAlchemy expressions per operator."""

    @pytest.fixture
    def service(self, db_session):
        """Create TaggingRulesService instance."""
        return TaggingRulesService(db_session)

    def _compile(self, filter_expr):
        """Compile a SQLAlchemy filter to a readable SQL string."""
        return str(filter_expr.compile(compile_kwargs={"literal_binds": True}))

    def test_contains_operator(self, service):
        """Verify 'contains' produces a LIKE '%value%' filter."""
        condition = {"field": "description", "operator": "contains", "value": "coffee"}
        result = service._build_single_filter(condition, CreditCardTransaction)
        compiled = self._compile(result)

        assert "LIKE" in compiled
        assert "%coffee%" in compiled

    def test_equals_operator(self, service):
        """Verify 'equals' produces an exact match filter."""
        condition = {"field": "provider", "operator": "equals", "value": "Visa"}
        result = service._build_single_filter(condition, CreditCardTransaction)
        compiled = self._compile(result)

        assert "= " in compiled
        assert "Visa" in compiled

    def test_starts_with_operator(self, service):
        """Verify 'starts_with' produces a LIKE 'value%' filter."""
        condition = {"field": "description", "operator": "starts_with", "value": "Super"}
        result = service._build_single_filter(condition, CreditCardTransaction)
        compiled = self._compile(result)

        assert "LIKE" in compiled
        assert "Super%" in compiled
        assert "%Super" not in compiled

    def test_ends_with_operator(self, service):
        """Verify 'ends_with' produces a LIKE '%value' filter."""
        condition = {"field": "description", "operator": "ends_with", "value": "market"}
        result = service._build_single_filter(condition, CreditCardTransaction)
        compiled = self._compile(result)

        assert "LIKE" in compiled
        assert "%market" in compiled

    def test_gt_operator(self, service):
        """Verify 'gt' produces a > comparison."""
        condition = {"field": "amount", "operator": "gt", "value": 100}
        result = service._build_single_filter(condition, CreditCardTransaction)
        compiled = self._compile(result)

        assert "> " in compiled

    def test_lt_operator(self, service):
        """Verify 'lt' produces a < comparison."""
        condition = {"field": "amount", "operator": "lt", "value": -50}
        result = service._build_single_filter(condition, CreditCardTransaction)
        compiled = self._compile(result)

        assert "< " in compiled

    def test_gte_operator(self, service):
        """Verify 'gte' produces a >= comparison."""
        condition = {"field": "amount", "operator": "gte", "value": 0}
        result = service._build_single_filter(condition, CreditCardTransaction)
        compiled = self._compile(result)

        assert ">=" in compiled

    def test_lte_operator(self, service):
        """Verify 'lte' produces a <= comparison."""
        condition = {"field": "amount", "operator": "lte", "value": 1000}
        result = service._build_single_filter(condition, CreditCardTransaction)
        compiled = self._compile(result)

        assert "<=" in compiled

    def test_between_operator(self, service):
        """Verify 'between' produces a BETWEEN clause."""
        condition = {"field": "amount", "operator": "between", "value": [-100, -10]}
        result = service._build_single_filter(condition, CreditCardTransaction)
        compiled = self._compile(result)

        assert "BETWEEN" in compiled

    def test_service_field_returns_true(self, service):
        """Verify 'service' field is ignored and returns True (handled by table selection)."""
        condition = {"field": "service", "operator": "equals", "value": "credit_card"}
        result = service._build_single_filter(condition, CreditCardTransaction)

        assert result is True

    def test_unknown_field_returns_true(self, service):
        """Verify unknown field returns True (no filtering)."""
        condition = {"field": "nonexistent", "operator": "equals", "value": "x"}
        result = service._build_single_filter(condition, CreditCardTransaction)

        assert result is True


class TestBuildRecursiveFilter:
    """Tests for _build_recursive_filter handling nested condition trees."""

    @pytest.fixture
    def service(self, db_session):
        """Create TaggingRulesService instance."""
        return TaggingRulesService(db_session)

    def _compile(self, filter_expr):
        """Compile a SQLAlchemy filter to a readable SQL string."""
        return str(filter_expr.compile(compile_kwargs={"literal_binds": True}))

    def test_single_condition(self, service):
        """Verify a single CONDITION node produces a simple filter."""
        conditions = {
            "type": "CONDITION",
            "field": "description",
            "operator": "contains",
            "value": "Netflix",
        }
        result = service._build_recursive_filter(conditions, CreditCardTransaction)
        compiled = self._compile(result)

        assert "LIKE" in compiled
        assert "%Netflix%" in compiled

    def test_and_group(self, service):
        """Verify AND group joins subconditions with AND."""
        conditions = {
            "type": "AND",
            "subconditions": [
                {"type": "CONDITION", "field": "description", "operator": "contains", "value": "Uber"},
                {"type": "CONDITION", "field": "amount", "operator": "lt", "value": 0},
            ],
        }
        result = service._build_recursive_filter(conditions, CreditCardTransaction)
        compiled = self._compile(result)

        assert "AND" in compiled
        assert "LIKE" in compiled

    def test_or_group(self, service):
        """Verify OR group joins subconditions with OR."""
        conditions = {
            "type": "OR",
            "subconditions": [
                {"type": "CONDITION", "field": "provider", "operator": "equals", "value": "Visa"},
                {"type": "CONDITION", "field": "provider", "operator": "equals", "value": "Mastercard"},
            ],
        }
        result = service._build_recursive_filter(conditions, CreditCardTransaction)
        compiled = self._compile(result)

        assert "OR" in compiled

    def test_empty_subconditions_returns_true(self, service):
        """Verify empty AND/OR group matches everything."""
        conditions = {"type": "AND", "subconditions": []}
        result = service._build_recursive_filter(conditions, CreditCardTransaction)

        assert result is True

    def test_unknown_type_returns_false(self, service):
        """Verify unknown condition type matches nothing."""
        conditions = {"type": "UNKNOWN"}
        result = service._build_recursive_filter(conditions, CreditCardTransaction)

        assert result is False

    def test_deeply_nested_conditions(self, service):
        """Verify deeply nested AND(OR(CONDITION, CONDITION), CONDITION) works."""
        conditions = {
            "type": "AND",
            "subconditions": [
                {
                    "type": "OR",
                    "subconditions": [
                        {"type": "CONDITION", "field": "description", "operator": "contains", "value": "food"},
                        {"type": "CONDITION", "field": "description", "operator": "contains", "value": "grocery"},
                    ],
                },
                {"type": "CONDITION", "field": "amount", "operator": "lt", "value": -20},
            ],
        }
        result = service._build_recursive_filter(conditions, CreditCardTransaction)
        compiled = self._compile(result)

        assert "AND" in compiled
        assert "OR" in compiled
        assert "%food%" in compiled
        assert "%grocery%" in compiled


class TestGetModelColumn:
    """Tests for _get_model_column mapping field names to ORM columns."""

    @pytest.fixture
    def service(self, db_session):
        """Create TaggingRulesService instance."""
        return TaggingRulesService(db_session)

    def test_description_field(self, service):
        """Verify 'description' maps to model.description."""
        col = service._get_model_column("description", CreditCardTransaction)
        assert col is not None
        assert col.key == "description"

    def test_amount_field(self, service):
        """Verify 'amount' maps to model.amount."""
        col = service._get_model_column("amount", CreditCardTransaction)
        assert col is not None
        assert col.key == "amount"

    def test_provider_field(self, service):
        """Verify 'provider' maps to model.provider."""
        col = service._get_model_column("provider", BankTransaction)
        assert col is not None
        assert col.key == "provider"

    def test_account_name_field(self, service):
        """Verify 'account_name' maps to model.account_name."""
        col = service._get_model_column("account_name", BankTransaction)
        assert col is not None
        assert col.key == "account_name"

    def test_service_field_returns_none(self, service):
        """Verify 'service' returns None (handled by table selection)."""
        col = service._get_model_column("service", CreditCardTransaction)
        assert col is None

    def test_unknown_field_returns_none(self, service):
        """Verify unknown field returns None."""
        col = service._get_model_column("nonexistent", CreditCardTransaction)
        assert col is None


class TestPreviewRule:
    """Tests for preview_rule returning matching transactions from the database."""

    @pytest.fixture
    def service(self, db_session):
        """Create TaggingRulesService instance."""
        return TaggingRulesService(db_session)

    @pytest.fixture
    def seed_preview_data(self, db_session):
        """Seed transactions for preview testing."""
        db_session.add_all([
            CreditCardTransaction(
                id="1", date="2024-01-15", amount=-45.0,
                description="Supermarket Purchase", account_name="Card1",
                provider="Visa", source="credit_card_transactions",
            ),
            CreditCardTransaction(
                id="2", date="2024-01-16", amount=-12.0,
                description="Netflix Subscription", account_name="Card1",
                provider="Visa", source="credit_card_transactions",
            ),
            BankTransaction(
                id="3", date="2024-01-17", amount=-200.0,
                description="Supermarket Bulk", account_name="Bank1",
                provider="Hapoalim", source="bank_transactions",
            ),
        ])
        db_session.commit()

    def test_preview_matches_correct_transactions(self, service, seed_preview_data):
        """Verify preview returns only transactions matching the condition."""
        conditions = {
            "type": "CONDITION",
            "field": "description",
            "operator": "contains",
            "value": "Supermarket",
        }
        results = service.preview_rule(conditions)

        assert len(results) == 2
        descriptions = {r["description"] for r in results}
        assert "Supermarket Purchase" in descriptions
        assert "Supermarket Bulk" in descriptions

    def test_preview_no_matches(self, service, seed_preview_data):
        """Verify preview returns empty list when nothing matches."""
        conditions = {
            "type": "CONDITION",
            "field": "description",
            "operator": "contains",
            "value": "NonexistentThing",
        }
        results = service.preview_rule(conditions)

        assert results == []

    def test_preview_respects_limit(self, service, seed_preview_data):
        """Verify preview respects the limit parameter."""
        conditions = {
            "type": "CONDITION",
            "field": "amount",
            "operator": "lt",
            "value": 0,
        }
        results = service.preview_rule(conditions, limit=1)

        assert len(results) == 1

    def test_preview_includes_source_column(self, service, seed_preview_data):
        """Verify preview results include the source table name."""
        conditions = {
            "type": "CONDITION",
            "field": "description",
            "operator": "contains",
            "value": "Netflix",
        }
        results = service.preview_rule(conditions)

        assert len(results) == 1
        assert results[0]["source"] == "credit_card_transactions"


class TestApplySingleRule:
    """Tests for _apply_single_rule_returning_ids updating transactions in the database."""

    @pytest.fixture
    def service(self, db_session):
        """Create TaggingRulesService instance."""
        return TaggingRulesService(db_session)

    @pytest.fixture
    def seed_untagged(self, db_session):
        """Seed untagged transactions for apply rule testing."""
        db_session.add_all([
            CreditCardTransaction(
                id="10", date="2024-02-01", amount=-30.0,
                description="Uber Ride", account_name="Card1",
                provider="Visa", source="credit_card_transactions",
                category=None, tag=None,
            ),
            CreditCardTransaction(
                id="11", date="2024-02-02", amount=-15.0,
                description="Uber Eats", account_name="Card1",
                provider="Visa", source="credit_card_transactions",
                category=None, tag=None,
            ),
            CreditCardTransaction(
                id="12", date="2024-02-03", amount=-50.0,
                description="Amazon Order", account_name="Card1",
                provider="Visa", source="credit_card_transactions",
                category="Shopping", tag="Online",
            ),
        ])
        db_session.commit()

    def test_apply_rule_tags_untagged_transactions(self, service, seed_untagged, db_session):
        """Verify rule tags only untagged transactions by default."""
        rule = {
            "conditions": {
                "type": "CONDITION",
                "field": "description",
                "operator": "contains",
                "value": "Uber",
            },
            "category": "Transport",
            "tag": "Rideshare",
        }
        modified = service._apply_single_rule_returning_ids(rule, overwrite=False)

        assert len(modified) == 2

        # Verify DB was actually updated
        rows = db_session.execute(
            select(CreditCardTransaction).where(CreditCardTransaction.category == "Transport")
        ).scalars().all()
        assert len(rows) == 2
        assert all(r.tag == "Rideshare" for r in rows)

    def test_apply_rule_skips_already_tagged(self, service, seed_untagged, db_session):
        """Verify rule does not overwrite already-tagged transactions when overwrite=False."""
        rule = {
            "conditions": {
                "type": "CONDITION",
                "field": "amount",
                "operator": "lt",
                "value": 0,
            },
            "category": "General",
            "tag": "Expense",
        }
        modified = service._apply_single_rule_returning_ids(rule, overwrite=False)

        # Should tag Uber Ride and Uber Eats but skip Amazon (already tagged)
        assert len(modified) == 2

        # Amazon should keep original tagging
        amazon = db_session.execute(
            select(CreditCardTransaction).where(CreditCardTransaction.id == "12")
        ).scalar_one()
        assert amazon.category == "Shopping"
        assert amazon.tag == "Online"

    def test_apply_rule_with_overwrite(self, service, seed_untagged, db_session):
        """Verify rule overwrites existing tags when overwrite=True."""
        rule = {
            "conditions": {
                "type": "CONDITION",
                "field": "amount",
                "operator": "lt",
                "value": 0,
            },
            "category": "AllExpenses",
            "tag": "Catch-All",
        }
        modified = service._apply_single_rule_returning_ids(rule, overwrite=True)

        # Should tag all 3 transactions
        assert len(modified) == 3

        rows = db_session.execute(
            select(CreditCardTransaction).where(CreditCardTransaction.category == "AllExpenses")
        ).scalars().all()
        assert len(rows) == 3

    def test_apply_rule_no_matches(self, service, seed_untagged):
        """Verify rule returns empty set when no transactions match."""
        rule = {
            "conditions": {
                "type": "CONDITION",
                "field": "description",
                "operator": "contains",
                "value": "Nonexistent",
            },
            "category": "X",
            "tag": "Y",
        }
        modified = service._apply_single_rule_returning_ids(rule)

        assert len(modified) == 0


class TestNormalizeConditions:
    """Tests for _normalize_conditions handling legacy and edge-case formats."""

    @pytest.fixture
    def service(self, db_session):
        """Create TaggingRulesService instance."""
        return TaggingRulesService(db_session)

    def test_invalid_json_string_fallback(self, service):
        """Verify a plain non-JSON string is treated as a description contains condition."""
        result = service._normalize_conditions("not valid json {{{")

        assert result["type"] == "CONDITION"
        assert result["field"] == "description"
        assert result["operator"] == "contains"
        assert result["value"] == "not valid json {{{"

    def test_valid_json_string_parsed(self, service):
        """Verify a valid JSON string is parsed and normalized."""
        import json
        conditions = {"type": "CONDITION", "field": "amount", "operator": "gt", "value": 100}
        result = service._normalize_conditions(json.dumps(conditions))

        assert result["type"] == "CONDITION"
        assert result["field"] == "amount"
        assert result["operator"] == "gt"

    def test_list_to_and_conversion(self, service):
        """Verify a legacy list of conditions is wrapped in an AND group."""
        conditions_list = [
            {"field": "description", "operator": "contains", "value": "coffee"},
            {"field": "amount", "operator": "lt", "value": -5},
        ]
        result = service._normalize_conditions(conditions_list)

        assert result["type"] == "AND"
        assert len(result["subconditions"]) == 2
        assert result["subconditions"][0]["type"] == "CONDITION"
        assert result["subconditions"][0]["field"] == "description"
        assert result["subconditions"][1]["type"] == "CONDITION"

    def test_single_condition_dict_without_type(self, service):
        """Verify a dict without 'type' key is normalized to a CONDITION node."""
        conditions = {"field": "provider", "operator": "equals", "value": "Visa"}
        result = service._normalize_conditions(conditions)

        assert result["type"] == "CONDITION"
        assert result["field"] == "provider"
        assert result["operator"] == "equals"
        assert result["value"] == "Visa"

    def test_single_condition_dict_missing_fields_uses_defaults(self, service):
        """Verify a dict without 'type' uses defaults for missing field/operator/value."""
        result = service._normalize_conditions({})

        assert result["type"] == "CONDITION"
        assert result["field"] == "description"
        assert result["operator"] == "contains"
        assert result["value"] == ""

    def test_non_dict_non_list_non_string_fallback(self, service):
        """Verify an unexpected type (e.g. int) returns the last-resort fallback."""
        result = service._normalize_conditions(12345)

        assert result["type"] == "CONDITION"
        assert result["field"] == "description"
        assert result["operator"] == "contains"
        assert result["value"] == ""


class TestUpdateRuleNotFound:
    """Tests for update_rule when the rule does not exist."""

    @pytest.fixture
    def service(self, db_session):
        """Create TaggingRulesService instance."""
        return TaggingRulesService(db_session)

    def test_update_rule_not_found_raises(self, service):
        """Verify updating a nonexistent rule raises EntityNotFoundException."""
        from backend.errors import EntityNotFoundException

        with pytest.raises(EntityNotFoundException, match="Rule 99999 not found"):
            service.update_rule(99999, name="New Name")


class TestApplyRuleByIdNotFound:
    """Tests for apply_rule_by_id when the rule does not exist."""

    @pytest.fixture
    def service(self, db_session):
        """Create TaggingRulesService instance."""
        return TaggingRulesService(db_session)

    def test_apply_rule_by_id_not_found_raises(self, service):
        """Verify applying a nonexistent rule raises EntityNotFoundException."""
        from backend.errors import EntityNotFoundException

        with pytest.raises(EntityNotFoundException, match="Rule 99999 not found"):
            service.apply_rule_by_id(99999)


class TestValidateRuleIntegrityEdgeCases:
    """Tests for validate_rule_integrity covering edge cases in condition validation."""

    @pytest.fixture
    def service(self, db_session):
        """Create TaggingRulesService instance."""
        return TaggingRulesService(db_session)

    def test_empty_subconditions_raises(self, service):
        """Verify AND group with empty subconditions raises BadRequestException."""
        conditions = {"type": "AND", "subconditions": []}

        with pytest.raises(BadRequestException, match="Group must have subconditions"):
            service.validate_rule_integrity(conditions)

    def test_or_group_empty_subconditions_raises(self, service):
        """Verify OR group with empty subconditions raises BadRequestException."""
        conditions = {"type": "OR", "subconditions": []}

        with pytest.raises(BadRequestException, match="Group must have subconditions"):
            service.validate_rule_integrity(conditions)

    def test_condition_missing_field_raises(self, service):
        """Verify a CONDITION without field raises BadRequestException."""
        conditions = {"type": "CONDITION", "operator": "contains", "value": "test"}

        with pytest.raises(BadRequestException, match="missing field or operator"):
            service.validate_rule_integrity(conditions)

    def test_condition_missing_operator_raises(self, service):
        """Verify a CONDITION without operator raises BadRequestException."""
        conditions = {"type": "CONDITION", "field": "description", "value": "test"}

        with pytest.raises(BadRequestException, match="missing field or operator"):
            service.validate_rule_integrity(conditions)

    def test_invalid_numeric_operator_on_amount_raises(self, service):
        """Verify a text operator on a numeric field raises BadRequestException."""
        conditions = {
            "type": "CONDITION",
            "field": "amount",
            "operator": "contains",
            "value": "100",
        }

        with pytest.raises(BadRequestException, match="not valid for numeric field"):
            service.validate_rule_integrity(conditions)

    def test_between_operator_requires_list_of_two(self, service):
        """Verify 'between' operator with non-list value raises BadRequestException."""
        conditions = {
            "type": "CONDITION",
            "field": "amount",
            "operator": "between",
            "value": 100,
        }

        with pytest.raises(BadRequestException, match="list of 2 numbers"):
            service.validate_rule_integrity(conditions)

    def test_between_operator_with_non_numeric_values_raises(self, service):
        """Verify 'between' operator with non-numeric list values raises BadRequestException."""
        conditions = {
            "type": "CONDITION",
            "field": "amount",
            "operator": "between",
            "value": ["abc", "def"],
        }

        with pytest.raises(BadRequestException, match="must be numbers"):
            service.validate_rule_integrity(conditions)

    def test_between_operator_valid(self, service):
        """Verify 'between' operator with valid numeric list passes validation."""
        conditions = {
            "type": "CONDITION",
            "field": "amount",
            "operator": "between",
            "value": [-100, -10],
        }

        service.validate_rule_integrity(conditions)

    def test_non_numeric_value_for_amount_raises(self, service):
        """Verify non-numeric value for amount field raises BadRequestException."""
        conditions = {
            "type": "CONDITION",
            "field": "amount",
            "operator": "gt",
            "value": "not_a_number",
        }

        with pytest.raises(BadRequestException, match="must be a number"):
            service.validate_rule_integrity(conditions)


class TestCheckConflictsEdgeCases:
    """Tests for check_conflicts covering JSON parsing and empty-match short-circuit."""

    @pytest.fixture
    def service(self, db_session):
        """Create TaggingRulesService instance."""
        return TaggingRulesService(db_session)

    @pytest.fixture
    def seed_transactions(self, db_session):
        """Seed transactions for conflict testing."""
        db_session.add(CreditCardTransaction(
            id="cc-1",
            date="2024-01-01",
            amount=-50.0,
            description="Test Store",
            account_name="Card1",
            provider="Visa",
            source="credit_card_transactions",
        ))
        db_session.commit()

    def test_no_matching_transactions_short_circuits(self, service, seed_transactions):
        """Verify check_conflicts returns early when no transactions match the new rule."""
        conditions = {
            "type": "CONDITION",
            "field": "description",
            "operator": "contains",
            "value": "NonexistentStore12345",
        }

        # Add an existing rule first
        service.add_rule(
            "Existing Rule",
            {"type": "CONDITION", "field": "description", "operator": "contains", "value": "Test Store"},
            "Shopping",
            "Groceries",
        )

        # This should return early without raising, even though an existing rule exists
        service.check_conflicts(conditions, "Different", "Tag")

    def test_stored_conditions_json_string_parsed(self, service, db_session, seed_transactions):
        """Verify check_conflicts can parse stored conditions that are JSON strings."""
        import json
        from backend.models.tagging_rules import TaggingRule

        # Directly insert a rule with conditions stored as a JSON string
        rule = TaggingRule(
            name="JSON String Rule",
            conditions=json.dumps({
                "type": "CONDITION",
                "field": "description",
                "operator": "contains",
                "value": "Test",
            }),
            category="Shopping",
            tag="General",
        )
        db_session.add(rule)
        db_session.commit()

        # Try adding a conflicting rule (matches same transaction, different category)
        with pytest.raises(BadRequestException, match="Conflict detected"):
            service.check_conflicts(
                {"type": "CONDITION", "field": "description", "operator": "contains", "value": "Test Store"},
                "Electronics",
                "Gadgets",
            )

    def test_stored_conditions_invalid_json_string_skipped(self, service, db_session, seed_transactions):
        """Verify check_conflicts skips rules with unparseable stored conditions."""
        from backend.models.tagging_rules import TaggingRule

        # Insert a rule with invalid JSON string conditions
        rule = TaggingRule(
            name="Broken Rule",
            conditions="this is not valid json {{{",
            category="Shopping",
            tag="General",
        )
        db_session.add(rule)
        db_session.commit()

        # Should not raise -- the broken rule is skipped
        service.check_conflicts(
            {"type": "CONDITION", "field": "description", "operator": "contains", "value": "Test Store"},
            "Electronics",
            "Gadgets",
        )


class TestBuildSingleFilterUnrecognizedOperator:
    """Tests for _build_single_filter with unrecognized operators."""

    @pytest.fixture
    def service(self, db_session):
        """Create TaggingRulesService instance."""
        return TaggingRulesService(db_session)

    def test_unrecognized_operator_returns_true(self, service):
        """Verify an unrecognized operator returns True (matches everything)."""
        condition = {"field": "description", "operator": "regex_match", "value": ".*"}
        result = service._build_single_filter(condition, CreditCardTransaction)

        assert result is True


class TestGetTablesNamesForConditions:
    """Tests for _get_tables_names_for_conditions with service filtering."""

    @pytest.fixture
    def service(self, db_session):
        """Create TaggingRulesService instance."""
        return TaggingRulesService(db_session)

    def test_no_service_condition_returns_all_tables(self, service):
        """Verify conditions without service field return both tables."""
        conditions = {
            "type": "CONDITION",
            "field": "description",
            "operator": "contains",
            "value": "test",
        }
        tables = service._get_tables_names_for_conditions(conditions)

        assert "credit_card_transactions" in tables
        assert "bank_transactions" in tables

    def test_credit_card_service_filter(self, service):
        """Verify service=credit_card limits to credit card table only."""
        conditions = {
            "type": "AND",
            "subconditions": [
                {"type": "CONDITION", "field": "service", "operator": "equals", "value": "credit_card"},
                {"type": "CONDITION", "field": "description", "operator": "contains", "value": "test"},
            ],
        }
        tables = service._get_tables_names_for_conditions(conditions)

        assert tables == ["credit_card_transactions"]

    def test_bank_service_filter(self, service):
        """Verify service=bank limits to bank table only."""
        conditions = {
            "type": "AND",
            "subconditions": [
                {"type": "CONDITION", "field": "service", "operator": "equals", "value": "bank"},
                {"type": "CONDITION", "field": "description", "operator": "contains", "value": "test"},
            ],
        }
        tables = service._get_tables_names_for_conditions(conditions)

        assert tables == ["bank_transactions"]

    def test_service_value_normalized_with_spaces(self, service):
        """Verify service value with spaces is normalized (e.g. 'Credit Card' -> 'credit_card')."""
        conditions = {
            "type": "CONDITION",
            "field": "service",
            "operator": "equals",
            "value": "Credit Card",
        }
        tables = service._get_tables_names_for_conditions(conditions)

        assert tables == ["credit_card_transactions"]


class TestCollectServices:
    """Tests for _collect_services recursively finding service fields."""

    @pytest.fixture
    def service(self, db_session):
        """Create TaggingRulesService instance."""
        return TaggingRulesService(db_session)

    def test_collects_service_from_nested_or(self, service):
        """Verify _collect_services finds service fields in nested OR groups."""
        conditions = {
            "type": "OR",
            "subconditions": [
                {"type": "CONDITION", "field": "service", "operator": "equals", "value": "bank"},
                {"type": "CONDITION", "field": "service", "operator": "equals", "value": "credit_card"},
            ],
        }
        services = set()
        service._collect_services(conditions, services)

        assert services == {"bank", "credit_card"}

    def test_ignores_non_equals_operator_on_service(self, service):
        """Verify _collect_services only collects service fields with equals operator."""
        conditions = {
            "type": "CONDITION",
            "field": "service",
            "operator": "contains",
            "value": "bank",
        }
        services = set()
        service._collect_services(conditions, services)

        assert services == set()

    def test_collects_from_deeply_nested_tree(self, service):
        """Verify _collect_services traverses deeply nested AND/OR trees."""
        conditions = {
            "type": "AND",
            "subconditions": [
                {
                    "type": "OR",
                    "subconditions": [
                        {"type": "CONDITION", "field": "service", "operator": "equals", "value": "bank"},
                        {"type": "CONDITION", "field": "description", "operator": "contains", "value": "test"},
                    ],
                },
                {"type": "CONDITION", "field": "amount", "operator": "lt", "value": 0},
            ],
        }
        services = set()
        service._collect_services(conditions, services)

        assert services == {"bank"}


class TestAutoTagCreditCardsBills:
    """Tests for auto_tag_credit_cards_bills matching bank debits to CC totals."""

    @pytest.fixture
    def service(self, db_session):
        """Create TaggingRulesService instance."""
        return TaggingRulesService(db_session)

    @pytest.fixture
    def seed_cc_bill_data(self, db_session):
        """Seed bank and credit card transactions for CC bill matching.

        CC transactions are in December 2023 (after +1 month +1 day shift they
        become January 2024), and the bank CC bill payment is in January 2024.
        """
        db_session.add_all([
            CreditCardTransaction(
                id="cc-1",
                date="2023-12-01",
                amount=-100.0,
                description="Store A",
                account_name="Gold",
                account_number="1234",
                provider="Visa",
                source="credit_card_transactions",
            ),
            CreditCardTransaction(
                id="cc-2",
                date="2023-12-15",
                amount=-50.0,
                description="Store B",
                account_name="Gold",
                account_number="1234",
                provider="Visa",
                source="credit_card_transactions",
            ),
        ])

        db_session.add(BankTransaction(
            id="bank-1",
            date="2024-01-10",
            amount=-150.0,
            description="Credit Card Bill",
            account_name="MyBank",
            provider="Hapoalim",
            source="bank_transactions",
            category=None,
            tag=None,
        ))

        db_session.commit()

    def test_auto_tag_matches_cc_bill(self, service, seed_cc_bill_data, db_session, monkeypatch):
        """Verify bank transaction matching CC total is tagged as Credit Cards."""
        monkeypatch.setattr(
            service.categories_tags_service,
            "categories_and_tags",
            {"Credit Cards": ["Visa - Gold - 1234"]},
        )

        count = service.auto_tag_credit_cards_bills()

        assert count == 1

        tagged = db_session.execute(
            select(BankTransaction).where(BankTransaction.category == "Credit Cards")
        ).scalar_one()
        assert tagged.tag == "Visa - Gold - 1234"

    def test_auto_tag_no_untagged_bank_transactions(self, service, db_session, monkeypatch):
        """Verify returns 0 when all bank transactions are already tagged."""
        db_session.add(BankTransaction(
            id="bank-tagged",
            date="2024-01-10",
            amount=-150.0,
            description="Credit Card Bill",
            account_name="MyBank",
            provider="Hapoalim",
            source="bank_transactions",
            category="Already Tagged",
            tag="Existing",
        ))
        db_session.commit()

        monkeypatch.setattr(
            service.categories_tags_service,
            "categories_and_tags",
            {"Credit Cards": ["Visa - Gold - 1234"]},
        )

        count = service.auto_tag_credit_cards_bills()

        assert count == 0

    def test_auto_tag_no_cc_transactions(self, service, db_session, monkeypatch):
        """Verify returns 0 when there are no credit card transactions at all."""
        db_session.add(BankTransaction(
            id="bank-1",
            date="2024-01-10",
            amount=-150.0,
            description="Credit Card Bill",
            account_name="MyBank",
            provider="Hapoalim",
            source="bank_transactions",
            category=None,
            tag=None,
        ))
        db_session.commit()

        monkeypatch.setattr(
            service.categories_tags_service,
            "categories_and_tags",
            {"Credit Cards": ["Visa - Gold - 1234"]},
        )

        count = service.auto_tag_credit_cards_bills()

        assert count == 0

    def test_auto_tag_no_match_when_amounts_differ(self, service, db_session, monkeypatch):
        """Verify no tagging occurs when bank amount does not match CC total."""
        db_session.add(CreditCardTransaction(
            id="cc-1",
            date="2023-12-01",
            amount=-100.0,
            description="Store A",
            account_name="Gold",
            account_number="1234",
            provider="Visa",
            source="credit_card_transactions",
        ))
        db_session.add(BankTransaction(
            id="bank-1",
            date="2024-01-10",
            amount=-999.0,
            description="Credit Card Bill",
            account_name="MyBank",
            provider="Hapoalim",
            source="bank_transactions",
            category=None,
            tag=None,
        ))
        db_session.commit()

        monkeypatch.setattr(
            service.categories_tags_service,
            "categories_and_tags",
            {"Credit Cards": ["Visa - Gold - 1234"]},
        )

        count = service.auto_tag_credit_cards_bills()

        assert count == 0

    def test_auto_tag_skips_ambiguous_multiple_matches(self, service, db_session, monkeypatch):
        """Verify no tagging when multiple bank transactions match the same CC total."""
        db_session.add(CreditCardTransaction(
            id="cc-1",
            date="2023-12-01",
            amount=-100.0,
            description="Store A",
            account_name="Gold",
            account_number="1234",
            provider="Visa",
            source="credit_card_transactions",
        ))
        db_session.add_all([
            BankTransaction(
                id="bank-1",
                date="2024-01-10",
                amount=-100.0,
                description="CC Bill 1",
                account_name="MyBank",
                provider="Hapoalim",
                source="bank_transactions",
                category=None,
                tag=None,
            ),
            BankTransaction(
                id="bank-2",
                date="2024-01-11",
                amount=-100.0,
                description="CC Bill 2",
                account_name="MyBank",
                provider="Hapoalim",
                source="bank_transactions",
                category=None,
                tag=None,
            ),
        ])
        db_session.commit()

        monkeypatch.setattr(
            service.categories_tags_service,
            "categories_and_tags",
            {"Credit Cards": ["Visa - Gold - 1234"]},
        )

        count = service.auto_tag_credit_cards_bills()

        # Ambiguous match -- should not tag either
        assert count == 0
