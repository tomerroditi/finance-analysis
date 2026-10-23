"""Keep a linked refund under the same category and tag as its purchase.

A refund linked to a purchase cancels it, wherever the two fell — but only in
a breakdown that reads both rows under the same tag. A ₪300 "Bit" refund that
pays back a ₪300 "Restaurants" dinner leaves Restaurants overstated and the
refund's own tag understated by the same ₪300. So a link carries the
purchase's tag over to the money it covers:

- a link covering a whole refund transaction (or a whole split part) retags it
  in place;
- a link covering part of one carves that part off as a split under the
  purchase's tag, and the rest keeps its own tag.

Whatever tag the user later gives the purchase, its linked refund money
follows (:meth:`RefundTagAlignmentService.cascade_from_transactions`), and
tagging rules leave a whole-linked refund alone
(:meth:`RefundTagAlignmentService.linked_refund_ids`).
"""

from dataclasses import dataclass
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from backend.constants.tables import canonical_table
from backend.models.pending_refund import PendingRefund, RefundLink
from backend.repositories.pending_refunds_repository import PendingRefundsRepository
from backend.repositories.transactions import TransactionsRepository, TxRef

#: Amounts closer than this are the same amount.
_EPS = 0.005


@dataclass(frozen=True)
class Tagging:
    """A category/tag pair, with blank and missing values treated alike."""

    category: str | None
    tag: str | None

    @classmethod
    def of(cls, category: Any, tag: Any) -> "Tagging":
        """Build a tagging from raw column values.

        Parameters
        ----------
        category : Any
            Category as stored (``None``, ``NaN`` or ``""`` mean none).
        tag : Any
            Tag as stored.

        Returns
        -------
        Tagging
            The normalized pair.
        """
        return cls(_clean(category), _clean(tag))


