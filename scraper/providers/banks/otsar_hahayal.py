from __future__ import annotations

import logging

from scraper.providers.banks.beinleumi_group import BeinleumiGroupBaseScraper

logger = logging.getLogger(__name__)


class OtsarHahayalScraper(BeinleumiGroupBaseScraper):
    """Scraper for Bank Otsar Hahayal (https://www.bankotsar.co.il).

    Extends the Beinleumi group base scraper with Otsar Hahayal-specific
    URLs for login and transaction fetching.
    """

    BASE_URL = "https://online.bankotsar.co.il"
    LOGIN_URL = (
        f"{BASE_URL}/MatafLoginService/MatafLoginServlet"
        "?bankId=OTSARPRTAL&site=Private&KODSAFA=HE"
    )
    TRANSACTIONS_URL = (
        f"{BASE_URL}/wps/myportal/FibiMenu/Online"
        "/OnAccountMngment/OnBalanceTrans/PrivateAccountFlow"
    )
