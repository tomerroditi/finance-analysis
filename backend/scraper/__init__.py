from backend.scraper.adapter import InsuranceScraperAdapter, ScraperAdapter, create_adapter

# Providers that require 2FA. Kept in sync with scraper.models.credentials.
_2FA_PROVIDERS = {"onezero", "hafenix", "test_bank_2fa", "test_credit_card_2fa"}


def is_2fa_required(service_name: str, provider_name: str) -> bool:
    """Check if a provider requires two-factor authentication.

    Parameters
    ----------
    service_name : str
        Service type (e.g. ``"credit_cards"``, ``"banks"``).
    provider_name : str
        Provider identifier (e.g. ``"hapoalim"``, ``"onezero"``).

    Returns
    -------
    bool
        ``True`` if the provider requires 2FA.
    """
    return provider_name in _2FA_PROVIDERS


__all__ = ["InsuranceScraperAdapter", "ScraperAdapter", "create_adapter", "is_2fa_required"]
