from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta

from scraper.base import BrowserScraper, LoginOptions
from scraper.models.account import AccountResult
from scraper.models.result import LoginResult
from scraper.models.transaction import Transaction, TransactionStatus, TransactionType
from scraper.utils import (
    click_button,
    element_present_on_page,
    page_eval_all,
    wait_for_navigation,
    wait_until_element_disappear,
    wait_until_element_found,
)

logger = logging.getLogger(__name__)

SHEKEL_CURRENCY = "ILS"

LOGIN_URL = "https://login.yahav.co.il/login/"
BASE_URL = "https://digital.yahav.co.il/BaNCSDigitalUI/app/index.html#/"
INVALID_DETAILS_SELECTOR = ".ui-dialog-buttons"
CHANGE_PASSWORD_OLD_PASS = "input#ef_req_parameter_old_credential"
BASE_WELCOME_URL = f"{BASE_URL}main/home"

ACCOUNT_ID_SELECTOR = (
    'span.portfolio-value[ng-if="mainController.data.portfolioList.length === 1"]'
)
ACCOUNT_DETAILS_SELECTOR = ".account-details"
DATE_FORMAT = "%d/%m/%Y"

USER_ELEM = "#username"
PASSWD_ELEM = "#password"
NATIONALID_ELEM = "#pinno"
SUBMIT_LOGIN_SELECTOR = ".btn"


def _get_amount_data(amount_str: str) -> float:
    """Parse amount string to float, handling commas.

    Parameters
    ----------
    amount_str : str
        Amount string potentially containing commas.

    Returns
    -------
    float
        Parsed amount, or 0.0 if unparseable.
    """
    try:
        return float(amount_str.replace(",", ""))
    except (ValueError, TypeError):
        return 0.0


def _get_txn_amount(credit: str, debit: str) -> float:
    """Calculate transaction amount from credit and debit strings.

    Parameters
    ----------
    credit : str
        Credit amount string.
    debit : str
        Debit amount string.

    Returns
    -------
    float
        Net amount (credit - debit).
    """
    credit_val = _get_amount_data(credit)
    debit_val = _get_amount_data(debit)
    return credit_val - debit_val


def _convert_transactions(txns: list[dict]) -> list[Transaction]:
    """Convert raw scraped Yahav transactions to Transaction objects.

    Parameters
    ----------
    txns : list[dict]
        Raw transaction dicts with credit, debit, date, etc.

    Returns
    -------
    list[Transaction]
        Parsed transaction objects.
    """
    results: list[Transaction] = []
    for txn in txns:
        date_str = txn.get("date", "")
        try:
            txn_date = datetime.strptime(date_str, "%d/%m/%Y")
            date_iso = txn_date.isoformat()
        except (ValueError, TypeError):
            date_iso = date_str

        amount = _get_txn_amount(
            txn.get("credit", ""), txn.get("debit", "")
        )

        reference = txn.get("reference", "")
        # Remove non-digit characters from reference
        clean_ref = re.sub(r"\D+", "", reference)
        identifier = clean_ref if clean_ref else None

        results.append(
            Transaction(
                type=TransactionType.NORMAL,
                status=txn.get("status", TransactionStatus.COMPLETED),
                date=date_iso,
                processed_date=date_iso,
                original_amount=amount,
                original_currency=SHEKEL_CURRENCY,
                charged_amount=amount,
                description=txn.get("description", ""),
                identifier=identifier,
                memo=txn.get("memo") or None,
            )
        )
    return results


def _get_possible_login_results(page) -> dict[LoginResult, list]:
    """Build login result detection rules for Yahav.

    Parameters
    ----------
    page : Page
        Playwright page instance.

    Returns
    -------
    dict[LoginResult, list]
        Mapping of login results to detection checks.
    """

    async def is_invalid_password(**kwargs):
        return await element_present_on_page(page, INVALID_DETAILS_SELECTOR)

    async def is_change_password(**kwargs):
        return await element_present_on_page(page, CHANGE_PASSWORD_OLD_PASS)

    return {
        LoginResult.SUCCESS: [BASE_WELCOME_URL],
        LoginResult.INVALID_PASSWORD: [is_invalid_password],
        LoginResult.CHANGE_PASSWORD: [is_change_password],
    }


