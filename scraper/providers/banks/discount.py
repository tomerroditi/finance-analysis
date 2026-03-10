from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from scraper.base import BrowserScraper, LoginOptions
from scraper.models.account import AccountResult
from scraper.models.result import LoginResult
from scraper.models.transaction import Transaction, TransactionStatus, TransactionType
from scraper.utils import (
    fetch_get_within_page,
    wait_for_navigation,
    wait_until_element_found,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://start.telebank.co.il"
DATE_FORMAT = "%Y%m%d"


def _convert_transactions(
    txns: list[dict] | None, txn_status: TransactionStatus
) -> list[Transaction]:
    """Convert raw Discount transaction dicts to Transaction objects.

    Parameters
    ----------
    txns : list[dict] or None
        Raw transaction data from the Discount API.
    txn_status : TransactionStatus
        Status to assign (completed or pending).

    Returns
    -------
    list[Transaction]
        Parsed transaction objects.
    """
    if not txns:
        return []

    results = []
    for txn in txns:
        operation_date = txn.get("OperationDate", "")
        value_date = txn.get("ValueDate", "")

        date_iso = ""
        if operation_date:
            try:
                date_iso = datetime.strptime(
                    str(operation_date), DATE_FORMAT
                ).isoformat()
            except ValueError:
                date_iso = str(operation_date)

        processed_date_iso = ""
        if value_date:
            try:
                processed_date_iso = datetime.strptime(
                    str(value_date), DATE_FORMAT
                ).isoformat()
            except ValueError:
                processed_date_iso = str(value_date)

        amount = txn.get("OperationAmount", 0)
        operation_number = txn.get("OperationNumber")
        identifier = str(operation_number) if operation_number is not None else None

        results.append(
            Transaction(
                type=TransactionType.NORMAL,
                identifier=identifier,
                date=date_iso,
                processed_date=processed_date_iso,
                original_amount=amount,
                original_currency="ILS",
                charged_amount=amount,
                description=txn.get("OperationDescriptionToDisplay", ""),
                status=txn_status,
            )
        )

    return results


async def _fetch_account_data(page, options) -> list[AccountResult]:
    """Fetch account data from the Discount Bank API via browser context.

    Parameters
    ----------
    page : Page
        Playwright page instance (authenticated).
    options : ScraperOptions
        Scraper options including start_date.

    Returns
    -------
    list[AccountResult]
        Account results with transactions and balances.

    Raises
    ------
    Exception
        If account data cannot be retrieved or transaction fetch fails.
    """
    api_site_url = f"{BASE_URL}/Titan/gatewayAPI"

    account_data_url = f"{api_site_url}/userAccountsData"
    account_info = await fetch_get_within_page(page, account_data_url)

    if not account_info:
        raise Exception("Failed to get account data")

    user_accounts_data = account_info.get("UserAccountsData", {})
    user_accounts = user_accounts_data.get("UserAccounts", [])
    accounts_ids = [
        acc.get("NewAccountInfo", {}).get("AccountID", "")
        for acc in user_accounts
    ]

    default_start = date.today() - timedelta(days=364)
    start_date = options.start_date
    effective_start = max(default_start, start_date)
    start_date_str = effective_start.strftime(DATE_FORMAT)

    results: list[AccountResult] = []
    for account_number in accounts_ids:
        txns_url = (
            f"{api_site_url}/lastTransactions/{account_number}/Date"
            f"?IsCategoryDescCode=True"
            f"&IsTransactionDetails=True"
            f"&IsEventNames=True"
            f"&IsFutureTransactionFlag=True"
            f"&FromDate={start_date_str}"
        )
        txns_result = await fetch_get_within_page(page, txns_url)

        if not txns_result:
            raise Exception(f"Failed to fetch transactions for account {account_number}")

        if txns_result.get("Error"):
            raise Exception(
                txns_result["Error"].get("MsgText", "Unknown error")
            )

        current_account = txns_result.get("CurrentAccountLastTransactions")
        if not current_account:
            raise Exception(
                f"No transaction data for account {account_number}"
            )

        completed_txns = _convert_transactions(
            current_account.get("OperationEntry"),
            TransactionStatus.COMPLETED,
        )

        future_block = current_account.get("FutureTransactionsBlock", {})
        pending_txns = _convert_transactions(
            future_block.get("FutureTransactionEntry") if future_block else None,
            TransactionStatus.PENDING,
        )

        balance = current_account.get("CurrentAccountInfo", {}).get(
            "AccountBalance"
        )

        results.append(
            AccountResult(
                account_number=account_number,
                transactions=[*completed_txns, *pending_txns],
                balance=balance,
            )
        )

    return results


async def _navigate_or_error_label(page) -> None:
    """Wait for navigation or an error label to appear.

    Parameters
    ----------
    page : Page
        Playwright page instance.
    """
    try:
        await wait_for_navigation(page)
    except Exception:
        try:
            await wait_until_element_found(page, "#general-error", timeout=100)
        except Exception:
            pass


def _get_possible_login_results() -> dict[LoginResult, list]:
    """Build the login result detection rules for Discount Bank.

    Returns
    -------
    dict[LoginResult, list]
        Mapping of login results to URL patterns/strings.
    """
    return {
        LoginResult.SUCCESS: [
            f"{BASE_URL}/apollo/retail/#/MY_ACCOUNT_HOMEPAGE",
            f"{BASE_URL}/apollo/retail2/#/MY_ACCOUNT_HOMEPAGE",
            f"{BASE_URL}/apollo/retail2/",
        ],
        LoginResult.INVALID_PASSWORD: [
            f"{BASE_URL}/apollo/core/templates/lobby/masterPage.html#/LOGIN_PAGE",
        ],
        LoginResult.CHANGE_PASSWORD: [
            f"{BASE_URL}/apollo/core/templates/lobby/masterPage.html#/PWD_RENEW",
        ],
    }


def _create_login_fields(credentials: dict) -> list[dict[str, str]]:
    """Build the login form field definitions for Discount Bank.

    Parameters
    ----------
    credentials : dict
        Must contain 'id', 'password', and 'num' keys.

    Returns
    -------
    list[dict[str, str]]
        Field definitions for the login flow.
    """
    return [
        {"selector": "#tzId", "value": credentials["id"]},
        {"selector": "#tzPassword", "value": credentials["password"]},
        {"selector": "#aidnum", "value": credentials["num"]},
    ]


class DiscountScraper(BrowserScraper):
    """Scraper for Discount Bank (https://www.discountbank.co.il).

    Uses browser automation to log in, then fetches transaction data
    via the bank's internal REST API (Titan gateway).
    """

    def get_login_options(self, credentials: dict) -> LoginOptions:
        """Return Discount Bank login configuration.

        Parameters
        ----------
        credentials : dict
            Must contain 'id', 'password', and 'num' keys.

        Returns
        -------
        LoginOptions
            Login configuration for the generic login flow.
        """
        return LoginOptions(
            login_url=f"{BASE_URL}/login/#/LOGIN_PAGE",
            check_readiness=lambda: wait_until_element_found(
                self.page, "#tzId"
            ),
            fields=_create_login_fields(credentials),
            submit_button_selector=".sendBtn",
            post_action=lambda: _navigate_or_error_label(self.page),
            possible_results=_get_possible_login_results(),
        )

    async def fetch_data(self) -> list[AccountResult]:
        """Fetch account data and transactions from Discount Bank.

        Returns
        -------
        list[AccountResult]
            List of accounts with their transactions and balances.
        """
        return await _fetch_account_data(self.page, self.options)
