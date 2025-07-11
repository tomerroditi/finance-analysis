from enum import Enum
from typing import Type

ID = 'id'
CATEGORY = 'category'
TAGS = 'tags'
NAME = 'name'
AMOUNT = 'amount'
MONTH = 'month'
YEAR = 'year'
ALL_TAGS = 'all_tags'

TOTAL_BUDGET = 'Total Budget'

cc_providers = [
    'amex',
    'behatsdaa',
    'beyahad bishvilha',
    'isracard',
    'max',
    'visa_cal',
]

bank_providers = [
    'beinleumi',
    'discount',
    'hapoalim',
    'leumi',
    'massad',
    'mercantile',
    'mizrahi',
    'onezero',
    'otsar_hahayal',
    'union',
    'yahav',
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
    AUTO_TAGGER : str
        Name of the table storing automatic tagging rules.
    BUDGET_RULES : str
        Name of the table storing budget rules.
    SPLIT_TRANSACTIONS : str
        Name of the table storing split transactions.
    """
    CREDIT_CARD = 'credit_card_transactions'
    BANK = 'bank_transactions'
    AUTO_TAGGER = 'automatic_tagger'
    BUDGET_RULES = 'budget_rules'
    SPLIT_TRANSACTIONS = 'split_transactions'


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
    ('ACCOUNT_NUMBER', 'account_number'),
    ('TYPE', 'type'),
    ('ID', 'id'),
    ('DATE', 'date'),
    ('DESCRIPTION', 'desc'),
    ('AMOUNT', 'amount'),
    ('STATUS', 'status'),
    ('ACCOUNT_NAME', 'account_name'),
    ('PROVIDER', 'provider'),
    ('CATEGORY', 'category'),
    ('TAG', 'tag'),
]

TransactionsTableFields = create_enum('TransactionsTableFields', fields)
CreditCardTableFields = create_enum('CreditCardTableFields', fields)
BankTableFields = create_enum('BankTableFields', fields)

split_fields = [
    ('ID', 'id'),
    ('TRANSACTION_ID', 'transaction_id'),
    ('SERVICE', 'service'),
    ('AMOUNT', 'amount'),
    ('CATEGORY', 'category'),
    ('TAG', 'tag'),
]

SplitTransactionsTableFields = create_enum('SplitTransactionsTableFields', split_fields)


class AutoTaggerTableFields(Enum):
    """
    Enum defining field names for the automatic tagger table.

    Attributes
    ----------
    NAME : str
        Field name for the transaction name/description.
    CATEGORY : str
        Field name for the transaction category.
    TAG : str
        Field name for the transaction tag.
    SERVICE : str
        Field name for the service type (e.g., bank, credit card).
    ACCOUNT_NUMBER : str
        Field name for the account number.
    """
    NAME = 'name'
    CATEGORY = 'category'
    TAG = 'tag'
    SERVICE = 'service'
    ACCOUNT_NUMBER = 'account_number'


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
    YEAR = 'year'
    MONTH = 'month'
    CATEGORY = 'category'
    TAGS = 'tags'
    NAME = 'name'
    AMOUNT = 'amount'


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
    CREDIT_CARD = 'credit_card'
    BANK = 'bank'
    INSURANCE = 'insurance'


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
    MAX = 'max'
    VISA_CAL = 'visa cal'
    ISRACARD = 'isracard'
    AMEX = 'amex'
    BEYAHAD_BISHVILHA = 'beyahad bishvilha'
    BEHATSADAA = 'behatsdaa'


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
    HAPOALIM = 'hapoalim'
    LEUMI = 'leumi'
    DISCOUNT = 'discount'
    MIZRAHI = 'mizrahi'
    MERCANTILE = 'mercantile'
    OTSAR_HAHAYAL = 'otsar hahayal'
    UNION = 'union'
    BEINLEUMI = 'beinleumi'
    MASSAD = 'massad'
    YAHAV = 'yahav'
    ONEZERO = 'onezero'


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
    MENORA = 'menora'
    CLAL = 'clal'
    HAREL = 'harel'
    HAFENIX = 'hafenix'


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
    SAVINGS : str
        Money set aside as savings.
    INVESTMENTS : str
        Money allocated to investments.
    OTHER_INCOME : str
        Income from sources other than salary.
    LIABILITIES : str
        Payments related to liabilities.
    """
    IGNORE = 'Ignore'
    SALARY = 'Salary'
    SAVINGS = 'Savings'
    INVESTMENTS = 'Investments'
    OTHER_INCOME = 'Other Income'
    LIABILITIES = 'Liabilities'


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
    ID = 'id'
    CARD_6_DIGITS = 'card6Digits'
    PASSWORD = 'password'
    USERNAME = 'username'
    USER_CODE = 'userCode'
    NUM = 'num'
    NATIONAL_ID = 'nationalID'
    EMAIL = 'email'
    PHONE_NUMBER = 'phoneNumber'


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
        'max': ['username', 'password'],
        'visa cal': ['username', 'password'],
        'isracard': ['id', 'card6Digits', 'password'],
        'amex': ['id', 'card6Digits', 'password'],
        'beyahad bishvilha': ['id', 'password'],
        'behatsdaa': ['id', 'password'],
        # banks
        'hapoalim': ['userCode', 'password'],
        'leumi': ['username', 'password'],
        'mizrahi': ['username', 'password'],
        'discount': ['id', 'password', 'num'],
        'mercantile': ['id', 'password', 'num'],
        'otsar hahayal': ['username', 'password'],
        'union': ['username', 'password'],
        'beinleumi': ['username', 'password'],
        'massad': ['username', 'password'],
        'yahav': ['username', 'nationalID', 'password'],
        'onezero': ['email', 'password', 'phoneNumber'],
        'dummy_tfa': ['email', 'password', 'phoneNumber'],
        'dummy_tfa_no_otp': ['email', 'password', 'phoneNumber'],
        # insurances
        'menora': ['username', 'password'],
        'clal': ['username', 'password'],
        'harel': ['username', 'password'],
        'hafenix': ['username', 'password']
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
        'id': 'ID Number',
        'card6Digits': 'Card 6 Digits',
        'password': 'Password',
        'username': 'Username',
        'userCode': 'User Code',
        'num': 'Num',
        'nationalID': 'National ID',
        'email': 'Email',
        'phoneNumber': 'Phone Number'
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
