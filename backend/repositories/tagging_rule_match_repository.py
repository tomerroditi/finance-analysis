"""SQL evaluation of tagging-rule condition trees against transaction tables.

A rule's conditions are a recursive tree of ``AND``/``OR`` groups and
``CONDITION`` leaves (see ``TaggingRulesService``). This module compiles such
a tree into a SQLAlchemy filter for one transaction model and runs the
queries the service needs: which rows match, which of them a write would
change, and the write itself. Validation, precedence between rules and table
selection stay in the service.
"""

from typing import Any

import pandas as pd
from sqlalchemy import ColumnElement, and_, func, or_, select, update
from sqlalchemy.orm import InstrumentedAttribute, Session

from backend.constants.tables import Tables
from backend.models.transaction import (
    BankTransaction,
    CreditCardTransaction,
    TransactionBase,
)
from backend.repositories._sql import chunked

# Tables a tagging rule can run against.
RULE_TABLE_MODELS: dict[str, type[TransactionBase]] = {
    Tables.CREDIT_CARD.value: CreditCardTransaction,
    Tables.BANK.value: BankTransaction,
}

# Rule-matching ``IN (...)`` lists: kept under SQLite's 999-parameter cap with
# room for the condition tree's own bound values.
RULE_IN_CHUNK = 900


def escape_like(value: Any) -> str:
    r"""Escape SQL ``LIKE`` metacharacters in a user-supplied search value.

    ``%`` and ``_`` are wildcards inside a ``LIKE`` pattern, so a rule
    searching for a literal ``"50%"`` would otherwise match ``"5000"`` too.
    Callers must pass ``escape="\\"`` to the ``like()`` call.

    Parameters
    ----------
    value : Any
        Raw condition value; coerced to ``str``.

    Returns
    -------
    str
        The value with ``\``, ``%``, and ``_`` backslash-escaped.
    """
    return str(value).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def model_column(
    field: str | None, model: type[TransactionBase]
) -> InstrumentedAttribute[Any] | None:
    """Map a condition field name to the corresponding SQLAlchemy model column.

    Parameters
    ----------
    field : str
        Condition field name (e.g. ``"description"``, ``"amount"``).
    model : type[TransactionBase]
        SQLAlchemy model class.

    Returns
    -------
    InstrumentedAttribute or None
        The model column, or ``None`` for the ``"service"`` field (which
        is handled at the table-selection level) and unknown fields.
    """
    field_mapping = {
        "description": model.description,
        "amount": model.amount,
        "provider": model.provider,
        "account_name": model.account_name,
        "service": None,  # Handled by table selection
    }
    return field_mapping.get(field)


def build_single_filter(
    condition: dict[str, Any], model: type[TransactionBase]
) -> ColumnElement[bool] | bool:
    """Build a single SQLAlchemy filter expression from a leaf condition dict.

    Parameters
    ----------
    condition : dict
        Leaf condition with ``field``, ``operator``, and ``value`` keys.
    model : type[TransactionBase]
        SQLAlchemy model class to build the filter against.

    Returns
    -------
    ColumnElement[bool] or bool
        Filter clause. ``True`` for the ``service`` pseudo-field (handled
        by table selection); ``False`` for an unknown field or operator
        so a malformed rule matches nothing rather than everything.
    """
    field = condition.get("field")
    operator = condition.get("operator")
    value = condition.get("value")

    if field == "service":
        # Restriction handled at the table-selection level, not here.
        return True

    column = model_column(field, model)
    if column is None:
        # An unrecognised field is a broken rule. Matching nothing keeps it
        # inert; returning True would silently re-tag every transaction.
        return False

    if operator == "contains":
        return column.like(f"%{escape_like(value)}%", escape="\\")
    if operator == "equals":
        return column == value
    if operator == "starts_with":
        return column.like(f"{escape_like(value)}%", escape="\\")
    if operator == "ends_with":
        return column.like(f"%{escape_like(value)}", escape="\\")
    if operator == "gt":
        return column > float(value)
    if operator == "lt":
        return column < float(value)
    if operator == "gte":
        return column >= float(value)
    if operator == "lte":
        return column <= float(value)
    if operator == "between":
        return column.between(float(value[0]), float(value[1]))

    return False


def build_filter(
    condition_node: dict[str, Any], model: type[TransactionBase]
) -> ColumnElement[bool] | bool:
    """Build a SQLAlchemy filter expression from a condition tree, recursively.

    Fails closed: an empty group or an unknown node type matches nothing.
    ``TaggingRulesService.validate_rule_integrity`` rejects both before a rule
    is stored, so reaching them here means the stored rule is malformed —
    matching every transaction would be the worst possible interpretation.

    Parameters
    ----------
    condition_node : dict
        Group or leaf node of the condition tree.
    model : type[TransactionBase]
        Transaction model to build the filter against.

    Returns
    -------
    ColumnElement[bool] or bool
        Filter clause, or ``False`` for a malformed node.
    """
    c_type = condition_node.get("type")

    if c_type in ("AND", "OR"):
        subconditions = condition_node.get("subconditions", [])
        if not subconditions:
            return False

        clauses = [build_filter(sub, model) for sub in subconditions]
        return and_(*clauses) if c_type == "AND" else or_(*clauses)

    if c_type == "CONDITION":
        return build_single_filter(condition_node, model)

    return False


