from backend.scraper.adapter import ScraperAdapter


def is_2fa_required(service_name: str, provider_name: str) -> bool:
    """Check if a provider requires two-factor authentication.

    Delegates to the scraper framework's ``PROVIDER_CONFIGS`` registry.

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
    from scraper.models.credentials import PROVIDER_CONFIGS

    config = PROVIDER_CONFIGS.get(provider_name)
    return config.requires_2fa if config else False


__all__ = ["ScraperAdapter", "is_2fa_required"]
