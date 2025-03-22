import os

from enum import Enum

__version__ = "0.0.1"


SRC_PATH = os.path.dirname(os.path.abspath(__file__))
USER_DIR = os.path.join(os.path.expanduser('~'), '.finance-analysis')
CREDENTIALS_PATH = os.path.join(USER_DIR, 'credentials.yaml')
DB_PATH = os.path.join(USER_DIR, 'data.db')
CATEGORIES_PATH = os.path.join(USER_DIR, 'categories.yaml')


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
