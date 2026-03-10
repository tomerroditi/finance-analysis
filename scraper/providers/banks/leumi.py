from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date, datetime, timedelta

from scraper.utils.dates import utc_to_israel_date_str

from scraper.base import BrowserScraper, LoginOptions
from scraper.models.account import AccountResult
from scraper.models.result import LoginResult
from scraper.models.transaction import Transaction, TransactionStatus, TransactionType
from scraper.utils import (
    click_button,
    fill_input,
    page_eval,
    page_eval_all,
    sleep,
    wait_for_navigation,
    wait_until_element_found,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://hb2.bankleumi.co.il"
LOGIN_URL = "https://www.leumi.co.il/he"
TRANSACTIONS_URL = (
    f"{BASE_URL}/eBanking/SO/SPA.aspx#/ts/BusinessAccountTrx?WidgetPar=1"
)
FILTERED_TRANSACTIONS_URL = (
    f"{BASE_URL}/ChannelWCF/Broker.svc/ProcessRequest"
    "?moduleName=UC_SO_27_GetBusinessAccountTrx"
)

ACCOUNT_BLOCKED_MSG = "\u05d4\u05de\u05e0\u05d5\u05d9 \u05d7\u05e1\u05d5\u05dd"
INVALID_PASSWORD_MSG = (
    "\u05d0\u05d7\u05d3 \u05d0\u05d5 \u05d9\u05d5\u05ea\u05e8 "
    "\u05de\u05e4\u05e8\u05d8\u05d9 \u05d4\u05d4\u05d6\u05d3\u05d4\u05d5\u05ea "
    "\u05e9\u05de\u05e1\u05e8\u05ea \u05e9\u05d2\u05d5\u05d9\u05d9\u05dd. "
    "\u05e0\u05d9\u05ea\u05df \u05dc\u05e0\u05e1\u05d5\u05ea \u05e9\u05d5\u05d1"
)

SHEKEL_CURRENCY = "ILS"


def _remove_special_characters(s: str) -> str:
    """Remove non-numeric characters except dash and slash."""
    return re.sub(r"[^0-9/\-]", "", s)


def _extract_transactions_from_page(
    transactions: list[dict] | None,
    status: TransactionStatus,
) -> list[Transaction]:
    """Convert raw Leumi transaction dicts to Transaction objects.

    Parameters
    ----------
    transactions : list[dict] | None
        Raw transaction data from the Leumi response.
    status : TransactionStatus
        Status to assign to each transaction.

    Returns
    -------
    list[Transaction]
        Parsed transaction objects.
    """
    if not transactions:
        return []

    results: list[Transaction] = []
    for raw in transactions:
        date_utc = raw.get("DateUTC", "")
        try:
            date_iso = utc_to_israel_date_str(date_utc) if date_utc else datetime.now().strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            date_iso = str(date_utc)

        results.append(
            Transaction(
                type=TransactionType.NORMAL,
                status=status,
                date=date_iso,
                processed_date=date_iso,
                original_amount=raw.get("Amount", 0),
                original_currency=SHEKEL_CURRENCY,
                charged_amount=raw.get("Amount", 0),
                description=raw.get("Description", ""),
                identifier=raw.get("ReferenceNumberLong"),
                memo=raw.get("AdditionalData") or None,
            )
        )
    return results


async def _navigate_to_login(page) -> None:
    """Navigate from the homepage to the login form.

    Parameters
    ----------
    page : Page
        Playwright page instance.
    """
    login_button_selector = ".enter_account"
    logger.debug("Waiting for homepage login button")
    await wait_until_element_found(page, login_button_selector)

    login_url = await page_eval(page, login_button_selector, "el => el.href")
    if login_url:
        logger.debug("Navigating to login page: %s", login_url)
        await page.goto(login_url)
        await wait_for_navigation(page, "networkidle")
        await asyncio.gather(
            wait_until_element_found(
                page, 'input[placeholder="\u05e9\u05dd \u05de\u05e9\u05ea\u05de\u05e9"]', only_visible=True
            ),
            wait_until_element_found(
                page, 'input[placeholder="\u05e1\u05d9\u05e1\u05de\u05d4"]', only_visible=True
            ),
            wait_until_element_found(
                page, 'button[type="submit"]', only_visible=True
            ),
        )


async def _wait_for_post_login(page) -> None:
    """Wait for post-login indicators to appear.

    Parameters
    ----------
    page : Page
        Playwright page instance.
    """
    done, pending = await asyncio.wait(
        [
            asyncio.create_task(
                wait_until_element_found(
                    page,
                    'a[title="\u05d3\u05dc\u05d2 \u05dc\u05d7\u05e9\u05d1\u05d5\u05df"]',
                    only_visible=True,
                    timeout=60000,
                )
            ),
            asyncio.create_task(
                wait_until_element_found(
                    page, "div.main-content", only_visible=False, timeout=60000
                )
            ),
            asyncio.create_task(
                wait_until_element_found(
                    page, 'form[action="/changepassword"]', only_visible=True, timeout=60000
                )
            ),
        ],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()


def _get_possible_login_results(page) -> dict[LoginResult, list]:
    """Build login result detection rules for Leumi.

    Parameters
    ----------
    page : Page
        Playwright page instance.

    Returns
    -------
    dict[LoginResult, list]
        Mapping of login results to URL patterns or callables.
    """

    async def is_invalid_password(**kwargs):
        error_message = await page_eval_all(
            kwargs.get("page", page),
            "svg#Capa_1",
            "elements => { const p = elements[0]?.parentElement; return p?.children[1]?.innerText || ''; }",
        )
        return bool(error_message and error_message.startswith(INVALID_PASSWORD_MSG))

    async def is_account_blocked(**kwargs):
        error_message = await page_eval_all(
            kwargs.get("page", page),
            ".errHeader",
            "elements => { return elements[0]?.innerText || ''; }",
        )
        return bool(error_message and error_message.startswith(ACCOUNT_BLOCKED_MSG))

    return {
        LoginResult.SUCCESS: [re.compile(r"ebanking/SO/SPA\.aspx", re.IGNORECASE)],
        LoginResult.INVALID_PASSWORD: [is_invalid_password],
        LoginResult.ACCOUNT_BLOCKED: [is_account_blocked],
        LoginResult.CHANGE_PASSWORD: ["https://hb2.bankleumi.co.il/authenticate"],
    }


async def _fetch_transactions_for_account(
    page,
    start_date: date,
    account_id: str,
) -> AccountResult:
    """Fetch transactions for a single Leumi account.

    Parameters
    ----------
    page : Page
        Playwright page instance.
    start_date : date
        Earliest transaction date to fetch.
    account_id : str
        The account identifier from the accounts dropdown.

    Returns
    -------
    AccountResult
        Account data with transactions and balance.
    """
    # Wait for the page to settle (account number may change at runtime)
    await sleep(4.0)

    await wait_until_element_found(
        page, 'button[title="\u05d7\u05d9\u05e4\u05d5\u05e9 \u05de\u05ea\u05e7\u05d3\u05dd"]', only_visible=True
    )
    await click_button(page, 'button[title="\u05d7\u05d9\u05e4\u05d5\u05e9 \u05de\u05ea\u05e7\u05d3\u05dd"]')
    await wait_until_element_found(page, "bll-radio-button", only_visible=True)
    await click_button(page, "bll-radio-button:not([checked])")

    await wait_until_element_found(
        page, 'input[formcontrolname="txtInputFrom"]', only_visible=True
    )

    # Format date as DD.MM.YY
    date_str = start_date.strftime("%d.%m.%y")
    await fill_input(page, 'input[formcontrolname="txtInputFrom"]', date_str)

    # Blur from-date input before clicking filter
    await page.focus("button[aria-label='\u05e1\u05e0\u05df']")
    await click_button(page, "button[aria-label='\u05e1\u05e0\u05df']")

    # Wait for the filtered transactions response
    response = await page.wait_for_event(
        "response",
        predicate=lambda r: (
            r.url == FILTERED_TRANSACTIONS_URL and r.request.method == "POST"
        ),
    )
    response_json = await response.json()

    parsed = json.loads(response_json.get("jsonResp", "{}"))

    account_number = _remove_special_characters(account_id.replace("/", "_"))

    pending_transactions = parsed.get("TodayTransactionsItems")
    completed_transactions = parsed.get("HistoryTransactionsItems")
    balance_str = parsed.get("BalanceDisplay")
    balance = float(balance_str) if balance_str else None

    pending_txns = _extract_transactions_from_page(
        pending_transactions, TransactionStatus.PENDING
    )
    completed_txns = _extract_transactions_from_page(
        completed_transactions, TransactionStatus.COMPLETED
    )

    return AccountResult(
        account_number=account_number,
        transactions=[*pending_txns, *completed_txns],
        balance=balance,
    )


async def _fetch_transactions(
    page,
    start_date: date,
) -> list[AccountResult]:
    """Fetch transactions for all accounts.

    Parameters
    ----------
    page : Page
        Playwright page instance.
    start_date : date
        Earliest transaction date to fetch.

    Returns
    -------
    list[AccountResult]
        List of account results.
    """
    accounts: list[AccountResult] = []

    # Wait for account numbers to stabilize
    await sleep(4.0)

    account_ids = await page.evaluate(
        """() => Array.from(
            document.querySelectorAll('app-masked-number-combo span.display-number-li'),
            e => e.textContent
        )"""
    )

    if not account_ids:
        raise Exception("Failed to extract or parse the account number")

    for i, account_id in enumerate(account_ids):
        if len(account_ids) > 1:
            combo = await page.query_selector_all(
                'xpath=//*[contains(@class, "number") and contains(@class, "combo-inner")]'
            )
            if combo:
                await combo[0].click()

            target_span = await page.query_selector_all(
                f'xpath=//span[contains(text(), "{account_id}")]'
            )
            if target_span:
                await target_span[0].click()

        account = await _fetch_transactions_for_account(
            page,
            start_date,
            _remove_special_characters(account_id or ""),
        )
        accounts.append(account)

    return accounts


class LeumiScraper(BrowserScraper):
    """Scraper for Bank Leumi (https://www.leumi.co.il).

    Uses DOM scraping with response interception to fetch transaction data
    from Leumi's online banking after browser-based authentication.
    """

    def get_login_options(self, credentials: dict) -> LoginOptions:
        """Return Leumi-specific login configuration.

        Parameters
        ----------
        credentials : dict
            Must contain 'username' and 'password' keys.

        Returns
        -------
        LoginOptions
            Login configuration for the generic login flow.
        """
        return LoginOptions(
            login_url=LOGIN_URL,
            fields=[
                {
                    "selector": 'input[placeholder="\u05e9\u05dd \u05de\u05e9\u05ea\u05de\u05e9"]',
                    "value": credentials["username"],
                },
                {
                    "selector": 'input[placeholder="\u05e1\u05d9\u05e1\u05de\u05d4"]',
                    "value": credentials["password"],
                },
            ],
            submit_button_selector="button[type='submit']",
            check_readiness=lambda: _navigate_to_login(self.page),
            post_action=lambda: _wait_for_post_login(self.page),
            possible_results=_get_possible_login_results(self.page),
        )

    async def fetch_data(self) -> list[AccountResult]:
        """Fetch account data and transactions from Bank Leumi.

        Returns
        -------
        list[AccountResult]
            List of accounts with their transactions and balances.
        """
        minimum_start = date.today() - timedelta(days=3 * 365 - 1)
        default_start = date.today() - timedelta(days=365 - 1)
        effective_start = max(
            minimum_start, self.options.start_date or default_start
        )

        await self.navigate_to(TRANSACTIONS_URL)

        return await _fetch_transactions(self.page, effective_start)
