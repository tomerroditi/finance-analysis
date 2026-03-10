from __future__ import annotations

import logging

from scraper.providers.banks.beinleumi_group import BeinleumiGroupBaseScraper

logger = logging.getLogger(__name__)


class PagiScraper(BeinleumiGroupBaseScraper):
    """Scraper for Bank Pagi (https://www.pagi.co.il).

    Extends the Beinleumi group base scraper with Pagi-specific
    URLs for login and transaction fetching.
    """

    BASE_URL = "https://online.pagi.co.il/"
    LOGIN_URL = (
        f"{BASE_URL}MatafLoginService/MatafLoginServlet"
        "?bankId=PAGIPORTAL&site=Private&KODSAFA=HE"
    )
    TRANSACTIONS_URL = (
        f"{BASE_URL}wps/myportal/FibiMenu/Online"
        "/OnAccountMngment/OnBalanceTrans/PrivateAccountFlow"
    )
