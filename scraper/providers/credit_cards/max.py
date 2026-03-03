import logging
import re
from datetime import date, datetime
from typing import Optional
from urllib.parse import urlencode

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
    fetch_get_within_page,
    filter_old_transactions,
    fix_installments,
    get_all_months,
    sort_transactions_by_date,
    wait_for_redirect,
    wait_until_element_found,
)

logger = logging.getLogger(__name__)

BASE_API_ACTIONS_URL = "https://onlinelcapi.max.co.il"
BASE_WELCOME_URL = "https://www.max.co.il"

LOGIN_URL = f"{BASE_WELCOME_URL}/login"
PASSWORD_EXPIRED_URL = f"{BASE_WELCOME_URL}/renew-password"
SUCCESS_URL = f"{BASE_WELCOME_URL}/homepage/personal"

INVALID_DETAILS_SELECTOR = "#popupWrongDetails"
LOGIN_ERROR_SELECTOR = "#popupCardHoldersLoginError"

SHEKEL_CURRENCY = "ILS"
DOLLAR_CURRENCY = "USD"
EURO_CURRENCY = "EUR"

# Plan names for transaction type classification
NORMAL_PLAN_NAMES = {
    "רגילה",
    "חיוב עסקות מיידי",
    "אינטרנט/חו\"ל",
    "חיוב חודשי",
    "דחוי חודש",
    "דחוי לחיוב החודשי",
    "תשלום חודשי",
    "מימון לרכישה עתידית",
    "דחוי חודש תשלומים",
    "עסקת 30 פלוס",
    "דחוי חודשיים",
    "דחוי 2 ח' תשלומים",
    "חודשי + ריבית",
    "סל מצטבר",
    "פריסת העסקה הדחויה",
    "כרטיס חליפי",
    "פרעון מוקדם",
    "דמי כרטיס",
    "חיוב ארנק מטח",
    "חלוקת חיוב חודשי",
}

INSTALLMENTS_PLAN_NAMES = {
    "תשלומים",
    "קרדיט",
    "קרדיט-מחוץ למסגרת",
}

# In-memory category cache
_categories: dict[int, str] = {}


def _get_transactions_url(month_date: date) -> str:
    """Build the transactions API URL for a given month.

    Parameters
    ----------
    month_date : date
        The first day of the month to fetch.

    Returns
    -------
    str
        The full URL with query parameters.
    """
    month = month_date.month
    year = month_date.year
    date_str = f"{year}-{month}-01"

    filter_data = (
        f'{{"userIndex":-1,"cardIndex":-1,"monthView":true,'
        f'"date":"{date_str}",'
        f'"dates":{{"startDate":"0","endDate":"0"}},'
        f'"bankAccount":{{"bankAccountIndex":-1,"cards":null}}}}'
    )

    base = f"{BASE_API_ACTIONS_URL}/api/registered/transactionDetails/getTransactionsAndGraphs"
    params = urlencode({
        "filterData": filter_data,
        "firstCallCardIndex": "-1",
    })
    return f"{base}?{params}"


async def _load_categories(page) -> None:
    """Load transaction categories from the Max API."""
    logger.debug("Loading categories")
    res = await fetch_get_within_page(
        page,
        f"{BASE_API_ACTIONS_URL}/api/contents/getCategories",
        ignore_errors=True,
    )
    if res and isinstance(res.get("result"), list):
        logger.debug("%d categories loaded", len(res["result"]))
        for item in res["result"]:
            _categories[item["id"]] = item["name"]


def _get_transaction_type(plan_name: str, plan_type_id: int) -> TransactionType:
    """Determine transaction type from the plan name and type ID.

    Parameters
    ----------
    plan_name : str
        The Hebrew plan name from the API response.
    plan_type_id : int
        The numeric plan type identifier.

    Returns
    -------
    TransactionType
        NORMAL or INSTALLMENTS.

    Raises
    ------
    ValueError
        If the plan name and type ID combination is unknown.
    """
    cleaned = plan_name.replace("\t", " ").strip()

    if cleaned in NORMAL_PLAN_NAMES:
        return TransactionType.NORMAL
    if cleaned in INSTALLMENTS_PLAN_NAMES:
        return TransactionType.INSTALLMENTS

    # Fallback to plan type ID
    if plan_type_id in (2, 3):
        return TransactionType.INSTALLMENTS
    if plan_type_id == 5:
        return TransactionType.NORMAL

    raise ValueError(f"Unknown transaction type {cleaned}")


def _get_installments_info(comments: str) -> Optional[InstallmentInfo]:
    """Parse installment info from comment string.

    Parameters
    ----------
    comments : str
        The transaction comments field.

    Returns
    -------
    Optional[InstallmentInfo]
        Parsed installment info, or None if not applicable.
    """
    if not comments:
        return None
    matches = re.findall(r"\d+", comments)
    if len(matches) < 2:
        return None
    return InstallmentInfo(
        number=int(matches[0]),
        total=int(matches[1]),
    )


