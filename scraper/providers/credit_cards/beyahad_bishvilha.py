from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from scraper.base import BrowserScraper, LoginOptions
from scraper.models.account import AccountResult
from scraper.models.result import LoginResult
from scraper.models.transaction import Transaction, TransactionStatus, TransactionType
from scraper.utils import (
    filter_old_transactions,
    page_eval,
    page_eval_all,
    wait_until_element_found,
)

logger = logging.getLogger(__name__)

SHEKEL_CURRENCY = "ILS"
SHEKEL_CURRENCY_SYMBOL = "\u20aa"
DOLLAR_CURRENCY = "USD"
DOLLAR_CURRENCY_SYMBOL = "$"
EURO_CURRENCY = "EUR"
EURO_CURRENCY_SYMBOL = "\u20ac"

DATE_FORMAT = "%d/%m/%y"
LOGIN_URL = "https://www.hist.org.il/login"
SUCCESS_URL = "https://www.hist.org.il/"
CARD_URL = "https://www.hist.org.il/card/balanceAndUses"


def _get_amount_data(amount_str: str) -> tuple[float | None, str | None]:
    """Parse an amount string to extract value and currency.

    Parameters
    ----------
    amount_str : str
        Amount string with currency symbol or code.

    Returns
    -------
    tuple[float | None, str | None]
        Parsed (amount, currency) tuple.
    """
    if not amount_str:
        return None, None

    cleaned = amount_str.replace(",", "")

    if SHEKEL_CURRENCY_SYMBOL in cleaned:
        amount = _safe_float(cleaned.replace(SHEKEL_CURRENCY_SYMBOL, ""))
        return amount, SHEKEL_CURRENCY
    elif DOLLAR_CURRENCY_SYMBOL in cleaned:
        amount = _safe_float(cleaned.replace(DOLLAR_CURRENCY_SYMBOL, ""))
        return amount, DOLLAR_CURRENCY
    elif EURO_CURRENCY_SYMBOL in cleaned:
        amount = _safe_float(cleaned.replace(EURO_CURRENCY_SYMBOL, ""))
        return amount, EURO_CURRENCY
    else:
        parts = cleaned.split(" ")
        if len(parts) >= 2:
            return _safe_float(parts[1]), parts[0]
        return _safe_float(cleaned), None


def _safe_float(s: str) -> float | None:
    """Safely parse a string to float.

    Parameters
    ----------
    s : str
        String to parse.

    Returns
    -------
    float | None
        Parsed float or None if unparseable.
    """
    try:
        return float(s.strip())
    except (ValueError, TypeError):
        return None


def _convert_transactions(txns: list[dict]) -> list[Transaction]:
    """Convert raw scraped transactions to Transaction objects.

    Parameters
    ----------
    txns : list[dict]
        Raw transaction dicts with date, description, chargedAmount, etc.

    Returns
    -------
    list[Transaction]
        Converted transaction objects.
    """
    results: list[Transaction] = []
    for txn in txns:
        charged_amount_str = txn.get("chargedAmount", "")
        amount, currency = _get_amount_data(charged_amount_str)

        date_str = txn.get("date", "")
        try:
            txn_date = datetime.strptime(date_str, DATE_FORMAT)
            date_iso = txn_date.isoformat()
        except (ValueError, TypeError):
            date_iso = date_str

        results.append(
            Transaction(
                type=TransactionType.NORMAL,
                status=TransactionStatus.COMPLETED,
                date=date_iso,
                processed_date=date_iso,
                original_amount=amount,
                original_currency=currency,
                charged_amount=amount,
                charged_currency=currency,
                description=txn.get("description", ""),
                identifier=txn.get("identifier"),
                memo=None,
            )
        )
    return results


def _get_possible_login_results() -> dict[LoginResult, list]:
    """Build login result detection rules for Beyahad Bishvilha.

    Returns
    -------
    dict[LoginResult, list]
        Mapping of login results to URL patterns.
    """
    return {
        LoginResult.SUCCESS: [SUCCESS_URL],
    }


# JS expression to extract account number text from the wallet details element.
_ACCOUNT_NUMBER_JS = (
    "el => el.innerText.replace("
    "'\u05de\u05e1\u05e4\u05e8 \u05db\u05e8\u05d8\u05d9\u05e1 ', '')"
)

# JS expression to extract transaction data from DOM elements.
_TRANSACTIONS_JS = """items => items.map(el => {
    const columns = el.querySelectorAll('.transaction-item > span');
    if (columns.length === 7) {
        return {
            date: columns[0].innerText,
            identifier: columns[1].innerText,
            description: columns[3].innerText,
            type: columns[5].innerText,
            chargedAmount: columns[6].innerText
        };
    }
    return null;
})"""


class BeyahadBishvilhaScraper(BrowserScraper):
    """Scraper for Beyahad Bishvilha credit card (https://www.hist.org.il).

    Uses DOM scraping to extract transaction data from the card balance
    and usage page after browser-based authentication.
    """

    def get_login_options(self, credentials: dict) -> LoginOptions:
        """Return Beyahad Bishvilha-specific login configuration.

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

        async def submit_button_action():
            button = await page.query_selector(
                'xpath=//button[contains(., "\u05d4\u05ea\u05d7\u05d1\u05e8")]'
            )
            if button:
                await button.click()

        return LoginOptions(
            login_url=LOGIN_URL,
            fields=[
                {"selector": "#loginId", "value": credentials["id"]},
                {
                    "selector": "#loginPassword",
                    "value": credentials["password"],
                },
            ],
            submit_button_selector=submit_button_action,
            possible_results=_get_possible_login_results(),
        )

    async def fetch_data(self) -> list[AccountResult]:
        """Fetch credit card transaction data from Beyahad Bishvilha.

        Returns
        -------
        list[AccountResult]
            Single account with transactions and balance.
        """
        await self.page.goto(CARD_URL)
        await wait_until_element_found(
            self.page, ".react-loading.hide", only_visible=False
        )

        default_start = date.today() - timedelta(days=365)
        effective_start = max(
            default_start, self.options.start_date or default_start
        )

        # Extract account number
        account_number = await page_eval(
            self.page,
            ".wallet-details div:nth-of-type(2)",
            _ACCOUNT_NUMBER_JS,
        )

        # Extract balance
        balance_text = await page_eval(
            self.page,
            ".wallet-details div:nth-of-type(4) > span:nth-of-type(2)",
            "el => el.innerText",
        )
        balance_amount, _ = _get_amount_data(balance_text or "")

        # Extract raw transactions from the DOM
        logger.debug("Fetching raw transactions from page")
        raw_transactions = await page_eval_all(
            self.page,
            ".transaction-container, .transaction-component-container",
            _TRANSACTIONS_JS,
            [],
        )

        # Filter out null entries
        valid_txns = [t for t in (raw_transactions or []) if t is not None]
        logger.debug("Fetched %d raw transactions from page", len(valid_txns))

        account_transactions = _convert_transactions(valid_txns)

        # Filter old transactions
        txns = filter_old_transactions(
            account_transactions, effective_start, False
        )

        logger.debug(
            "Found %d valid transactions out of %d for account %s",
            len(txns),
            len(account_transactions),
            (account_number or "")[-2:],
        )

        return [
            AccountResult(
                account_number=account_number or "",
                transactions=txns,
                balance=balance_amount,
            )
        ]
