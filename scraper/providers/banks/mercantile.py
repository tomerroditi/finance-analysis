from __future__ import annotations

import logging

from scraper.base import LoginOptions
from scraper.providers.banks.discount import DiscountScraper

logger = logging.getLogger(__name__)

MERCANTILE_LOGIN_URL = "https://start.telebank.co.il/login/?bank=m"


class MercantileScraper(DiscountScraper):
    """Scraper for Mercantile Discount Bank.

    Extends the Discount Bank scraper with a Mercantile-specific login URL.
    All other functionality (API endpoints, transaction parsing) is identical.
    """

    def get_login_options(self, credentials: dict) -> LoginOptions:
        """Return Mercantile Bank login configuration.

        Parameters
        ----------
        credentials : dict
            Must contain 'id', 'password', and 'num' keys.

        Returns
        -------
        LoginOptions
            Login configuration with Mercantile-specific login URL.
        """
        options = super().get_login_options(credentials)
        options.login_url = MERCANTILE_LOGIN_URL
        return options