def _get_charged_currency(currency_id: Optional[int]) -> Optional[str]:
    """Map numeric currency ID to ISO currency code.

    Parameters
    ----------
    currency_id : Optional[int]
        The numeric currency identifier from the API.

    Returns
    -------
    Optional[str]
        ISO currency code, or None if unknown.
    """
    currency_map = {
        376: SHEKEL_CURRENCY,
        840: DOLLAR_CURRENCY,
        978: EURO_CURRENCY,
    }
    return currency_map.get(currency_id)


def _get_memo(
    comments: str,
    funds_transfer_receiver: Optional[str] = None,
    funds_transfer_comment: Optional[str] = None,
) -> Optional[str]:
    """Build memo string from transaction fields.

    Parameters
    ----------
    comments : str
        The base comments string.
    funds_transfer_receiver : Optional[str]
        The funds transfer receiver/transfer field.
    funds_transfer_comment : Optional[str]
        The funds transfer comment field.

    Returns
    -------
    Optional[str]
        Composed memo string.
    """
    if funds_transfer_receiver:
        memo = f"{comments} {funds_transfer_receiver}" if comments else funds_transfer_receiver
        return f"{memo}: {funds_transfer_comment}" if funds_transfer_comment else memo
    return comments or None


def _map_transaction(raw: dict) -> Transaction:
    """Convert a raw Max API transaction to a Transaction model.

    Parameters
    ----------
    raw : dict
        Raw transaction dictionary from the API response.

    Returns
    -------
    Transaction
        Mapped transaction object.
    """
    is_pending = raw.get("paymentDate") is None
    purchase_date_str = raw.get("purchaseDate", "")
    payment_date_str = raw.get("paymentDate") if not is_pending else purchase_date_str

    # Parse dates - Max returns ISO date strings
    try:
        txn_date = datetime.fromisoformat(purchase_date_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        txn_date = datetime.now()

    try:
        processed_date = datetime.fromisoformat(
            payment_date_str.replace("Z", "+00:00")
        )
    except (ValueError, AttributeError):
        processed_date = txn_date

    status = TransactionStatus.PENDING if is_pending else TransactionStatus.COMPLETED

    installments = _get_installments_info(raw.get("comments", ""))

    # Build identifier from ARN + installment number
    arn = None
    deal_data = raw.get("dealData")
    if deal_data and isinstance(deal_data, dict):
        arn = deal_data.get("arn")
    if installments and arn:
        identifier = f"{arn}_{installments.number}"
    else:
        identifier = arn

    return Transaction(
        type=_get_transaction_type(
            raw.get("planName", ""),
            raw.get("planTypeId", 0),
        ),
        date=txn_date.isoformat(),
        processed_date=processed_date.isoformat(),
        original_amount=-raw.get("originalAmount", 0),
        original_currency=raw.get("originalCurrency", SHEKEL_CURRENCY),
        charged_amount=-float(raw.get("actualPaymentAmount", 0)),
        charged_currency=_get_charged_currency(raw.get("paymentCurrency")),
        description=raw.get("merchantName", "").strip(),
        memo=_get_memo(
            raw.get("comments", ""),
            raw.get("fundsTransferReceiverOrTransfer"),
            raw.get("fundsTransferComment"),
        ),
        category=_categories.get(raw.get("categoryId")),
        installments=installments,
        identifier=identifier,
        status=status,
    )


async def _fetch_transactions_for_month(
    page, month_date: date
) -> dict[str, list[Transaction]]:
    """Fetch and parse transactions for a single month.

    Parameters
    ----------
    page : Page
        The Playwright browser page.
    month_date : date
        The first day of the month to fetch.

    Returns
    -------
    dict[str, list[Transaction]]
        Transactions grouped by card number.
    """
    url = _get_transactions_url(month_date)
    data = await fetch_get_within_page(page, url, ignore_errors=True)

    transactions_by_account: dict[str, list[Transaction]] = {}

    if not data or not data.get("result"):
        return transactions_by_account

    raw_transactions = data["result"].get("transactions", [])
    for raw_txn in raw_transactions:
        # Filter out non-transactions without a plan name (e.g. summary rows)
        if not raw_txn.get("planName"):
            continue

        card_number = raw_txn.get("shortCardNumber", "unknown")
        if card_number not in transactions_by_account:
            transactions_by_account[card_number] = []

        mapped = _map_transaction(raw_txn)
        transactions_by_account[card_number].append(mapped)

    return transactions_by_account


def _prepare_transactions(
    txns: list[Transaction],
    start_date: date,
    combine_installments: bool,
    enable_filter_by_date: bool,
) -> list[Transaction]:
    """Apply installment fixes, sorting, and date filtering.

    Parameters
    ----------
    txns : list[Transaction]
        Raw transaction list.
    start_date : date
        Earliest date to keep.
    combine_installments : bool
        Whether to combine installment transactions.
    enable_filter_by_date : bool
        Whether to filter out old transactions.

    Returns
    -------
    list[Transaction]
        Processed transaction list.
    """
    result = list(txns)
    if not combine_installments:
        result = fix_installments(result)
    result = sort_transactions_by_date(result)
    if enable_filter_by_date:
        result = filter_old_transactions(result, start_date, combine_installments)
    return result


class MaxScraper(BrowserScraper):
    """Scraper for Max (formerly Leumi Card) credit card transactions.

    Uses the Max online API to fetch transaction data month by month
    after authenticating via the browser login flow.
    """

    def get_login_options(self, credentials: dict) -> LoginOptions:
        """Return Max-specific login configuration.

        Parameters
        ----------
        credentials : dict
            Must contain 'username' and 'password' keys.

        Returns
        -------
        LoginOptions
            Configuration for the Max login flow.
        """
        page = self.page

        async def check_readiness():
            await wait_until_element_found(
                page,
                ".personal-area > a.go-to-personal-area",
                only_visible=True,
            )

        async def pre_action():
            if await element_present_on_page(page, "#closePopup"):
                await click_button(page, "#closePopup")
            await click_button(page, ".personal-area > a.go-to-personal-area")
            if await element_present_on_page(page, ".login-link#private"):
                await click_button(page, ".login-link#private")
            await wait_until_element_found(page, "#login-password-link", only_visible=True)
            await click_button(page, "#login-password-link")
            await wait_until_element_found(
                page,
                "#login-password.tab-pane.active app-user-login-form",
                only_visible=True,
            )
            return None

        async def post_action():
            await _redirect_or_dialog(page)

        return LoginOptions(
            login_url=LOGIN_URL,
            fields=[
                {"selector": "#user-name", "value": credentials["username"]},
                {"selector": "#password", "value": credentials["password"]},
            ],
            submit_button_selector="app-user-login-form .general-button.send-me-code",
            possible_results=_get_possible_login_results(page),
            check_readiness=check_readiness,
            pre_action=pre_action,
            post_action=post_action,
            wait_until="domcontentloaded",
        )

    async def fetch_data(self) -> list[AccountResult]:
        """Fetch transaction data from Max API.

        Iterates through months from start_date to now, loading categories
        first, then fetching and merging transactions per card.

        Returns
        -------
        list[AccountResult]
            Accounts with their transactions.
        """
        future_months = self.options.future_months_to_scrape
        start_date = self.options.start_date
        start_limit = date.today() - relativedelta(years=4)
        effective_start = max(start_limit, start_date)
        all_months = get_all_months(effective_start, future_months)

        await _load_categories(self.page)

        all_results: dict[str, list[Transaction]] = {}
        for month_date in all_months:
            result = await _fetch_transactions_for_month(self.page, month_date)
            for account_number, txns in result.items():
                if account_number not in all_results:
                    all_results[account_number] = []
                all_results[account_number].extend(txns)

        # Prepare transactions for each account
        accounts = []
        for account_number, txns in all_results.items():
            prepared = _prepare_transactions(
                txns,
                effective_start,
                self.options.combine_installments,
                True,
            )
            accounts.append(
                AccountResult(
                    account_number=account_number,
                    transactions=prepared,
                )
            )

        return accounts


async def _redirect_or_dialog(page) -> None:
    """Wait for either a redirect or a login error dialog.

    Parameters
    ----------
    page : Page
        The Playwright browser page.
    """
    import asyncio

    done, pending = await asyncio.wait(
        [
            asyncio.create_task(
                wait_for_redirect(
                    page,
                    timeout=20.0,
                    ignore_list=[BASE_WELCOME_URL, f"{BASE_WELCOME_URL}/"],
                )
            ),
            asyncio.create_task(
                wait_until_element_found(page, INVALID_DETAILS_SELECTOR, only_visible=True)
            ),
            asyncio.create_task(
                wait_until_element_found(page, LOGIN_ERROR_SELECTOR, only_visible=True)
            ),
        ],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
    # Re-raise if the completed task had an exception (besides cancellation)
    for task in done:
        exc = task.exception()
        if exc is not None:
            raise exc


def _get_possible_login_results(page) -> dict[LoginResult, list]:
    """Build the possible login results map for Max.

    Parameters
    ----------
    page : Page
        The Playwright browser page.

    Returns
    -------
    dict[LoginResult, list]
        Mapping of login results to their detection checks.
    """

    async def is_invalid_password(**kwargs):
        return await element_present_on_page(page, INVALID_DETAILS_SELECTOR)

    async def is_unknown_error(**kwargs):
        return await element_present_on_page(page, LOGIN_ERROR_SELECTOR)

    return {
        LoginResult.SUCCESS: [SUCCESS_URL],
        LoginResult.CHANGE_PASSWORD: [PASSWORD_EXPIRED_URL],
        LoginResult.INVALID_PASSWORD: [is_invalid_password],
        LoginResult.UNKNOWN_ERROR: [is_unknown_error],
    }
