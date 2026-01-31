from enum import Enum
from typing import Type

ID = "id"
CATEGORY = "category"
TAGS = "tags"
NAME = "name"
AMOUNT = "amount"
MONTH = "month"
YEAR = "year"
ALL_TAGS = "all_tags"

TOTAL_BUDGET = "Total Budget"

cc_providers = [
    "amex",
    "behatsdaa",
    "beyahad bishvilha",
    "isracard",
    "max",
    "visa cal",
    "test_credit_card",
    "test_credit_card_2fa",
]

bank_providers = [
    "beinleumi",
    "discount",
    "hapoalim",
    "leumi",
    "massad",
    "mercantile",
    "mizrahi",
    "onezero",
    "otsar hahayal",
    "union",
    "yahav",
    "test_bank",
    "test_bank_2fa",
]


class Tables(Enum):
    """
    Enum defining database table names used in the application.

    Attributes
    ----------
    CREDIT_CARD : str
        Name of the table storing credit card transactions.
    BANK : str
        Name of the table storing bank transactions.
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
    MANUAL_INVESTMENT_TRANSACTIONS : str
        Name of the table storing manual inserted investment transactions (for unreachable data).
    """

    CREDIT_CARD = "credit_card_transactions"
    BANK = "bank_transactions"
    CASH = "cash_transactions"
    TAGGING_RULES = "tagging_rules"
    BUDGET_RULES = "budget_rules"
    SPLIT_TRANSACTIONS = "split_transactions"
    SCRAPING_HISTORY = "scraping_history"
    INVESTMENTS = "investments"
    MANUAL_INVESTMENT_TRANSACTIONS = "manual_investment_transactions"
    PENDING_REFUNDS = "pending_refunds"
    REFUND_LINKS = "refund_links"


def create_enum(name: str, fields: list[tuple[str, str]]) -> Type[Enum]:
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


fields = [
    ("UNIQUE_ID", "unique_id"),
    ("ACCOUNT_NUMBER", "account_number"),
    ("TYPE", "type"),
    ("ID", "id"),
    ("DATE", "date"),
    ("DESCRIPTION", "desc"),
    ("AMOUNT", "amount"),
    ("STATUS", "status"),
    ("ACCOUNT_NAME", "account_name"),
    ("PROVIDER", "provider"),
    ("CATEGORY", "category"),
    ("TAG", "tag"),
    ("SOURCE", "source"),
    ("SPLIT_ID", "split_id"),
]

TransactionsTableFields = create_enum("TransactionsTableFields", fields)
CreditCardTableFields = create_enum("CreditCardTableFields", fields)
BankTableFields = create_enum("BankTableFields", fields)
CashTableFields = create_enum("CashTableFields", fields)
ManualInvestmentTransactionsTableFields = create_enum(
    "ManualInvestmentTransactionsTableFields", fields
)

split_fields = [
    ("ID", "id"),
    ("TRANSACTION_ID", "transaction_id"),
    ("AMOUNT", "amount"),
    ("CATEGORY", "category"),
    ("TAG", "tag"),
    ("SOURCE", "source"),
]

SplitTransactionsTableFields = create_enum("SplitTransactionsTableFields", split_fields)


class InvestmentsType(Enum):
    """
    Enum defining types of investments.

    Attributes
    ----------
    BROKERAGE_ACCOUNT : str
        Identifier for brokerage account investments.
    STOCKS : str
        Identifier for stocks investments.
    CRYPTO : str
        Identifier for cryptocurrency investments.
    BONDS : str
        Identifier for bonds investments.
    REAL_ESTATE : str
        Identifier for real estate investments.
    PENSION : str
        Identifier for pension investments.
    STUDY_FUNDS : str
        Identifier for study funds investments (AKA Keren Hishtalmut).
    P2P_LENDING : str
        Identifier for peer-to-peer lending investments.
    PAKAM : str
        Identifier for Pakam investments.
    OTHER : str
        Identifier for other types of investments.
    """

    BROKERAGE_ACCOUNT = "brokerage_account"  # no forecast feature
    STOCKS = "stocks"  # no forecast feature, daily value tracking
    CRYPTO = "crypto"  # no forecast feature, daily value tracking
    BONDS = "bonds"  # real forecast feature
    REAL_ESTATE = "real_estate"  # no forecast feature
    PENSION = "pension"  # estimated forecast feature
    STUDY_FUNDS = "study_funds"  # estimated forecast feature
    P2P_LENDING = "p2p_lending"  # estimate forecast feature
    PAKAM = "pakam"  # estimated forecast feature, daily value tracking
    OTHER = "other"  # no forecast feature

    # notes:
    # tax regulations
    # interest rate
    # commissions (both deposit and gaining for pension and keren hishtalmut)
    # liquidity date


