from backend.scraper.adapter import InsuranceScraperAdapter, ScraperAdapter, create_adapter

# Providers that can request 2FA. Kept in sync with the ``requires_2fa`` flag
# on ``scraper.models.credentials.PROVIDER_CONFIGS``. The duplication is a
# legacy of ``backend.scraper`` shadowing the root ``scraper`` package — keep
# both in sync until they're unified.
#
# Semantics: "requires_2fa" means the scraper *may* request an OTP during
# login (e.g. Hapoalim only requests it from new devices). The status only
# flips to WAITING_FOR_2FA once the scraper actually awaits the OTP — see
# ``ScraperAdapter._otp_callback``.
_2FA_PROVIDERS = {
    "hapoalim",
    "onezero",
    "hafenix",
    "test_bank_2fa",
    "test_credit_card_2fa",
}


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
