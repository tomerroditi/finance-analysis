"""
Tests for TaggingRulesService.
"""

import json

import pytest
from sqlalchemy import select

import backend.services.tagging_service as ts
from backend.errors import BadRequestException, EntityNotFoundException
from backend.models.category import Category
from backend.models.tagging_rules import TaggingRule
from backend.models.transaction import BankTransaction, CreditCardTransaction
from backend.services.tagging_rules_service import TaggingRulesService

# Every category/tag pair a rule in this module assigns. Rules may only target
# pairs the categories table knows about, so the pairs are injected into the
# service's in-memory cache rather than seeded per test.
RULE_CATEGORIES = {
    "Cloud": ["Hosting"],
    "Software": ["Dev"],
    "Technology": ["Cloud"],
    "Entertainment": ["Fun", "Streaming"],
    "Other": ["ATM"],
    "Subscriptions": ["Streaming"],
    "Cash": ["Withdrawals"],
    "Shopping": ["Groceries", "General", "Online"],
    "Electronics": ["Gadgets"],
    "Different": ["Tag"],
    "Transport": ["Rideshare", "Rides"],
    "General": ["Expense"],
    "AllExpenses": ["Catch-All"],
    "Food": ["Groceries", "Restaurants", "Delivery"],
    "Credit Cards": ["Visa - Gold - 1234"],
}


@pytest.fixture(autouse=True)
def _rule_categories(monkeypatch):
    """Serve ``RULE_CATEGORIES`` from the categories cache for every test.

    The cache is partitioned by resolved database path, not by demo-mode
    flag, so the entry has to be keyed with ``cache_key()`` or the service
    falls through to the (empty) repository.
    """
    monkeypatch.setattr(ts, "_categories_cache", {ts.cache_key(): RULE_CATEGORIES})


def _condition(field: str, operator: str, value) -> dict:
    """Build a single CONDITION node."""
    return {"type": "CONDITION", "field": field, "operator": operator, "value": value}


def _contains(value: str) -> dict:
    """Build a ``description contains value`` condition."""
    return _condition("description", "contains", value)


def _cc(db_session, id_: str, description: str, amount: float = -10.0, **kwargs):
    """Insert one credit-card transaction and return it."""
    row = CreditCardTransaction(
        id=id_, date="2024-01-01", description=description, amount=amount,
        account_name=kwargs.pop("account_name", "Card1"),
        provider=kwargs.pop("provider", "Visa"),
        source="credit_card_transactions", **kwargs,
    )
    db_session.add(row)
    db_session.commit()
    return row


def _cc_row(db_session, id_: str) -> CreditCardTransaction:
    """Reload one credit-card transaction by its source ``id``."""
    db_session.expire_all()
    return db_session.execute(
        select(CreditCardTransaction).where(CreditCardTransaction.id == id_)
    ).scalar_one()


class TestTaggingRulesService:
    """Tests for TaggingRulesService validation and conflict detection."""

    @pytest.fixture
    def service(self, db_session):
        """Create TaggingRulesService instance."""
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
                _contains("GitHub"),
                _condition("amount", "lt", -10),
            ],
        }
        service.validate_rule_integrity(conditions)

    def test_validate_rule_integrity_invalid_operator(self, service):
        """Test numeric operator on text field fails."""
        with pytest.raises(BadRequestException):
            service.validate_rule_integrity(_condition("description", "gt", 100))

    def test_check_conflicts_no_conflict(self, service, setup_transactions):
        """Test adding a non-conflicting rule."""
        service.add_rule("AWS Rule", _contains("AWS"), "Cloud", "Hosting")

        # Matches a different transaction than the AWS rule -> no conflict.
        service.check_conflicts(_contains("GitHub"), "Software", "Dev")

    def test_check_conflicts_detected(self, service, setup_transactions):
        """Test adding a conflicting rule raises error."""
        service.add_rule("Rule A", _contains("GitHub"), "Software", "Dev")

        # The GitHub tx is -50, so "amount < -10" ALSO matches it with a
        # different tag -> conflict.
        with pytest.raises(BadRequestException, match="Conflict detected"):
            service.check_conflicts(
                _condition("amount", "lt", -10), "Entertainment", "Fun"
            )

    def test_check_conflicts_same_tag_allowed(self, service, setup_transactions):
        """Test overlapping rule with SAME tag is allowed."""
        service.add_rule("Rule A", _contains("GitHub"), "Software", "Dev")

        # Matches the same tx, but assigns the SAME tag -> redundant but safe.
        service.check_conflicts(_condition("amount", "lt", -10), "Software", "Dev")

        # Only the tag equality made it pass: the identical conditions with a
        # DIFFERENT tag are rejected (guards against a no-op checker).
        with pytest.raises(BadRequestException, match="Conflict detected"):
            service.check_conflicts(
                _condition("amount", "lt", -10), "Entertainment", "Fun"
            )

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

        service.add_rule("ATM Rule", _contains("ATM"), "Other", "ATM")

        # Matches the Mastercard transaction (different row, same source id).
        service.check_conflicts(
            {
                "type": "AND",
                "subconditions": [
                    _contains("Mastercard"),
                    _condition("amount", "equals", -21.90),
                ],
            },
            "Subscriptions",
            "Streaming",
        )

        # Sanity: a rule that DOES match the same ATM transaction with a
        # different tag is still flagged — the pass above wasn't a no-op.
        with pytest.raises(BadRequestException, match="Conflict detected"):
            service.check_conflicts(_contains("ATM"), "Cash", "Withdrawals")

    def test_update_conflicts_excluding_self(self, service, setup_transactions):
        """Test updating a rule checks conflicts but ignores itself."""
        service.add_rule("Rule A", _contains("GitHub"), "Software", "Dev")
        id_b, _ = service.add_rule("Rule B", _contains("AWS"), "Technology", "Cloud")

        # Updating Rule B to claim GitHub conflicts with Rule A.
        with pytest.raises(BadRequestException, match="Conflict detected"):
            service.update_rule(id_b, conditions=_contains("GitHub"))