class InterestRateType(Enum):
    """
    Enum defining types of interest rates for investments.

    Attributes
    ----------
    FIXED : str
        Fixed/guaranteed interest rate.
    EXPECTED : str
        Expected/projected interest rate (not guaranteed).
    """

    FIXED = "fixed"
    EXPECTED = "expected"


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


class ScrapingHistoryTableFields(Enum):
    """
    Enum defining field names for the scraping history table.

    Attributes
    ----------
    ID : str
        Field name for the unique identifier.
    SERVICE_NAME : str
        Field name for the service type (banks, credit_cards).
    PROVIDER_NAME : str
        Field name for the provider name (hapoalim, isracard, etc.).
    ACCOUNT_NAME : str
        Field name for the account name.
    DATE : str
        Field name for the last scraping timestamp.
    STATUS : str
        Field name for the last scraping status (success, failed).
    START_DATE : str
        Field name for the date used for scraping.
    """

    ID = "id"
    SERVICE_NAME = "service_name"
    PROVIDER_NAME = "provider_name"
    ACCOUNT_NAME = "account_name"
    DATE = "date"
    STATUS = "status"
    START_DATE = "start_date"


class BudgetRulesTableFields(Enum):
    """
    Enum defining field names for the budget rules table.

    Attributes
    ----------
    ID : str
        Field name for the unique identifier.
    YEAR : str
        Field name for the budget year.
    MONTH : str
        Field name for the budget month.
    CATEGORY : str
        Field name for the budget category.
    TAGS : str
        Field name for the budget tags.
    NAME : str
        Field name for the budget rule name.
    AMOUNT : str
        Field name for the budget amount.
    """

    ID = "id"
    YEAR = "year"
    MONTH = "month"
    CATEGORY = "category"
    TAGS = "tags"
    NAME = "name"
    AMOUNT = "amount"


class TaggingRulesTableFields(Enum):
    """
    Enum defining field names for the tagging rules table.

    Attributes
    ----------
    ID : str
        Field name for the unique identifier.
    NAME : str
        Field name for the rule name.
    PRIORITY : str
        Field name for the rule priority (higher number = higher priority).
    CONDITIONS : str
        Field name for the rule conditions (JSON format).
    CATEGORY : str
        Field name for the category to assign.
    TAG : str
        Field name for the tag to assign.
    SERVICE : str
        Field name for the service type (credit_card, bank).
    ACCOUNT_NUMBER : str
        Field name for the account number (optional, for bank rules).
    IS_ACTIVE : str
        Field name for whether the rule is active.
    CREATED_DATE : str
        Field name for when the rule was created.
    """

    ID = "id"
    NAME = "name"
    PRIORITY = "priority"
    CONDITIONS = "conditions"
    CATEGORY = "category"
    TAG = "tag"
    SERVICE = "service"
    ACCOUNT_NUMBER = "account_number"
    IS_ACTIVE = "is_active"
    CREATED_DATE = "created_date"


class RuleOperators(Enum):
    """
    Enum defining operators for rule conditions.
    """

    CONTAINS = "contains"
    EQUALS = "equals"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    GREATER_THAN = "gt"
    LESS_THAN = "lt"
    GREATER_THAN_EQUAL = "gte"
    LESS_THAN_EQUAL = "lte"
    BETWEEN = "between"


class RuleFields(Enum):
    """
    Enum defining fields that can be used in rule conditions.
    """

    DESCRIPTION = "desc"
    AMOUNT = "amount"
    PROVIDER = "provider"
    ACCOUNT_NAME = "account_name"
    ACCOUNT_NUMBER = "account_number"
    SERVICE = "service"


