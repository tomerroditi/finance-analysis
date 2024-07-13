from enum import Enum


class Tables(Enum):
    CREDIT_CARD = 'credit_card_transactions'
    BANK = 'bank_transactions'
    INSURANCE = 'insurance_transactions'
    SAVINGS = 'savings'
    TAGS = 'tags'


class CreditCardTableFields(Enum):
    ACCOUNT_NUMBER = 'account_number'
    TYPE = 'type'
    ID = 'id'
    DATE = 'date'
    DESCRIPTION = 'desc'
    AMOUNT = 'amount'
    STATUS = 'status'
    ACCOUNT_NAME = 'account_name'

class BankTableFields(Enum):
    ACCOUNT_NUMBER = 'account_number'
    TYPE = 'type'
    ID = 'id'
    DATE = 'date'
    DESCRIPTION = 'desc'
    AMOUNT = 'amount'
    STATUS = 'status'
    ACCOUNT_NAME = 'account_name'


class TagsTableFields(Enum):
    NAME = 'name'
    CATEGORY = 'category'
    TAG = 'tag'


class CreditCards(Enum):
    MAX = 'max'
    VISA_CAL = 'visa cal'
    ISRACARD = 'isracard'
    AMEX = 'amex'
    BEYAHAD_BISHVILHA = 'beyahad bishvilha'
    BEHATSADAA = 'behatsdaa'


class Banks(Enum):
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
    MENORA = 'menora'
    CLAL = 'clal'
    HAREL = 'harel'
    HAFENIX = 'hafenix'


class Fields(Enum):
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
        # insurances
        'menora': ['username', 'password'],
        'clal': ['username', 'password'],
        'harel': ['username', 'password'],
        'hafenix': ['username', 'password']
    }

    @staticmethod
    def get_fields(provider: str) -> list[str]:
        return LoginFields.providers_fields[provider]


class DisplayFields:
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
        try:
            return DisplayFields.field_display[field]
        except KeyError:
            return field
