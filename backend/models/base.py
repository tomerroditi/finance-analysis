"""
Base model configuration and common mixins.
"""

from sqlalchemy import Column, DateTime, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class TimestampMixin:
    """Mixin that adds audit timestamp columns to any SQLAlchemy ORM model.

    Attributes
    ----------
    created_at : DateTime
        Timestamp set automatically when the row is first inserted.
    updated_at : DateTime
        Timestamp set on insert and updated automatically on every subsequent write.
    """

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )
