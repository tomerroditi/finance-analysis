"""
Transaction identity: which table a transaction lives in, and its id there.

``unique_id`` is a per-table auto-increment, so a transaction is only
identified by the pair. Clients and older stored rows spell the table either
way — ``"bank_transactions"`` or the service name ``"banks"`` — and every
method that took a bare ``(source, unique_id)`` used to resolve that spelling
on its own, failing in its own way when it could not. ``TxRef.parse`` resolves
it once, at the edge: past it, the table is always canonical and the id always
an ``int``, and the only failure mode is a ``ValidationException``.
"""

from dataclasses import dataclass

from backend.constants.tables import SERVICE_TO_TABLE, TABLE_TO_SERVICE
from backend.errors import ValidationException


def transaction_table(source: object) -> str:
    """Resolve any spelling of a transaction table to its canonical table name.

    Parameters
    ----------
    source : object
        Table name (``"bank_transactions"``) or service name (``"banks"``).

    Returns
    -------
    str
        The table name.

    Raises
    ------
    ValidationException
        If ``source`` names no transaction table.
    """
    if isinstance(source, str):
        if source in TABLE_TO_SERVICE:
            return source
        if source in SERVICE_TO_TABLE:
            return SERVICE_TO_TABLE[source]
    raise ValidationException(
        f"Invalid source: '{source}'. Valid sources: "
        + ", ".join(sorted([*SERVICE_TO_TABLE, *TABLE_TO_SERVICE]))
    )


@dataclass(frozen=True)
class TxRef:
    """A transaction's identity: its canonical table and its id in that table.

    Attributes
    ----------
    table : str
        Canonical table name, e.g. ``"bank_transactions"``.
    unique_id : int
        The transaction's ``unique_id`` within ``table``.
    """

    table: str
    unique_id: int

    @classmethod
    def parse(cls, source: object, unique_id: object) -> "TxRef":
        """Build a reference from a client- or row-supplied source and id.

        Parameters
        ----------
        source : object
            Any spelling of the transaction table.
        unique_id : object
            The id, as an ``int`` or an integer string (route path segments).

        Returns
        -------
        TxRef
            The canonical reference.

        Raises
        ------
        ValidationException
            If ``source`` names no transaction table or ``unique_id`` is not
            an integer.
        """
        table = transaction_table(source)
        if isinstance(unique_id, bool) or (
            isinstance(unique_id, float) and not unique_id.is_integer()
        ):
            raise ValidationException(f"Invalid transaction id: {unique_id!r}")
        try:
            uid = int(unique_id)  # type: ignore[call-overload]
        except (TypeError, ValueError):
            raise ValidationException(
                f"Invalid transaction id: {unique_id!r}"
            ) from None
        return cls(table, uid)