class TestOperatorSemantics:
    """Operators are pinned at the DB level through ``preview_rule``."""

    @pytest.fixture
    def service(self, db_session):
        """Create a service over a small mixed-case, mixed-sign dataset."""
        rows = [
            ("Coffee Shop", -50.0),
            ("coffee shop", -100.0),
            ("Supermarket", -10.0),
            ("סופר פארם", -20.0),
            ("Gas", 100.0),
        ]
        for i, (description, amount) in enumerate(rows):
            _cc(db_session, f"op-{i}", description, amount)
        return TaggingRulesService(db_session)

    @pytest.mark.parametrize(
        "operator, value, expected",
        [
            ("gt", -50, {"Supermarket", "סופר פארם", "Gas"}),
            ("gte", -50, {"Coffee Shop", "Supermarket", "סופר פארם", "Gas"}),
            ("lt", -50, {"coffee shop"}),
            ("lte", -50, {"Coffee Shop", "coffee shop"}),
            ("between", [-100, -10], {"Coffee Shop", "coffee shop", "Supermarket", "סופר פארם"}),
            ("between", [-10, -100], set()),
            ("equals", "-50", {"Coffee Shop"}),
        ],
        ids=["gt", "gte", "lt", "lte", "between", "between-reversed", "equals-string"],
    )
    def test_numeric_operator_boundaries(self, service, operator, value, expected):
        """Numeric operators are exclusive/inclusive exactly as named.

        A reversed ``between`` range is SQL ``BETWEEN hi AND lo`` and matches
        nothing; an ``equals`` string is coerced by the column's REAL
        affinity, so ``"-50"`` still finds ``-50.0``.
        """
        matched = service.preview_rule(_condition("amount", operator, value))
        assert {m["description"] for m in matched} == expected

    @pytest.mark.parametrize(
        "operator, value, expected",
        [
            ("contains", "coffee", {"Coffee Shop", "coffee shop"}),
            ("starts_with", "coffee", {"Coffee Shop", "coffee shop"}),
            ("ends_with", "SHOP", {"Coffee Shop", "coffee shop"}),
            ("equals", "coffee shop", {"coffee shop"}),
            ("contains", "סופר", {"סופר פארם"}),
        ],
        ids=["contains", "starts_with", "ends_with", "equals", "contains-hebrew"],
    )
    def test_text_operator_case_sensitivity(self, service, operator, value, expected):
        """LIKE-backed operators ignore ASCII case; ``equals`` is exact.

        Hebrew has no case, so a Hebrew ``contains`` is a plain substring
        match.
        """
        matched = service.preview_rule(_condition("description", operator, value))
        assert {m["description"] for m in matched} == expected

    def test_service_field_returns_true(self, service):
        """Verify the 'service' field defers to table selection (matches all)."""
        condition = {"field": "service", "operator": "equals", "value": "bank"}
        assert service._build_single_filter(condition, CreditCardTransaction) is True

    def test_unrecognized_operator_matches_nothing(self, service):
        """An unrecognised operator fails closed instead of matching everything."""
        condition = {"field": "description", "operator": "regex_match", "value": ".*"}
        assert service._build_single_filter(condition, CreditCardTransaction) is False
        assert service.preview_rule(condition) == []


