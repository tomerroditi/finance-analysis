import json
import logging
import random
import re
import uuid
from datetime import date, datetime, timedelta

from scraper.base import BrowserScraper
from scraper.models.account import AccountResult
from scraper.models.result import LoginResult
from scraper.models.transaction import Transaction, TransactionStatus, TransactionType
from scraper.utils import (
    fetch_get_within_page,
    wait_until,
    wait_until_element_found,
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


LOGIN_URL = f"{BASE_URL}/cgi-bin/poalwwwc?reqName=getLogonPage"

# OTP modal selectors. Hapoalim renders an Angular ``auth-otp-login`` modal on
# the SAME URL as the login form when 2FA is needed (new-device check), so
# detection must be DOM-based, not URL-based. The five digit inputs carry
# ``data-testid="separated-{0..4}"`` and the submit button is the only
# ``type="submit"`` inside ``auth-otp-login``.
OTP_MODAL_SELECTOR = "auth-otp-login"
OTP_FIRST_INPUT_SELECTOR = 'auth-otp-login input[data-testid="separated-0"]'
OTP_SUBMIT_SELECTOR = 'auth-otp-login button[type="submit"]'
OTP_LENGTH = 5

# Substrings the live page transitions to once the bank has resolved the login
# attempt. We pass these into a single ``wait_for_function`` that races against
# the OTP modal showing up, so we exit the wait as soon as *either* path fires.
_SUCCESS_URL_SUBSTRINGS = [
    "/portalserver/HomePage",
    "/ng-portals-bt/rb/he/homepage",
    "/ng-portals/rb/he/homepage",
]
_ERROR_URL_SUBSTRINGS = [
    "errorcode=1.6",  # invalid password
    "/MCP/START",  # password expired
    "/ABOUTTOEXPIRE/START",  # password expiring soon
]


class HapoalimScraper(BrowserScraper):
    """Scraper for Bank Hapoalim (https://www.bankhapoalim.co.il).

    Uses browser automation to log in, then fetches transaction data
    via the bank's internal REST API endpoints. The login flow handles
    Hapoalim's *conditional* SMS-OTP challenge: the bank only asks for
    a one-time code when it doesn't recognise the device, so the
    scraper detects the OTP modal at runtime instead of always
    expecting it.
    """

    async def login(self) -> LoginResult:
        """Log in to Hapoalim, handling the SMS-OTP challenge if it appears.

        Flow:

        1. Navigate to the login page and fill ``userCode`` + ``password``
           with human-like timing (Hapoalim fingerprints bots).
        2. Click the submit button, then race-wait for either:

           - a URL match against a known SUCCESS / INVALID_PASSWORD /
             CHANGE_PASSWORD pattern, OR
           - the ``auth-otp-login`` modal being injected into the DOM
             (only happens when the bank doesn't trust the device).

        3. If the OTP modal appeared, request the code from the user
           (the adapter flips the scraping status to WAITING_FOR_2FA at
           this point), type it into the five separated inputs, submit
           the modal, then re-check the URL against the result patterns.

        Returns
        -------
        LoginResult
            SUCCESS / INVALID_PASSWORD / CHANGE_PASSWORD / UNKNOWN_ERROR.
        """
        try:
            possible_results = _get_possible_login_results()

            self._emit_progress("navigating to login page")
            await self.navigate_to(LOGIN_URL)
            await wait_until_element_found(self.page, ".login-btn")

            await self._human_delay(0.5, 1.0)
            await self._human_mouse_move()
            await self._human_delay(0.3, 0.7)

            self._emit_progress("filling login credentials")
            await self.page.click("#userCode")
            await self._human_delay(0.1, 0.3)
            await self._type_like_human("#userCode", self.credentials["userCode"])
            await self._human_delay(0.3, 0.8)

            await self.page.click("#password")
            await self._human_delay(0.1, 0.3)
            await self._type_like_human("#password", self.credentials["password"])
            await self._human_delay(0.5, 1.0)

            self._emit_progress("submitting login form")
            await self.page.click(".login-btn")

            post_state = await self._wait_for_post_login_state()

            if post_state == "needs_otp":
                otp_result = await self._handle_otp_challenge()
                if otp_result != LoginResult.SUCCESS:
                    return otp_result

            return await self._detect_login_result(possible_results)

        except Exception as exc:
            logger.error("Hapoalim login failed: %s", exc)
            return LoginResult.UNKNOWN_ERROR

    async def _wait_for_post_login_state(self) -> str:
        """Race-wait for the post-submit state.

        Returns
        -------
        str
            ``"needs_otp"`` if the auth-otp-login modal appears,
            ``"resolved"`` if the URL transitions to a known result pattern.
        """
        js_fn = """([successSubs, errorSubs, otpSelector]) => {
            const url = window.location.href.toLowerCase();
            const lower = (s) => s.toLowerCase();
            if (successSubs.some(s => url.includes(lower(s)))) return 'resolved';
            if (errorSubs.some(s => url.includes(lower(s)))) return 'resolved';
            if (document.querySelector(otpSelector)) return 'needs_otp';
            return false;
        }"""
        handle = await self.page.wait_for_function(
            js_fn,
            arg=[
                _SUCCESS_URL_SUBSTRINGS,
                _ERROR_URL_SUBSTRINGS,
                OTP_MODAL_SELECTOR,
            ],
            timeout=self.options.default_timeout,
        )
        return await handle.json_value()

    async def _handle_otp_challenge(self) -> LoginResult:
        """Request OTP from the user and submit it via the modal.

        Returns
        -------
        LoginResult
            SUCCESS if the modal was successfully submitted and the page
            navigated to a homepage URL; UNKNOWN_ERROR on cancellation or
            invalid input.
        """
        if self.on_otp_request is None:
            logger.error(
                "Hapoalim 2FA modal appeared but no on_otp_request callback "
                "is configured — provider is misregistered"
            )
            return LoginResult.UNKNOWN_ERROR

        self._emit_progress("waiting for OTP code")
        otp_code = await self.on_otp_request()

        if otp_code == "cancel":
            return LoginResult.UNKNOWN_ERROR

        digits = (otp_code or "").strip()
        if len(digits) != OTP_LENGTH or not digits.isdigit():
            logger.error(
                "Hapoalim OTP must be %d digits, got %r",
                OTP_LENGTH, otp_code,
            )
            return LoginResult.UNKNOWN_ERROR

        self._emit_progress("submitting OTP code")
        # Focus the first separated input; the Angular component auto-advances
        # focus to the next input on each keystroke, so we can just type the
        # digits through the keyboard API.
        await self.page.click(OTP_FIRST_INPUT_SELECTOR)
        await self._human_delay(0.2, 0.4)
        for digit in digits:
            await self.page.keyboard.type(digit, delay=random.randint(50, 150))
            await self._human_delay(0.05, 0.15)

        await self._human_delay(0.3, 0.7)

        await self.page.wait_for_selector(
            f"{OTP_SUBMIT_SELECTOR}:not([disabled])", timeout=10000
        )
        await self.page.click(OTP_SUBMIT_SELECTOR)

        self._emit_progress("waiting for login to complete")
        try:
            await self.page.wait_for_function(
                """([successSubs]) => {
                    const url = window.location.href.toLowerCase();
                    return successSubs.some(s => url.includes(s.toLowerCase()));
                }""",
                arg=[_SUCCESS_URL_SUBSTRINGS],
                timeout=self.options.default_timeout,
            )
        except Exception as exc:
            logger.error("Hapoalim post-OTP navigation failed: %s", exc)
            return LoginResult.UNKNOWN_ERROR

        return LoginResult.SUCCESS

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
