from __future__ import annotations

import logging
from datetime import date, datetime

from scraper.base import BrowserScraper, LoginOptions
from scraper.models.account import AccountResult
from scraper.models.result import LoginResult
from scraper.models.transaction import Transaction, TransactionStatus, TransactionType
from scraper.utils import (
    fetch_post_within_page,
    sleep,
    wait_until_element_found,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://www.behatsdaa.org.il"
LOGIN_URL = f"{BASE_URL}/login"
PURCHASE_HISTORY_URL = "https://back.behatsdaa.org.il/api/purchases/purchaseHistory"


def _variant_to_transaction(variant: dict) -> Transaction:
    """Convert a raw purchase variant to a Transaction object.

    Parameters
    ----------
    variant : dict
        Raw variant data from the Behatsdaa API with keys:
        name, variantName, customerPrice, orderDate, tTransactionID.

    Returns
    -------
    Transaction
        Converted transaction object.
    """
    original_amount = -variant.get("customerPrice", 0)

    order_date_str = variant.get("orderDate", "")
    try:
        order_date = datetime.fromisoformat(order_date_str)
        date_iso = order_date.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        date_iso = order_date_str

    return Transaction(
        type=TransactionType.NORMAL,
        status=TransactionStatus.COMPLETED,
        date=date_iso,
        processed_date=date_iso,
        original_amount=original_amount,
        original_currency="ILS",
        charged_amount=original_amount,
        charged_currency="ILS",
        description=variant.get("name", ""),
        identifier=variant.get("tTransactionID"),
        memo=variant.get("variantName") or None,
    )


class BehatsdaaScraper(BrowserScraper):
    """Scraper for Behatsdaa credit card (https://www.behatsdaa.org.il).

    Uses browser login to authenticate, then extracts a bearer token from
    local storage to fetch purchase history via the Behatsdaa REST API.
    """

    def get_login_options(self, credentials: dict) -> LoginOptions:
        """Return Behatsdaa-specific login configuration.

        Parameters
        ----------
        credentials : dict
            Must contain 'id' and 'password' keys.

        Returns
        -------
        LoginOptions
            Login configuration for the generic login flow.
        """
        page = self.page

        async def check_readiness():
            await wait_until_element_found(page, "#loginPassword")
            await wait_until_element_found(page, "#loginId")

        async def submit_button_action():
            await sleep(1.0)
            logger.debug("Looking for submit button")
            button = await page.query_selector(
                'xpath=//button[contains(., "\u05d4\u05ea\u05d7\u05d1\u05e8\u05d5\u05ea")]'
            )
            if button:
                logger.debug("Submit button found, clicking")
                await button.click()
            else:
                logger.debug("Submit button not found")

        return LoginOptions(
            login_url=LOGIN_URL,
            fields=[
                {"selector": "#loginId", "value": credentials["id"]},
                {
                    "selector": "#loginPassword",
                    "value": credentials["password"],
                },
            ],
            check_readiness=check_readiness,
            possible_results={
                LoginResult.SUCCESS: [f"{BASE_URL}/"],
                LoginResult.INVALID_PASSWORD: [
                    ".custom-input-error-label"
                ],
            },
            submit_button_selector=submit_button_action,
        )

    async def fetch_data(self) -> list[AccountResult]:
        """Fetch purchase history from the Behatsdaa API.

        Returns
        -------
        list[AccountResult]
            Single account with transactions.

        Raises
        ------
        Exception
            If the token is not found or the API returns an error.
        """
        token = await self.page.evaluate(
            "() => window.localStorage.getItem('userToken')"
        )
        if not token:
            logger.debug("Token not found in local storage")
            raise Exception("Token not found in local storage")

        start_date = self.options.start_date or date.today()
        from_date = datetime.combine(start_date, datetime.min.time())
        to_date = datetime.now()

        body = {
            "FromDate": from_date.strftime("%Y-%m-%dT%H:%M:%S"),
            "ToDate": to_date.strftime("%Y-%m-%dT%H:%M:%S"),
            "BenefitStatusId": None,
        }

        logger.debug("Fetching purchase history")
        res = await fetch_post_within_page(
            self.page,
            PURCHASE_HISTORY_URL,
            body,
            extra_headers={
                "authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "organizationid": "20",
            },
        )

        logger.debug("Purchase history fetched")

        if not res:
            raise Exception("No data received from Behatsdaa API")

        error_desc = res.get("errorDescription") or (
            res.get("data", {}).get("errorDescription")
            if res.get("data")
            else None
        )
        if error_desc:
            logger.debug("Error from API: %s", error_desc)
            raise Exception(f"API error: {error_desc}")

        data = res.get("data")
        if not data:
            raise Exception("No data in Behatsdaa API response")

        member_id = data.get("memberId", "")
        variants = data.get("variants", [])

        transactions = [_variant_to_transaction(v) for v in variants]

        logger.debug("Fetched %d transactions", len(transactions))

        return [
            AccountResult(
                account_number=member_id,
                transactions=transactions,
            )
        ]