async def _wait_readiness_for_all(page) -> None:
    """Wait for all login form elements to be visible.

    Parameters
    ----------
    page : Page
        Playwright page instance.
    """
    await wait_until_element_found(page, USER_ELEM, only_visible=True)
    await wait_until_element_found(page, PASSWD_ELEM, only_visible=True)
    await wait_until_element_found(page, NATIONALID_ELEM, only_visible=True)
    await wait_until_element_found(
        page, SUBMIT_LOGIN_SELECTOR, only_visible=True
    )


async def _redirect_or_dialog(page) -> None:
    """Handle post-login redirects or bank message dialogs.

    Parameters
    ----------
    page : Page
        Playwright page instance.
    """
    import asyncio

    await wait_for_navigation(page)
    await wait_until_element_disappear(page, ".loading-bar-spinner")

    has_message = await element_present_on_page(
        page, ".messaging-links-container"
    )
    if has_message:
        await click_button(page, ".link-1")

    done, pending = await asyncio.wait(
        [
            asyncio.create_task(
                page.wait_for_selector(
                    ACCOUNT_DETAILS_SELECTOR, timeout=30000
                )
            ),
            asyncio.create_task(
                page.wait_for_selector(
                    CHANGE_PASSWORD_OLD_PASS, timeout=30000
                )
            ),
        ],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()

    await wait_until_element_disappear(page, ".loading-bar-spinner")


async def _get_account_id(page) -> str:
    """Extract the account ID from the page.

    Parameters
    ----------
    page : Page
        Playwright page instance.

    Returns
    -------
    str
        The account ID text.
    """
    try:
        element = await page.query_selector(ACCOUNT_ID_SELECTOR)
        if element:
            text = await element.text_content()
            return text or ""
    except Exception as e:
        raise Exception(
            f"Failed to retrieve account ID. "
            f"Possible outdated selector '{ACCOUNT_ID_SELECTOR}': {e}"
        )
    raise Exception(
        f"Failed to retrieve account ID. "
        f"Possible outdated selector '{ACCOUNT_ID_SELECTOR}'"
    )


async def _search_by_dates(page, start_date: date) -> None:
    """Manipulate the calendar dropdown to set the start date.

    Parameters
    ----------
    page : Page
        Playwright page instance.
    start_date : date
        The start date for the transaction search.
    """
    start_day = str(start_date.day)
    start_month = str(start_date.month)
    start_year = str(start_date.year)

    # Open the calendar date picker
    date_from_pick = (
        "div.date-options-cell:nth-child(7) > date-picker:nth-child(1) "
        "> div:nth-child(1) > span:nth-child(2)"
    )
    await wait_until_element_found(page, date_from_pick, only_visible=True)
    await click_button(page, date_from_pick)

    # Wait for days to appear
    await wait_until_element_found(
        page, ".pmu-days > div:nth-child(1)", only_visible=True
    )

    # Open months view
    month_from_pick = ".pmu-month"
    await wait_until_element_found(page, month_from_pick, only_visible=True)
    await click_button(page, month_from_pick)
    await wait_until_element_found(
        page, ".pmu-months > div:nth-child(1)", only_visible=True
    )

    # Open years view
    await wait_until_element_found(page, month_from_pick, only_visible=True)
    await click_button(page, month_from_pick)
    await wait_until_element_found(
        page, ".pmu-years > div:nth-child(1)", only_visible=True
    )

    # Select year from the 12-year grid
    for i in range(1, 13):
        selector = f".pmu-years > div:nth-child({i})"
        element = await page.query_selector(selector)
        if element:
            year_text = await element.inner_text()
            if start_year == year_text:
                await click_button(page, selector)
                break

    # Select month (1-indexed: January = 1)
    await wait_until_element_found(
        page, ".pmu-months > div:nth-child(1)", only_visible=True
    )
    month_selector = f".pmu-months > div:nth-child({start_month})"
    await click_button(page, month_selector)

    # Select day from the calendar grid (up to 42 cells)
    for i in range(1, 43):
        selector = f".pmu-days > div:nth-child({i})"
        element = await page.query_selector(selector)
        if element:
            day_text = await element.inner_text()
            if start_day == day_text:
                await click_button(page, selector)
                break


async def _get_account_transactions(page) -> list[Transaction]:
    """Extract transactions from the transactions table.

    Parameters
    ----------
    page : Page
        Playwright page instance.

    Returns
    -------
    list[Transaction]
        Parsed transaction objects.
    """
    await wait_until_element_found(
        page, ".under-line-txn-table-header", only_visible=True
    )

    transaction_divs = await page_eval_all(
        page,
        ".list-item-holder .entire-content-ctr",
        """divs => divs.map(div => ({
            id: div.getAttribute('id') || '',
            innerDivs: Array.from(div.getElementsByTagName('div')).map(
                el => el.innerText
            )
        }))""",
        [],
    )

    txns: list[dict] = []
    for row in transaction_divs or []:
        divs = row.get("innerDivs", [])
        if len(divs) < 6:
            continue
        # Remove non-digit characters from reference
        txns.append(
            {
                "date": divs[1],
                "reference": divs[2],
                "description": divs[3],
                "debit": divs[4],
                "credit": divs[5],
                "memo": "",
                "status": TransactionStatus.COMPLETED,
            }
        )

    return _convert_transactions(txns)


async def _fetch_account_data(
    page,
    start_date: date,
    account_id: str,
) -> AccountResult:
    """Fetch transaction data for a single Yahav account.

    Parameters
    ----------
    page : Page
        Playwright page instance.
    start_date : date
        Earliest transaction date.
    account_id : str
        The account identifier.

    Returns
    -------
    AccountResult
        Account with transactions.
    """
    await wait_until_element_disappear(page, ".loading-bar-spinner")
    await _search_by_dates(page, start_date)
    await wait_until_element_disappear(page, ".loading-bar-spinner")
    txns = await _get_account_transactions(page)

    return AccountResult(
        account_number=account_id,
        transactions=txns,
    )


class YahavScraper(BrowserScraper):
    """Scraper for Yahav Bank (https://www.yahav.co.il).

    Uses DOM scraping pattern to navigate and extract transaction data
    from Yahav's online banking portal with calendar-based date selection.
    """

    def get_login_options(self, credentials: dict) -> LoginOptions:
        """Return Yahav-specific login configuration.

        Parameters
        ----------
        credentials : dict
            Must contain 'username', 'password', and 'nationalID' keys.

        Returns
        -------
        LoginOptions
            Login configuration for the generic login flow.
        """
        return LoginOptions(
            login_url=LOGIN_URL,
            fields=[
                {"selector": USER_ELEM, "value": credentials["username"]},
                {"selector": PASSWD_ELEM, "value": credentials["password"]},
                {
                    "selector": NATIONALID_ELEM,
                    "value": credentials["nationalID"],
                },
            ],
            submit_button_selector=SUBMIT_LOGIN_SELECTOR,
            check_readiness=lambda: _wait_readiness_for_all(self.page),
            post_action=lambda: _redirect_or_dialog(self.page),
            possible_results=_get_possible_login_results(self.page),
        )

    async def fetch_data(self) -> list[AccountResult]:
        """Fetch account data and transactions from Yahav Bank.

        Returns
        -------
        list[AccountResult]
            List of accounts with their transactions.
        """
        # Navigate to account details / statements page
        await wait_until_element_found(
            self.page, ACCOUNT_DETAILS_SELECTOR, only_visible=True
        )
        await click_button(self.page, ACCOUNT_DETAILS_SELECTOR)
        await wait_until_element_found(
            self.page, ".statement-options .selected-item-top", only_visible=True
        )

        default_start = date.today() - timedelta(days=90 - 1)
        effective_start = max(
            default_start, self.options.start_date or default_start
        )

        account_id = await _get_account_id(self.page)
        account = await _fetch_account_data(
            self.page, effective_start, account_id
        )

        return [account]