class TaggingRuleMatchRepository:
    """Runs tagging-rule condition trees against the rule-taggable tables.

    Every method takes a table name from ``RULE_TABLE_MODELS`` and a
    normalized condition tree.

    Parameters
    ----------
    db : Session
        SQLAlchemy database session.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def preview(
        self, table: str, conditions: dict[str, Any], limit: int | None = None
    ) -> pd.DataFrame:
        """Return the key fields of the rows matching a condition tree.

        Parameters
        ----------
        table : str
            Table to query.
        conditions : dict
            Normalized condition tree.
        limit : int or None, optional
            Maximum number of rows; ``None`` returns all.

        Returns
        -------
        pd.DataFrame
            Columns ``id``, ``unique_id``, ``date``, ``description``,
            ``amount``, ``category``, ``tag``, ``account_name``,
            ``provider``.
        """
        model = RULE_TABLE_MODELS[table]
        stmt = select(
            model.id,
            model.unique_id,
            model.date,
            model.description,
            model.amount,
            model.category,
            model.tag,
            model.account_name,
            model.provider,
        ).where(build_filter(conditions, model))
        if limit is not None:
            stmt = stmt.limit(limit)
        return pd.read_sql(stmt, self.db.bind)

    def match_ids(self, table: str, conditions: dict[str, Any]) -> list[int]:
        """Return the ``unique_id`` of every row matching a condition tree.

        Parameters
        ----------
        table : str
            Table to query.
        conditions : dict
            Normalized condition tree.

        Returns
        -------
        list[int]
            Matching ``unique_id`` values.
        """
        model = RULE_TABLE_MODELS[table]
        stmt = select(model.unique_id).where(build_filter(conditions, model))
        return pd.read_sql(stmt, self.db.bind)["unique_id"].tolist()

    def match_writable_ids(
        self,
        table: str,
        conditions: dict[str, Any],
        category: str,
        tag: str,
        overwrite: bool = False,
        previous: tuple[str, str] | None = None,
    ) -> list[int]:
        """Return the matching rows a rule assigning ``(category, tag)`` may write.

        Parameters
        ----------
        table : str
            Table to query.
        conditions : dict
            Normalized condition tree.
        category : str
            Category the rule assigns.
        tag : str
            Tag the rule assigns.
        overwrite : bool, optional
            When ``True``, every matching row not already carrying
            ``(category, tag)`` qualifies.
        previous : (str, str), optional
            Used when ``overwrite`` is ``False``: untagged rows qualify, and
            so do rows still carrying this former ``(category, tag)``.

        Returns
        -------
        list[int]
            ``unique_id`` values; with neither option only untagged rows
            (``category IS NULL``) qualify.
        """
        model = RULE_TABLE_MODELS[table]
        if overwrite:
            writable = or_(
                model.category.is_(None),
                model.category.isnot(category),
                model.tag.isnot(tag),
            )
        elif previous is not None:
            writable = or_(
                model.category.is_(None),
                and_(model.category == previous[0], model.tag == previous[1]),
            )
        else:
            writable = model.category.is_(None)

        stmt = select(model.unique_id).where(
            and_(build_filter(conditions, model), writable)
        )
        return pd.read_sql(stmt, self.db.bind)["unique_id"].tolist()

    def any_match_among(
        self, table: str, conditions: dict[str, Any], unique_ids: list[int]
    ) -> bool:
        """Report whether any of the given rows matches a condition tree.

        Parameters
        ----------
        table : str
            Table to query.
        conditions : dict
            Normalized condition tree.
        unique_ids : list[int]
            Rows to test, queried in ``IN`` chunks of ``RULE_IN_CHUNK``.

        Returns
        -------
        bool
            ``True`` as soon as one chunk holds a matching row.
        """
        model = RULE_TABLE_MODELS[table]
        condition_filter = build_filter(conditions, model)
        for chunk in chunked(unique_ids, RULE_IN_CHUNK):
            stmt = (
                select(func.count())
                .select_from(model)
                .where(and_(model.unique_id.in_(chunk), condition_filter))
            )
            if self.db.execute(stmt).scalar() > 0:
                return True
        return False

    def assign(
        self, table: str, unique_ids: list[int], category: str, tag: str
    ) -> None:
        """Set ``(category, tag)`` on the given rows in one commit.

        Parameters
        ----------
        table : str
            Table to write.
        unique_ids : list[int]
            Rows to update, written in ``IN`` chunks of ``RULE_IN_CHUNK``.
        category : str
            Category to assign.
        tag : str
            Tag to assign.
        """
        model = RULE_TABLE_MODELS[table]
        for chunk in chunked(unique_ids, RULE_IN_CHUNK):
            self.db.execute(
                update(model)
                .where(model.unique_id.in_(chunk))
                .values(category=category, tag=tag)
            )
        self.db.commit()
