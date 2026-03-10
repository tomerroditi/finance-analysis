"""Credential model for storing provider account credentials."""

from sqlalchemy import Column, Integer, JSON, String, UniqueConstraint

from backend.constants.tables import Tables
from backend.models.base import Base, TimestampMixin


class Credential(Base, TimestampMixin):
    """Model for provider credentials with non-sensitive fields as JSON."""

    __tablename__ = Tables.CREDENTIALS.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    service = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    account_name = Column(String, nullable=False)
    fields = Column(JSON, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("service", "provider", "account_name", name="uq_credential"),
    )
