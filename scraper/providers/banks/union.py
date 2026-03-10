from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, timedelta

from scraper.base import BrowserScraper, LoginOptions
from scraper.models.account import AccountResult
from scraper.models.result import LoginResult
from scraper.models.transaction import Transaction, TransactionStatus, TransactionType
from scraper.utils import (
    click_button,
    dropdown_elements,
    dropdown_select,
    element_present_on_page,
    fill_input,
    page_eval_all,
    wait_for_navigation,
    wait_until_element_found,
)

logger = logging.getLogger(__name__)

SHEKEL_CURRENCY = "ILS"

BASE_URL = "https://hb.unionbank.co.il"
TRANSACTIONS_URL = f"{BASE_URL}/eBanking/Accounts/ExtendedActivity.aspx#/"
DATE_FORMAT = "%d/%m/%y"
NO_TRANSACTION_IN_DATE_RANGE_TEXT = (
    "\u05dc\u05d0 \u05e7\u05d9\u05d9\u05de\u05d5\u05ea "
    "\u05ea\u05e0\u05d5\u05e2\u05d5\u05ea \u05de\u05ea\u05d0\u05d9\u05de\u05d5\u05ea "
    "\u05e2\u05dc \u05e4\u05d9 \u05d4\u05e1\u05d9\u05e0\u05d5\u05df "
    "\u05e9\u05d4\u05d5\u05d2\u05d3\u05e8"
)

DATE_HEADER = "\u05ea\u05d0\u05e8\u05d9\u05da"
DESCRIPTION_HEADER = "\u05ea\u05d9\u05d0\u05d5\u05e8"
REFERENCE_HEADER = "\u05d0\u05e1\u05de\u05db\u05ea\u05d0"
DEBIT_HEADER = "\u05d7\u05d5\u05d1\u05d4"
CREDIT_HEADER = "\u05d6\u05db\u05d5\u05ea"

PENDING_TRANSACTIONS_TABLE_ID = "trTodayActivityNapaTableUpper"
COMPLETED_TRANSACTIONS_TABLE_ID = "ctlActivityTable"
ERROR_MESSAGE_CLASS = "errInfo"
ACCOUNTS_DROPDOWN_SELECTOR = "select#ddlAccounts_m_ddl"


def _get_amount_data(amount_str: str) -> float:
    """Parse amount string to float.

    Parameters
    ----------
    amount_str : str
        Amount string with optional commas.

    Returns
    -------
    float
        Parsed amount, or NaN if unparseable.
    """
    try:
        return float(amount_str.replace(",", ""))
    except (ValueError, TypeError):
        return float("nan")