class TestBuildRecursiveFilter:
    """Tests for _build_recursive_filter handling nested condition trees."""

    @pytest.fixture
    def service(self, db_session):
        """Create TaggingRulesService instance."""
        return TaggingRulesService(db_session)

    def _compile(self, filter_expr):
        """Compile a SQLAlchemy filter to a readable SQL string."""
        return str(filter_expr.compile(compile_kwargs={"literal_binds": True}))

    def test_empty_subconditions_matches_nothing(self, service, db_session):
        """An empty AND/OR group fails closed: it matches no transaction."""
        _cc(db_session, "e1", "anything")
        conditions = {"type": "AND", "subconditions": []}

        assert service._build_recursive_filter(conditions, CreditCardTransaction) is False
        assert service.preview_rule({"type": "OR", "subconditions": []}) == []

    def test_unknown_type_returns_false(self, service):
        """Verify unknown condition type matches nothing."""
        result = service._build_recursive_filter({"type": "UNKNOWN"}, CreditCardTransaction)

        assert result is False

    def test_deeply_nested_conditions(self, service):
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
    def test_field_maps_to_its_model_column(self, service, field, model, expected):
        """Each real field maps to the same-named column; ``service`` maps to None.

        ``service`` is a pseudo-field handled by table selection, so it has no
        column of its own.
        """
        col = service._get_model_column(field, model)

        assert (col.key if col is not None else None) == expected


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
        results = service.preview_rule(_contains("Supermarket"))

        assert len(results) == 2
        descriptions = {r["description"] for r in results}
        assert "Supermarket Purchase" in descriptions
        assert "Supermarket Bulk" in descriptions

    def test_preview_no_matches(self, service, seed_preview_data):
        """Verify preview returns empty list when nothing matches."""
        assert service.preview_rule(_contains("NonexistentThing")) == []

    def test_preview_respects_limit(self, service, seed_preview_data):
        """Verify preview respects the limit parameter."""
        results = service.preview_rule(_condition("amount", "lt", 0), limit=1)

        assert len(results) == 1

    def test_preview_no_limit_returns_all_matches(self, service, seed_preview_data):
        """Verify preview returns all matches when limit is None."""
        results = service.preview_rule(_condition("amount", "lt", 0), limit=None)

        assert len(results) == 3

    def test_preview_includes_source_column(self, service, seed_preview_data):
        """Verify preview results include the source table name."""
        results = service.preview_rule(_contains("Netflix"))

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
        rule = {"conditions": _contains("Uber"), "category": "Transport", "tag": "Rideshare"}
        modified = service._apply_single_rule_returning_ids(rule, overwrite=False)

        assert len(modified) == 2

        rows = db_session.execute(
            select(CreditCardTransaction).where(CreditCardTransaction.category == "Transport")
        ).scalars().all()
        assert len(rows) == 2
        assert all(r.tag == "Rideshare" for r in rows)

    def test_apply_rule_skips_already_tagged(self, service, seed_untagged, db_session):
        """Verify rule does not overwrite already-tagged transactions when overwrite=False."""
        rule = {"conditions": _condition("amount", "lt", 0), "category": "General", "tag": "Expense"}
        modified = service._apply_single_rule_returning_ids(rule, overwrite=False)

        # Should tag Uber Ride and Uber Eats but skip Amazon (already tagged)
        assert len(modified) == 2

        amazon = _cc_row(db_session, "12")
        assert amazon.category == "Shopping"
        assert amazon.tag == "Online"

    def test_apply_rule_with_overwrite(self, service, seed_untagged, db_session):
        """Verify rule overwrites existing tags when overwrite=True."""
        rule = {"conditions": _condition("amount", "lt", 0), "category": "AllExpenses", "tag": "Catch-All"}
        modified = service._apply_single_rule_returning_ids(rule, overwrite=True)

        assert len(modified) == 3

        rows = db_session.execute(
            select(CreditCardTransaction).where(CreditCardTransaction.category == "AllExpenses")
        ).scalars().all()
        assert len(rows) == 3

    def test_apply_rule_no_matches(self, service, seed_untagged):
        """Verify rule returns empty set when no transactions match."""
        rule = {"conditions": _contains("Nonexistent"), "category": "X", "tag": "Y"}
        modified = service._apply_single_rule_returning_ids(rule)

        assert len(modified) == 0


