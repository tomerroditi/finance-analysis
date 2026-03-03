from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta

from playwright.async_api import Frame, Page

from scraper.base import BrowserScraper, LoginOptions
from scraper.models.account import AccountResult
from scraper.models.result import LoginResult
from scraper.models.transaction import Transaction, TransactionStatus, TransactionType
from scraper.utils import (
    click_button,
    element_present_on_page,
    fill_input,
    page_eval,
    page_eval_all,
    sleep,
    wait_for_navigation,
    wait_until_element_found,
)

logger = logging.getLogger(__name__)

DATE_FORMAT = "%d/%m/%Y"
SHEKEL_CURRENCY = "ILS"
SHEKEL_CURRENCY_SYMBOL = "\u20aa"

NO_TRANSACTION_IN_DATE_RANGE_TEXT = "\u05dc\u05d0 \u05e0\u05de\u05e6\u05d0\u05d5 \u05e0\u05ea\u05d5\u05e0\u05d9\u05dd \u05d1\u05e0\u05d5\u05e9\u05d0 \u05d4\u05de\u05d1\u05d5\u05e7\u05e9"
DATE_COLUMN_CLASS_COMPLETED = "date first"
DATE_COLUMN_CLASS_PENDING = "first date"
DESCRIPTION_COLUMN_CLASS_COMPLETED = "reference wrap_normal"
DESCRIPTION_COLUMN_CLASS_PENDING = "details wrap_normal"
REFERENCE_COLUMN_CLASS = "details"
DEBIT_COLUMN_CLASS = "debit"
CREDIT_COLUMN_CLASS = "credit"
ERROR_MESSAGE_CLASS = "NO_DATA"
ACCOUNTS_NUMBER = "div.fibi_account span.acc_num"
CLOSE_SEARCH_BY_DATES_BUTTON_CLASS = "ui-datepicker-close"
SHOW_SEARCH_BY_DATES_BUTTON_VALUE = "\u05d4\u05e6\u05d2"
COMPLETED_TRANSACTIONS_TABLE = "table#dataTable077"
PENDING_TRANSACTIONS_TABLE = "table#dataTable023"
NEXT_PAGE_LINK = "a#Npage.paging"
CURRENT_BALANCE = ".main_balance"
IFRAME_NAME = "iframe-old-pages"
ELEMENT_RENDER_TIMEOUT_MS = 10000


def _get_possible_login_results() -> dict[LoginResult, list]:
    """Build the login result detection rules for Beinleumi group.

    Returns
    -------
    dict[LoginResult, list]
        Mapping of login results to URL patterns.
    """
    return {
        LoginResult.SUCCESS: [
            re.compile(r"fibi.*accountSummary"),
            re.compile(r"Resources/PortalNG/shell"),
            re.compile(r"FibiMenu/Online"),
        ],
        LoginResult.INVALID_PASSWORD: [
            re.compile(r"FibiMenu/Marketing/Private/Home"),
        ],
    }


def _create_login_fields(credentials: dict) -> list[dict[str, str]]:
    """Build the login form field definitions.

    Parameters
    ----------
    credentials : dict
        Must contain 'username' and 'password' keys.

    Returns
    -------
    list[dict[str, str]]
        Field definitions for the login flow.
    """
    return [
        {"selector": "#username", "value": credentials["username"]},
        {"selector": "#password", "value": credentials["password"]},
    ]


def _get_amount_data(amount_str: str) -> float:
    """Parse a formatted amount string into a float.

    Parameters
    ----------
    amount_str : str
        Amount string potentially containing shekel symbol and commas.

    Returns
    -------
    float
        Parsed numeric value, or NaN if unparseable.
    """
    cleaned = amount_str.replace(SHEKEL_CURRENCY_SYMBOL, "").replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return float("nan")


