"""
Tagging rule model.
"""

from sqlalchemy import Column, Integer, String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, TimestampMixin
from backend.naming_conventions import Tables


class TaggingRule(Base, TimestampMixin):
    """
    Model for automated tagging rules.
    """

    __tablename__ = Tables.TAGGING_RULES.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    priority = Column(Integer, default=1)
    conditions = Column(Text, nullable=False)  # JSON string
    category = Column(String, nullable=False)
    tag = Column(String, nullable=False)
    is_active = Column(Integer, default=1)  # 0 or 1
    created_date = Column(
        Text, nullable=True
    )  # Historical string date, kept for migration logic
