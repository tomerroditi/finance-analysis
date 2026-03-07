from __future__ import annotations

import json
import logging
from datetime import datetime

from scraper.base import BrowserScraper
from scraper.models.account import AccountResult
from scraper.models.result import LoginResult
from scraper.models.transaction import Transaction, TransactionStatus, TransactionType
from scraper.utils import wait_until_element_found

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

# JS: Extract savings account list from sessionStorage
_EXTRACT_ACCOUNT_LIST_JS = """
() => {
    const appState = JSON.parse(sessionStorage.getItem('appState') || '{}');
    const savingList = appState.share?.resSavings?.savingList;
    if (!savingList) return null;
    return savingList.map(s => ({
        policyId: s.policyId || '',
        policyType: s.policyType || '',
        pensionType: s.pensionType || '',
        balance: s.sum?.value || 0,
        productDescription: s.productDescription || '',
        balanceDate: s.tarNehunut || '',
    }));
}
"""

# JS: Extract pension detail from sessionStorage
_EXTRACT_PENSION_DETAIL_JS = """
() => {
    const appState = JSON.parse(sessionStorage.getItem('appState') || '{}');
    const policy = appState.pensionPolicies?.pensionPolicy;
    if (!policy) return null;
    return {
        general: policy.general || {},
        investmentRoutes: policy.investmentRoutes?.routes || [],
        managementFee: policy.managementFee?.updatedMngFee || {},
        depositsYear: policy.depositsYear || {},
        covers: policy.covers?.list || [],
        accountTransactions: policy.accountTransactions?.list || [],
    };
}
"""

