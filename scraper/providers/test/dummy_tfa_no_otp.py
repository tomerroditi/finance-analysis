from scraper.providers.test.dummy_tfa import DummyTFAScraper


class DummyTFANoOTPScraper(DummyTFAScraper):
    """Trivial 2FA scraper subclass for testing provider type variants.

    Behaves identically to DummyTFAScraper; exists for registry/type distinction.
    """
