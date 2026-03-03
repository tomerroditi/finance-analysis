from __future__ import annotations

import logging
from datetime import date, datetime
from enum import Enum
from typing import Optional

from dateutil.relativedelta import relativedelta

from scraper.base import BrowserScraper, LoginOptions
from scraper.models.account import AccountResult
from scraper.models.result import LoginResult
from scraper.models.transaction import (
    InstallmentInfo,
    Transaction,
    TransactionStatus,
    TransactionType,
)
from scraper.utils import (
    click_button,
    element_present_on_page,
    fetch_post,
    filter_old_transactions,
    page_eval,
    wait_for_navigation,
    wait_until,
    wait_until_element_found,
    wait_until_iframe_found,
)

logger = logging.getLogger(__name__)

API_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/142.0.0.0 Safari/537.36"
    ),
    "Origin": "https://digital-web.cal-online.co.il",
    "Referer": "https://digital-web.cal-online.co.il",
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
}

LOGIN_URL = "https://www.cal-online.co.il/"
TRANSACTIONS_REQUEST_ENDPOINT = (
    "https://api.cal-online.co.il/Transactions/api/"
    "transactionsDetails/getCardTransactionsDetails"
)
FRAMES_REQUEST_ENDPOINT = (
    "https://api.cal-online.co.il/Frames/api/Frames/GetFrameStatus"
)
PENDING_TRANSACTIONS_REQUEST_ENDPOINT = (
    "https://api.cal-online.co.il/Transactions/api/"
    "approvals/getClearanceRequests"
)

INVALID_PASSWORD_MESSAGE = (
    "\u05e9\u05dd \u05d4\u05de\u05e9\u05ea\u05de\u05e9 \u05d0\u05d5 "
    "\u05d4\u05e1\u05d9\u05e1\u05de\u05d4 \u05e9\u05d4\u05d5\u05d6\u05e0\u05d5 "
    "\u05e9\u05d2\u05d5\u05d9\u05d9\u05dd"
)

X_SITE_ID = "09031987-273E-2311-906C-8AF85B17C8D9"


class TrnTypeCode(str, Enum):
    """Visa Cal transaction type codes."""

    REGULAR = "5"
    CREDIT = "6"
    INSTALLMENTS = "8"
    STANDING_ORDER = "9"


def _is_pending(transaction: dict) -> bool:
    """Check if a transaction is pending (no debit date)."""
    return "debCrdDate" not in transaction


