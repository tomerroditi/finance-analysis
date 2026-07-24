from __future__ import annotations

import logging
import math
import re
from datetime import date, datetime, timedelta
from typing import Optional

from scraper.base import BrowserScraper, LoginOptions
from scraper.models.account import AccountResult
from scraper.models.result import LoginResult
from scraper.models.transaction import Transaction, TransactionStatus, TransactionType
from scraper.utils import (
    fetch_post_within_page,
    page_eval_all,
    parse_int_identifier,
    parse_provider_date,
    to_amount,
    wait_for_first,
    wait_for_url,
    wait_until_element_disappear,
    wait_until_element_found,
    wait_until_iframe_found,
)

logger = logging.getLogger(__name__)

SHEKEL_CURRENCY = "ILS"

BASE_WEBSITE_URL = "https://www.mizrahi-tefahot.co.il"
LOGIN_URL = f"{BASE_WEBSITE_URL}/login/index.html#/auth-page-he"
BASE_APP_URL = "https://mto.mizrahi-tefahot.co.il"
AFTER_LOGIN_BASE_URL = re.compile(
    r"https://mto\.mizrahi-tefahot\.co\.il/OnlineApp/.*"
)
OSH_PAGE = "/osh/legacy/legacy-Osh-Main"
TRANSACTIONS_PAGE = "/osh/legacy/root-main-osh-p428New"
TRANSACTIONS_REQUEST_URLS = [
    f"{BASE_APP_URL}/OnlinePilot/api/SkyOSH/get428Index",
    f"{BASE_APP_URL}/Online/api/SkyOSH/get428Index",
]
PENDING_TRANSACTIONS_PAGE = "/osh/legacy/legacy-Osh-p420"
PENDING_TRANSACTIONS_IFRAME = "p420.aspx"
MORE_DETAILS_URL = f"{BASE_APP_URL}/Online/api/OSH/getMaherBerurimSMF"
CHANGE_PASSWORD_URL = re.compile(
    r"https://www\.mizrahi-tefahot\.co\.il/login/index\.html#/change-pass"
)
DATE_FORMAT = "%d/%m/%Y"
MAX_ROWS_PER_REQUEST = 10000000000

USERNAME_SELECTOR = "#userNumberDesktopHeb"
PASSWORD_SELECTOR = "#passwordDesktopHeb"
SUBMIT_BUTTON_SELECTOR = "button.btn.btn-primary"
INVALID_PASSWORD_SELECTOR = (
    'a[href*="https://sc.mizrahi-tefahot.co.il/SCServices/SC/P010.aspx"]'
)
AFTER_LOGIN_SELECTOR = "#dropdownBasic"
LOGIN_SPINNER_SELECTOR = "div.ngx-overlay.loading-foreground"
ACCOUNT_DROPDOWN_ITEM_SELECTOR = "#AccountPicker .item"
PENDING_TRX_IDENTIFIER_ID = "#ctl00_ContentPlaceHolder2_panel1"
CHECKING_ACCOUNT_TAB_HEBREW = "\u05e2\u05d5\u05d1\u05e8 \u05d5\u05e9\u05d1"
CHECKING_ACCOUNT_TAB_ENGLISH = "Checking Account"


def _get_start_moment(options_start_date: date) -> date:
    """Calculate effective start date for Mizrahi scraping.

    Parameters
    ----------
    options_start_date : date
        User-configured start date.

    Returns
    -------
    date
        Effective start date (max of default and configured).
    """
    default_start = date.today() - timedelta(days=365)
    return max(default_start, options_start_date)


def _get_transaction_identifier(row: dict) -> Optional[str]:
    """Extract a transaction identifier from a raw row.

    Parameters
    ----------
    row : dict
        Raw scraped transaction data.

    Returns
    -------
    Optional[str]
        Transaction identifier string, or None.
    """
    ref = row.get("MC02AsmahtaMekoritEZ")
    if not ref:
        return None
    txn_number = row.get("TransactionNumber")
    if txn_number and str(txn_number) != "1":
        return f"{ref}-{txn_number}"
    try:
        return str(int(ref))
    except (ValueError, TypeError):
        return str(ref)


