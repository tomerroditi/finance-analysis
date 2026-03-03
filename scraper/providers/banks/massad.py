from __future__ import annotations

import logging

from scraper.providers.banks.beinleumi_group import BeinleumiGroupBaseScraper

logger = logging.getLogger(__name__)


class MassadScraper(BeinleumiGroupBaseScraper):
    """Scraper for Bank Massad (https://www.bankmassad.co.il).

    Extends the Beinleumi group base scraper with Massad-specific
    URLs for login and transaction fetching.
    """

    BASE_URL = "https://online.bankmassad.co.il"
    LOGIN_URL = (
        f"{BASE_URL}/MatafLoginService/MatafLoginServlet"
        "?bankId=MASADPRTAL&site=Private&KODSAFA=HE"
    )
    TRANSACTIONS_URL = (
        f"{BASE_URL}/wps/myportal/FibiMenu/Online"
        "/OnAccountMngment/OnBalanceTrans/PrivateAccountFlow"
    )
