from enum import Enum
from typing import Type


class Tables(Enum):
    """
    Enum defining database table names used in the application.

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
        Name of the table storing scraping history and daily limits.
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
    BANK_BALANCES : str
        Name of the table storing bank account balance snapshots.
    CASH_BALANCES : str
        Name of the table storing cash balance snapshots and prior wealth.
    CATEGORIES : str
        Name of the table storing categories, tags, and icons.
    CREDENTIALS : str
        Name of the table storing provider account credentials.
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
    BANK_BALANCES = "bank_balances"
    CASH_BALANCES = "cash_balances"
    CATEGORIES = "categories"
    CREDENTIALS = "credentials"
    INSURANCE = "insurance_transactions"
    INSURANCE_ACCOUNTS = "insurance_accounts"


def _create_enum(name: str, fields: list[tuple[str, str]]) -> Type[Enum]:
    """
    Create an Enum class dynamically with the given name and fields.

    Parameters
    ----------
    name : str
        The name to give to the created Enum class.
    fields : list[tuple[str, str]]
        List of tuples where each tuple contains (enum_member_name, enum_member_value).

    Returns
    -------
    Type[Enum]
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
    """
    Enum defining field names for the investments tracking table.

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


class InvestmentBalanceSnapshotsTableFields(Enum):
    """Field names for the investment_balance_snapshots table."""

    ID = "id"
    INVESTMENT_ID = "investment_id"
    DATE = "date"
    BALANCE = "balance"
    SOURCE = "source"