async def _convert_transactions(
    txns: list[dict],
    pending_if_today: bool = False,
) -> list[Transaction]:
    """Convert raw Mizrahi transaction dicts to Transaction objects.

    Parameters
    ----------
    txns : list[dict]
        Raw transaction rows from the API.
    pending_if_today : bool
        Whether to mark today's transactions as pending.

    Returns
    -------
    list[Transaction]
        Parsed transaction objects.
    """
    results: list[Transaction] = []
    for row in txns:
        date_str = row.get("MC02PeulaTaaEZ", "")
        txn_date = parse_provider_date(date_str)
        if txn_date is None:
            logger.warning(
                "Mizrahi: dropping transaction with unparseable date %r",
                date_str,
            )
            continue
        date_iso = txn_date.isoformat()

        is_today = row.get("IsTodayTransaction", False)
        status = (
            TransactionStatus.PENDING
            if pending_if_today and is_today
            else TransactionStatus.COMPLETED
        )

        results.append(
            Transaction(
                type=TransactionType.NORMAL,
                identifier=_get_transaction_identifier(row),
                date=date_iso,
                processed_date=date_iso,
                original_amount=row.get("MC02SchumEZ", 0),
                original_currency=SHEKEL_CURRENCY,
                charged_amount=row.get("MC02SchumEZ", 0),
                description=row.get("MC02TnuaTeurEZ", ""),
                status=status,
            )
        )
    return results


async def _extract_pending_transactions(frame) -> list[Transaction]:
    """Extract pending transactions from the pending iframe.

    Unlike the completed path — which receives an already-signed amount from
    the API — this table renders unsigned magnitudes of pending *charges*.
    The amount is therefore normalized to negative (the repo-wide expense
    convention); a cell that already carries a sign is not double-negated.

    Rows whose date or amount cannot be read are dropped: the previous
    ``except -> amount = 0.0`` fallback inserted real zero-amount
    transactions whenever a cell carried a shekel sign or a bidi mark.

    The pending grid's columns are date, description, reference, amount,
    balance; the reference cell supplies the identifier (int-normalized
    the same way the completed path normalizes its asmachta) so two
    same-day, same-amount pending rows stay distinguishable.

    Parameters
    ----------
    frame : Frame
        Playwright frame containing pending transactions.

    Returns
    -------
    list[Transaction]
        Parsed pending transaction objects.
    """
    rows = await page_eval_all(
        frame,
        "tr.rgRow, tr.rgAltRow",
        """trs => trs.map(tr =>
            Array.from(tr.querySelectorAll('td'), td => td.textContent || '')
        )""",
        [],
    )

    transactions: list[Transaction] = []
    if not rows:
        return transactions

    for row in rows:
        if len(row) < 5:
            continue
        date_str = row[0]
        description = row[1]
        reference_str = row[2]
        amount_str = row[3]

        txn_date = parse_provider_date(date_str, "%d/%m/%y")
        if txn_date is None:
            continue
        date_iso = txn_date.isoformat()

        raw_amount = to_amount(amount_str, default=float("nan"))
        if math.isnan(raw_amount):
            logger.warning(
                "Mizrahi: dropping pending row with unparseable amount %r",
                amount_str,
            )
            continue

        # Pending rows are charges awaiting settlement; the table shows the
        # magnitude only. Recording it as scraped made every pending charge
        # look like income until it settled.
        amount = -abs(raw_amount)

        transactions.append(
            Transaction(
                type=TransactionType.NORMAL,
                status=TransactionStatus.PENDING,
                date=date_iso,
                processed_date=date_iso,
                original_amount=amount,
                original_currency=SHEKEL_CURRENCY,
                charged_amount=amount,
                description=description,
                identifier=parse_int_identifier(reference_str, strip=True),
            )
        )
    return transactions


