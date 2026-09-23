"""Database table names and column-name enums."""

from enum import Enum

from backend.constants.providers import Services


class Tables(Enum):
    """Enum defining database table names used in the application.

    Attributes
    ----------
    CREDIT_CARD : str
        Name of the table storing credit card transactions.
    BANK : str
        Name of the table storing bank transactions.
    CASH : str
        Name of the table storing cash transactions.
    TAGGING_RULES : str
        Name of the table storing rule-based tagging rules.
    BUDGET_RULES : str
        Name of the table storing budget rules.
    SPLIT_TRANSACTIONS : str
        Name of the table storing split transactions.
    SCRAPING_HISTORY : str
        Name of the table storing scraping history (the next scrape window's
        watermark).
    INVESTMENTS : str
        Name of the table storing investment tracking data.
    INVESTMENT_BALANCE_SNAPSHOTS : str
        Name of the table storing investment balance snapshots over time.
    MANUAL_INVESTMENT_TRANSACTIONS : str
        Name of the table storing manual inserted investment transactions (for unreachable data).
    PENDING_REFUNDS : str
        Name of the table storing pending refunds.
    REFUND_LINKS : str
        Name of the table storing refund links.
    REFUND_SOURCE_NOTES : str
        Name of the table storing user notes on refund source transactions.
    BUDGET_MONTH_OVERRIDES : str
        Name of the table storing per-transaction monthly-budget month overrides.
    BANK_BALANCES : str
        Name of the table storing bank account balance snapshots.
    CASH_BALANCES : str
        Name of the table storing cash balance snapshots and prior wealth.
    CATEGORIES : str
        Name of the table storing categories, tags, and icons.
    CREDENTIALS : str
        Name of the table storing provider account credentials.
    LIABILITY_TRANSACTIONS : str
        Name of the table storing auto-generated liability payment transactions.
    SAVINGS_GOAL_ALLOCATIONS : str
        Name of the table storing per-month surplus allocations to savings goals.
    SAVINGS_GOAL_LINKS : str
        Name of the table storing transaction-to-savings-goal links.
    SAVINGS_GOAL_INVESTMENTS : str
        Name of the table storing investment-to-savings-goal earmarks.
    RECURRING_DECISIONS : str
        Name of the table storing user verdicts on detected recurring charges.
    INSIGHT_DISMISSALS : str
        Name of the table storing insight cards the user has dismissed.
    """

    CREDIT_CARD = "credit_card_transactions"
    BANK = "bank_transactions"
    CASH = "cash_transactions"
    TAGGING_RULES = "tagging_rules"
    BUDGET_RULES = "budget_rules"
    SPLIT_TRANSACTIONS = "split_transactions"
    SCRAPING_HISTORY = "scraping_history"
    INVESTMENTS = "investments"
    INVESTMENT_BALANCE_SNAPSHOTS = "investment_balance_snapshots"
    MANUAL_INVESTMENT_TRANSACTIONS = "manual_investment_transactions"
    PENDING_REFUNDS = "pending_refunds"
    REFUND_LINKS = "refund_links"
    REFUND_SOURCE_NOTES = "refund_source_notes"
    BUDGET_MONTH_OVERRIDES = "budget_month_overrides"
    BANK_BALANCES = "bank_balances"
    CASH_BALANCES = "cash_balances"
    CATEGORIES = "categories"
    CREDENTIALS = "credentials"
    INSURANCE = "insurance_transactions"
    INSURANCE_ACCOUNTS = "insurance_accounts"
    LIABILITIES = "liabilities"
    LIABILITY_TRANSACTIONS = "liability_transactions"
    INTEREST_RATES = "interest_rates"
    RETIREMENT_GOAL = "retirement_goals"
    SAVINGS_GOALS = "savings_goals"
    SAVINGS_GOAL_ALLOCATIONS = "savings_goal_allocations"
    SAVINGS_GOAL_LINKS = "savings_goal_links"
    SAVINGS_GOAL_INVESTMENTS = "savings_goal_investments"
    RECURRING_DECISIONS = "recurring_decisions"
    INSIGHT_DISMISSALS = "insight_dismissals"


# The five transaction tables, keyed by the service name the frontend and API
# use for them. This is the one source of truth for the service <-> table
# pairing; every other mapping in the backend is derived from it.
SERVICE_TO_TABLE: dict[str, str] = {
    Services.CREDIT_CARD.value: Tables.CREDIT_CARD.value,
    Services.BANK.value: Tables.BANK.value,
    Services.CASH.value: Tables.CASH.value,
    Services.MANUAL_INVESTMENTS.value: Tables.MANUAL_INVESTMENT_TRANSACTIONS.value,
    Services.INSURANCE.value: Tables.INSURANCE.value,
}

TABLE_TO_SERVICE: dict[str, str] = {
    table: service for service, table in SERVICE_TO_TABLE.items()
}

# Every spelling that identifies a transaction table: the table names plus the
# service names that older rows (refunds, overrides) and clients still send.
TRANSACTION_SOURCES: frozenset[str] = frozenset(SERVICE_TO_TABLE) | frozenset(
    TABLE_TO_SERVICE
)


