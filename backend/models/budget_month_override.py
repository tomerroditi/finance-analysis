"""Budget month override model."""

from sqlalchemy import Column, Integer, String, UniqueConstraint

from backend.models.base import Base, TimestampMixin
from backend.constants.tables import Tables


class BudgetMonthOverride(Base, TimestampMixin):
    """
    Reassigns a transaction/split to a different month for monthly-budget purposes.

    The transaction keeps its real ``date`` everywhere else in the app; this
    record only changes which month the monthly budget view buckets it into.
    A transaction may be moved at most one month away from its real month
    (enforced in the service layer).

    Attributes
    ----------
    source_type : str
        Type of source: 'transaction' or 'split'.
    source_id : int
        ID of the source (unique_id for transactions, id for splits).
    source_table : str
        Table where the source lives (e.g. 'bank_transactions',
        'credit_card_transactions', 'cash_transactions').
    override_year : int
        Calendar year the transaction should be counted in for the budget.
    override_month : int
        Calendar month (1-12) the transaction should be counted in.
    """

    __tablename__ = Tables.BUDGET_MONTH_OVERRIDES.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_type = Column(String, nullable=False)  # 'transaction' or 'split'
    source_id = Column(Integer, nullable=False)
    source_table = Column(String, nullable=False)
    override_year = Column(Integer, nullable=False)
    override_month = Column(Integer, nullable=False)

    # One override per source. A racing upsert could otherwise insert a
    # second row, after which every read of that source raised
    # MultipleResultsFound — a permanent 500 with no way to repair it.
    __table_args__ = (
        UniqueConstraint(
            "source_type", "source_id", "source_table",
            name="uq_budget_month_override_source",
        ),
    )