class TestApplyRulesPrecedence:
    """``apply_rules`` runs rules in creation order and the first match wins."""

    @pytest.fixture
    def service(self, db_session):
        """Create TaggingRulesService instance."""
        return TaggingRulesService(db_session)

    def _insert_rule(self, db_session, name, conditions, category, tag):
        """Insert a rule straight into the table, bypassing conflict checks."""
        db_session.add(TaggingRule(name=name, conditions=conditions, category=category, tag=tag))
        db_session.commit()

    def test_overwrite_first_rule_wins_not_last(self, service, db_session):
        """With overwrite=True two overlapping rules resolve to the FIRST one.

        Each rule used to re-tag whatever the previous one had just set, so
        the last rule silently won.
        """
        _cc(db_session, "p1", "Uber Eats Delivery")
        self._insert_rule(db_session, "Uber", _contains("Uber"), "Transport", "Rides")
        self._insert_rule(db_session, "Eats", _contains("Eats"), "Food", "Delivery")

        count = service.apply_rules(overwrite=True)

        assert count == 1
        row = _cc_row(db_session, "p1")
        assert (row.category, row.tag) == ("Transport", "Rides")

    def test_a_rule_owns_rows_it_already_agrees_with(self, service, db_session):
        """A no-op match still claims the row, so a later rule cannot steal it.

        The first rule had nothing to write (the row already carried its
        pair), so it did not register the row as claimed and the second
        overlapping rule re-tagged it — making a *second* overwrite pass
        produce a different answer from the first.
        """
        _cc(db_session, "p2", "Uber Eats Delivery", category="Transport", tag="Rides")
        self._insert_rule(db_session, "Uber", _contains("Uber"), "Transport", "Rides")
        self._insert_rule(db_session, "Eats", _contains("Eats"), "Food", "Delivery")

        assert service.apply_rules(overwrite=True) == 0
        row = _cc_row(db_session, "p2")
        assert (row.category, row.tag) == ("Transport", "Rides")

    def test_overwrite_resets_manually_tagged_rows(self, service, db_session):
        """overwrite=True re-tags hand-tagged rows too — pinned on purpose.

        The transaction tables do not record whether a tag was set by a rule
        or by hand, so "overwrite" can only mean "reset every matching
        transaction to what the rules say".
        """
        _cc(db_session, "m1", "Uber Ride", category="Shopping", tag="Online")
        self._insert_rule(db_session, "Uber", _contains("Uber"), "Transport", "Rides")

        assert service.apply_rules(overwrite=True) == 1
        row = _cc_row(db_session, "m1")
        assert (row.category, row.tag) == ("Transport", "Rides")

    def test_non_overwrite_keeps_manual_tags(self, service, db_session):
        """Without overwrite a hand-tagged row is never touched."""
        _cc(db_session, "m2", "Uber Ride", category="Shopping", tag="Online")
        self._insert_rule(db_session, "Uber", _contains("Uber"), "Transport", "Rides")

        assert service.apply_rules(overwrite=False) == 0
        row = _cc_row(db_session, "m2")
        assert (row.category, row.tag) == ("Shopping", "Online")

    def test_later_overlap_is_won_by_the_older_rule(self, service, db_session):
        """Two rules that did not overlap at creation may both match a later
        transaction; the older rule (lower id) wins deterministically."""
        _cc(db_session, "old-1", "Uber Ride")
        _cc(db_session, "old-2", "Wolt Eats")
        service.add_rule("Uber", _contains("Uber"), "Transport", "Rides")
        service.add_rule("Eats", _contains("Eats"), "Food", "Delivery")

        _cc(db_session, "new", "Uber Eats Delivery")
        assert service.apply_rules() == 1

        row = _cc_row(db_session, "new")
        assert (row.category, row.tag) == ("Transport", "Rides")

    def test_broken_rule_is_skipped_by_apply(self, service, db_session, caplog):
        """A rule whose stored conditions are not JSON tags nothing and is logged."""
        _cc(db_session, "b1", "this is not valid json {{{")
        self._insert_rule(db_session, "Broken", "this is not valid json {{{", "Shopping", "General")

        with caplog.at_level("WARNING"):
            assert service.apply_rules() == 0
            broken_id = int(service.get_all_rules().iloc[0]["id"])
            assert service.apply_rule_by_id(broken_id) == 0

        assert "Skipping tagging rule" in caplog.text
        assert _cc_row(db_session, "b1").category is None

    def test_broken_rule_name_never_reaches_the_log(
        self, service, db_session, caplog
    ):
        """The rule name stays out of the log line entirely.

        The name is whatever the user typed, so a newline in it would split
        the warning into what reads as a second, legitimate log record
        (CWE-117), and these logs are what a user pastes into a bug report.
        The id identifies the rule without carrying user text.
        """
        self._insert_rule(
            db_session,
            "Evil\nWARNING forged entry",
            "this is not valid json {{{",
            "Shopping",
            "General",
        )

        with caplog.at_level("WARNING"):
            assert service.apply_rules() == 0

        assert "Skipping tagging rule" in caplog.text
        assert "WARNING forged entry" not in caplog.text
        assert "Evil" not in caplog.text

    def test_broken_rule_without_an_id_still_reads_clearly(
        self, service, caplog
    ):
        """A row carrying no id logs a readable phrase, not a bare ``None``."""
        with caplog.at_level("WARNING"):
            assert service._stored_conditions({"conditions": "not json {{{"}) is None

        assert "of unknown id" in caplog.text


class TestNormalizeConditions:
    """Tests for _normalize_conditions handling legacy and edge-case formats."""

    @pytest.fixture
    def service(self, db_session):
        """Create TaggingRulesService instance."""
        return TaggingRulesService(db_session)

    def test_invalid_json_string_raises(self, service):
        """A non-JSON string is a broken rule, not a description search."""
        with pytest.raises(ValueError, match="not valid JSON"):
            service._normalize_conditions("not valid json {{{")

    def test_valid_json_string_parsed(self, service):
        """Verify a valid JSON string is parsed and normalized."""
        result = service._normalize_conditions(json.dumps(_condition("amount", "gt", 100)))

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
        result = service._normalize_conditions(
            {"field": "provider", "operator": "equals", "value": "Visa"}
        )

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


