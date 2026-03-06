from __future__ import annotations

import logging
from datetime import datetime

from scraper.base import BrowserScraper
from scraper.models.account import AccountResult
from scraper.models.result import LoginResult
from scraper.models.transaction import Transaction, TransactionStatus, TransactionType
from scraper.utils import (
    fill_input,
    sleep,
    wait_until_element_found,
)

logger = logging.getLogger(__name__)

LOGIN_URL = "https://my.fnx.co.il/"
SAVINGS_URL = "https://my.fnx.co.il/savings"

# Step 1: Login form selectors (Angular SPA on my.fnx.co.il)
ID_FIELD_SELECTOR = "#fnx-id"
PHONE_FIELD_SELECTOR = 'input[placeholder="טלפון נייד או כתובת מייל*"]'

# Step 2: OTP page selectors (on login.fnx.co.il)
OTP_FIELD_SELECTOR = "#otp"
OTP_SUBMIT_SELECTOR = "#login-btn"

# JS to click the send-code button (no stable CSS selector)
_CLICK_SEND_CODE_JS = """
() => {
    const btn = Array.from(document.querySelectorAll('button'))
        .find(b => b.textContent.includes('שלחו לי קוד כניסה'));
    if (btn) btn.click();
}
"""

# JS to extract savings data from Angular sessionStorage cache
_EXTRACT_SAVINGS_JS = """
() => {
    const appState = JSON.parse(sessionStorage.getItem('appState') || '{}');
    const resSavings = appState.share?.resSavings;
    if (!resSavings) return null;
    return resSavings;
}
"""

# JS to extract deposits/charges from Angular sessionStorage cache
_EXTRACT_DEPOSITS_JS = """
() => {
    const appState = JSON.parse(sessionStorage.getItem('appState') || '{}');
    const chargesPayments = appState.depositsCharges?.chargesPayments;
    if (!chargesPayments) return null;
    return chargesPayments.list || [];
}
"""


def _parse_date(date_str: str) -> str:
    """Parse date from HaPhoenix format to ISO format.

    Parameters
    ----------
    date_str : str
        Date in DD.MM.YYYY or ISO format.

    Returns
    -------
    str
        Date in YYYY-MM-DD format.
    """
    if "T" in date_str:
        return date_str.split("T")[0]
    try:
        return datetime.strptime(date_str, "%d.%m.%Y").strftime("%Y-%m-%d")
    except ValueError:
        return date_str