class Services(Enum):
    """
    Enum defining the types of financial services supported by the application.

    Attributes
    ----------
    CREDIT_CARD : str
        Identifier for credit card services.
    BANK : str
        Identifier for banking services.
    INSURANCE : str
        Identifier for insurance services.
    """

    CREDIT_CARD = "credit_cards"
    BANK = "banks"
    INSURANCE = "insurances"
    CASH = "cash"
    MANUAL_INVESTMENTS = "manual_investments"


class CreditCards(Enum):
    """
    Enum defining supported credit card providers.

    Attributes
    ----------
    MAX : str
        Identifier for MAX credit card.
    VISA_CAL : str
        Identifier for Visa CAL credit card.
    ISRACARD : str
        Identifier for Isracard credit card.
    AMEX : str
        Identifier for American Express credit card.
    BEYAHAD_BISHVILHA : str
        Identifier for Beyahad Bishvilha credit card.
    BEHATSADAA : str
        Identifier for Behatsdaa credit card.
    """

    MAX = "max"
    VISA_CAL = "visa cal"
    ISRACARD = "isracard"
    AMEX = "amex"
    BEYAHAD_BISHVILHA = "beyahad bishvilha"
    BEHATSADAA = "behatsdaa"
    TEST_CREDIT_CARD = "test_credit_card"
    TEST_CREDIT_CARD_2FA = "test_credit_card_2fa"


class Banks(Enum):
    """
    Enum defining supported bank providers.

    Attributes
    ----------
    HAPOALIM : str
        Identifier for Bank Hapoalim.
    LEUMI : str
        Identifier for Bank Leumi.
    DISCOUNT : str
        Identifier for Discount Bank.
    MIZRAHI : str
        Identifier for Mizrahi-Tefahot Bank.
    MERCANTILE : str
        Identifier for Mercantile Bank.
    OTSAR_HAHAYAL : str
        Identifier for Otsar Hahayal Bank.
    UNION : str
        Identifier for Union Bank.
    BEINLEUMI : str
        Identifier for First International Bank (Beinleumi).
    MASSAD : str
        Identifier for Massad Bank.
    YAHAV : str
        Identifier for Bank Yahav.
    ONEZERO : str
        Identifier for One Zero Digital Bank.
    """

    HAPOALIM = "hapoalim"
    LEUMI = "leumi"
    DISCOUNT = "discount"
    MIZRAHI = "mizrahi"
    MERCANTILE = "mercantile"
    OTSAR_HAHAYAL = "otsar hahayal"
    UNION = "union"
    BEINLEUMI = "beinleumi"
    MASSAD = "massad"
    YAHAV = "yahav"
    ONEZERO = "onezero"
    TEST_BANK = "test_bank"
    TEST_BANK_2FA = "test_bank_2fa"


class Insurances(Enum):
    """
    Enum defining supported insurance providers.

    Attributes
    ----------
    MENORA : str
        Identifier for Menora Mivtachim Insurance.
    CLAL : str
        Identifier for Clal Insurance.
    HAREL : str
        Identifier for Harel Insurance.
    HAFENIX : str
        Identifier for Hafenix (Phoenix) Insurance.
    """

    MENORA = "menora"
    CLAL = "clal"
    HAREL = "harel"
    HAFENIX = "hafenix"


class InvestmentCategories(Enum):
    """
    Enum defining categories that are considered savings and investments.
    """

    INVESTMENTS = "Investments"


class IncomeCategories(Enum):
    """
    Enum defining categories that are considered income.
    """

    SALARY = "Salary"
    OTHER_INCOME = "Other Income"


class LiabilitiesCategories(Enum):
    LIABILITIES = "Liabilities"


class NonExpensesCategories(Enum):
    """
    Enum defining categories that are not considered expenses.

    These categories are used to classify transactions that should not be counted
    as expenses in financial analysis.

    Attributes
    ----------
    IGNORE : str
        Transactions to be ignored in analysis.
    SALARY : str
        Income from employment.
    INVESTMENTS : str
        Money allocated to investments.
    OTHER_INCOME : str
        Income from sources other than salary.
    LIABILITIES : str
        Payments related to liabilities.
    """

    IGNORE = "Ignore"
    INVESTMENTS = InvestmentCategories.INVESTMENTS.value
    SALARY = IncomeCategories.SALARY.value
    OTHER_INCOME = IncomeCategories.OTHER_INCOME.value
    LIABILITIES = LiabilitiesCategories.LIABILITIES.value


