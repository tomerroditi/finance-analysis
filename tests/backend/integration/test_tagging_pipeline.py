"""
Integration tests for the tagging rules pipeline.

Tests the full flow of creating, applying, updating, previewing,
and deleting tagging rules against real transactions in an in-memory
SQLite database.
"""

import pytest
from sqlalchemy import text

from backend.errors import BadRequestException
from backend.models.transaction import CreditCardTransaction
from backend.services.tagging_rules_service import TaggingRulesService


def _make_conditions(field: str, operator: str, value):
    """Build a standard AND-wrapped condition dict."""
    return {
        "type": "AND",
        "subconditions": [
            {
                "type": "CONDITION",
                "field": field,
                "operator": operator,
                "value": value,
            }
        ],
    }


def _get_transaction_by_id(db_session, table: str, tx_id: str) -> dict:
    """Fetch a single transaction row by its ``id`` column."""
    row = db_session.execute(
        text(f"SELECT * FROM {table} WHERE id = :id"), {"id": tx_id}
    ).mappings().first()
    return dict(row) if row else {}


@pytest.fixture(autouse=True)
def _patch_categories_cache(sample_categories_yaml, monkeypatch):
    """Inject the sample categories dict into the module-level cache."""
    monkeypatch.setattr(
        "backend.services.tagging_service._categories_cache",
        {False: sample_categories_yaml},
    )