def _get_possible_login_results(page) -> dict[LoginResult, list]:
    """Build login result detection rules for Mizrahi.

    Parameters
    ----------
    page : Page
        Playwright page instance.

    Returns
    -------
    dict[LoginResult, list]
        Mapping of login results to detection checks.
    """

    async def is_logged_in(**kwargs):
        target_page = kwargs.get("page", page)
        osh_xpath = (
            f'xpath=//a//span[contains(., "{CHECKING_ACCOUNT_TAB_HEBREW}") '
            f'or contains(., "{CHECKING_ACCOUNT_TAB_ENGLISH}")]'
        )
        elements = await target_page.query_selector_all(osh_xpath)
        return len(elements) > 0

    async def is_invalid_password(**kwargs):
        target_page = kwargs.get("page", page)
        el = await target_page.query_selector(INVALID_PASSWORD_SELECTOR)
        return el is not None

    return {
        LoginResult.SUCCESS: [AFTER_LOGIN_BASE_URL, is_logged_in],
        LoginResult.INVALID_PASSWORD: [is_invalid_password],
        LoginResult.CHANGE_PASSWORD: [CHANGE_PASSWORD_URL],
    }


async def _post_login(page) -> None:
    """Wait for post-login page elements.

    Parameters
    ----------
    page : Page
        Playwright page instance.
    """
    await wait_for_first(
        wait_until_element_found(page, AFTER_LOGIN_SELECTOR),
        wait_until_element_found(page, INVALID_PASSWORD_SELECTOR),
        wait_for_url(page, CHANGE_PASSWORD_URL),
    )


