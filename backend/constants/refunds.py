"""How a breakdown treats refunds the user linked to a purchase in the app.

Only links made in the app (``refund_links``) and expectations marked on a
purchase (``pending_refunds``) are ever acted on. A positive row in an expense
category that no link names is money back in the month it arrived, whatever
the mode.
"""

from enum import StrEnum


class RefundMode(StrEnum):
    """The Income & Expenses card's refund setting.

    Attributes
    ----------
    NONE : str
        No refund handling: a linked refund and its purchase each count in
        their own month, and a purchase awaiting a refund counts in full.
    LINKED : str
        A linked refund cancels its purchase wherever the two fell.
    PENDING : str
        As ``LINKED``, and a purchase still awaiting its refund is taken off
        by what is still expected back.
    """

    NONE = "none"
    LINKED = "linked"
    PENDING = "pending"

    @property
    def nets_links(self) -> bool:
        """Whether linked refunds are netted against their purchases."""
        return self is not RefundMode.NONE

    @property
    def excludes_pending(self) -> bool:
        """Whether a purchase awaiting its refund is taken off what it cost."""
        return self is RefundMode.PENDING
