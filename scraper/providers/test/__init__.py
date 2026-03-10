from scraper.providers.test.dummy_regular import (
    DummyCreditCardScraper,
    DummyRegularScraper,
)
from scraper.providers.test.dummy_tfa import DummyTFAScraper
from scraper.providers.test.dummy_tfa_no_otp import DummyTFANoOTPScraper

__all__ = [
    "DummyCreditCardScraper",
    "DummyRegularScraper",
    "DummyTFAScraper",
    "DummyTFANoOTPScraper",
]
