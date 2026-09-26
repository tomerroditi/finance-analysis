"""Tagging rules model."""

from sqlalchemy import JSON, Column, Integer, String

from backend.constants.tables import Tables
from backend.models.base import Base, TimestampMixin


class TaggingRule(Base, TimestampMixin):
    """ORM model for an automated tagging rule with recursive conditions.

    Rules run in creation order (``id`` ascending) and the first match wins;
    there is no priority column.

    Attributes
    ----------
    name : str
        Human-readable rule name.
    conditions : dict
        JSON condition tree. Branch nodes combine children with ``AND`` /
        ``OR``; leaf nodes (``type == "CONDITION"``) compare a transaction
        ``field`` against ``value`` with an ``operator`` (``contains``,
        ``equals``, ``starts_with``, ``ends_with``, ``gt``, ``lt``, ``gte``,
        ``lte``, ``between``). The ``service`` pseudo-field restricts which
        transaction tables the rule scans.
    category : str
        Category assigned to matching transactions.
    tag : str
        Tag assigned to matching transactions.

    Examples
    --------
    A ``conditions`` value matching supermarket charges over ₪50::

        {
            "type": "AND",
            "subconditions": [
                {"type": "CONDITION", "field": "description",
                 "operator": "contains", "value": "SUPER"},
                {"type": "OR", "subconditions": [...]},
                {"type": "CONDITION", "field": "amount",
                 "operator": "lt", "value": -50},
            ],
        }
    """

    __tablename__ = Tables.TAGGING_RULES.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    conditions = Column(JSON, nullable=False)
    category = Column(String, nullable=False)
    tag = Column(String, nullable=False)
