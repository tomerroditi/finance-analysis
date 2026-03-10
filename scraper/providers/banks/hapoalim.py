import json
import logging
import re
import uuid
from datetime import date, datetime, timedelta

from scraper.base import BrowserScraper, LoginOptions
from scraper.models.account import AccountResult
from scraper.models.result import LoginResult
from scraper.models.transaction import Transaction, TransactionStatus, TransactionType
from scraper.utils import (
    fetch_get_within_page,
    wait_for_redirect,
    wait_until,
)

logger = logging.getLogger(__name__)

DATE_FORMAT = "%Y%m%d"

BASE_URL = "https://login.bankhapoalim.co.il"


def _convert_transactions(txns: list[dict]) -> list[Transaction]:
    """Convert raw Hapoalim transaction dicts to Transaction objects.

    Parameters
    ----------
    txns : list[dict]
        Raw transaction data from the Hapoalim API.

    Returns
    -------
    list[Transaction]
        Parsed transaction objects.
    """
    results = []
    for txn in txns:
        is_outbound = txn.get("eventActivityTypeCode") == 2

        event_amount = txn.get("eventAmount", 0)
        amount = -event_amount if is_outbound else event_amount

        memo = ""
        beneficiary = txn.get("beneficiaryDetailsData")
        if beneficiary:
            memo_lines: list[str] = []
            party_headline = beneficiary.get("partyHeadline")
            if party_headline:
                memo_lines.append(party_headline)

            party_name = beneficiary.get("partyName")
            if party_name:
                memo_lines.append(f"{party_name}.")

            message_headline = beneficiary.get("messageHeadline")
            if message_headline:
                memo_lines.append(message_headline)

            message_detail = beneficiary.get("messageDetail")
            if message_detail:
                memo_lines.append(f"{message_detail}.")

            if memo_lines:
                memo = " ".join(memo_lines)

        event_date_str = txn.get("eventDate", "")
        value_date_str = txn.get("valueDate", "")

        date_iso = ""
        if event_date_str:
            try:
                date_iso = datetime.strptime(
                    str(event_date_str), DATE_FORMAT
                ).isoformat()
            except ValueError:
                date_iso = str(event_date_str)

        processed_date_iso = ""
        if value_date_str:
            try:
                processed_date_iso = datetime.strptime(
                    str(value_date_str), DATE_FORMAT
                ).isoformat()
            except ValueError:
                processed_date_iso = str(value_date_str)

        serial_number = txn.get("serialNumber")
        status = (
            TransactionStatus.PENDING
            if serial_number == 0
            else TransactionStatus.COMPLETED
        )

        reference_number = txn.get("referenceNumber")
        identifier = str(reference_number) if reference_number is not None else None

        results.append(
            Transaction(
                type=TransactionType.NORMAL,
                identifier=identifier,
                date=date_iso,
                processed_date=processed_date_iso,
                original_amount=amount,
                original_currency="ILS",
                charged_amount=amount,
                description=txn.get("activityDescription", ""),
                status=status,
                memo=memo if memo else None,
            )
        )

    return results


async def _get_rest_context(page) -> str:
    """Wait for the Hapoalim app context and extract the REST context path.

    Parameters
    ----------
    page : Page
        Playwright page instance.

    Returns
    -------
    str
        The REST context path (without leading slash).
    """
    await wait_until(
        lambda: page.evaluate("() => !!window.bnhpApp"),
        "waiting for app data load",
    )

    result = await page.evaluate("() => window.bnhpApp.restContext")
    # Remove the leading slash
    return result[1:]


