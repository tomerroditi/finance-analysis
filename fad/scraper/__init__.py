import os

from .two_fa import TwoFAHandler
from .scrapers import CreditCardScraper, BankScraper

NODE_JS_SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), 'node')
