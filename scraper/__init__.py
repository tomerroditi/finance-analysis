from scraper.base.base_scraper import BaseScraper, ScraperOptions
from scraper.models.credentials import PROVIDER_CONFIGS, ProviderConfig
from scraper.models.result import ScrapingResult


def create_scraper(
    provider: str, credentials: dict, options: ScraperOptions | None = None
) -> BaseScraper:
    """Create a scraper instance for the given provider.

    Parameters
    ----------
    provider : str
        Provider key (e.g., "hapoalim", "visa cal").
    credentials : dict
        Provider-specific credentials.
    options : ScraperOptions | None
        Scraper configuration options.

    Returns
    -------
    BaseScraper
        A configured scraper instance.

    Raises
    ------
    ValueError
        If the provider is not recognized.
    """
    # Lazy imports to avoid circular dependencies and import errors
    # before provider scrapers are implemented (Tasks 16+)
    from scraper.providers.banks.beinleumi import BeinleumiScraper
    from scraper.providers.banks.discount import DiscountScraper
    from scraper.providers.banks.hapoalim import HapoalimScraper
    from scraper.providers.banks.leumi import LeumiScraper
    from scraper.providers.banks.massad import MassadScraper
    from scraper.providers.banks.mercantile import MercantileScraper
    from scraper.providers.banks.mizrahi import MizrahiScraper
    from scraper.providers.banks.onezero import OneZeroScraper
    from scraper.providers.banks.otsar_hahayal import OtsarHahayalScraper
    from scraper.providers.banks.pagi import PagiScraper
    from scraper.providers.banks.union import UnionBankScraper
    from scraper.providers.banks.yahav import YahavScraper
    from scraper.providers.credit_cards.amex import AmexScraper
    from scraper.providers.credit_cards.behatsdaa import BehatsdaaScraper
    from scraper.providers.credit_cards.beyahad_bishvilha import (
        BeyahadBishvilhaScraper,
    )
    from scraper.providers.credit_cards.isracard import IsracardScraper
    from scraper.providers.credit_cards.max import MaxScraper
    from scraper.providers.credit_cards.visa_cal import VisaCalScraper

    scrapers = {
        "hapoalim": HapoalimScraper,
        "leumi": LeumiScraper,
        "discount": DiscountScraper,
        "mercantile": MercantileScraper,
        "mizrahi": MizrahiScraper,
        "otsar hahayal": OtsarHahayalScraper,
        "union": UnionBankScraper,
        "beinleumi": BeinleumiScraper,
        "massad": MassadScraper,
        "yahav": YahavScraper,
        "onezero": OneZeroScraper,
        "pagi": PagiScraper,
        "max": MaxScraper,
        "visa cal": VisaCalScraper,
        "isracard": IsracardScraper,
        "amex": AmexScraper,
        "beyahad bishvilha": BeyahadBishvilhaScraper,
        "behatsdaa": BehatsdaaScraper,
    }

    scraper_class = scrapers.get(provider)
    if not scraper_class:
        raise ValueError(f"Unknown provider: {provider}")
    return scraper_class(provider, credentials, options)


def is_2fa_required(provider: str) -> bool:
    """Check if a provider requires two-factor authentication.

    Parameters
    ----------
    provider : str
        Provider key.

    Returns
    -------
    bool
        True if the provider requires 2FA.
    """
    config = PROVIDER_CONFIGS.get(provider)
    return config.requires_2fa if config else False