async def _fetch_poalim_xsrf_within_page(page, url: str, page_uuid: str):
    """Fetch data from Hapoalim API with XSRF token and page UUID headers.

    Parameters
    ----------
    page : Page
        Playwright page instance.
    url : str
        API endpoint URL.
    page_uuid : str
        The page UUID for the API request header.

    Returns
    -------
    dict or None
        Parsed JSON response, or None on failure.
    """
    cookies = await page.context.cookies()
    xsrf_cookie = next(
        (c for c in cookies if c["name"] == "XSRF-TOKEN"), None
    )

    headers = {}
    if xsrf_cookie is not None:
        headers["X-XSRF-TOKEN"] = xsrf_cookie["value"]
    headers["pageUuid"] = page_uuid
    headers["uuid"] = str(uuid.uuid4())
    headers["Content-Type"] = "application/json;charset=UTF-8"

    js_fn = """async ([url, headers]) => {
            try {
                const response = await fetch(url, {
                    method: 'POST',
                    body: JSON.stringify([]),
                    credentials: 'include',
                    headers: headers,
                });
                if (response.status === 204) return { __data: null };
                return { __data: await response.text() };
            } catch (e) {
                return { __error: e.message };
            }
        }"""
    result = await page.evaluate(js_fn, [url, headers])
    if "__error" in result:
        raise Exception(
            f"fetchPoalimXSRFWithinPage error: {result['__error']}, url: {url}"
        )
    text = result.get("__data")
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise Exception(
            f"fetchPoalimXSRFWithinPage parse error: {e}, url: {url}"
        )


async def _get_extra_scrap(
    txns_result: dict, base_url: str, page, account_number: str
) -> dict:
    """Fetch additional PFM transaction details for each transaction.

    Parameters
    ----------
    txns_result : dict
        The initial transaction result with 'transactions' key.
    base_url : str
        Base PFM URL prefix.
    page : Page
        Playwright page instance.
    account_number : str
        The account identifier.

    Returns
    -------
    dict
        Updated transaction result with enriched reference numbers.
    """
    enriched = []
    for transaction in txns_result.get("transactions", []):
        pfm_details = transaction.get("pfmDetails", "")
        serial_number = transaction.get("serialNumber")
        if serial_number != 0 and pfm_details:
            url = f"{base_url}{pfm_details}&accountId={account_number}&lang=he"
            extra_details = await fetch_get_within_page(page, url, ignore_errors=True)
            if extra_details and isinstance(extra_details, list) and len(extra_details) > 0:
                txn_number = extra_details[0].get("transactionNumber")
                if txn_number:
                    transaction = {
                        **transaction,
                        "referenceNumber": txn_number,
                        "additionalInformation": extra_details,
                    }
        enriched.append(transaction)
    return {"transactions": enriched}


async def _get_account_transactions(
    base_url: str,
    api_site_url: str,
    page,
    account_number: str,
    start_date: str,
    end_date: str,
    additional_transaction_information: bool = False,
) -> list[Transaction]:
    """Fetch and convert transactions for a single account.

    Parameters
    ----------
    base_url : str
        The base URL for PFM detail requests.
    api_site_url : str
        The REST API base URL.
    page : Page
        Playwright page instance.
    account_number : str
        The full account identifier (bank-branch-account).
    start_date : str
        Start date in YYYYMMDD format.
    end_date : str
        End date in YYYYMMDD format.
    additional_transaction_information : bool
        Whether to fetch extra PFM details per transaction.

    Returns
    -------
    list[Transaction]
        Converted transaction objects.
    """
    txns_url = (
        f"{api_site_url}/current-account/transactions"
        f"?accountId={account_number}"
        f"&numItemsPerPage=1000"
        f"&retrievalEndDate={end_date}"
        f"&retrievalStartDate={start_date}"
        f"&sortCode=1"
    )
    txns_result = await _fetch_poalim_xsrf_within_page(
        page, txns_url, "/current-account/transactions"
    )

    final_result = txns_result
    if (
        additional_transaction_information
        and txns_result
        and txns_result.get("transactions")
    ):
        final_result = await _get_extra_scrap(
            txns_result, base_url, page, account_number
        )

    transactions = final_result.get("transactions", []) if final_result else []
    return _convert_transactions(transactions)


