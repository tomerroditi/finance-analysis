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