def canonical_table(source: str) -> str:
    """Normalize a transaction source to its table name.

    Parameters
    ----------
    source : str
        Table name (``"bank_transactions"``) or legacy service name
        (``"banks"``).

    Returns
    -------
    str
        The table name when ``source`` is a known spelling, ``source``
        unchanged otherwise.
    """
    return SERVICE_TO_TABLE.get(source, source)


def table_aliases(table: str) -> list[str]:
    """Return every stored spelling of a transaction table.

    Parameters
    ----------
    table : str
        Canonical table name.

    Returns
    -------
    list[str]
        ``[table]`` followed by its legacy service name, when it has one.
    """
    service = TABLE_TO_SERVICE.get(table)
    return [table, service] if service else [table]


def _create_enum(name: str, fields: list[tuple[str, str]]) -> type[Enum]:
    """Create an Enum class dynamically with the given name and fields.

    Parameters
    ----------
    name : str
        The name to give to the created Enum class.
    fields : list[tuple[str, str]]
        List of tuples where each tuple contains (enum_member_name, enum_member_value).

    Returns
    -------
    type[Enum]
        A new Enum class with the specified name and fields.
    """
    return Enum(name, fields)


_transaction_fields = [
    ("UNIQUE_ID", "unique_id"),
    ("ACCOUNT_NUMBER", "account_number"),
    ("TYPE", "type"),
    ("ID", "id"),
    ("DATE", "date"),
    ("DESCRIPTION", "description"),
    ("AMOUNT", "amount"),
    ("STATUS", "status"),
    ("ACCOUNT_NAME", "account_name"),
    ("PROVIDER", "provider"),
    ("CATEGORY", "category"),
    ("TAG", "tag"),
    ("SOURCE", "source"),
    ("SPLIT_ID", "split_id"),
]

TransactionsTableFields = _create_enum("TransactionsTableFields", _transaction_fields)
CreditCardTableFields = _create_enum("CreditCardTableFields", _transaction_fields)
BankTableFields = _create_enum("BankTableFields", _transaction_fields)

_split_fields = [
    ("ID", "id"),
    ("TRANSACTION_ID", "transaction_id"),
    ("AMOUNT", "amount"),
    ("CATEGORY", "category"),
    ("TAG", "tag"),
    ("SOURCE", "source"),
]

SplitTransactionsTableFields = _create_enum(
    "SplitTransactionsTableFields", _split_fields
)


class InvestmentsTableFields(Enum):
    """Enum defining field names for the investments tracking table.

    Attributes
    ----------
    ID : str
        Field name for the unique identifier.
    CATEGORY : str
        Field name for the investment category.
    TAG : str
        Field name for the investment tag.
    TYPE : str
        Field name for the investment type (e.g., stocks, bonds).
    NAME : str
        Field name for the investment name.
    IS_CLOSED : str
        Field name for whether the investment is closed.
    CREATED_DATE : str
        Field name for when the investment tracking was created.
    CLOSED_DATE : str
        Field name for when the investment was closed.
    NOTES : str
        Field name for additional notes.
    """

    ID = "id"
    CATEGORY = "category"
    TAG = "tag"
    TYPE = "type"
    NAME = "name"
    IS_CLOSED = "is_closed"
    CREATED_DATE = "created_date"
    CLOSED_DATE = "closed_date"
    NOTES = "notes"
    INSURANCE_POLICY_ID = "insurance_policy_id"


class InvestmentBalanceSnapshotsTableFields(Enum):
    """Field names for the investment_balance_snapshots table."""

    ID = "id"
    INVESTMENT_ID = "investment_id"
    DATE = "date"
    BALANCE = "balance"
    SOURCE = "source"


class LiabilitiesTableFields(Enum):
    """Field names for the liabilities table."""

    ID = "id"
    NAME = "name"
    LENDER = "lender"
    CATEGORY = "category"
    TAG = "tag"
    PRINCIPAL_AMOUNT = "principal_amount"
    INTEREST_RATE = "interest_rate"
    LOAN_TYPE = "loan_type"
    AMORTIZATION_METHOD = "amortization_method"
    RATE_SPREAD = "rate_spread"
    RATE_RESET_MONTHS = "rate_reset_months"
    TERM_MONTHS = "term_months"
    START_DATE = "start_date"
    IS_PAID_OFF = "is_paid_off"
    PAID_OFF_DATE = "paid_off_date"
    NOTES = "notes"
    CREATED_DATE = "created_date"


class LiabilityTransactionsTableFields(Enum):
    """Field names for the liability_transactions table."""

    ID = "id"
    LIABILITY_ID = "liability_id"
    DATE = "date"
    AMOUNT = "amount"
    PAYMENT_NUMBER = "payment_number"
    DESCRIPTION = "description"


class InterestRatesTableFields(Enum):
    """Field names for the interest_rates table."""

    ID = "id"
    SERIES = "series"
    DATE = "date"
    VALUE = "value"
    SOURCE = "source"