class TestUpdateRule:
    """Tests for update_rule re-tagging and error handling."""

    @pytest.fixture
    def service(self, db_session):
        """Create TaggingRulesService instance."""
        return TaggingRulesService(db_session)

    def test_update_rule_not_found_raises(self, service):
        """Verify updating a nonexistent rule raises EntityNotFoundException."""
        with pytest.raises(EntityNotFoundException, match="Rule 99999 not found"):
            service.update_rule(99999, name="New Name")

    def test_changing_target_retags_rows_the_rule_tagged(self, service, db_session):
        """Rows carrying the rule's old category/tag move to the new pair."""
        _cc(db_session, "u1", "Uber Ride")
        _cc(db_session, "u2", "Uber Eats")
        rule_id, n_tagged = service.add_rule("Uber", _contains("Uber"), "Transport", "Rides")
        assert n_tagged == 2

        assert service.update_rule(rule_id, category="Transport", tag="Rideshare") == 2

        for id_ in ("u1", "u2"):
            row = _cc_row(db_session, id_)
            assert (row.category, row.tag) == ("Transport", "Rideshare")

    def test_changing_target_leaves_other_tags_alone(self, service, db_session):
        """Only rows with the rule's OLD pair are moved — not hand-tagged rows,
        and not rows with the old pair that no longer match the conditions."""
        _cc(db_session, "u1", "Uber Ride", category="Shopping", tag="Online")
        _cc(db_session, "u2", "Taxi Ride", category="Transport", tag="Rides")
        _cc(db_session, "u3", "Uber Ride")
        rule_id, _ = service.add_rule("Uber", _contains("Uber"), "Transport", "Rides")

        assert service.update_rule(rule_id, tag="Rideshare") == 1

        assert (_cc_row(db_session, "u1").category, _cc_row(db_session, "u1").tag) == ("Shopping", "Online")
        assert (_cc_row(db_session, "u2").category, _cc_row(db_session, "u2").tag) == ("Transport", "Rides")
        assert (_cc_row(db_session, "u3").category, _cc_row(db_session, "u3").tag) == ("Transport", "Rideshare")

    def test_update_without_target_change_only_tags_untagged(self, service, db_session):
        """Editing the name (or conditions) never re-tags rows the rule owns."""
        _cc(db_session, "u1", "Uber Ride")
        rule_id, _ = service.add_rule("Uber", _contains("Uber"), "Transport", "Rides")
        _cc(db_session, "u2", "Uber Eats")

        assert service.update_rule(rule_id, name="Renamed") == 1
        assert _cc_row(db_session, "u2").tag == "Rides"


class TestApplyRuleByIdNotFound:
    """Tests for apply_rule_by_id when the rule does not exist."""

    @pytest.fixture
    def service(self, db_session):
        """Create TaggingRulesService instance."""
        return TaggingRulesService(db_session)

    def test_apply_rule_by_id_not_found_raises(self, service):
        """Verify applying a nonexistent rule raises EntityNotFoundException."""
        with pytest.raises(EntityNotFoundException, match="Rule 99999 not found"):
            service.apply_rule_by_id(99999)


class TestRuleTargetValidation:
    """Rules may only assign category/tag pairs that exist."""

    @pytest.fixture
    def service(self, db_session):
        """Create TaggingRulesService instance."""
        return TaggingRulesService(db_session)

    @pytest.mark.parametrize(
        "category, tag, message",
        [
            ("Nonexistent", "Groceries", "Unknown category"),
            ("Food", "", "must not be blank"),
            ("Food", "   ", "must not be blank"),
            ("Food", None, "must not be blank"),
            ("", "Groceries", "must not be blank"),
            ("Food", "Rides", "does not exist under category"),
        ],
    )
    def test_add_rule_rejects_unknown_target(self, service, db_session, category, tag, message):
        """add_rule refuses an unknown category, a blank tag, or a tag from another category."""
        _cc(db_session, "t1", "Uber Ride")

        with pytest.raises(BadRequestException, match=message):
            service.add_rule("Bad", _contains("Uber"), category, tag)

        assert service.get_all_rules().empty
        assert _cc_row(db_session, "t1").category is None

    def test_update_rule_rejects_unknown_target(self, service, db_session):
        """update_rule validates the effective (category, tag) pair."""
        _cc(db_session, "t1", "Uber Ride")
        rule_id, _ = service.add_rule("Uber", _contains("Uber"), "Transport", "Rides")

        with pytest.raises(BadRequestException, match="does not exist under category"):
            service.update_rule(rule_id, category="Food")

        rule = service.rules_repo.get_rule_by_id(rule_id)
        assert (rule.category, rule.tag) == ("Transport", "Rides")


