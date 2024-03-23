from enum import Enum


__version__ = "0.0.1"


class Tables(Enum):
    CREDIT_CARDS = 'credit_card_transactions'
    TAGS = 'tags'


class Columns(Enum):
    # Credit card transactions table
    ACCOUNT_NUMBER = 'account_number'
    TYPE = 'type'
    ID = 'id'
    DATE = 'date'
    AMOUNT = 'amount'
    DESCRIPTION = 'desc'
    STATUS = 'status'

    # Tags table
    TAGS = 'tags'
    CATEGORY = 'category'
    NAME = 'name'