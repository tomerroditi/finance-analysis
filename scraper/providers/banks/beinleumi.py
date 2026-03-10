from __future__ import annotations

import logging

from scraper.providers.banks.beinleumi_group import BeinleumiGroupBaseScraper

logger = logging.getLogger(__name__)


class BeinleumiScraper(BeinleumiGroupBaseScraper):
    """Scraper for Bank Beinleumi (https://www.fibi.co.il).

    Extends the Beinleumi group base scraper with Beinleumi-specific
    URLs for login and transaction fetching.
    """

    BASE_URL = "https://online.fibi.co.il"
    LOGIN_URL = (
        f"{BASE_URL}/MatafLoginService/MatafLoginServlet"
        "?bankId=FIBIPORTAL&site=Private&KODSAFA=HE"
    )
    TRANSACTIONS_URL = (
        f"{BASE_URL}/wps/myportal/FibiMenu/Online"
        "/OnAccountMngment/OnBalanceTrans/PrivateAccountFlow"
    )