class TestValidateRuleIntegrityEdgeCases:
    """Tests for validate_rule_integrity covering edge cases in condition validation."""

    @pytest.fixture
    def service(self, db_session):
        """Create TaggingRulesService instance."""
        return TaggingRulesService(db_session)

    @pytest.mark.parametrize("group", ["AND", "OR"])
    def test_empty_subconditions_raises(self, service, group):
        """Verify a group with empty subconditions raises BadRequestException."""
        with pytest.raises(BadRequestException, match="Group must have subconditions"):
            service.validate_rule_integrity({"type": group, "subconditions": []})

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
        with pytest.raises(BadRequestException, match="not valid for numeric field"):
            service.validate_rule_integrity(_condition("amount", "contains", "100"))

    def test_between_operator_requires_list_of_two(self, service):
        """Verify 'between' operator with non-list value raises BadRequestException."""
        with pytest.raises(BadRequestException, match="list of 2 numbers"):
            service.validate_rule_integrity(_condition("amount", "between", 100))

    def test_between_operator_with_non_numeric_values_raises(self, service):
        """Verify 'between' operator with non-numeric list values raises BadRequestException."""
        with pytest.raises(BadRequestException, match="must be numbers"):
            service.validate_rule_integrity(_condition("amount", "between", ["abc", "def"]))

    def test_between_operator_valid(self, service):
        """Verify 'between' operator with valid numeric list passes validation."""
        service.validate_rule_integrity(_condition("amount", "between", [-100, -10]))

    def test_non_numeric_value_for_amount_raises(self, service):
        """Verify non-numeric value for amount field raises BadRequestException."""
        with pytest.raises(BadRequestException, match="must be a number"):
            service.validate_rule_integrity(_condition("amount", "gt", "not_a_number"))

    @pytest.mark.parametrize("value", ["", "   ", None])
    def test_blank_text_pattern_raises(self, service, value):
        """A blank text pattern would match every transaction, so it is rejected."""
        with pytest.raises(BadRequestException, match="must not be blank"):
            service.validate_rule_integrity(_contains(value))

    @pytest.mark.parametrize("value", ["bank", "credit_card", "Credit Card", "BANK"])
    def test_service_condition_accepts_known_services(self, service, value):
        """``service equals <known service>`` is valid in any casing/spacing."""
        service.validate_rule_integrity(_condition("service", "equals", value))

    @pytest.mark.parametrize("value", ["cash", "banks", "", "credit-card"])
    def test_service_condition_rejects_unknown_services(self, service, value):
        """A service outside {bank, credit_card} is rejected."""
        with pytest.raises(BadRequestException, match="Unknown service"):
            service.validate_rule_integrity(_condition("service", "equals", value))

    @pytest.mark.parametrize("operator", ["contains", "starts_with", "ends_with"])
    def test_service_condition_rejects_non_equals_operator(self, service, operator):
        """The service selector only honours ``equals``."""
        with pytest.raises(BadRequestException, match="only supports the 'equals' operator"):
            service.validate_rule_integrity(_condition("service", operator, "bank"))


class TestCheckConflictsEdgeCases:
    """Tests for check_conflicts covering JSON parsing and empty-match short-circuit."""

    @pytest.fixture
    def service(self, db_session):
        """Create TaggingRulesService instance."""
        return TaggingRulesService(db_session)

    @pytest.fixture
    def seed_transactions(self, db_session):
        """Seed transactions for conflict testing."""
        _cc(db_session, "cc-1", "Test Store", -50.0)

    def test_no_matching_transactions_short_circuits(self, service, seed_transactions):
        """Verify check_conflicts returns early when no transactions match the new rule."""
        service.add_rule("Existing Rule", _contains("Test Store"), "Shopping", "Groceries")

        # Returns early without raising, even though an existing rule exists.
        service.check_conflicts(_contains("NonexistentStore12345"), "Different", "Tag")

    def test_stored_conditions_json_string_parsed(self, service, db_session, seed_transactions):
        """Verify check_conflicts can parse stored conditions that are JSON strings."""
        db_session.add(TaggingRule(
            name="JSON String Rule",
            conditions=json.dumps(_contains("Test")),
            category="Shopping",
            tag="General",
        ))
        db_session.commit()

        with pytest.raises(BadRequestException, match="Conflict detected"):
            service.check_conflicts(_contains("Test Store"), "Electronics", "Gadgets")

    def test_broken_stored_conditions_skipped_everywhere(self, service, db_session, seed_transactions):
        """A rule with unparseable conditions is skipped by conflict detection
        AND by apply — it is inert, not silently reinterpreted."""
        db_session.add(TaggingRule(
            name="Broken Rule",
            conditions="this is not valid json {{{",
            category="Shopping",
            tag="General",
        ))
        db_session.commit()

        # Conflict detection: does not raise, does not delete the rule.
        service.check_conflicts(_contains("Test Store"), "Electronics", "Gadgets")
        assert "Broken Rule" in service.get_all_rules()["name"].tolist()

        # Apply: tags nothing (it used to become ``description contains "<garbage>"``).
        _cc(db_session, "cc-garbage", "this is not valid json {{{")
        assert service.apply_rules() == 0
        assert _cc_row(db_session, "cc-garbage").category is None

        # A rule with parseable conditions still triggers detection on the same tx.
        db_session.add(TaggingRule(
            name="Parseable Rule",
            conditions=_contains("Test Store"),
            category="Shopping",
            tag="General",
        ))
        db_session.commit()
        with pytest.raises(BadRequestException, match="Conflict detected"):
            service.check_conflicts(_contains("Test Store"), "Electronics", "Gadgets")