def _get_txn_amount(credit: str, debit: str) -> float:
    """Calculate net transaction amount.

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
    import math

    credit_val = _get_amount_data(credit)
    debit_val = _get_amount_data(debit)
    return (0 if math.isnan(credit_val) else credit_val) - (
        0 if math.isnan(debit_val) else debit_val
    )


def _convert_transactions(txns: list[dict]) -> list[Transaction]:
    """Convert raw Union Bank transactions to Transaction objects.

    Parameters
    ----------
    txns : list[dict]
        Raw transaction dicts.

    Returns
    -------
    list[Transaction]
        Converted transaction objects.
    """
    results: list[Transaction] = []
    for txn in txns:
        date_str = txn.get("date", "")
        try:
            txn_date = datetime.strptime(date_str, "%d/%m/%y")
            date_iso = txn_date.isoformat()
        except (ValueError, TypeError):
            date_iso = date_str

        amount = _get_txn_amount(
            txn.get("credit", ""), txn.get("debit", "")
        )

        reference = txn.get("reference", "")
        try:
            identifier = str(int(reference)) if reference else None
        except (ValueError, TypeError):
            identifier = reference if reference else None

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


def _get_possible_login_results() -> dict[LoginResult, list]:
    """Build login result detection rules for Union Bank.

    Returns
    -------
    dict[LoginResult, list]
        Mapping of login results to URL patterns.
    """
    return {
        LoginResult.SUCCESS: [re.compile(r"eBanking/Accounts")],
        LoginResult.INVALID_PASSWORD: [
            re.compile(r"InternalSite/CustomUpdate/leumi/LoginPage\.ASP")
        ],
    }


async def _get_transactions_table_headers(
    page, table_type_id: str
) -> dict[str, int]:
    """Extract column header indices from a transactions table.

    Parameters
    ----------
    page : Page
        Playwright page instance.
    table_type_id : str
        ID of the transactions table element.

    Returns
    -------
    dict[str, int]
        Mapping of header text to column index.
    """
    headers = await page_eval_all(
        page,
        f"#WorkSpaceBox #{table_type_id} tr[class='header'] th",
        """ths => ths.map((th, index) => ({
            text: th.innerText.trim(),
            index: index
        }))""",
        [],
    )

    return {h["text"]: h["index"] for h in (headers or [])}


async def _extract_transactions_from_table(
    page,
    table_type_id: str,
    txn_status: TransactionStatus,
) -> list[dict]:
    """Extract raw transaction data from a table on the page.

    Parameters
    ----------
    page : Page
        Playwright page instance.
    table_type_id : str
        ID of the transactions table element.
    txn_status : TransactionStatus
        Status to assign to extracted transactions.

    Returns
    -------
    list[dict]
        Raw transaction dicts.
    """
    txns: list[dict] = []
    headers = await _get_transactions_table_headers(page, table_type_id)

    rows = await page_eval_all(
        page,
        f"#WorkSpaceBox #{table_type_id} tr[class]:not([class='header'])",
        """trs => trs.map(tr => ({
            id: tr.getAttribute('id') || '',
            innerTds: Array.from(
                tr.getElementsByTagName('td')
            ).map(td => td.innerText)
        }))""",
        [],
    )

    for row in rows or []:
        row_id = row.get("id", "")
        tds = row.get("innerTds", [])

        if row_id == "rowAdded":
            # Expanded description row - append to last transaction
            if txns and tds:
                txns[-1]["description"] = (
                    f"{txns[-1]['description']} {tds[0]}"
                )
        else:
            txns.append(
                {
                    "status": txn_status,
                    "date": (
                        tds[headers[DATE_HEADER]].strip()
                        if DATE_HEADER in headers and len(tds) > headers[DATE_HEADER]
                        else ""
                    ),
                    "description": (
                        tds[headers[DESCRIPTION_HEADER]].strip()
                        if DESCRIPTION_HEADER in headers and len(tds) > headers[DESCRIPTION_HEADER]
                        else ""
                    ),
                    "reference": (
                        tds[headers[REFERENCE_HEADER]].strip()
                        if REFERENCE_HEADER in headers and len(tds) > headers[REFERENCE_HEADER]
                        else ""
                    ),
                    "debit": (
                        tds[headers[DEBIT_HEADER]].strip()
                        if DEBIT_HEADER in headers and len(tds) > headers[DEBIT_HEADER]
                        else ""
                    ),
                    "credit": (
                        tds[headers[CREDIT_HEADER]].strip()
                        if CREDIT_HEADER in headers and len(tds) > headers[CREDIT_HEADER]
                        else ""
                    ),
                    "memo": "",
                }
            )

    return txns


async def _is_no_transaction_in_date_range(page) -> bool:
    """Check if the 'no transactions' error is shown.

    Parameters
    ----------
    page : Page
        Playwright page instance.

    Returns
    -------
    bool
        True if no transactions exist in the date range.
    """
    has_error = await element_present_on_page(page, f".{ERROR_MESSAGE_CLASS}")
    if has_error:
        element = await page.query_selector(f".{ERROR_MESSAGE_CLASS}")
        if element:
            error_text = await element.inner_text()
            return error_text.strip() == NO_TRANSACTION_IN_DATE_RANGE_TEXT
    return False


async def _search_by_dates(page, start_date: date) -> None:
    """Set the date filter on the transactions page.

    Parameters
    ----------
    page : Page
        Playwright page instance.
    start_date : date
        Start date for filtering.
    """
    await dropdown_select(page, "select#ddlTransactionPeriod", "004")
    await wait_until_element_found(page, "select#ddlTransactionPeriod")
    await fill_input(
        page, "input#dtFromDate_textBox", start_date.strftime("%d/%m/%y")
    )
    await click_button(page, "input#btnDisplayDates")
    await wait_for_navigation(page)


async def _get_account_number(page) -> str:
    """Get the currently selected account number.

    Parameters
    ----------
    page : Page
        Playwright page instance.

    Returns
    -------
    str
        Account number with '/' replaced by '_'.
    """
    element = await page.query_selector(
        '#ddlAccounts_m_ddl option[selected="selected"]'
    )
    if element:
        text = await element.inner_text()
        return text.replace("/", "_")
    return ""


async def _expand_transactions_table(page) -> None:
    """Click 'expand all' button if present.

    Parameters
    ----------
    page : Page
        Playwright page instance.
    """
    has_expand = await element_present_on_page(
        page, "a[id*='lnkCtlExpandAll']"
    )
    if has_expand:
        await click_button(page, "a[id*='lnkCtlExpandAll']")


async def _get_account_transactions(page) -> list[Transaction]:
    """Extract all transactions from the current page.

    Parameters
    ----------
    page : Page
        Playwright page instance.

    Returns
    -------
    list[Transaction]
        All transactions (pending + completed).
    """
    done, pending_tasks = await asyncio.wait(
        [
            asyncio.create_task(
                wait_until_element_found(
                    page, f"#{COMPLETED_TRANSACTIONS_TABLE_ID}"
                )
            ),
            asyncio.create_task(
                wait_until_element_found(page, f".{ERROR_MESSAGE_CLASS}")
            ),
        ],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending_tasks:
        task.cancel()

    if await _is_no_transaction_in_date_range(page):
        return []

    await _expand_transactions_table(page)

    pending_txns = await _extract_transactions_from_table(
        page, PENDING_TRANSACTIONS_TABLE_ID, TransactionStatus.PENDING
    )
    completed_txns = await _extract_transactions_from_table(
        page, COMPLETED_TRANSACTIONS_TABLE_ID, TransactionStatus.COMPLETED
    )
    all_txns = [*pending_txns, *completed_txns]
    return _convert_transactions(all_txns)


async def _fetch_account_data(
    page,
    start_date: date,
    account_id: str,
) -> AccountResult:
    """Fetch transaction data for a single account.

    Parameters
    ----------
    page : Page
        Playwright page instance.
    start_date : date
        Earliest date for transactions.
    account_id : str
        Dropdown value for the account.

    Returns
    -------
    AccountResult
        Account with transactions.
    """
    # Select account if there is a dropdown
    has_dropdown = await element_present_on_page(
        page, ACCOUNTS_DROPDOWN_SELECTOR
    )
    if has_dropdown:
        await dropdown_select(page, ACCOUNTS_DROPDOWN_SELECTOR, account_id)

    await _search_by_dates(page, start_date)
    account_number = await _get_account_number(page)
    txns = await _get_account_transactions(page)

    return AccountResult(
        account_number=account_number,
        transactions=txns,
    )


async def _fetch_accounts(
    page, start_date: date
) -> list[AccountResult]:
    """Fetch transactions for all accounts.

    Parameters
    ----------
    page : Page
        Playwright page instance.
    start_date : date
        Earliest transaction date.

    Returns
    -------
    list[AccountResult]
        List of account results.
    """
    accounts: list[AccountResult] = []
    accounts_list = await dropdown_elements(page, ACCOUNTS_DROPDOWN_SELECTOR)

    for account in accounts_list:
        if account.get("value") != "-1":
            account_data = await _fetch_account_data(
                page, start_date, account["value"]
            )
            accounts.append(account_data)

    return accounts


async def _wait_for_post_login(page) -> None:
    """Wait for post-login page to load.

    Parameters
    ----------
    page : Page
        Playwright page instance.
    """
    done, pending = await asyncio.wait(
        [
            asyncio.create_task(
                wait_until_element_found(page, "#signoff", only_visible=True)
            ),
            asyncio.create_task(
                wait_until_element_found(page, "#restore", only_visible=True)
            ),
        ],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()


class UnionBankScraper(BrowserScraper):
    """Scraper for Union Bank (https://www.unionbank.co.il).

    Uses DOM scraping with table parsing to extract transaction data
    from Union Bank's online banking interface.
    """

    def get_login_options(self, credentials: dict) -> LoginOptions:
        """Return Union Bank-specific login configuration.

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
            login_url=BASE_URL,
            fields=[
                {"selector": "#uid", "value": credentials["username"]},
                {"selector": "#password", "value": credentials["password"]},
            ],
            submit_button_selector="#enter",
            post_action=lambda: _wait_for_post_login(self.page),
            possible_results=_get_possible_login_results(),
        )

    async def fetch_data(self) -> list[AccountResult]:
        """Fetch account data and transactions from Union Bank.

        Returns
        -------
        list[AccountResult]
            List of accounts with their transactions.
        """
        default_start = date.today() - timedelta(days=365 - 1)
        effective_start = max(
            default_start, self.options.start_date or default_start
        )

        await self.navigate_to(TRANSACTIONS_URL)

        return await _fetch_accounts(self.page, effective_start)
