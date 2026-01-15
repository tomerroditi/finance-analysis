"""
Base model configuration and common mixins.
"""
from datetime import datetime
from sqlalchemy import Column, DateTime, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class TimestampMixin:
    """
    Mixin to add created_at and updated_at columns to a model.
    """
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