class TestGetTablesNamesForConditions:
    """Tests for _get_tables_names_for_conditions with service filtering."""

    @pytest.fixture
    def service(self, db_session):
        """Create TaggingRulesService instance."""
        return TaggingRulesService(db_session)

    def test_no_service_condition_returns_all_tables(self, service):
        """Verify conditions without service field return both tables."""
        tables = service._get_tables_names_for_conditions(_contains("test"))

        assert "credit_card_transactions" in tables
        assert "bank_transactions" in tables

    def test_credit_card_service_filter(self, service):
        """Verify service=credit_card limits to credit card table only."""
        conditions = {
            "type": "AND",
            "subconditions": [
                _condition("service", "equals", "credit_card"),
                _contains("test"),
            ],
        }
        tables = service._get_tables_names_for_conditions(conditions)

        assert tables == ["credit_card_transactions"]

    def test_bank_service_filter(self, service):
        """Verify service=bank limits to bank table only."""
        conditions = {
            "type": "AND",
            "subconditions": [
                _condition("service", "equals", "bank"),
                _contains("test"),
            ],
        }
        tables = service._get_tables_names_for_conditions(conditions)

        assert tables == ["bank_transactions"]

    def test_service_value_normalized_with_spaces(self, service):
        """Verify service value with spaces is normalized (e.g. 'Credit Card' -> 'credit_card')."""
        tables = service._get_tables_names_for_conditions(
            _condition("service", "equals", "Credit Card")
        )

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
                _condition("service", "equals", "bank"),
                _condition("service", "equals", "credit_card"),
            ],
        }
        services = set()
        service._collect_services(conditions, services)

        assert services == {"bank", "credit_card"}

    def test_ignores_non_equals_operator_on_service(self, service):
        """Verify _collect_services only collects service fields with equals operator."""
        services = set()
        service._collect_services(_condition("service", "contains", "bank"), services)

        assert services == set()

    def test_collects_from_deeply_nested_tree(self, service):
        """Verify _collect_services traverses deeply nested AND/OR trees."""
        conditions = {
            "type": "AND",
            "subconditions": [
                {
                    "type": "OR",
                    "subconditions": [
                        _condition("service", "equals", "bank"),
                        _contains("test"),
                    ],
                },
                _condition("amount", "lt", 0),
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

    @staticmethod
    def _bank_bill(db_session, id_: str, amount: float, category=None, tag=None):
        """Insert one bank debit dated January 2024."""
        db_session.add(BankTransaction(
            id=id_,
            date="2024-01-10",
            amount=amount,
            description="Credit Card Bill",
            account_name="MyBank",
            provider="Hapoalim",
            source="bank_transactions",
            category=category,
            tag=tag,
        ))
        db_session.commit()

    @staticmethod
    def _cc_charge(db_session, id_: str, amount: float, provider="Visa", account_name="Gold"):
        """Insert one CC charge dated December 2023 (billed in January 2024)."""
        db_session.add(CreditCardTransaction(
            id=id_,
            date="2023-12-01",
            amount=amount,
            description="Store",
            account_name=account_name,
            account_number="1234",
            provider=provider,
            source="credit_card_transactions",
        ))
        db_session.commit()

    def test_auto_tag_matches_cc_bill(self, service, db_session):
        """Verify bank transaction matching CC total is tagged as Credit Cards."""
        self._cc_charge(db_session, "cc-1", -100.0)
        self._cc_charge(db_session, "cc-2", -50.0)
        self._bank_bill(db_session, "bank-1", -150.0)

        assert service.auto_tag_credit_cards_bills() == 1

        tagged = db_session.execute(
            select(BankTransaction).where(BankTransaction.category == "Credit Cards")
        ).scalar_one()
        assert tagged.tag == "Visa - Gold - 1234"

    def test_auto_tag_no_untagged_bank_transactions(self, service, db_session):
        """Verify returns 0 when all bank transactions are already tagged."""
        self._bank_bill(db_session, "bank-tagged", -150.0, category="Already Tagged", tag="Existing")

        assert service.auto_tag_credit_cards_bills() == 0

    def test_auto_tag_no_cc_transactions(self, service, db_session):
        """Verify returns 0 when there are no credit card transactions at all."""
        self._bank_bill(db_session, "bank-1", -150.0)

        assert service.auto_tag_credit_cards_bills() == 0

    def test_auto_tag_no_match_when_amounts_differ(self, service, db_session):
        """Verify no tagging occurs when bank amount does not match CC total."""
        self._cc_charge(db_session, "cc-1", -100.0)
        self._bank_bill(db_session, "bank-1", -999.0)

        assert service.auto_tag_credit_cards_bills() == 0

    def test_auto_tag_skips_ambiguous_multiple_matches(self, service, db_session):
        """Verify no tagging when multiple bank transactions match the same CC total."""
        self._cc_charge(db_session, "cc-1", -100.0)
        self._bank_bill(db_session, "bank-1", -100.0)
        self._bank_bill(db_session, "bank-2", -100.0)

        assert service.auto_tag_credit_cards_bills() == 0

    def test_lowercase_provider_end_to_end(self, service, db_session, monkeypatch):
        """Discovery title-cases the tag; matching back to the lowercase rows works.

        ``add_new_credit_card_tags`` stored ``"Isracard - Main Card - 1234"``
        while the rows say ``provider="isracard"``, so the exact-match lookup
        found zero charges and never tagged the bill.
        """
        monkeypatch.setattr(ts, "_categories_cache", {})
        db_session.add(Category(name="Credit Cards", tags=[]))
        db_session.commit()
        self._cc_charge(db_session, "cc-1", -80.0, provider="isracard", account_name="main card")
        self._cc_charge(db_session, "cc-2", -20.0, provider="isracard", account_name="main card")
        self._bank_bill(db_session, "bank-1", -100.0)

        service.categories_tags_service.add_new_credit_card_tags()
        assert service.categories_tags_service.categories_and_tags["Credit Cards"] == [
            "Isracard - Main Card - 1234"
        ]

        assert service.auto_tag_credit_cards_bills() == 1
        tagged = db_session.execute(
            select(BankTransaction).where(BankTransaction.category == "Credit Cards")
        ).scalar_one()
        assert tagged.tag == "Isracard - Main Card - 1234"


class TestLikeWildcardEscaping:
    """Condition values match literally — LIKE metacharacters are escaped."""

    def _seed(self, db_session, suffix, description):
        """Seed one untagged bank transaction."""
        db_session.add(
            BankTransaction(
                id=f"like-{suffix}", date="2026-03-10", provider="p",
                account_name="a", description=description, amount=-10.0,
                category=None, tag=None, source="bank_transactions",
                type="normal", status="completed",
            )
        )
        db_session.commit()

    def test_percent_is_literal_not_wildcard(self, db_session):
        """A '%' in the value matches a literal percent sign."""
        self._seed(db_session, "a", "SALE 50% OFF")
        self._seed(db_session, "b", "SALE 5000 SHEKEL")

        matched = TaggingRulesService(db_session).preview_rule(_contains("50%"))
        assert {m["description"] for m in matched} == {"SALE 50% OFF"}

    def test_underscore_is_literal_not_wildcard(self, db_session):
        """An '_' in the value matches a literal underscore."""
        self._seed(db_session, "a", "PAY_ME")
        self._seed(db_session, "b", "PAYXME")

        matched = TaggingRulesService(db_session).preview_rule(_contains("PAY_ME"))
        assert {m["description"] for m in matched} == {"PAY_ME"}

    def test_unknown_field_matches_no_transactions(self, db_session):
        """A typo'd field matches nothing rather than every transaction."""
        self._seed(db_session, "a", "groceries")
        self._seed(db_session, "b", "fuel")

        matched = TaggingRulesService(db_session).preview_rule(
            _condition("descripton", "contains", "groceries")
        )
        assert matched == []

    def test_validate_rejects_unknown_field(self, db_session):
        """Rule validation rejects an unrecognised condition field."""
        with pytest.raises(BadRequestException, match="Unknown condition field"):
            TaggingRulesService(db_session).validate_rule_integrity(
                _condition("descripton", "contains", "x")
            )


class TestNullNumericValueIsRejected:
    """A JSON null on a numeric field is a client error, not a crash."""

    @pytest.mark.parametrize(
        "operator,value", [("lt", None), ("between", [None, 1])]
    )
    def test_null_value_raises_bad_request(self, db_session, operator, value):
        """None reaching float() raises BadRequestException, not TypeError.

        The validator only caught ValueError, so a null escaped validation
        and surfaced as a 500 from add_rule/update_rule.
        """
        with pytest.raises(BadRequestException):
            TaggingRulesService(db_session).validate_rule_integrity(
                _condition("amount", operator, value)
            )