class HaPhoenixScraper(BrowserScraper):
    """Scraper for HaPhoenix Insurance (https://my.fnx.co.il).

    Uses browser automation with SMS-based 2FA for authentication.
    Login flow: enter ID + phone number -> receive SMS -> enter OTP code.
    Fetches pension, keren hishtalmut, and insurance data.
    """

    async def login(self) -> LoginResult:
        """Authenticate with HaPhoenix personal area.

        Two-step browser login:
        1. Fill ID number and phone number on my.fnx.co.il, submit.
        2. Redirected to login.fnx.co.il OTP page, fill code, submit.

        Returns
        -------
        LoginResult
            SUCCESS on successful authentication, UNKNOWN_ERROR on failure.
        """
        try:
            # Step 1: Navigate to login page
            self._emit_progress("navigating to login page")
            await self.navigate_to(LOGIN_URL)
            await sleep(2.0)

            # Wait for login form to render (SPA)
            self._emit_progress("waiting for login form")
            await wait_until_element_found(
                self.page, ID_FIELD_SELECTOR, only_visible=True, timeout=15000
            )

            # Fill credentials
            self._emit_progress("filling login credentials")
            await fill_input(self.page, ID_FIELD_SELECTOR, self.credentials["id"])
            await fill_input(
                self.page, PHONE_FIELD_SELECTOR, self.credentials["phoneNumber"]
            )
            await sleep(0.5)

            # Wait for submit button to become enabled, then click
            self._emit_progress("submitting credentials")
            await self._wait_for_submit_enabled()
            await self.page.evaluate(_CLICK_SEND_CODE_JS)

            # Step 2: Wait for OTP page (redirects to login.fnx.co.il)
            self._emit_progress("waiting for OTP page")
            await wait_until_element_found(
                self.page, OTP_FIELD_SELECTOR, only_visible=True, timeout=30000
            )

            # Request OTP from user
            if self.on_otp_request is None:
                logger.error("on_otp_request callback not set")
                return LoginResult.UNKNOWN_ERROR

            self._emit_progress("waiting for OTP code")
            otp_code = await self.on_otp_request()

            if otp_code == "cancel":
                return LoginResult.UNKNOWN_ERROR

            # Fill OTP and wait for submit button to become enabled
            self._emit_progress("submitting OTP code")
            await fill_input(self.page, OTP_FIELD_SELECTOR, otp_code)
            await self.page.wait_for_selector(
                f"{OTP_SUBMIT_SELECTOR}:not([disabled])", timeout=10000
            )
            await self.page.click(OTP_SUBMIT_SELECTOR)

            # Wait for post-login redirect back to my.fnx.co.il
            # Flow: login.fnx.co.il -> my.fnx.co.il/redirect?code=... -> my.fnx.co.il/
            self._emit_progress("waiting for login to complete")
            await self.page.wait_for_url(
                lambda url: "login.fnx.co.il" not in url,
                timeout=30000,
            )
            # Wait for the dashboard nav to render (confirms login succeeded)
            await wait_until_element_found(
                self.page, 'a[href="/savings"]', only_visible=True, timeout=30000
            )
            logger.info("HaPhoenix login successful: %s", self.page.url)
            return LoginResult.SUCCESS

        except Exception as e:
            logger.error("HaPhoenix login failed: %s", e)
            return LoginResult.UNKNOWN_ERROR

    async def _wait_for_submit_enabled(self, timeout: float = 10000) -> None:
        """Wait for the 'send code' button to drop its disabled state."""
        await self.page.wait_for_function(
            """
            () => {
                const btn = Array.from(document.querySelectorAll('button'))
                    .find(b => b.textContent.includes('שלחו לי קוד כניסה'));
                return btn && btn.getAttribute('aria-disabled') !== 'true';
            }
            """,
            timeout=timeout,
        )

    async def fetch_data(self) -> list[AccountResult]:
        """Fetch pension/keren hishtalmut data from HaPhoenix.

        Navigates to the savings page to trigger the Angular app's API calls,
        then reads the cached response from sessionStorage.

        Returns
        -------
        list[AccountResult]
            One AccountResult per savings account (pension/hishtalmut),
            with balance and deposit transactions.
        """
        # Navigate to savings page to trigger data loading
        self._emit_progress("loading savings data")
        await self.navigate_to(SAVINGS_URL)
        await sleep(2.0)

        # Wait for savings data to be populated in sessionStorage
        await self.page.wait_for_function(
            """
            () => {
                const state = JSON.parse(sessionStorage.getItem('appState') || '{}');
                return state.share?.resSavings?.savingList?.length > 0;
            }
            """,
            timeout=30000,
        )

        # Extract savings accounts
        savings_data = await self.page.evaluate(_EXTRACT_SAVINGS_JS)
        if not savings_data:
            logger.warning("No savings data found")
            return []

        # Extract deposit/charge history
        deposits_data = await self.page.evaluate(_EXTRACT_DEPOSITS_JS) or []

        accounts: list[AccountResult] = []
        for saving in savings_data.get("savingList", []):
            policy_id = saving.get("policyId", "")
            balance = saving.get("sum", {}).get("value", 0)
            product = saving.get("productDescription", "")
            policy_type = saving.get("policyType", "")
            date_str = saving.get("tarNehunut", "")

            # Collect deposit transactions for this account
            transactions = self._build_transactions(policy_id, deposits_data)

            account = AccountResult(
                account_number=policy_id,
                transactions=transactions,
                balance=float(balance),
            )
            accounts.append(account)

            logger.info(
                "Found %s: %s (balance: ₪%s, as of %s, %d deposits)",
                policy_type, product, balance, date_str, len(transactions),
            )

        total = savings_data.get("savingDistribution", {}).get("totalSavings", {}).get("value", 0)
        logger.info("Total savings: ₪%s across %d accounts", total, len(accounts))

        return accounts

    def _build_transactions(
        self, policy_id: str, deposits_data: list[dict]
    ) -> list[Transaction]:
        """Build Transaction objects from deposit/charge records for an account.

        Parameters
        ----------
        policy_id : str
            The policy ID to filter deposits for.
        deposits_data : list[dict]
            Raw deposit/charge records from the API.

        Returns
        -------
        list[Transaction]
            Deposit transactions matching the policy ID.
        """
        transactions: list[Transaction] = []

        for deposit in deposits_data:
            dep_policy_id = deposit.get("policyId", "")
            if dep_policy_id != policy_id:
                continue

            amount_data = deposit.get("amount", {})
            amount_value = float(amount_data.get("value", 0))
            sign = amount_data.get("sign", "")
            if sign == "minus":
                amount_value = -amount_value

            date_raw = deposit.get("date", "")
            date_str = _parse_date(date_raw)
            dep_type = deposit.get("type", "")
            policy_name = deposit.get("policyName", "")
            policy_type_data = deposit.get("policyTypeData", {})
            type_name = policy_type_data.get("name", "")
            method = deposit.get("method", "")

            description = f"{type_name} - {dep_type}"
            if method:
                description += f" ({method})"

            transactions.append(
                Transaction(
                    type=TransactionType.NORMAL,
                    status=TransactionStatus.COMPLETED,
                    date=date_str,
                    processed_date=date_str,
                    original_amount=amount_value,
                    original_currency="ILS",
                    charged_amount=amount_value,
                    charged_currency="ILS",
                    description=description,
                    identifier=f"{policy_id}_{date_str}_{amount_value}",
                    memo=policy_name,
                )
            )

        return transactions