# JS: Extract hishtalmut detail from sessionStorage (used in Task 6)
_EXTRACT_HISHTALMUT_DETAIL_JS = """
() => {
    const appState = JSON.parse(sessionStorage.getItem('appState') || '{}');
    const policy = appState.gemelPolicies?.hishtalmut;
    if (!policy) return null;
    return {
        general: policy.general || {},
        investmentRoutes: policy.investmentRoutesTransferConcentration?.investmentRoutes?.list || [],
        managementFee: policy.managementFee?.updatedMngFee || {},
        deposits: policy.deposits?.yearlyDeposits || {},
        expectedPayments: policy.expectedPaymentsExcellence?.list || [],
    };
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
            await self.navigate_to(LOGIN_URL, wait_until="domcontentloaded")

            # Wait for login form to render (Angular SPA)
            self._emit_progress("waiting for login form")
            await wait_until_element_found(
                self.page, ID_FIELD_SELECTOR, only_visible=True, timeout=30000
            )

            # Human-like: move mouse around, scroll a bit before interacting
            await self._human_delay(1.0, 2.0)
            await self._human_mouse_move()
            await self._human_delay(0.3, 0.8)
            await self._human_scroll()
            await self._human_delay(0.5, 1.0)

            # Fill credentials with human-like clicking and typing
            self._emit_progress("filling login credentials")
            await self.page.click(ID_FIELD_SELECTOR)
            await self._human_delay(0.2, 0.5)
            await self._type_like_human(ID_FIELD_SELECTOR, self.credentials["id"])
            await self._human_delay(0.5, 1.2)

            await self.page.click(PHONE_FIELD_SELECTOR)
            await self._human_delay(0.2, 0.5)
            await self._type_like_human(
                PHONE_FIELD_SELECTOR, self.credentials["phoneNumber"]
            )
            await self._human_delay(0.5, 1.0)

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

            # Fill OTP with human-like typing
            self._emit_progress("submitting OTP code")
            await self._human_delay(0.5, 1.0)
            await self.page.click(OTP_FIELD_SELECTOR)
            await self._human_delay(0.2, 0.5)
            await self._type_like_human(OTP_FIELD_SELECTOR, otp_code)
            await self._human_delay(0.3, 0.8)
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

        Discovers all accounts from the savings page, then navigates to each
        account's detail page to extract rich data (investment tracks,
        commissions, deposits, covers).

        Returns
        -------
        list[AccountResult]
            One AccountResult per policy with transactions and metadata.
        """
        # Step 1: Navigate to savings page to discover accounts
        self._emit_progress("discovering accounts")
        await self.navigate_to(SAVINGS_URL, wait_until="domcontentloaded")
        await self.page.wait_for_function(
            """
            () => {
                const state = JSON.parse(sessionStorage.getItem('appState') || '{}');
                return state.share?.resSavings?.savingList?.length > 0;
            }
            """,
            timeout=30000,
        )

        account_list = await self.page.evaluate(_EXTRACT_ACCOUNT_LIST_JS)
        if not account_list:
            logger.warning("No accounts found in savingList")
            return []

        logger.info("Discovered %d accounts", len(account_list))

        # Step 2: Scrape each account's detail page
        results: list[AccountResult] = []
        for account_info in account_list:
            try:
                result = await self._scrape_account_detail(account_info)
                if result:
                    results.append(result)
            except Exception as e:
                logger.error(
                    "Failed to scrape account %s: %s",
                    account_info.get("policyId", "unknown"), e,
                )

        return results

    async def _scrape_account_detail(
        self, account_info: dict
    ) -> AccountResult | None:
        """Navigate to an account's detail page and extract data.

        Parameters
        ----------
        account_info : dict
            Account summary from savingList with policyId, policyType, etc.

        Returns
        -------
        AccountResult or None
            Account data with transactions and metadata, or None on failure.
        """
        policy_id = account_info["policyId"]
        policy_type = account_info.get("policyType", "").lower()

        if "pension" in policy_type or "פנסי" in policy_type:
            return await self._scrape_pension(account_info)
        elif "hishtalmut" in policy_type or "השתלמות" in policy_type:
            return await self._scrape_hishtalmut(account_info)
        else:
            logger.warning(
                "Unknown policy type '%s' for %s, skipping",
                policy_type, policy_id,
            )
            return None

    async def _scrape_pension(self, account_info: dict) -> AccountResult:
        """Scrape a pension account's detail page.

        Parameters
        ----------
        account_info : dict
            Account summary from savingList.

        Returns
        -------
        AccountResult
            Pension account data with deposit transactions and metadata.
        """
        policy_id = account_info["policyId"]
        pension_type = account_info.get("pensionType", "makifa").lower()
        balance = float(account_info.get("balance", 0))
        balance_date = _parse_date(account_info.get("balanceDate", ""))

        self._emit_progress(f"scraping pension {policy_id}")

        # Navigate to pension detail page
        url = f"https://my.fnx.co.il/policies/pension/{policy_id}/{pension_type}/info"
        await self.navigate_to(url, wait_until="domcontentloaded")
        await self._human_delay(1.0, 2.0)

        # Wait for pension data to populate in sessionStorage
        await self.page.wait_for_function(
            """
            () => {
                const state = JSON.parse(sessionStorage.getItem('appState') || '{}');
                return !!state.pensionPolicies?.pensionPolicy?.general;
            }
            """,
            timeout=30000,
        )
        await self._human_delay(1.0, 2.0)

        # Try to load all deposit years
        await self._load_all_deposit_years()

        detail = await self.page.evaluate(_EXTRACT_PENSION_DETAIL_JS)
        if not detail:
            logger.warning("No pension detail for %s", policy_id)
            return AccountResult(account_number=policy_id, balance=balance)

        # Extract investment tracks
        tracks = []
        routes = detail.get("investmentRoutes", [])
        for route in routes:
            tracks.append({
                "name": route.get("investmentRouteTitle", ""),
                "yield_pct": route.get("yieldPercentage", 0),
                # Single track = 100%. Multi-track: TODO improve when we have a reference
                "allocation_pct": 100.0 if len(routes) == 1 else None,
                "sum": None,
            })

        # Extract commissions
        fee = detail.get("managementFee", {})
        commission_deposits = fee.get("fromDeposit", {}).get("percentageData", {}).get("value")
        commission_savings = fee.get("fromSaving", {}).get("percentageData", {}).get("value")

        # Extract insurance covers
        covers = []
        for cover in detail.get("covers", []):
            covers.append({
                "title": cover.get("coverTitle", ""),
                "desc": cover.get("coverDesc", ""),
                "sum": cover.get("coverSum", 0),
            })

        # Build deposit transactions
        transactions = self._build_pension_deposits(policy_id, detail)

        # Build insurance cost transactions
        transactions.extend(self._build_insurance_costs(policy_id, detail))

        account_name = detail.get("general", {}).get("policyName", f"Pension {policy_id}")

        logger.info(
            "Pension %s: %s (balance: ₪%s, %d tracks, %d deposits, %d covers)",
            policy_id, account_name, balance, len(tracks),
            len(transactions), len(covers),
        )

        return AccountResult(
            account_number=policy_id,
            transactions=transactions,
            balance=balance,
            metadata={
                "provider": "hafenix",
                "policy_id": policy_id,
                "policy_type": "pension",
                "pension_type": pension_type,
                "account_name": account_name,
                "balance": balance,
                "balance_date": balance_date,
                "investment_tracks": json.dumps(tracks, ensure_ascii=False),
                "commission_deposits_pct": commission_deposits,
                "commission_savings_pct": commission_savings,
                "insurance_covers": json.dumps(covers, ensure_ascii=False),
                "liquidity_date": None,
            },
        )

    async def _scrape_hishtalmut(self, account_info: dict) -> AccountResult:
        """Scrape a keren hishtalmut account's detail page.

        Parameters
        ----------
        account_info : dict
            Account summary from savingList.

        Returns
        -------
        AccountResult
            Hishtalmut account data with deposit transactions and metadata.
        """
        policy_id = account_info["policyId"]
        balance = float(account_info.get("balance", 0))
        balance_date = _parse_date(account_info.get("balanceDate", ""))

        self._emit_progress(f"scraping hishtalmut {policy_id}")

        # Navigate to hishtalmut detail page
        encoded_id = policy_id.replace(" ", "%20")
        url = f"https://my.fnx.co.il/policies/hishtalmut/{encoded_id}/info"
        await self.navigate_to(url, wait_until="domcontentloaded")
        await self._human_delay(1.0, 2.0)

        # Wait for hishtalmut data to populate in sessionStorage
        await self.page.wait_for_function(
            """
            () => {
                const state = JSON.parse(sessionStorage.getItem('appState') || '{}');
                return !!state.gemelPolicies?.hishtalmut?.general;
            }
            """,
            timeout=30000,
        )
        await self._human_delay(1.0, 2.0)

        # Try to load all deposit years
        await self._load_all_deposit_years()

        detail = await self.page.evaluate(_EXTRACT_HISHTALMUT_DETAIL_JS)
        if not detail:
            logger.warning("No hishtalmut detail for %s", policy_id)
            return AccountResult(account_number=policy_id, balance=balance)

        # Extract investment tracks (hishtalmut has allocation %)
        tracks = []
        for route in detail.get("investmentRoutes", []):
            tracks.append({
                "name": route.get("investmentRouteTitle", ""),
                "yield_pct": route.get("yieldPercentage", 0),
                "allocation_pct": route.get("investmentPercent", {}).get("value"),
                "sum": route.get("investmentSum", {}).get("value"),
            })

        # Extract commissions
        fee = detail.get("managementFee", {})
        commission_deposits = fee.get("fromDeposit", {}).get("percentageData", {}).get("value")
        commission_savings = fee.get("fromSaving", {}).get("percentageData", {}).get("value")

        # Extract liquidity date
        liquidity_date = None
        for payment in detail.get("expectedPayments", []):
            title = payment.get("title", "")
            if "משיכה חד פעמית" in title or "סכום למשיכה" in title:
                sub_title = payment.get("subTitle", "")
                liquidity_date = self._parse_liquidity_date(sub_title)
                break

        # Build deposit transactions
        transactions = self._build_hishtalmut_deposits(policy_id, detail)

        account_name = detail.get("general", {}).get("policyName", f"Hishtalmut {policy_id}")

        logger.info(
            "Hishtalmut %s: %s (balance: ₪%s, %d tracks, %d deposits, liquidity: %s)",
            policy_id, account_name, balance, len(tracks),
            len(transactions), liquidity_date,
        )

        return AccountResult(
            account_number=policy_id,
            transactions=transactions,
            balance=balance,
            metadata={
                "provider": "hafenix",
                "policy_id": policy_id,
                "policy_type": "hishtalmut",
                "pension_type": None,
                "account_name": account_name,
                "balance": balance,
                "balance_date": balance_date,
                "investment_tracks": json.dumps(tracks, ensure_ascii=False),
                "commission_deposits_pct": commission_deposits,
                "commission_savings_pct": commission_savings,
                "insurance_covers": None,
                "liquidity_date": liquidity_date,
            },
        )

    async def _load_all_deposit_years(self) -> None:
        """Attempt to load all available deposit years by clicking year options.

        This is a best-effort method — if the year selector is not found or
        clicking fails, we proceed with whatever years are already loaded.

        The exact selector may need adjustment based on live testing.
        """
        # TODO: The year selector mechanism needs live testing.
        # The site may use a dropdown, tabs, or API calls for year switching.
        # For now, we rely on whatever years are loaded by default.
        try:
            year_elements = await self.page.query_selector_all(
                ".year-select option, .year-tab, [data-year]"
            )
            if not year_elements:
                return

            for el in year_elements:
                try:
                    await el.click()
                    await self._human_delay(0.5, 1.0)
                except Exception:
                    continue
        except Exception as e:
            logger.debug("Year iteration not available: %s", e)

    def _build_pension_deposits(
        self, policy_id: str, detail: dict
    ) -> list[Transaction]:
        """Build Transaction objects from pension deposit records.

        Parameters
        ----------
        policy_id : str
            The policy ID.
        detail : dict
            Pension detail data from sessionStorage.

        Returns
        -------
        list[Transaction]
            Deposit transactions across all available years.
        """
        transactions: list[Transaction] = []
        deposits_year = detail.get("depositsYear", {})

        for year_data in deposits_year.get("list", []):
            for deposit in year_data.get("list", []):
                date_raw = deposit.get("depositDate", "")
                date_str = _parse_date(date_raw)
                total = float(deposit.get("totalDeposit", 0))
                employer_name = deposit.get("employerName", "")
                employee = float(deposit.get("employeeDeposit", 0))
                employer = float(deposit.get("employerDeposit", 0))
                compensation = float(deposit.get("compensationDeposit", 0))

                description = f"הפקדה - {employer_name}" if employer_name else "הפקדה"
                memo_parts = []
                if employee:
                    memo_parts.append(f"עובד: {employee:.0f}")
                if employer:
                    memo_parts.append(f"מעסיק: {employer:.0f}")
                if compensation:
                    memo_parts.append(f"פיצויים: {compensation:.0f}")
                memo = " / ".join(memo_parts) if memo_parts else None

                transactions.append(
                    Transaction(
                        type=TransactionType.NORMAL,
                        status=TransactionStatus.COMPLETED,
                        date=date_str,
                        processed_date=date_str,
                        original_amount=total,
                        original_currency="ILS",
                        charged_amount=total,
                        charged_currency="ILS",
                        description=description,
                        identifier=f"{policy_id}_{date_str}_{total}",
                        memo=memo,
                    )
                )

        return transactions

    def _build_insurance_costs(
        self, policy_id: str, detail: dict
    ) -> list[Transaction]:
        """Build Transaction objects from pension insurance cost records.

        Parameters
        ----------
        policy_id : str
            The policy ID.
        detail : dict
            Pension detail data from sessionStorage.

        Returns
        -------
        list[Transaction]
            Insurance cost transactions (negative amounts).
        """
        transactions: list[Transaction] = []
        cost_keywords = ["עלות הביטוח לסיכוני נכות", "עלות הביטוח למקרה מוות"]

        for item in detail.get("accountTransactions", []):
            item_type = item.get("type", "")
            if not any(kw in item_type for kw in cost_keywords):
                continue

            amount_data = item.get("amount", {})
            amount_value = float(amount_data.get("value", 0))
            # Insurance costs are expenses — ensure negative
            if amount_value > 0:
                amount_value = -amount_value

            date_raw = item.get("date", "")
            date_str = _parse_date(date_raw)

            short_type = "נכות" if "נכות" in item_type else "מוות"
            description = f"עלות ביטוח - {short_type}"

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
                    identifier=f"{policy_id}_{date_str}_insurance_{short_type}",
                    memo=None,
                )
            )

        return transactions

    def _build_hishtalmut_deposits(
        self, policy_id: str, detail: dict
    ) -> list[Transaction]:
        """Build Transaction objects from hishtalmut deposit records.

        Parameters
        ----------
        policy_id : str
            The policy ID.
        detail : dict
            Hishtalmut detail data from sessionStorage.

        Returns
        -------
        list[Transaction]
            Deposit transactions across all available years.
        """
        transactions: list[Transaction] = []
        yearly_deposits = detail.get("deposits", {})

        for year_data in yearly_deposits.get("list", []):
            for deposit in year_data.get("list", []):
                date_raw = deposit.get("depositDate", "")
                date_str = _parse_date(date_raw)
                total = float(deposit.get("totalDeposit", 0))

                transactions.append(
                    Transaction(
                        type=TransactionType.NORMAL,
                        status=TransactionStatus.COMPLETED,
                        date=date_str,
                        processed_date=date_str,
                        original_amount=total,
                        original_currency="ILS",
                        charged_amount=total,
                        charged_currency="ILS",
                        description="הפקדה",
                        identifier=f"{policy_id}_{date_str}_{total}",
                        memo=None,
                    )
                )

        return transactions

    @staticmethod
    def _parse_liquidity_date(text: str) -> str | None:
        """Parse liquidity date from Hebrew text like 'החל מ31.05.2029'.

        Parameters
        ----------
        text : str
            Hebrew text containing a date.

        Returns
        -------
        str or None
            Date in YYYY-MM-DD format, or None if parsing fails.
        """
        import re
        match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", text)
        if match:
            day, month, year = match.groups()
            return f"{year}-{month}-{day}"
        return None