class TestTaggingPipeline:
    """Integration tests for the tagging rules pipeline end-to-end."""

    def test_creation_order_decides_a_later_overlap(
        self, db_session, seed_untagged_transactions
    ):
        """The older of two rules claims a transaction that matches both.

        Rules carry no priority: they run in creation order (``id`` ASC) and
        the first match wins. Two rules can only ever both match a
        transaction that arrived *after* they were created — an overlap that
        exists at creation time is refused by conflict detection — so this
        seeds the overlapping transaction last.
        """
        service = TaggingRulesService(db_session)

        # Older rule, broad. Nothing in the seed mentions SHUFERSAL, so
        # neither rule overlaps anything at creation time.
        service.add_rule(
            name="Shufersal Broad",
            conditions=_make_conditions("description", "contains", "SHUFERSAL"),
            category="Food",
            tag="Groceries",
        )
        # Newer rule, narrower — and therefore the one a user would expect to
        # win. It does not: age beats specificity.
        service.add_rule(
            name="Shufersal Online Specific",
            conditions=_make_conditions("description", "contains", "SHUFERSAL ONLINE"),
            category="Food",
            tag="Restaurants",
        )

        # A newly scraped transaction matches BOTH rules.
        db_session.add(
            CreditCardTransaction(
                id="cc_shufersal",
                date="2024-03-01",
                provider="isracard",
                account_name="Main Card",
                description="SHUFERSAL ONLINE DELIVERY",
                amount=-240.0,
                source="credit_card_transactions",
            )
        )
        db_session.commit()

        assert service.apply_rules() == 1

        row = _get_transaction_by_id(
            db_session, "credit_card_transactions", "cc_shufersal"
        )
        assert (row["category"], row["tag"]) == ("Food", "Groceries")

        # ...and re-running with overwrite=True does not hand it to the
        # younger rule either — first match still wins in both modes.
        service.apply_rules(overwrite=True)
        row = _get_transaction_by_id(
            db_session, "credit_card_transactions", "cc_shufersal"
        )
        assert (row["category"], row["tag"]) == ("Food", "Groceries")

    def test_rule_does_not_overwrite_existing_tags(
        self, db_session, seed_untagged_transactions, seed_base_transactions
    ):
        """Apply rules with overwrite=False; already-tagged transactions keep their tags."""
        service = TaggingRulesService(db_session)

        # seed_base_transactions includes cc_jan_1 "Shufersal Deal" tagged Food/Groceries
        # Create a broad rule that could match "Deal" in description
        conditions = _make_conditions("description", "contains", "Deal")
        service.add_rule(
            name="Deal Rule",
            conditions=conditions,
            category="Entertainment",
            tag="Cinema",
        )

        # The already-tagged transaction should remain Food/Groceries
        cc = _get_transaction_by_id(db_session, "credit_card_transactions", "cc_jan_1")
        assert cc["category"] == "Food"
        assert cc["tag"] == "Groceries"

    def test_retarget_a_rule_moves_the_rows_it_had_tagged(
        self, db_session, seed_untagged_transactions
    ):
        """Editing a rule's tag moves the rows it owns; a re-apply is then a no-op."""
        service = TaggingRulesService(db_session)

        # First, tag SUPERMARKET transactions as Food/Groceries
        conditions = _make_conditions("description", "contains", "SUPERMARKET")
        rule_id, n_tagged = service.add_rule(
            name="Supermarket Initial",
            conditions=conditions,
            category="Food",
            tag="Groceries",
        )
        assert n_tagged == 2

        # Verify initial tagging
        cc = _get_transaction_by_id(db_session, "credit_card_transactions", "cc_untag_1")
        assert cc["category"] == "Food"
        assert cc["tag"] == "Groceries"

        # Retargeting the rule re-tags the rows still carrying its old pair.
        assert service.update_rule(rule_id, category="Food", tag="Restaurants") == 2

        cc = _get_transaction_by_id(db_session, "credit_card_transactions", "cc_untag_1")
        assert cc["category"] == "Food"
        assert cc["tag"] == "Restaurants"

        bank = _get_transaction_by_id(db_session, "bank_transactions", "bank_untag_1")
        assert bank["category"] == "Food"
        assert bank["tag"] == "Restaurants"

        # Every matching row already says what the rule says, so even an
        # explicit overwrite pass has nothing left to change.
        assert service.apply_rule_by_id(rule_id, overwrite=True) == 0

    def test_delete_rule_does_not_untag(self, db_session, seed_untagged_transactions):
        """Tag transactions via a rule, delete the rule, verify tags remain."""
        service = TaggingRulesService(db_session)

        conditions = _make_conditions("description", "contains", "SUPERMARKET")
        rule_id, n_tagged = service.add_rule(
            name="Supermarket Temp",
            conditions=conditions,
            category="Food",
            tag="Groceries",
        )
        assert n_tagged == 2

        # Delete the rule
        result = service.delete_rule(rule_id)
        assert result is True

        # Tags should still be on the transactions
        cc = _get_transaction_by_id(db_session, "credit_card_transactions", "cc_untag_1")
        assert cc["category"] == "Food"
        assert cc["tag"] == "Groceries"

        bank = _get_transaction_by_id(db_session, "bank_transactions", "bank_untag_1")
        assert bank["category"] == "Food"
        assert bank["tag"] == "Groceries"

    def test_multiple_rules_different_categories(
        self, db_session, seed_untagged_transactions
    ):
        """Create SUPERMARKET->Food/Groceries and UBER->Transport/Rides rules; verify each transaction gets the correct category."""
        service = TaggingRulesService(db_session)

        supermarket_cond = _make_conditions("description", "contains", "SUPERMARKET")
        rule_id_1, n_1 = service.add_rule(
            name="Supermarket Rule",
            conditions=supermarket_cond,
            category="Food",
            tag="Groceries",
        )
        assert n_1 == 2

        uber_cond = _make_conditions("description", "contains", "UBER")
        rule_id_2, n_2 = service.add_rule(
            name="Uber Rule",
            conditions=uber_cond,
            category="Transport",
            tag="Rides",
        )
        assert n_2 == 2

        # Verify SUPERMARKET transactions
        cc1 = _get_transaction_by_id(db_session, "credit_card_transactions", "cc_untag_1")
        assert cc1["category"] == "Food"
        assert cc1["tag"] == "Groceries"

        bank1 = _get_transaction_by_id(db_session, "bank_transactions", "bank_untag_1")
        assert bank1["category"] == "Food"
        assert bank1["tag"] == "Groceries"

        # Verify UBER transactions
        cc2 = _get_transaction_by_id(db_session, "credit_card_transactions", "cc_untag_2")
        assert cc2["category"] == "Transport"
        assert cc2["tag"] == "Rides"

        bank2 = _get_transaction_by_id(db_session, "bank_transactions", "bank_untag_2")
        assert bank2["category"] == "Transport"
        assert bank2["tag"] == "Rides"

        # Unrelated transactions remain untagged
        cc4 = _get_transaction_by_id(db_session, "credit_card_transactions", "cc_untag_4")
        assert cc4["category"] is None

    def test_update_rule_conditions(self, db_session, seed_untagged_transactions):
        """Create a rule, apply it, update conditions, re-apply, verify new matches."""
        service = TaggingRulesService(db_session)

        # Start with PHARMACY
        conditions = _make_conditions("description", "contains", "PHARMACY")
        rule_id, n_tagged = service.add_rule(
            name="Pharmacy Rule",
            conditions=conditions,
            category="Food",
            tag="Groceries",
        )
        assert n_tagged == 1  # cc_untag_4

        pharm = _get_transaction_by_id(db_session, "credit_card_transactions", "cc_untag_4")
        assert pharm["category"] == "Food"
        assert pharm["tag"] == "Groceries"

        # Unknown Wire Transfer should be untagged
        wire = _get_transaction_by_id(db_session, "bank_transactions", "bank_untag_4")
        assert wire["category"] is None

        # Update rule to match "Unknown Wire" instead
        new_conditions = _make_conditions("description", "contains", "Unknown Wire")
        service.update_rule(rule_id, conditions=new_conditions)

        # Now the wire transfer should be tagged
        wire = _get_transaction_by_id(db_session, "bank_transactions", "bank_untag_4")
        assert wire["category"] == "Food"
        assert wire["tag"] == "Groceries"

    def test_preview_rule(self, db_session, seed_untagged_transactions):
        """Use preview_rule to see matching transactions without modifying them."""
        service = TaggingRulesService(db_session)

        conditions = _make_conditions("description", "contains", "SUPERMARKET")
        results = service.preview_rule(conditions)

        assert len(results) == 2
        descriptions = {r["description"] for r in results}
        assert "SUPERMARKET PURCHASE" in descriptions
        assert "SUPERMARKET CHAIN" in descriptions

        # Verify transactions are NOT modified
        cc = _get_transaction_by_id(db_session, "credit_card_transactions", "cc_untag_1")
        assert cc["category"] is None

        bank = _get_transaction_by_id(db_session, "bank_transactions", "bank_untag_1")
        assert bank["category"] is None

    def test_validate_rule_conflict(self, db_session, seed_untagged_transactions):
        """Create 2 rules matching the same transactions with different category/tag; verify conflict raises BadRequestException."""
        service = TaggingRulesService(db_session)

        # First rule: SUPERMARKET -> Food/Groceries
        conditions = _make_conditions("description", "contains", "SUPERMARKET")
        service.add_rule(
            name="Supermarket Food",
            conditions=conditions,
            category="Food",
            tag="Groceries",
        )

        # Second rule with same conditions but a different (and valid)
        # category/tag. The transactions are already tagged, but the conflict
        # check looks at overlapping matching transactions between rules with
        # different category/tag, so it still fires.
        conflicting_conditions = _make_conditions("description", "contains", "SUPERMARKET")
        with pytest.raises(BadRequestException, match="Conflict detected"):
            service.add_rule(
                name="Supermarket Other",
                conditions=conflicting_conditions,
                category="Home",
                tag="Cleaning",
            )

        # The refused rule was never stored and changed nothing.
        assert len(service.get_all_rules()) == 1
        cc = _get_transaction_by_id(db_session, "credit_card_transactions", "cc_untag_1")
        assert (cc["category"], cc["tag"]) == ("Food", "Groceries")