def _convert_parsed_data_to_transactions(
    data: list[dict],
    pending_data: dict | None = None,
) -> list[Transaction]:
    """Convert raw Visa Cal API response data to Transaction objects.

    Parameters
    ----------
    data : list[dict]
        Monthly transaction detail responses.
    pending_data : dict | None
        Pending transactions response.

    Returns
    -------
    list[Transaction]
        Converted transaction objects.
    """
    pending_transactions: list[dict] = []
    if pending_data and pending_data.get("result"):
        for card in pending_data["result"].get("cardsList", []):
            pending_transactions.extend(card.get("authDetalisList", []))

    completed_transactions: list[dict] = []
    for month_data in data:
        result = month_data.get("result", {})
        for bank_account in result.get("bankAccounts", []):
            for debit_date in bank_account.get("debitDates", []):
                completed_transactions.extend(
                    debit_date.get("transactions", [])
                )
            immediate = bank_account.get("immidiateDebits", {})
            for debit_day in immediate.get("debitDays", []):
                completed_transactions.extend(
                    debit_day.get("transactions", [])
                )

    all_txns = [*pending_transactions, *completed_transactions]

    results: list[Transaction] = []
    for txn in all_txns:
        is_pending_txn = _is_pending(txn)
        trn_type_code = str(txn.get("trnTypeCode", ""))

        num_payments = (
            txn.get("numberOfPayments", 0)
            if is_pending_txn
            else txn.get("numOfPayments", 0)
        )
        installments = None
        if num_payments:
            installments = InstallmentInfo(
                number=1 if is_pending_txn else txn.get("curPaymentNum", 1),
                total=num_payments,
            )

        purchase_date_str = txn.get("trnPurchaseDate", "")
        try:
            purchase_date = datetime.fromisoformat(
                purchase_date_str.replace("Z", "+00:00")
            )
        except (ValueError, AttributeError):
            purchase_date = datetime.now()

        if installments:
            purchase_date = purchase_date + relativedelta(
                months=installments.number - 1
            )

        charged_amount = (
            txn.get("trnAmt", 0)
            if is_pending_txn
            else txn.get("amtBeforeConvAndIndex", 0)
        ) * -1

        is_credit = trn_type_code == TrnTypeCode.CREDIT
        original_amount = txn.get("trnAmt", 0) * (1 if is_credit else -1)

        if is_pending_txn:
            processed_date = purchase_date
        else:
            deb_crd_date = txn.get("debCrdDate", "")
            try:
                processed_date = datetime.fromisoformat(
                    deb_crd_date.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                processed_date = purchase_date

        txn_type = (
            TransactionType.NORMAL
            if trn_type_code in (TrnTypeCode.REGULAR, TrnTypeCode.STANDING_ORDER)
            else TransactionType.INSTALLMENTS
        )

        result = Transaction(
            type=txn_type,
            status=(
                TransactionStatus.PENDING
                if is_pending_txn
                else TransactionStatus.COMPLETED
            ),
            date=purchase_date.isoformat(),
            processed_date=processed_date.isoformat(),
            original_amount=original_amount,
            original_currency=txn.get("trnCurrencySymbol", "ILS"),
            charged_amount=charged_amount,
            charged_currency=(
                txn.get("debCrdCurrencySymbol")
                if not is_pending_txn
                else None
            ),
            description=txn.get("merchantName", ""),
            memo=str(txn.get("transTypeCommentDetails", "")),
            category=txn.get("branchCodeDesc"),
            identifier=txn.get("trnIntId") if not is_pending_txn else None,
            installments=installments,
        )
        results.append(result)

    return results


async def _get_login_frame(page):
    """Wait for the Visa Cal login iframe to appear.

    Parameters
    ----------
    page : Page
        Playwright page instance.

    Returns
    -------
    Frame
        The login iframe.
    """
    return await wait_until_iframe_found(
        page,
        lambda f: "connect" in f.url,
        "login iframe",
        timeout=10.0,
    )


async def _has_invalid_password_error(page) -> bool:
    """Check if invalid password error is displayed in the login iframe.

    Parameters
    ----------
    page : Page
        Playwright page instance.

    Returns
    -------
    bool
        True if invalid password error is shown.
    """
    frame = await _get_login_frame(page)
    error_found = await element_present_on_page(frame, "div.general-error > div")
    if not error_found:
        return False
    error_text = await page_eval(
        frame,
        "div.general-error > div",
        "el => el.innerText",
        "",
    )
    return error_text == INVALID_PASSWORD_MESSAGE


async def _has_change_password_form(page) -> bool:
    """Check if change password form is displayed.

    Parameters
    ----------
    page : Page
        Playwright page instance.

    Returns
    -------
    bool
        True if change password form is present.
    """
    frame = await _get_login_frame(page)
    return await element_present_on_page(frame, ".change-password-subtitle")


def _get_possible_login_results(page) -> dict[LoginResult, list]:
    """Build login result detection rules for Visa Cal.

    Parameters
    ----------
    page : Page
        Playwright page instance.

    Returns
    -------
    dict[LoginResult, list]
        Mapping of login results to detection checks.
    """
    import re

    async def is_invalid_password(**kwargs):
        target_page = kwargs.get("page", page)
        return await _has_invalid_password_error(target_page)

    async def is_change_password(**kwargs):
        target_page = kwargs.get("page", page)
        return await _has_change_password_form(target_page)

    return {
        LoginResult.SUCCESS: [re.compile(r"dashboard", re.IGNORECASE)],
        LoginResult.INVALID_PASSWORD: [is_invalid_password],
        LoginResult.CHANGE_PASSWORD: [is_change_password],
    }


class VisaCalScraper(BrowserScraper):
    """Scraper for Visa Cal credit card (https://www.cal-online.co.il).

    Uses API-via-browser pattern: logs in through browser automation,
    extracts authentication tokens from session storage, then fetches
    transaction data via the Cal REST API.
    """

    _authorization: Optional[str] = None

    def get_login_options(self, credentials: dict) -> LoginOptions:
        """Return Visa Cal-specific login configuration.

        Parameters
        ----------
        credentials : dict
            Must contain 'username' and 'password' keys.

        Returns
        -------
        LoginOptions
            Login configuration for the generic login flow.
        """
        page = self.page

        async def open_login_popup():
            logger.debug("Waiting for login button")
            await wait_until_element_found(
                page, "#ccLoginDesktopBtn", only_visible=True
            )
            logger.debug("Clicking login button")
            await click_button(page, "#ccLoginDesktopBtn")
            logger.debug("Getting login frame")
            frame = await _get_login_frame(page)
            logger.debug("Waiting for regular-login tab")
            await wait_until_element_found(frame, "#regular-login")
            logger.debug("Clicking regular-login tab")
            await click_button(frame, "#regular-login")
            logger.debug("Waiting for regular-login form")
            await wait_until_element_found(frame, "regular-login")
            return frame

        async def post_action():
            try:
                await wait_for_navigation(page)
                current_url = page.url
                if current_url.endswith("site-tutorial"):
                    await click_button(page, "button.btn-close")
            except Exception:
                current_url = page.url
                if current_url.endswith("dashboard"):
                    return
                if await _has_change_password_form(page):
                    return
                raise

        return LoginOptions(
            login_url=LOGIN_URL,
            fields=[
                {
                    "selector": '[formcontrolname="userName"]',
                    "value": credentials["username"],
                },
                {
                    "selector": '[formcontrolname="password"]',
                    "value": credentials["password"],
                },
            ],
            submit_button_selector='button[type="submit"]',
            possible_results=_get_possible_login_results(page),
            check_readiness=lambda: wait_until_element_found(
                page, "#ccLoginDesktopBtn"
            ),
            pre_action=open_login_popup,
            post_action=post_action,
            user_agent=API_HEADERS["User-Agent"],
        )

    async def _get_cards(self) -> list[dict]:
        """Get card list from session storage.

        Returns
        -------
        list[dict]
            List of dicts with 'cardUniqueId' and 'last4Digits' keys.
        """
        init_data = await wait_until(
            lambda: self.page.evaluate(
                """() => {
                    const raw = sessionStorage.getItem('init');
                    return raw ? JSON.parse(raw) : null;
                }"""
            ),
            "get init data from session storage",
            timeout=10.0,
            interval=1.0,
        )
        if not init_data:
            raise Exception('Could not find "init" data in session storage')

        return [
            {
                "cardUniqueId": card["cardUniqueId"],
                "last4Digits": card["last4Digits"],
            }
            for card in init_data.get("result", {}).get("cards", [])
        ]

    async def _get_authorization_header(self) -> str:
        """Extract authorization token from session storage.

        Returns
        -------
        str
            The authorization header value.
        """
        if self._authorization:
            return self._authorization

        logger.debug("Fetching authorization header from session storage")
        auth_module = await wait_until(
            lambda: self.page.evaluate(
                """() => {
                    const raw = sessionStorage.getItem('auth-module');
                    if (!raw) return null;
                    const parsed = JSON.parse(raw);
                    if (parsed && parsed.auth && parsed.auth.calConnectToken
                        && String(parsed.auth.calConnectToken).trim()) {
                        return parsed;
                    }
                    return null;
                }"""
            ),
            "get authorization token from session storage",
            timeout=10.0,
            interval=0.05,
        )
        token = auth_module["auth"]["calConnectToken"]
        return f"CALAuthScheme {token}"

    async def fetch_data(self) -> list[AccountResult]:
        """Fetch credit card transaction data from Visa Cal API.

        Returns
        -------
        list[AccountResult]
            Accounts with their transactions and balances.
        """
        default_start = (
            date.today() - relativedelta(months=18) + relativedelta(days=1)
        )
        start_date = self.options.start_date or default_start
        effective_start = max(default_start, start_date)

        cards = await self._get_cards()
        authorization = await self._get_authorization_header()

        future_months = self.options.future_months_to_scrape or 1

        # Fetch frames (misgarot) for balance info
        headers = {
            "Authorization": authorization,
            "X-Site-Id": X_SITE_ID,
            "Content-Type": "application/json",
            **API_HEADERS,
        }

        frames_response = await fetch_post(
            FRAMES_REQUEST_ENDPOINT,
            {
                "cardsForFrameData": [
                    {"cardUniqueId": c["cardUniqueId"]} for c in cards
                ]
            },
            headers,
        )

        accounts: list[AccountResult] = []
        for card in cards:
            card_uid = card["cardUniqueId"]
            last4 = card["last4Digits"]

            final_month = date.today() + relativedelta(months=future_months)
            start_month = effective_start.replace(day=1)
            months_diff = (
                (final_month.year - start_month.year) * 12
                + final_month.month
                - start_month.month
            )

            # Fetch pending transactions
            logger.debug(
                "Fetching pending transactions for card %s", card_uid
            )
            pending_data = await fetch_post(
                PENDING_TRANSACTIONS_REQUEST_ENDPOINT,
                {"cardUniqueIDArray": [card_uid]},
                headers,
            )

            # Fetch completed transactions month by month
            logger.debug(
                "Fetching completed transactions for card %s", card_uid
            )
            all_months_data: list[dict] = []
            for i in range(months_diff + 1):
                month_date = final_month - relativedelta(months=i)
                month_data = await fetch_post(
                    TRANSACTIONS_REQUEST_ENDPOINT,
                    {
                        "cardUniqueId": card_uid,
                        "month": str(month_date.month),
                        "year": str(month_date.year),
                    },
                    headers,
                )

                if month_data.get("statusCode") != 1:
                    raise Exception(
                        f"Failed to fetch transactions for card {last4}. "
                        f"Message: {month_data.get('title', '')}"
                    )

                all_months_data.append(month_data)

            # Validate pending data
            if pending_data.get("statusCode") not in (1, 96):
                logger.debug(
                    "Failed to fetch pending for card %s: %s",
                    last4,
                    pending_data.get("title", ""),
                )
                pending_data = None

            transactions = _convert_parsed_data_to_transactions(
                all_months_data, pending_data
            )

            # Filter old transactions
            txns = filter_old_transactions(
                transactions,
                effective_start,
                self.options.combine_installments,
            )

            # Get balance from frames
            balance = None
            bank_issued = (
                frames_response.get("result", {})
                .get("bankIssuedCards", {})
                .get("cardLevelFrames", [])
            )
            for frame_item in bank_issued:
                if frame_item.get("cardUniqueId") == card_uid:
                    next_debit = frame_item.get("nextTotalDebit")
                    if next_debit is not None:
                        balance = -next_debit
                    break

            accounts.append(
                AccountResult(
                    account_number=last4,
                    transactions=txns,
                    balance=balance,
                )
            )

        return accounts