class MizrahiScraper(BrowserScraper):
    """Scraper for Mizrahi Tefahot Bank (https://www.mizrahi-tefahot.co.il).

    Uses complex DOM scraping with iframe handling to fetch transaction data
    from Mizrahi's online banking system.
    """

    def get_login_options(self, credentials: dict) -> LoginOptions:
        """Return Mizrahi-specific login configuration.

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
                {"selector": USERNAME_SELECTOR, "value": credentials["username"]},
                {"selector": PASSWORD_SELECTOR, "value": credentials["password"]},
            ],
            submit_button_selector=SUBMIT_BUTTON_SELECTOR,
            check_readiness=lambda: wait_until_element_disappear(
                self.page, LOGIN_SPINNER_SELECTOR
            ),
            post_action=lambda: _post_login(self.page),
            possible_results=_get_possible_login_results(self.page),
        )

    async def fetch_data(self) -> list[AccountResult]:
        """Fetch account data and transactions from Mizrahi Tefahot.

        Returns
        -------
        list[AccountResult]
            List of accounts with their transactions and balances.
        """
        # Click on account dropdown to count accounts
        await self.page.evaluate(
            """() => {
                const el = document.querySelector('#dropdownBasic, .item');
                if (el) el.click();
            }"""
        )

        account_elements = await self.page.query_selector_all(
            ACCOUNT_DROPDOWN_ITEM_SELECTOR
        )
        num_accounts = len(account_elements)

        results: list[AccountResult] = []
        for i in range(num_accounts):
            if i > 0:
                await self.page.evaluate(
                    """() => {
                        const el = document.querySelector('#dropdownBasic, .item');
                        if (el) el.click();
                    }"""
                )

            # Select the i-th account
            items = await self.page.query_selector_all(
                ACCOUNT_DROPDOWN_ITEM_SELECTOR
            )
            if i < len(items):
                await items[i].click()

            account = await self._fetch_account()
            results.append(account)

        return results

    async def _get_pending_transactions(self) -> list[Transaction]:
        """Fetch pending transactions from the pending iframe.

        Returns
        -------
        list[Transaction]
            Pending transaction objects.
        """
        await self.page.evaluate(
            f"""() => {{
                const el = document.querySelector('a[href*="{PENDING_TRANSACTIONS_PAGE}"]');
                if (el) el.click();
            }}"""
        )

        frame = await wait_until_iframe_found(
            self.page,
            lambda f: PENDING_TRANSACTIONS_IFRAME in f.url,
            "pending transactions iframe",
        )

        try:
            await wait_until_element_found(frame, PENDING_TRX_IDENTIFIER_ID)
        except Exception:
            return []

        return await _extract_pending_transactions(frame)

    async def _fetch_account(self) -> AccountResult:
        """Fetch transactions for the currently selected account.

        Returns
        -------
        AccountResult
            Account with transactions and balance.
        """
        await self.page.wait_for_selector(f'a[href*="{OSH_PAGE}"]')
        await self.page.evaluate(
            f"""() => {{
                const el = document.querySelector('a[href*="{OSH_PAGE}"]');
                if (el) el.click();
            }}"""
        )

        await wait_until_element_found(
            self.page, f'a[href*="{TRANSACTIONS_PAGE}"]'
        )
        await self.page.evaluate(
            f"""() => {{
                const el = document.querySelector('a[href*="{TRANSACTIONS_PAGE}"]');
                if (el) el.click();
            }}"""
        )

        # Get account number
        account_number_el = await self.page.query_selector(
            "#dropdownBasic b span"
        )
        account_number = ""
        if account_number_el:
            account_number = (
                await account_number_el.get_attribute("title") or ""
            )

        if not account_number:
            raise Exception("Account number not found")

        # Wait for and intercept transaction request
        start_date = _get_start_moment(self.options.start_date)

        response = None
        api_headers: dict[str, str] = {}

        for url in TRANSACTIONS_REQUEST_URLS:
            try:
                request = await self.page.wait_for_event(
                    "request",
                    predicate=lambda r, u=url: r.url == u,
                    timeout=15000,
                )

                import json

                post_data = json.loads(request.post_data or "{}")
                post_data["inFromDate"] = start_date.strftime(DATE_FORMAT)
                post_data["inToDate"] = date.today().strftime(DATE_FORMAT)
                if "table" in post_data:
                    post_data["table"]["maxRow"] = MAX_ROWS_PER_REQUEST

                api_headers = {
                    "mizrahixsrftoken": request.headers.get(
                        "mizrahixsrftoken", ""
                    ),
                    "Content-Type": request.headers.get(
                        "content-type", "application/json"
                    ),
                }

                response = await fetch_post_within_page(
                    self.page, url, post_data, api_headers
                )
                break
            except Exception:
                continue

        if not response or response.get("header", {}).get("success") is False:
            msg = ""
            if response:
                messages = response.get("header", {}).get("messages", [])
                if messages:
                    msg = messages[0].get("text", "")
            raise Exception(f"Error fetching transactions. Response: {msg}")

        # Parse transactions
        relevant_rows = [
            row
            for row in response.get("body", {}).get("table", {}).get("rows", [])
            if row.get("RecTypeSpecified")
        ]

        osh_txns = await _convert_transactions(relevant_rows)

        # Filter transactions before start date
        filtered_txns = []
        for txn in osh_txns:
            try:
                txn_date = datetime.fromisoformat(txn.date).date()
                if txn_date >= start_date:
                    filtered_txns.append(txn)
            except (ValueError, TypeError):
                filtered_txns.append(txn)

        # Get pending transactions
        pending_txns = await self._get_pending_transactions()
        all_txns = filtered_txns + pending_txns

        # Get balance
        balance_str = (
            response.get("body", {}).get("fields", {}).get("Yitra", "")
        )
        balance = float(balance_str) if balance_str else None

        return AccountResult(
            account_number=account_number,
            transactions=all_txns,
            balance=balance,
        )
