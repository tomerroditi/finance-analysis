"""
Liability tracking model.
"""

from sqlalchemy import Column, Integer, String, Float, Text, UniqueConstraint

from backend.models.base import Base
from backend.constants.tables import Tables


class Liability(Base):
    """ORM model for a tracked liability (loan/debt).

    Each liability is identified by its ``category`` + ``tag`` pair, which
    corresponds to the category/tag used on existing transactions tagged
    under the Liabilities category.

    Attributes
    ----------
    name : str
        Human-readable name of the liability.
    lender : str, optional
        Name of the lending institution.
    category : str
        Always "Liabilities".
    tag : str
        Tag identifying this specific liability.
    principal_amount : float
        Original loan amount.
    interest_rate : float
        Annual interest rate as percentage (e.g. 4.5 for 4.5%).
    term_months : int
        Loan duration in months.
    start_date : str
        Date the loan was taken (YYYY-MM-DD).
    is_paid_off : int
        1 if the liability has been paid off, 0 otherwise.
    paid_off_date : str, optional
        Date the liability was paid off (YYYY-MM-DD).
    notes : str, optional
        Free-text notes.
    created_date : str
        Date the record was created (YYYY-MM-DD).
    """

    __tablename__ = Tables.LIABILITIES.value
    __table_args__ = (
        UniqueConstraint("category", "tag", name="uq_liability_category_tag"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    lender = Column(String, nullable=True)
    category = Column(String, nullable=False)
    tag = Column(String, nullable=False)

    principal_amount = Column(Float, nullable=False)
    interest_rate = Column(Float, nullable=False)
    term_months = Column(Integer, nullable=False)

    start_date = Column(String, nullable=False)
    is_paid_off = Column(Integer, default=0)
    paid_off_date = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_date = Column(String, nullable=False)
