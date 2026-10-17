"""Tests for keeping linked refund money under its purchase's tag."""

import pytest

import backend.services.tagging_service as ts
from backend.errors import ValidationException
from backend.models.pending_refund import RefundLink
from backend.models.transaction import BankTransaction, SplitTransaction
from backend.services.pending_refunds_service import PendingRefundsService
from backend.services.refund_tag_alignment import RefundTagAlignmentService
from backend.services.tagging_rules_service import TaggingRulesService
from backend.services.transactions_service import TransactionsService

BANK = "bank_transactions"


def _bank(db_session, tx_id: str, amount: float, category: str, tag: str) -> BankTransaction:
    """Insert one bank row and return it."""
    row = BankTransaction(
        id=tx_id, date="2024-01-05", provider="hapoalim",
        account_name="Checking", description=tx_id, amount=amount,
        category=category, tag=tag, source=BANK,
        type="normal", status="completed",
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _splits(db_session, unique_id: int) -> list[tuple[float, str, str]]:
    """Return a transaction's split parts as ``(amount, category, tag)``, by id."""
    rows = (
        db_session.query(SplitTransaction)
        .filter(SplitTransaction.transaction_id == unique_id, SplitTransaction.source == BANK)
        .order_by(SplitTransaction.id)
        .all()
    )
    return [(float(r.amount), r.category, r.tag) for r in rows]


def _link(db_session, link_id: int) -> RefundLink:
    """Re-read a refund link."""
    db_session.expire_all()
    return db_session.get(RefundLink, link_id)


@pytest.fixture
def purchase(db_session) -> BankTransaction:
    """A ₪300 grocery purchase."""
    return _bank(db_session, "purchase", -300.0, "Food", "Groceries")


@pytest.fixture
def service(db_session) -> PendingRefundsService:
    """The pending refunds service under test."""
    return PendingRefundsService(db_session)


def _pending(service: PendingRefundsService, purchase: BankTransaction, amount: float) -> int:
    """Mark ``purchase`` as awaiting ``amount`` back and return the record id."""
    return service.mark_as_pending_refund("transaction", purchase.unique_id, "banks", amount)["id"]


def _link_id(service: PendingRefundsService, pending_id: int) -> int:
    """Return the only link of a pending refund."""
    links = service.repo.get_links_for_pending(pending_id)
    assert len(links) == 1
    return int(links["id"].iloc[0])


class TestLinkRefundRetag:
    """Linking demands the refund sit under the purchase's tag."""

    def test_mismatched_link_rejected_without_retag(self, db_session, service, purchase):
        """A refund tagged elsewhere is refused unless retag is asked for."""
        refund = _bank(db_session, "refund", 300.0, "Other Income", "Bit")
        pending_id = _pending(service, purchase, 300.0)

        with pytest.raises(ValidationException, match="tagged differently"):
            service.link_refund(pending_id, refund.unique_id, BANK, 300.0)

    def test_matching_link_needs_no_retag(self, db_session, service, purchase):
        """A refund already under the purchase's tag links and is left alone."""
        refund = _bank(db_session, "refund", 300.0, "Food", "Groceries")
        pending_id = _pending(service, purchase, 300.0)

        result = service.link_refund(pending_id, refund.unique_id, BANK, 300.0)

        assert result["retagged"] is False
        assert _splits(db_session, refund.unique_id) == []

    def test_full_refund_is_retagged_in_place(self, db_session, service, purchase):
        """A link covering the whole refund retags the refund itself."""
        refund = _bank(db_session, "refund", 300.0, "Other Income", "Bit")
        pending_id = _pending(service, purchase, 300.0)

        result = service.link_refund(pending_id, refund.unique_id, BANK, 300.0, retag=True)

        db_session.refresh(refund)
        assert result["retagged"] is True
        assert (refund.category, refund.tag, refund.type) == ("Food", "Groceries", "normal")
        assert _link(db_session, _link_id(service, pending_id)).refund_split_id is None

    def test_larger_refund_is_split_and_only_the_linked_part_retagged(
        self, db_session, service, purchase
    ):
        """A refund larger than the link is carved: the linked part moves, the rest stays."""
        refund = _bank(db_session, "refund", 1000.0, "Other Income", "Bit")
        pending_id = _pending(service, purchase, 300.0)

        service.link_refund(pending_id, refund.unique_id, BANK, 300.0, retag=True)

        db_session.refresh(refund)
        assert refund.type == "split_parent"
        parts = _splits(db_session, refund.unique_id)
        assert parts == [(300.0, "Food", "Groceries"), (700.0, "Other Income", "Bit")]
        link = _link(db_session, _link_id(service, pending_id))
        carved = db_session.get(SplitTransaction, link.refund_split_id)
        assert (carved.category, carved.amount) == ("Food", 300.0)

    def test_one_refund_paying_back_two_purchases_gets_a_part_per_purchase(
        self, db_session, service, purchase
    ):
        """Each purchase a refund pays back gets its own part, the leftover keeps its tag."""
        second = _bank(db_session, "second", -200.0, "Home", "Cleaning")
        refund = _bank(db_session, "refund", 1000.0, "Other Income", "Bit")
        first_id = _pending(service, purchase, 300.0)
        second_id = _pending(service, second, 200.0)

        service.link_refund(first_id, refund.unique_id, BANK, 300.0, retag=True)
        service.link_refund(second_id, refund.unique_id, BANK, 200.0, retag=True)

        assert sorted(_splits(db_session, refund.unique_id)) == sorted(
            [
                (300.0, "Food", "Groceries"),
                (200.0, "Home", "Cleaning"),
                (500.0, "Other Income", "Bit"),
            ]
        )
        for pending_id, category in ((first_id, "Food"), (second_id, "Home")):
            link = _link(db_session, _link_id(service, pending_id))
            assert db_session.get(SplitTransaction, link.refund_split_id).category == category
        assert RefundTagAlignmentService(db_session).get_mismatches() == []

    def test_split_refund_auto_picks_a_matching_part(self, db_session, service, purchase):
        """On an already-split refund, the part under the purchase's tag is linked untouched."""
        refund = _bank(db_session, "refund", 500.0, "Other Income", "Bit")
        TransactionsService(db_session).split_transaction(
            refund.unique_id, BANK,
            [
                {"amount": 200.0, "category": "Other Income", "tag": "Bit"},
                {"amount": 300.0, "category": "Food", "tag": "Groceries"},
            ],
        )
        pending_id = _pending(service, purchase, 300.0)

        result = service.link_refund(pending_id, refund.unique_id, BANK, 300.0)

        assert result["retagged"] is False
        link = _link(db_session, _link_id(service, pending_id))
        assert db_session.get(SplitTransaction, link.refund_split_id).category == "Food"

    def test_split_part_is_carved_when_larger_than_the_link(
        self, db_session, service, purchase
    ):
        """A link on part of a split part carves that part in two."""
        refund = _bank(db_session, "refund", 1000.0, "Other Income", "Bit")
        TransactionsService(db_session).split_transaction(
            refund.unique_id, BANK,
            [
                {"amount": 800.0, "category": "Other Income", "tag": "Bit"},
                {"amount": 200.0, "category": "Home", "tag": "Cleaning"},
            ],
        )
        first_part = db_session.query(SplitTransaction).order_by(SplitTransaction.id).first()
        pending_id = _pending(service, purchase, 300.0)

        service.link_refund(
            pending_id, refund.unique_id, BANK, 300.0,
            retag=True, refund_split_id=first_part.id,
        )

        assert sorted(_splits(db_session, refund.unique_id)) == sorted(
            [
                (500.0, "Other Income", "Bit"),
                (200.0, "Home", "Cleaning"),
                (300.0, "Food", "Groceries"),
            ]
        )

    def test_split_id_of_another_transaction_rejected(self, db_session, service, purchase):
        """A split part the refund does not own cannot be linked."""
        refund = _bank(db_session, "refund", 500.0, "Food", "Groceries")
        other = _bank(db_session, "other", 500.0, "Food", "Groceries")
        TransactionsService(db_session).split_transaction(
            refund.unique_id, BANK,
            [
                {"amount": 250.0, "category": "Food", "tag": "Groceries"},
                {"amount": 250.0, "category": "Food", "tag": "Groceries"},
            ],
        )
        TransactionsService(db_session).split_transaction(
            other.unique_id, BANK,
            [
                {"amount": 250.0, "category": "Food", "tag": "Groceries"},
                {"amount": 250.0, "category": "Food", "tag": "Groceries"},
            ],
        )
        foreign = _splits_ids(db_session, other.unique_id)[0]
        pending_id = _pending(service, purchase, 200.0)

        with pytest.raises(ValidationException):
            service.link_refund(
                pending_id, refund.unique_id, BANK, 200.0, refund_split_id=foreign
            )

    def test_split_id_on_unsplit_refund_rejected(self, db_session, service, purchase):
        """Naming a split part of a refund that is not split is refused."""
        refund = _bank(db_session, "refund", 300.0, "Food", "Groceries")
        pending_id = _pending(service, purchase, 300.0)

        with pytest.raises(ValidationException, match="not split"):
            service.link_refund(pending_id, refund.unique_id, BANK, 300.0, refund_split_id=1)


def _splits_ids(db_session, unique_id: int) -> list[int]:
    """Return a transaction's split part ids in order."""
    return [
        r.id
        for r in db_session.query(SplitTransaction)
        .filter(SplitTransaction.transaction_id == unique_id, SplitTransaction.source == BANK)
        .order_by(SplitTransaction.id)
    ]


class TestSplitLinkNetting:
    """A link pinned to a split part nets that part, not the whole refund."""

    def test_pinned_link_nets_its_part(self, db_session, service, purchase):
        """The carved part is cancelled out; the leftover part still counts in full."""
        refund = _bank(db_session, "refund", 1000.0, "Other Income", "Bit")
        pending_id = _pending(service, purchase, 300.0)
        service.link_refund(pending_id, refund.unique_id, BANK, 300.0, retag=True)
        link = _link(db_session, _link_id(service, pending_id))

        adjustments = service.get_refund_amount_adjustments()

        assert adjustments["splits"] == {int(link.refund_split_id): pytest.approx(-300.0)}
        assert adjustments["transactions"] == {
            (BANK, purchase.unique_id): pytest.approx(300.0)
        }


class TestUnpinOnResplit:
    """Re-splitting or reverting a refund keeps its links, covering the whole row."""

    def test_revert_unpins_and_fix_all_repins(self, db_session, service, purchase):
        """After a revert the link is a mismatch until fix-all carves it again."""
        refund = _bank(db_session, "refund", 1000.0, "Other Income", "Bit")
        pending_id = _pending(service, purchase, 300.0)
        service.link_refund(pending_id, refund.unique_id, BANK, 300.0, retag=True)
        link_id = _link_id(service, pending_id)

        TransactionsService(db_session).revert_split(refund.unique_id, BANK)

        assert _link(db_session, link_id).refund_split_id is None
        alignment = RefundTagAlignmentService(db_session)
        mismatches = alignment.get_mismatches()
        assert [m["link_id"] for m in mismatches] == [link_id]
        assert mismatches[0]["refund_category"] == "Other Income"

        assert alignment.fix_mismatches() == 1
        assert alignment.get_mismatches() == []
        assert _link(db_session, link_id).refund_split_id is not None


class TestCascadeFromPurchase:
    """Retagging a purchase carries its linked refund money along."""

    @pytest.fixture
    def linked(self, db_session, service, purchase) -> tuple[BankTransaction, int]:
        """A full refund linked to ``purchase``; returns the refund and link id."""
        refund = _bank(db_session, "refund", 300.0, "Food", "Groceries")
        pending_id = _pending(service, purchase, 300.0)
        service.link_refund(pending_id, refund.unique_id, BANK, 300.0)
        return refund, _link_id(service, pending_id)

    def test_update_tagging_by_id_cascades(self, db_session, purchase, linked):
        """The single-row tag write moves the refund too and reports it."""
        refund, _ = linked
        count = TransactionsService(db_session).update_tagging_by_id(
            BANK, purchase.unique_id, "Home", "Cleaning"
        )

        db_session.refresh(refund)
        assert count == 1
        assert (refund.category, refund.tag) == ("Home", "Cleaning")

    def test_update_transaction_cascades(self, db_session, purchase, linked):
        """Editing the purchase's tag in the editor moves the refund too."""
        refund, _ = linked
        result = TransactionsService(db_session).update_transaction(
            purchase.unique_id, BANK, {"category": "Home", "tag": "Cleaning"}
        )

        db_session.refresh(refund)
        assert result == {"updated": True, "refunds_retagged": 1}
        assert refund.category == "Home"

    def test_bulk_tag_cascades(self, db_session, purchase, linked):
        """Bulk-tagging the purchase moves the refund too."""
        refund, _ = linked
        count = TransactionsService(db_session).bulk_tag_transactions(
            [purchase.unique_id], BANK, "Home", "Cleaning"
        )

        db_session.refresh(refund)
        assert count == 1
        assert refund.category == "Home"

    def test_retagging_an_unlinked_row_cascades_nothing(self, db_session):
        """A purchase with no refund reports zero."""
        row = _bank(db_session, "lonely", -50.0, "Food", "Groceries")
        assert (
            TransactionsService(db_session).update_tagging_by_id(
                BANK, row.unique_id, "Home", "Cleaning"
            )
            == 0
        )


RULE_CATEGORIES = {
    "Food": ["Groceries"],
    "Home": ["Cleaning"],
    "Other Income": ["Bit"],
}


class TestTaggingRulesRespectLinks:
    """Tagging rules leave linked refunds under their purchase's tag."""

    @pytest.fixture(autouse=True)
    def _categories(self, monkeypatch):
        """Serve the categories the rules below assign."""
        monkeypatch.setattr(ts, "_categories_cache", {ts.cache_key(): RULE_CATEGORIES})

    def test_overwrite_rule_skips_linked_refund(self, db_session, service, purchase):
        """Even an overwriting rule does not take a linked refund back."""
        refund = _bank(db_session, "bit refund", 300.0, "Food", "Groceries")
        pending_id = _pending(service, purchase, 300.0)
        service.link_refund(pending_id, refund.unique_id, BANK, 300.0)
        rules = TaggingRulesService(db_session)
        rules.add_rule(
            "Bit",
            {"type": "CONDITION", "field": "description", "operator": "contains", "value": "bit"},
            "Other Income",
            "Bit",
        )

        rules.apply_rules(overwrite=True)

        db_session.refresh(refund)
        assert (refund.category, refund.tag) == ("Food", "Groceries")

    def test_rule_retagging_a_purchase_cascades(self, db_session, service, purchase):
        """A rule that retags a purchase moves its linked refund too."""
        refund = _bank(db_session, "refund", 300.0, "Food", "Groceries")
        pending_id = _pending(service, purchase, 300.0)
        service.link_refund(pending_id, refund.unique_id, BANK, 300.0)
        rules = TaggingRulesService(db_session)
        rules.add_rule(
            "Purchase",
            {"type": "CONDITION", "field": "description", "operator": "equals", "value": "purchase"},
            "Home",
            "Cleaning",
        )

        rules.apply_rules(overwrite=True)

        db_session.refresh(refund)
        assert (refund.category, refund.tag) == ("Home", "Cleaning")
