"""Category model for storing categories, tags, and icons."""

from sqlalchemy import Column, Integer, JSON, String

from backend.constants.tables import Tables
from backend.models.base import Base, TimestampMixin


class Category(Base, TimestampMixin):
    """Model for category with embedded tags list and optional icon."""

    __tablename__ = Tables.CATEGORIES.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    tags = Column(JSON, nullable=False, default=list)
    icon = Column(String, nullable=True)