class Fields(Enum):
    """
    Enum defining field names used for credential information.

    These fields represent different types of credential information required
    by various financial service providers.

    Attributes
    ----------
    ID : str
        Field name for ID number.
    CARD_6_DIGITS : str
        Field name for the first 6 digits of a credit card.
    PASSWORD : str
        Field name for password.
    USERNAME : str
        Field name for username.
    USER_CODE : str
        Field name for user code.
    NUM : str
        Field name for a numeric identifier.
    NATIONAL_ID : str
        Field name for national ID number.
    EMAIL : str
        Field name for email address.
    PHONE_NUMBER : str
        Field name for phone number.
    """

    ID = "id"
    CARD_6_DIGITS = "card6Digits"
    PASSWORD = "password"
    USERNAME = "username"
    USER_CODE = "userCode"
    NUM = "num"
    NATIONAL_ID = "nationalID"
    EMAIL = "email"
    PHONE_NUMBER = "phoneNumber"


class LoginFields:
    """
    Class defining the required login fields for different financial service providers.

    This class maintains a mapping of providers to their required login fields,
    and provides a method to retrieve the fields for a specific provider.

    Attributes
    ----------
    providers_fields : dict
        Dictionary mapping provider names to lists of required field names.
    """

    providers_fields = {
        # cards
        "max": ["username", "password"],
        "visa cal": ["username", "password"],
        "isracard": ["id", "card6Digits", "password"],
        "amex": ["id", "card6Digits", "password"],
        "beyahad bishvilha": ["id", "password"],
        "behatsdaa": ["id", "password"],
        # banks
        "hapoalim": ["userCode", "password"],
        "leumi": ["username", "password"],
        "mizrahi": ["username", "password"],
        "discount": ["id", "password", "num"],
        "mercantile": ["id", "password", "num"],
        "otsar hahayal": ["username", "password"],
        "union": ["username", "password"],
        "beinleumi": ["username", "password"],
        "massad": ["username", "password"],
        "yahav": ["username", "nationalID", "password"],
        "onezero": ["email", "password", "phoneNumber"],
        "dummy_tfa": ["email", "password", "phoneNumber"],
        "dummy_tfa_no_otp": ["email", "password", "phoneNumber"],
        "dummy_regular": ["username", "password"],
        # insurances
        "menora": ["username", "password"],
        "clal": ["username", "password"],
        "harel": ["username", "password"],
        "hafenix": ["username", "password"],
        # Test Providers
        "test_bank": ["username", "password"],
        "test_bank_2fa": ["email", "password", "phoneNumber"],
        "test_credit_card": ["username", "password"],
        "test_credit_card_2fa": ["email", "password", "phoneNumber"],
    }

    @staticmethod
    def get_fields(provider: str) -> list[str]:
        """
        Get the required login fields for a specific provider.

        Parameters
        ----------
        provider : str
            The name of the provider (e.g., 'max', 'hapoalim').

        Returns
        -------
        list[str]
            List of field names required for login to the specified provider.
        """
        return LoginFields.providers_fields[provider]


class DisplayFields:
    """
    Class defining display names for credential fields.

    This class maintains a mapping of internal field names to user-friendly display names,
    and provides a method to retrieve the display name for a specific field.

    Attributes
    ----------
    field_display : dict
        Dictionary mapping internal field names to user-friendly display names.
    """

    field_display = {
        "id": "ID Number",
        "card6Digits": "Card 6 Digits",
        "password": "Password",
        "username": "Username",
        "userCode": "User Code",
        "num": "Num",
        "nationalID": "National ID",
        "email": "Email",
        "phoneNumber": "Phone Number",
    }

    @staticmethod
    def get_display(field: str) -> str:
        """
        Get the user-friendly display name for a specific field.

        If the field is not found in the mapping, returns the original field name.

        Parameters
        ----------
        field : str
            The internal field name.

        Returns
        -------
        str
            The user-friendly display name for the field, or the original field name
            if no mapping exists.
        """
        try:
            return DisplayFields.field_display[field]
        except KeyError:
            return field
