"""
Tagging rules model.
"""

from sqlalchemy import JSON, Column, Integer, String

from backend.models.base import Base, TimestampMixin
from backend.constants.tables import Tables


class TaggingRule(Base, TimestampMixin):
    """
    Model for automated tagging rules with recursive conditions.
    """

    __tablename__ = Tables.TAGGING_RULES.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    # Conditions stored as JSON.
    # Structure:
    # {
    #   "type": "AND" | "OR",
    #   "subconditions": [
    #       { "type": "AND" | "OR", "subconditions": [...] },
    #       { "type": "CONDITION", "field": "...", "operator": "...", "value": "..." }
    #   ]
    # }
    conditions = Column(JSON, nullable=False)
    category = Column(String, nullable=False)
    tag = Column(String, nullable=False)
