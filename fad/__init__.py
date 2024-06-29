import os

from enum import Enum
from fad import scraper


__version__ = "0.0.1"


src_path = os.path.dirname(os.path.abspath(__file__))
credentials_path = os.path.join(src_path, 'scraper', 'credentials.yaml')
data_path = os.path.join(src_path, 'data.db')


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