def _clean(value: Any) -> str | None:
    """Normalize a stored category or tag to a non-empty string or ``None``."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value)
    return text or None


class RefundTagAlignmentService:
    """
    Carve and retag linked refund money so it sits under its purchase's tag.

    Parameters
    ----------
    db : Session
        SQLAlchemy session for database operations.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = PendingRefundsRepository(db)
        self.transactions_repo = TransactionsRepository(db)
        self.split_repo = self.transactions_repo.split_repo

    def purchase_tagging(self, pending: PendingRefund) -> Tagging | None:
        """
        Return the category and tag of the purchase a pending refund is on.

        Parameters
        ----------
        pending : PendingRefund
            The expectation.

        Returns
        -------
        Tagging or None
            The purchase's tagging, or ``None`` when the purchase is gone.
        """
        if pending.source_type == "split":
            split = self.split_repo.get_split(int(pending.source_id))
            return None if split is None else Tagging.of(split.category, split.tag)
        txn = self.transactions_repo.get_record(
            TxRef.parse(pending.source_table, pending.source_id)
        )
        return None if txn is None else Tagging.of(txn.category, txn.tag)

    def refund_tagging(self, link: RefundLink) -> Tagging | None:
        """
        Return the category and tag the money a link covers currently carries.

        Parameters
        ----------
        link : RefundLink
            The link.

        Returns
        -------
        Tagging or None
            The tagging of the split part or transaction the link covers, or
            ``None`` when that cannot be told: the row is gone, or the link
            covers a transaction since split into parts.
        """
        if link.refund_split_id is not None:
            split = self.split_repo.get_split(int(link.refund_split_id))
            return None if split is None else Tagging.of(split.category, split.tag)
        txn = self._refund_record(link)
        if txn is None or txn.type == "split_parent":
            return None
        return Tagging.of(txn.category, txn.tag)

    def pick_split_part(
        self,
        source: str,
        transaction_id: int,
        amount: float,
        target: Tagging,
        exclude_link_id: int | None = None,
    ) -> tuple[int, Tagging] | None:
        """
        Choose the split part of a refund transaction a new link should cover.

        A part already under the purchase's tag with room for ``amount`` wins;
        otherwise the part with the most room left, if it has enough.

        Parameters
        ----------
        source : str
            Table of the refund transaction.
        transaction_id : int
            unique_id of the refund transaction.
        amount : float
            Amount the link covers.
        target : Tagging
            The purchase's tagging.
        exclude_link_id : int or None, optional
            A link whose own allocation is not counted against the parts.

        Returns
        -------
        tuple[int, Tagging] or None
            The chosen part's split id and tagging, or ``None`` when no part
            has room.
        """
        parts = self.split_repo.get_splits_for_transaction(
            transaction_id, canonical_table(source)
        )
        if parts.empty:
            return None
        used = self._allocated_by_split(exclude_link_id)
        best: tuple[int, Tagging] | None = None
        best_room = -1.0
        for _, part in parts.iterrows():
            room = float(part["amount"]) - used.get(int(part["id"]), 0.0)
            if room < amount - _EPS:
                continue
            tagging = Tagging.of(part["category"], part["tag"])
            if tagging == target:
                return int(part["id"]), tagging
            if room > best_room:
                best, best_room = (int(part["id"]), tagging), room
        return best

    def split_room(self, split_id: int) -> float | None:
        """
        Return how much of a split part no link covers yet.

        Parameters
        ----------
        split_id : int
            The split part.

        Returns
        -------
        float or None
            The part's amount less its links, or ``None`` when it is gone.
        """
        split = self.split_repo.get_split(split_id)
        if split is None:
            return None
        return float(split.amount) - self._allocated_by_split().get(split_id, 0.0)

    def align_link(self, link_id: int) -> bool:
        """
        Move the money a link covers under its purchase's category and tag.

        Parameters
        ----------
        link_id : int
            The link to align.

        Returns
        -------
        bool
            Whether anything was retagged, carved or re-pointed. ``False``
            when the link already matches, or when it cannot be aligned
            without moving another link's money (its rows are gone, or the
            money is shared with other links in a way no carve can separate).
        """
        link = self.repo.get_link_by_id(link_id)
        if link is None:
            return False
        pending = self.repo.get_by_id(int(link.pending_refund_id))
        target = self.purchase_tagging(pending) if pending is not None else None
        if target is None:
            return False
        if link.refund_split_id is not None:
            return self._align_split_link(link, target)

        txn = self._refund_record(link)
        if txn is None:
            return False
        if txn.type == "split_parent":
            picked = self.pick_split_part(
                link.refund_source,
                int(link.refund_transaction_id),
                float(link.amount),
                target,
                exclude_link_id=link.id,
            )
            if picked is None:
                return False
            self.repo.set_link_split(link.id, picked[0])
            self.db.refresh(link)
            self._align_split_link(link, target)
            return True
        return self._align_transaction_link(link, txn, target)

    def cascade_from_transactions(self, source: str, unique_ids: list[int]) -> int:
        """
        Realign the refunds linked to purchases whose tag just changed.

        Parameters
        ----------
        source : str
            Table or service name of the retagged transactions.
        unique_ids : list[int]
            The retagged transactions.

        Returns
        -------
        int
            How many links had their refund money moved.
        """
        if not unique_ids:
            return 0
        pending_df = self.repo.get_all_pending_refunds()
        if pending_df.empty:
            return 0
        table = canonical_table(source)
        ids = {int(uid) for uid in unique_ids}
        mask = (
            (pending_df["source_type"] == "transaction")
            & (pending_df["source_table"].map(canonical_table) == table)
            & pending_df["source_id"].astype(int).isin(ids)
        )
        pending_ids = [int(v) for v in pending_df.loc[mask, "id"]]
        if not pending_ids:
            return 0
        links = self.repo.get_links_for_pendings(pending_ids)
        return sum(self.align_link(int(link_id)) for link_id in links["id"])

    def linked_refund_ids(self, source: str) -> set[int]:
        """
        Return the transactions of a table a link covers whole.

        Their tag is the purchase's, set by the link; a tagging rule must not
        take it back.

        Parameters
        ----------
        source : str
            Table or service name.

        Returns
        -------
        set[int]
            unique_ids with at least one link that covers no split part.
        """
        links = self.repo.get_all_links()
        if links.empty:
            return set()
        table = canonical_table(source)
        mask = (links["refund_source"].map(canonical_table) == table) & links[
            "refund_split_id"
        ].isna()
        return {int(v) for v in links.loc[mask, "refund_transaction_id"]}

    def get_mismatches(self) -> list[dict[str, Any]]:
        """
        List links whose refund money sits under another tag than the purchase.

        Returns
        -------
        list[dict]
            One entry per mismatched link: ``link_id``, ``pending_refund_id``,
            ``amount``, ``purchase_category``, ``purchase_tag``,
            ``refund_category`` and ``refund_tag`` (both ``None`` when the
            link covers a transaction since split into parts),
            ``refund_source`` and ``refund_transaction_id``.
        """
        links = self.repo.get_all_links()
        if links.empty:
            return []
        result = []
        pendings: dict[int, PendingRefund | None] = {}
        for link_id in links["id"]:
            link = self.repo.get_link_by_id(int(link_id))
            if link is None:
                continue
            pid = int(link.pending_refund_id)
            if pid not in pendings:
                pendings[pid] = self.repo.get_by_id(pid)
            pending = pendings[pid]
            target = self.purchase_tagging(pending) if pending is not None else None
            if target is None:
                continue
            current = self.refund_tagging(link)
            if current == target:
                continue
            result.append(
                {
                    "link_id": int(link.id),
                    "pending_refund_id": pid,
                    "amount": float(link.amount),
                    "purchase_category": target.category,
                    "purchase_tag": target.tag,
                    "refund_category": current.category if current else None,
                    "refund_tag": current.tag if current else None,
                    "refund_source": canonical_table(link.refund_source),
                    "refund_transaction_id": int(link.refund_transaction_id),
                }
            )
        return result

    def fix_mismatches(self) -> int:
        """
        Align every mismatched link.

        Returns
        -------
        int
            How many links were aligned.
        """
        return sum(self.align_link(m["link_id"]) for m in self.get_mismatches())

    def _refund_record(self, link: RefundLink) -> Any:
        """Return the refund transaction a link names, or ``None``."""
        return self.transactions_repo.get_record(
            TxRef.parse(link.refund_source, link.refund_transaction_id)
        )

    def _allocated_by_split(
        self, exclude_link_id: int | None = None
    ) -> dict[int, float]:
        """Sum link amounts per split part they cover."""
        links = self.repo.get_all_links()
        if links.empty:
            return {}
        pinned = links[links["refund_split_id"].notna()]
        if exclude_link_id is not None:
            pinned = pinned[pinned["id"] != exclude_link_id]
        return {
            int(k): float(v)
            for k, v in pinned.groupby("refund_split_id")["amount"].sum().items()
        }

    def _other_links(self, link: RefundLink) -> pd.DataFrame:
        """Return the other links sharing the money ``link`` covers."""
        links = self.repo.get_all_links()
        links = links[links["id"] != link.id]
        if link.refund_split_id is not None:
            return links[links["refund_split_id"] == link.refund_split_id]
        same_txn = (links["refund_transaction_id"] == link.refund_transaction_id) & (
            links["refund_source"].map(canonical_table)
            == canonical_table(link.refund_source)
        )
        return links[same_txn & links["refund_split_id"].isna()]

    def _align_split_link(self, link: RefundLink, target: Tagging) -> bool:
        """Align a link covering a split part: retag it whole or carve it."""
        split = self.split_repo.get_split(int(link.refund_split_id))
        if split is None:
            return False
        if Tagging.of(split.category, split.tag) == target:
            return False
        amount = float(link.amount)
        if amount >= float(split.amount) - _EPS:
            if not self._other_links(link).empty:
                return False
            self.split_repo.update_split(
                split.id, float(split.amount), target.category, target.tag
            )
            return True
        self.split_repo.update_split(
            split.id, float(split.amount) - amount, split.category, split.tag
        )
        carved = self.split_repo.add_split(
            int(split.transaction_id),
            split.source,
            amount,
            target.category,
            target.tag,
        )
        self.repo.set_link_split(link.id, carved)
        return True

    def _align_transaction_link(
        self, link: RefundLink, txn: Any, target: Tagging
    ) -> bool:
        """Align a link covering a whole transaction: retag it or carve it."""
        if Tagging.of(txn.category, txn.tag) == target:
            return False
        ref = TxRef.parse(link.refund_source, txn.unique_id)
        amount = float(link.amount)
        others = self._other_links(link)
        if amount >= float(txn.amount) - _EPS:
            if not others.empty:
                return False
            self.transactions_repo.update_tagging(ref, target.category, target.tag)
            return True
        self.transactions_repo.split_transaction(
            ref,
            [
                {"amount": amount, "category": target.category, "tag": target.tag},
                {
                    "amount": float(txn.amount) - amount,
                    "category": txn.category,
                    "tag": txn.tag,
                },
            ],
        )
        parts = self.split_repo.get_splits_for_transaction(ref.unique_id, ref.table)
        carved, rest = (int(v) for v in parts.sort_values("id")["id"])
        self.repo.set_link_split(link.id, carved)
        for other_id in others["id"]:
            self.repo.set_link_split(int(other_id), rest)
        return True
