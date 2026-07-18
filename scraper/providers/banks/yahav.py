from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta

from scraper.base import BrowserScraper, LoginOptions
from scraper.models.account import AccountResult
from scraper.models.result import LoginResult
from scraper.models.transaction import Transaction, TransactionStatus
from scraper.utils import (
    click_button,
    convert_credit_debit_rows,
    element_present_on_page,
    page_eval,
    page_eval_all,
    parse_digits_identifier,
    wait_for_first,
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

# Portfolio selectors (upstream 2026-06-12, commit 4521667). Multi-portfolio
# accounts render an <inline-drop-down> inside form[name="formPortfolioSelect"]
# with the current portfolio at .selected-item-top and the others as <li>s;
# single-portfolio accounts render only the single value span.
PORTFOLIO_FORM = 'form[name="formPortfolioSelect"]'
ACCOUNT_ID_SELECTOR_SINGLE = "span.portfolio-value"
ACCOUNT_ID_SELECTOR_MULTI = f"{PORTFOLIO_FORM} .selected-item-top"
PORTFOLIO_OPTION_SELECTOR = (
    f"{PORTFOLIO_FORM} .drop-down-item-list li.drop-down-item"
)
ACCOUNT_DETAILS_SELECTOR = ".account-details"
DATE_FORMAT = "%d/%m/%Y"

# All datepicker selectors are scoped to the "from date" control to avoid
# ambiguity with the "to date" picker.
FROM_PICKER = 'date-picker-access[btn-label="from"]'

USER_ELEM = "#username"
PASSWD_ELEM = "#password"
NATIONALID_ELEM = "#pinno"
SUBMIT_LOGIN_SELECTOR = ".btn"


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
    return convert_credit_debit_rows(
        txns,
        date_format=DATE_FORMAT,
        parse_identifier=parse_digits_identifier,
        currency=SHEKEL_CURRENCY,
    )


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
    await wait_for_navigation(page)
    await wait_until_element_disappear(page, ".loading-bar-spinner")

    has_message = await element_present_on_page(
        page, ".messaging-links-container"
    )
    if has_message:
        await click_button(page, ".link-1")

    await wait_for_first(
        page.wait_for_selector(ACCOUNT_DETAILS_SELECTOR, timeout=30000),
        page.wait_for_selector(CHANGE_PASSWORD_OLD_PASS, timeout=30000),
    )

    await wait_until_element_disappear(page, ".loading-bar-spinner")


async def _get_portfolio_ids(page) -> list[str]:
    """Snapshot the list of portfolio IDs available on the home page.

    The dropdown only lists *unselected* portfolios, so the IDs are captured
    up front (selected-first) before any portfolio switch loses the ones not
    yet scraped. Single-portfolio accounts render only the single value span.

    Parameters
    ----------
    page : Page
        Playwright page instance.

    Returns
    -------
    list[str]
        Portfolio IDs, selected portfolio first. Empty if none found.
    """
    await wait_for_first(
        page.wait_for_selector(ACCOUNT_ID_SELECTOR_MULTI, timeout=10000),
        page.wait_for_selector(ACCOUNT_ID_SELECTOR_SINGLE, timeout=10000),
    )

    selected_el = await page.query_selector(ACCOUNT_ID_SELECTOR_MULTI)
    if selected_el:
        selected = ((await selected_el.text_content()) or "").strip()
        if selected:
            option_els = await page.query_selector_all(PORTFOLIO_OPTION_SELECTOR)
            others = [
                ((await el.text_content()) or "").strip() for el in option_els
            ]
            return [pid for pid in [selected, *others] if pid]

    single_el = await page.query_selector(ACCOUNT_ID_SELECTOR_SINGLE)
    if single_el:
        single = ((await single_el.text_content()) or "").strip()
        return [single] if single else []
    return []


async def _select_portfolio(page, target_id: str) -> None:
    """Select a portfolio by its ID from the dropdown.

    Angular's listItemAction navigates the page back to /main/home with the
    new portfolio selected, so the caller must re-enter the statements flow
    after this returns.

    Parameters
    ----------
    page : Page
        Playwright page instance.
    target_id : str
        The portfolio ID (trimmed text) to select.
    """
    option_els = await page.query_selector_all(PORTFOLIO_OPTION_SELECTOR)
    for el in option_els:
        text = ((await el.text_content()) or "").strip()
        if text == target_id:
            await el.click()
            await wait_until_element_disappear(page, ".loading-bar-spinner")
            return
    raise Exception(f"Portfolio option not found for ID: {target_id}")


async def _search_by_dates(page, start_date: date) -> None:
    """Set the "from" date by stepping the datepicker calendar back.

    Opens the "from" picker, reads its current input value (always
    ``DD/MM/YYYY``) to learn which month it opened on, steps back the required
    number of months, then clicks the target day. Reading the input value
    avoids parsing the header text, which renders in the account's locale.

    Parameters
    ----------
    page : Page
        Playwright page instance.
    start_date : date
        The start date for the transaction search.
    """
    open_button = f"{FROM_PICKER} a.datepicker-button"
    await wait_until_element_found(page, open_button, only_visible=True)
    await click_button(page, open_button)
    await wait_until_element_found(
        page, f"{FROM_PICKER} .datepicker-calendar", only_visible=True
    )

    input_value = await page_eval(
        page, f"{FROM_PICKER} .date-picker-input", "el => el.value", ""
    )
    try:
        displayed = datetime.strptime(input_value, "%d/%m/%Y").date()
    except (ValueError, TypeError):
        displayed = date.today()

    months_to_go_back = (displayed.year - start_date.year) * 12 + (
        displayed.month - start_date.month
    )
    prev_month_selector = f"{FROM_PICKER} .datepicker-month-prev.enabled"
    for _ in range(max(0, months_to_go_back)):
        await wait_until_element_found(page, prev_month_selector, only_visible=True)
        await click_button(page, prev_month_selector)

    # :not(.other-month) avoids adjacent-month cells sharing the same day number.
    day_selector = (
        f'{FROM_PICKER} .datepicker-calendar td.day.selectable:not(.other-month)'
        f'[data-value="{start_date.day}"]'
    )
    await wait_until_element_found(page, day_selector, only_visible=True)
    await click_button(page, day_selector)


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


async def _fetch_accounts(page, start_date: date) -> list[AccountResult]:
    """Iterate every portfolio, entering the statements flow for each.

    Portfolio IDs are snapshotted up front (the dropdown only lists the
    unselected portfolios, so after the first switch the rest would be lost).
    For each portfolio the statements page is (re-)entered, since selecting a
    portfolio navigates back to /main/home.

    Parameters
    ----------
    page : Page
        Playwright page instance.
    start_date : date
        Earliest transaction date.

    Returns
    -------
    list[AccountResult]
        One result per portfolio.
    """
    portfolio_ids = await _get_portfolio_ids(page)
    if not portfolio_ids:
        raise Exception(
            "No portfolios found on /main/home — Yahav DOM likely changed"
        )

    accounts: list[AccountResult] = []
    for i, portfolio_id in enumerate(portfolio_ids):
        if i > 0:
            await _select_portfolio(page, portfolio_id)
        await wait_until_element_found(
            page, ACCOUNT_DETAILS_SELECTOR, only_visible=True
        )
        await click_button(page, ACCOUNT_DETAILS_SELECTOR)
        await wait_until_element_found(
            page, ".statement-options .selected-item-top", only_visible=True
        )
        accounts.append(
            await _fetch_account_data(page, start_date, portfolio_id)
        )

    return accounts


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
            One result per portfolio, each with its transactions.
        """
        # Wait for the home page; the statements flow is (re-)entered per
        # portfolio inside _fetch_accounts.
        await wait_until_element_found(
            self.page, ACCOUNT_DETAILS_SELECTOR, only_visible=True
        )

        default_start = date.today() - relativedelta(months=3) + timedelta(days=1)
        start = self.options.start_date or default_start
        # Clamp to [default_start, today]: never earlier than the default
        # window, never in the future.
        effective_start = min(max(default_start, start), date.today())

        return await _fetch_accounts(self.page, effective_start)