async def _get_account_balance(
    api_site_url: str, page, account_number: str
) -> float | None:
    """Fetch the current balance for an account.

    Parameters
    ----------
    api_site_url : str
        The REST API base URL.
    page : Page
        Playwright page instance.
    account_number : str
        The full account identifier.

    Returns
    -------
    float or None
        The current balance, or None if unavailable.
    """
    balance_url = (
        f"{api_site_url}/current-account/composite/balanceAndCreditLimit"
        f"?accountId={account_number}&view=details&lang=he"
    )
    balance_data = await fetch_get_within_page(page, balance_url, ignore_errors=True)
    if balance_data:
        return balance_data.get("currentBalance")
    return None


def _get_possible_login_results() -> dict[LoginResult, list]:
    """Build the login result detection rules for Hapoalim.

    Returns
    -------
    dict[LoginResult, list]
        Mapping of login results to URL patterns/strings.
    """
    return {
        LoginResult.SUCCESS: [
            f"{BASE_URL}/portalserver/HomePage",
            f"{BASE_URL}/ng-portals-bt/rb/he/homepage",
            f"{BASE_URL}/ng-portals/rb/he/homepage",
        ],
        LoginResult.INVALID_PASSWORD: [
            f"{BASE_URL}/AUTHENTICATE/LOGON?flow=AUTHENTICATE&state=LOGON&errorcode=1.6&callme=false",
        ],
        LoginResult.CHANGE_PASSWORD: [
            f"{BASE_URL}/MCP/START?flow=MCP&state=START&expiredDate=null",
            re.compile(r"/ABOUTTOEXPIRE/START", re.IGNORECASE),
        ],
    }


class HapoalimScraper(BrowserScraper):
    """Scraper for Bank Hapoalim (https://www.bankhapoalim.co.il).

    Uses browser automation to log in, then fetches transaction data
    via the bank's internal REST API endpoints.
    """

    def get_login_options(self, credentials: dict) -> LoginOptions:
        """Return Hapoalim-specific login configuration.

        Parameters
        ----------
        credentials : dict
            Must contain 'userCode' and 'password' keys.

        Returns
        -------
        LoginOptions
            Login configuration for the generic login flow.
        """
        return LoginOptions(
            login_url=f"{BASE_URL}/cgi-bin/poalwwwc?reqName=getLogonPage",
            fields=[
                {"selector": "#userCode", "value": credentials["userCode"]},
                {"selector": "#password", "value": credentials["password"]},
            ],
            submit_button_selector=".login-btn",
            post_action=lambda: wait_for_redirect(self.page),
            possible_results=_get_possible_login_results(),
        )

    async def fetch_data(self) -> list[AccountResult]:
        """Fetch account data and transactions from Bank Hapoalim.

        Returns
        -------
        list[AccountResult]
            List of accounts with their transactions and balances.
        """
        rest_context = await _get_rest_context(self.page)
        api_site_url = f"{BASE_URL}/{rest_context}"
        account_data_url = f"{BASE_URL}/ServerServices/general/accounts"

        logger.debug("Fetching accounts data")
        accounts_info = (
            await fetch_get_within_page(self.page, account_data_url)
        ) or []
        open_accounts = [
            acc
            for acc in accounts_info
            if acc.get("accountClosingReasonCode") == 0
        ]
        logger.debug(
            "Got %d open accounts from %d total accounts",
            len(open_accounts),
            len(accounts_info),
        )

        default_start = date.today() - timedelta(days=364)
        start_date = self.options.start_date
        effective_start = max(default_start, start_date)

        start_date_str = effective_start.strftime(DATE_FORMAT)
        end_date_str = date.today().strftime(DATE_FORMAT)

        accounts: list[AccountResult] = []
        for account in open_accounts:
            account_number = (
                f"{account['bankNumber']}-{account['branchNumber']}-{account['accountNumber']}"
            )
            logger.debug("Getting information for account %s", account_number)

            balance = await _get_account_balance(
                api_site_url, self.page, account_number
            )
            txns = await _get_account_transactions(
                BASE_URL,
                api_site_url,
                self.page,
                account_number,
                start_date_str,
                end_date_str,
            )

            accounts.append(
                AccountResult(
                    account_number=account_number,
                    transactions=txns,
                    balance=balance,
                )
            )

        logger.debug("Fetching ended")
        return accounts