def _get_txn_amount(credit: str, debit: str) -> float:
    """Calculate net transaction amount from credit and debit strings.

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
    credit_num = 0.0 if credit_val != credit_val else credit_val  # NaN check
    debit_num = 0.0 if debit_val != debit_val else debit_val
    return credit_num - debit_num


def _convert_transactions(txns: list[dict]) -> list[Transaction]:
    """Convert scraped transaction dicts to Transaction objects.

    Parameters
    ----------
    txns : list[dict]
        Raw scraped transaction dicts with date, description, reference,
        credit, debit, and status keys.

    Returns
    -------
    list[Transaction]
        Parsed transaction objects.
    """
    results = []
    for txn in txns:
        date_str = txn.get("date", "")
        if not date_str:
            continue

        try:
            converted_date = datetime.strptime(date_str, DATE_FORMAT).isoformat()
        except ValueError:
            converted_date = date_str

        amount = _get_txn_amount(txn.get("credit", ""), txn.get("debit", ""))

        reference = txn.get("reference", "").strip()
        identifier = None
        if reference:
            try:
                identifier = str(int(reference))
            except ValueError:
                identifier = reference

        results.append(
            Transaction(
                type=TransactionType.NORMAL,
                identifier=identifier,
                date=converted_date,
                processed_date=converted_date,
                original_amount=amount,
                original_currency=SHEKEL_CURRENCY,
                charged_amount=amount,
                description=txn.get("description", ""),
                memo=txn.get("memo"),
                status=txn.get("status", TransactionStatus.COMPLETED),
            )
        )

    return results


async def _get_transactions_cols_type_classes(
    page_or_frame: Page | Frame, table_locator: str
) -> dict[str, int]:
    """Map CSS class names to column indices for a transaction table.

    Parameters
    ----------
    page_or_frame : Page | Frame
        Active page or iframe.
    table_locator : str
        CSS selector for the table element.

    Returns
    -------
    dict[str, int]
        Mapping of column class name to column index.
    """
    type_classes = await page_eval_all(
        page_or_frame,
        f"{table_locator} tbody tr:first-of-type td",
        """tds => tds.map((td, index) => ({
            colClass: td.getAttribute('class'),
            index: index
        }))""",
        [],
    )
    result: dict[str, int] = {}
    for item in type_classes:
        col_class = item.get("colClass")
        if col_class:
            result[col_class] = item["index"]
    return result


def _extract_transaction_details(
    inner_tds: list[str],
    transaction_status: TransactionStatus,
    cols_types: dict[str, int],
) -> dict:
    """Extract transaction fields from a single table row.

    Parameters
    ----------
    inner_tds : list[str]
        List of cell text values for the row.
    transaction_status : TransactionStatus
        Whether this is a pending or completed transaction.
    cols_types : dict[str, int]
        Column class to index mapping.

    Returns
    -------
    dict
        Extracted transaction fields.
    """
    status_key = transaction_status.value

    if status_key == "completed":
        date_col = cols_types.get(DATE_COLUMN_CLASS_COMPLETED)
        desc_col = cols_types.get(DESCRIPTION_COLUMN_CLASS_COMPLETED)
    else:
        date_col = cols_types.get(DATE_COLUMN_CLASS_PENDING)
        desc_col = cols_types.get(DESCRIPTION_COLUMN_CLASS_PENDING)

    ref_col = cols_types.get(REFERENCE_COLUMN_CLASS)
    debit_col = cols_types.get(DEBIT_COLUMN_CLASS)
    credit_col = cols_types.get(CREDIT_COLUMN_CLASS)

    return {
        "status": transaction_status,
        "date": (inner_tds[date_col] if date_col is not None and date_col < len(inner_tds) else "").strip(),
        "description": (inner_tds[desc_col] if desc_col is not None and desc_col < len(inner_tds) else "").strip(),
        "reference": (inner_tds[ref_col] if ref_col is not None and ref_col < len(inner_tds) else "").strip(),
        "debit": (inner_tds[debit_col] if debit_col is not None and debit_col < len(inner_tds) else "").strip(),
        "credit": (inner_tds[credit_col] if credit_col is not None and credit_col < len(inner_tds) else "").strip(),
    }


async def _extract_transactions(
    page_or_frame: Page | Frame,
    table_locator: str,
    transaction_status: TransactionStatus,
) -> list[dict]:
    """Extract all transactions from a table on the page.

    Parameters
    ----------
    page_or_frame : Page | Frame
        Active page or iframe.
    table_locator : str
        CSS selector for the table.
    transaction_status : TransactionStatus
        Status to assign to extracted transactions.

    Returns
    -------
    list[dict]
        List of extracted transaction dicts.
    """
    cols_types = await _get_transactions_cols_type_classes(page_or_frame, table_locator)

    rows = await page_eval_all(
        page_or_frame,
        f"{table_locator} tbody tr",
        """trs => trs.map(tr => ({
            innerTds: Array.from(tr.getElementsByTagName('td')).map(td => td.innerText)
        }))""",
        [],
    )

    txns: list[dict] = []
    for row in rows:
        inner_tds = row.get("innerTds", [])
        txn = _extract_transaction_details(inner_tds, transaction_status, cols_types)
        if txn["date"]:
            txns.append(txn)

    return txns


async def _is_no_transaction_in_date_range_error(page_or_frame: Page | Frame) -> bool:
    """Check if the page shows a 'no data in date range' error.

    Parameters
    ----------
    page_or_frame : Page | Frame
        Active page or iframe.

    Returns
    -------
    bool
        True if the no-data error message is present.
    """
    has_error = await element_present_on_page(page_or_frame, f".{ERROR_MESSAGE_CLASS}")
    if has_error:
        error_text = await page_eval(
            page_or_frame,
            f".{ERROR_MESSAGE_CLASS}",
            "el => el.innerText",
            "",
        )
        return error_text.strip() == NO_TRANSACTION_IN_DATE_RANGE_TEXT
    return False


async def _search_by_dates(page_or_frame: Page | Frame, start_date: date) -> None:
    """Navigate the transaction page to show transactions from a specific date.

    Parameters
    ----------
    page_or_frame : Page | Frame
        Active page or iframe.
    start_date : date
        Start date for the transaction search.
    """
    await click_button(page_or_frame, "a#tabHeader4")
    await wait_until_element_found(page_or_frame, "div#fibi_dates")
    await fill_input(
        page_or_frame, "input#fromDate", start_date.strftime(DATE_FORMAT)
    )
    await click_button(
        page_or_frame,
        f"button[class*={CLOSE_SEARCH_BY_DATES_BUTTON_CLASS}]",
    )
    await click_button(
        page_or_frame,
        f"input[value={SHOW_SEARCH_BY_DATES_BUTTON_VALUE}]",
    )
    await wait_for_navigation(page_or_frame)


async def _get_account_number(page_or_frame: Page | Frame) -> str:
    """Extract the current account number from the page.

    Parameters
    ----------
    page_or_frame : Page | Frame
        Active page or iframe.

    Returns
    -------
    str
        The account number with '/' replaced by '_'.
    """
    await wait_until_element_found(
        page_or_frame, ACCOUNTS_NUMBER, only_visible=True, timeout=ELEMENT_RENDER_TIMEOUT_MS
    )
    account_text = await page_eval(
        page_or_frame, ACCOUNTS_NUMBER, "el => el.innerText", ""
    )
    return account_text.replace("/", "_").strip()


async def _get_current_balance(page_or_frame: Page | Frame) -> float:
    """Extract the current balance from the page.

    Parameters
    ----------
    page_or_frame : Page | Frame
        Active page or iframe.

    Returns
    -------
    float
        The current account balance.
    """
    await wait_until_element_found(
        page_or_frame, CURRENT_BALANCE, only_visible=True, timeout=ELEMENT_RENDER_TIMEOUT_MS
    )
    balance_str = await page_eval(
        page_or_frame, CURRENT_BALANCE, "el => el.innerText", "0"
    )
    return _get_amount_data(balance_str)


async def _check_if_has_next_page(page_or_frame: Page | Frame) -> bool:
    """Check if a next-page pagination link exists.

    Parameters
    ----------
    page_or_frame : Page | Frame
        Active page or iframe.

    Returns
    -------
    bool
        True if the next page link exists.
    """
    return await element_present_on_page(page_or_frame, NEXT_PAGE_LINK)


async def _navigate_to_next_page(page_or_frame: Page | Frame) -> None:
    """Click the next page link and wait for navigation.

    Parameters
    ----------
    page_or_frame : Page | Frame
        Active page or iframe.
    """
    await click_button(page_or_frame, NEXT_PAGE_LINK)
    await wait_for_navigation(page_or_frame)


async def _scrape_transactions(
    page_or_frame: Page | Frame,
    table_locator: str,
    transaction_status: TransactionStatus,
    need_to_paginate: bool,
) -> list[Transaction]:
    """Scrape transactions from a table, handling pagination.

    Parameters
    ----------
    page_or_frame : Page | Frame
        Active page or iframe.
    table_locator : str
        CSS selector for the transaction table.
    transaction_status : TransactionStatus
        Status to assign to transactions.
    need_to_paginate : bool
        Whether to check for and follow pagination links.

    Returns
    -------
    list[Transaction]
        Converted transaction objects.
    """
    txns: list[dict] = []
    has_next_page = False

    while True:
        current_page_txns = await _extract_transactions(
            page_or_frame, table_locator, transaction_status
        )
        txns.extend(current_page_txns)

        if need_to_paginate:
            has_next_page = await _check_if_has_next_page(page_or_frame)
            if has_next_page:
                await _navigate_to_next_page(page_or_frame)

        if not has_next_page:
            break

    return _convert_transactions(txns)


async def _get_account_transactions(
    page_or_frame: Page | Frame,
) -> list[Transaction]:
    """Fetch all transactions (pending + completed) from the current page.

    Parameters
    ----------
    page_or_frame : Page | Frame
        Active page or iframe.

    Returns
    -------
    list[Transaction]
        Combined pending and completed transactions.
    """
    # Wait for either the transactions table or the error message
    try:
        await wait_until_element_found(
            page_or_frame, "div[id*='divTable']", timeout=10000
        )
    except Exception:
        try:
            await wait_until_element_found(
                page_or_frame, f".{ERROR_MESSAGE_CLASS}", timeout=1000
            )
        except Exception:
            pass

    no_data = await _is_no_transaction_in_date_range_error(page_or_frame)
    if no_data:
        return []

    pending_txns = await _scrape_transactions(
        page_or_frame,
        PENDING_TRANSACTIONS_TABLE,
        TransactionStatus.PENDING,
        False,
    )
    completed_txns = await _scrape_transactions(
        page_or_frame,
        COMPLETED_TRANSACTIONS_TABLE,
        TransactionStatus.COMPLETED,
        True,
    )
    return [*pending_txns, *completed_txns]


async def _wait_for_post_login(page: Page) -> None:
    """Wait for the post-login page to render (new or old UI).

    Parameters
    ----------
    page : Page
        Playwright page instance.
    """
    selectors = [
        ("#card-header", False, 10000),
        ("#account_num", True, 3000),
        ("#matafLogoutLink", True, 3000),
        ("#validationMsg", True, 3000),
    ]
    for selector, only_visible, timeout in selectors:
        try:
            await wait_until_element_found(
                page, selector, only_visible=only_visible, timeout=timeout
            )
            return
        except Exception:
            pass


async def _get_transactions_frame(page: Page) -> Frame | None:
    """Attempt to find the transactions iframe (new UI).

    Parameters
    ----------
    page : Page
        Playwright page instance.

    Returns
    -------
    Frame or None
        The iframe if found, otherwise None.
    """
    for _attempt in range(3):
        await sleep(2.0)
        for frame in page.frames:
            if frame.name == IFRAME_NAME:
                return frame
    return None


async def _click_account_selector_get_account_ids(page: Page) -> list[str]:
    """Open the account dropdown and return available account labels (new UI).

    Parameters
    ----------
    page : Page
        Playwright page instance.

    Returns
    -------
    list[str]
        Available account labels, or empty list on failure.
    """
    try:
        account_selector = "div.current-account"
        dropdown_panel_selector = (
            "div.mat-mdc-autocomplete-panel.account-select-dd"
        )
        option_selector = "mat-option .mdc-list-item__primary-text"

        # Check if dropdown is already open
        dropdown_visible = await page_eval(
            page,
            dropdown_panel_selector,
            """el => {
                const style = window.getComputedStyle(el);
                return style.display !== 'none' && el.offsetParent !== null;
            }""",
            False,
        )

        if not dropdown_visible:
            await wait_until_element_found(
                page, account_selector, only_visible=True,
                timeout=ELEMENT_RENDER_TIMEOUT_MS,
            )
            await click_button(page, account_selector)
            await wait_until_element_found(
                page, dropdown_panel_selector, only_visible=True,
                timeout=ELEMENT_RENDER_TIMEOUT_MS,
            )

        account_labels = await page_eval_all(
            page,
            option_selector,
            "options => options.map(o => (o.textContent || '').trim()).filter(l => l !== '')",
            [],
        )
        return account_labels
    except Exception:
        return []


async def _get_account_ids_old_ui(page: Page) -> list[str]:
    """Get account IDs from the old UI dropdown.

    Parameters
    ----------
    page : Page
        Playwright page instance.

    Returns
    -------
    list[str]
        List of account option values.
    """
    js = """() => {
        const sel = document.getElementById('account_num_select');
        const opts = sel ? sel.querySelectorAll('option') : [];
        return Array.from(opts, o => o.value);
    }"""
    return await page.evaluate(js)


async def _get_account_ids_both_uis(page: Page) -> list[str]:
    """Get account IDs from either the new or old UI.

    Parameters
    ----------
    page : Page
        Playwright page instance.

    Returns
    -------
    list[str]
        List of account identifiers.
    """
    accounts_ids = await _click_account_selector_get_account_ids(page)
    if not accounts_ids:
        accounts_ids = await _get_account_ids_old_ui(page)
    return accounts_ids


async def _select_account_from_dropdown(page: Page, account_label: str) -> bool:
    """Select an account from the new UI dropdown.

    Parameters
    ----------
    page : Page
        Playwright page instance.
    account_label : str
        The text of the account to select.

    Returns
    -------
    bool
        True if the account was found and clicked.
    """
    available = await _click_account_selector_get_account_ids(page)
    if account_label not in available:
        return False

    option_selector = "mat-option .mdc-list-item__primary-text"
    await wait_until_element_found(
        page, option_selector, only_visible=True, timeout=ELEMENT_RENDER_TIMEOUT_MS
    )

    # Find and click the matching option via JS
    js = """(label) => {
        const options = document.querySelectorAll('mat-option .mdc-list-item__primary-text');
        for (const option of options) {
            if ((option.textContent || '').trim() === label) {
                option.click();
                return true;
            }
        }
        return false;
    }"""
    clicked = await page.evaluate(js, account_label)
    return bool(clicked)


async def _select_account_both_uis(page: Page, account_id: str) -> None:
    """Select an account using either new or old UI.

    Parameters
    ----------
    page : Page
        Playwright page instance.
    account_id : str
        Account identifier to select.
    """
    selected = await _select_account_from_dropdown(page, account_id)
    if not selected:
        await page.select_option("#account_num_select", account_id)
        await wait_until_element_found(page, "#account_num_select", only_visible=True)


async def _fetch_account_data_both_uis(
    page: Page, start_date: date
) -> dict:
    """Fetch account data using the appropriate UI (new iframe or old page).

    Parameters
    ----------
    page : Page
        Playwright page instance.
    start_date : date
        Start date for the transaction search.

    Returns
    -------
    dict
        Dict with 'accountNumber', 'txns', and 'balance' keys.
    """
    frame = await _get_transactions_frame(page)
    target: Page | Frame = frame if frame else page
    return await _fetch_single_account_data(target, start_date)


async def _fetch_single_account_data(
    page_or_frame: Page | Frame, start_date: date
) -> dict:
    """Fetch transactions and balance for the currently selected account.

    Parameters
    ----------
    page_or_frame : Page | Frame
        Active page or iframe.
    start_date : date
        Start date for the transaction search.

    Returns
    -------
    dict
        Dict with 'accountNumber', 'txns', and 'balance' keys.
    """
    account_number = await _get_account_number(page_or_frame)
    balance = await _get_current_balance(page_or_frame)
    await _search_by_dates(page_or_frame, start_date)
    txns = await _get_account_transactions(page_or_frame)

    return {
        "accountNumber": account_number,
        "txns": txns,
        "balance": balance,
    }


async def _fetch_accounts(
    page: Page, start_date: date
) -> list[AccountResult]:
    """Fetch data for all accounts on the page.

    Parameters
    ----------
    page : Page
        Playwright page instance.
    start_date : date
        Start date for the transaction search.

    Returns
    -------
    list[AccountResult]
        Account results with transactions and balances.
    """
    accounts_ids = await _get_account_ids_both_uis(page)

    if not accounts_ids:
        account_data = await _fetch_account_data_both_uis(page, start_date)
        return [
            AccountResult(
                account_number=account_data["accountNumber"],
                transactions=account_data["txns"],
                balance=account_data["balance"],
            )
        ]

    results: list[AccountResult] = []
    for account_id in accounts_ids:
        await _select_account_both_uis(page, account_id)
        account_data = await _fetch_account_data_both_uis(page, start_date)
        results.append(
            AccountResult(
                account_number=account_data["accountNumber"],
                transactions=account_data["txns"],
                balance=account_data["balance"],
            )
        )

    return results


class BeinleumiGroupBaseScraper(BrowserScraper):
    """Base scraper for the Beinleumi banking group.

    Handles login and transaction fetching via DOM scraping for banks
    in the Beinleumi group (Beinleumi, Otsar Hahayal, Massad, Pagi).
    Subclasses set BASE_URL, LOGIN_URL, and TRANSACTIONS_URL.
    """

    BASE_URL: str = ""
    LOGIN_URL: str = ""
    TRANSACTIONS_URL: str = ""

    def get_login_options(self, credentials: dict) -> LoginOptions:
        """Return Beinleumi group login configuration.

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
            login_url=self.LOGIN_URL,
            fields=_create_login_fields(credentials),
            submit_button_selector="#continueBtn",
            post_action=lambda: _wait_for_post_login(self.page),
            possible_results=_get_possible_login_results(),
            pre_action=lambda: sleep(1.0),
        )

    async def fetch_data(self) -> list[AccountResult]:
        """Fetch account data and transactions from the Beinleumi group bank.

        Returns
        -------
        list[AccountResult]
            List of accounts with their transactions and balances.
        """
        default_start = date.today() - timedelta(days=364)
        start_date = self.options.start_date
        effective_start = max(default_start, start_date)

        await self.navigate_to(self.TRANSACTIONS_URL)

        accounts = await _fetch_accounts(self.page, effective_start)

        logger.debug("Fetching ended with %d accounts", len(accounts))
        return accounts
