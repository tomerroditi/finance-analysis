import logging
import re
from datetime import date, datetime
from typing import Optional

from dateutil.relativedelta import relativedelta

from scraper.base import BrowserScraper, ScraperOptions
from scraper.models.account import AccountResult
from scraper.models.result import LoginResult
from scraper.models.transaction import (
    InstallmentInfo,
    Transaction,
    TransactionStatus,
    TransactionType,
)
from scraper.utils import (
    fetch_get_within_page,
    filter_old_transactions,
    fix_installments,
    get_all_months,
    sleep,
)

logger = logging.getLogger(__name__)

SHEKEL_CURRENCY = "ILS"
SHEKEL_CURRENCY_KEYWORD = 'ש"ח'
ALT_SHEKEL_CURRENCY = "NIS"

COUNTRY_CODE = "212"
ID_TYPE = "1"
INSTALLMENTS_KEYWORD = "תשלום"

DATE_FORMAT = "%d/%m/%Y"

RATE_LIMIT_SLEEP_BETWEEN = 1.0  # seconds
RATE_LIMIT_TRANSACTIONS_BATCH_SIZE = 10


def _get_accounts_url(services_url: str, month_date: date) -> str:
    """Build the accounts (DashboardMonth) URL for a given month.

    Parameters
    ----------
    services_url : str
        The base services proxy URL.
    month_date : date
        The first day of the month to query.

    Returns
    -------
    str
        The full URL with query parameters.
    """
    billing_date = month_date.strftime("%Y-%m-%d")
    return (
        f"{services_url}"
        f"?reqName=DashboardMonth"
        f"&actionCode=0"
        f"&billingDate={billing_date}"
        f"&format=Json"
    )


def _get_transactions_url(services_url: str, month_date: date) -> str:
    """Build the transactions (CardsTransactionsList) URL for a given month.

    Parameters
    ----------
    services_url : str
        The base services proxy URL.
    month_date : date
        The first day of the month to query.

    Returns
    -------
    str
        The full URL with query parameters.
    """
    month = month_date.month
    year = month_date.year
    month_str = f"{month:02d}"
    return (
        f"{services_url}"
        f"?reqName=CardsTransactionsList"
        f"&month={month_str}"
        f"&year={year}"
        f"&requiredDate=N"
    )


def _convert_currency(currency_str: str) -> str:
    """Convert Hebrew/alternative currency codes to ISO codes.

    Parameters
    ----------
    currency_str : str
        The currency string from the API response.

    Returns
    -------
    str
        ISO currency code.
    """
    if currency_str == SHEKEL_CURRENCY_KEYWORD or currency_str == ALT_SHEKEL_CURRENCY:
        return SHEKEL_CURRENCY
    return currency_str


def _get_installments_info(txn: dict) -> Optional[InstallmentInfo]:
    """Parse installment info from a transaction's moreInfo field.

    Parameters
    ----------
    txn : dict
        Raw transaction dictionary.

    Returns
    -------
    Optional[InstallmentInfo]
        Parsed installment info, or None if not applicable.
    """
    more_info = txn.get("moreInfo", "")
    if not more_info or INSTALLMENTS_KEYWORD not in more_info:
        return None
    matches = re.findall(r"\d+", more_info)
    if len(matches) < 2:
        return None
    return InstallmentInfo(
        number=int(matches[0]),
        total=int(matches[1]),
    )


def _get_transaction_type(txn: dict) -> TransactionType:
    """Determine transaction type based on installment info.

    Parameters
    ----------
    txn : dict
        Raw transaction dictionary.

    Returns
    -------
    TransactionType
        INSTALLMENTS if installment info present, otherwise NORMAL.
    """
    return (
        TransactionType.INSTALLMENTS
        if _get_installments_info(txn)
        else TransactionType.NORMAL
    )


def _parse_date(date_str: str) -> Optional[datetime]:
    """Parse a date string in DD/MM/YYYY format.

    Parameters
    ----------
    date_str : str
        The date string to parse.

    Returns
    -------
    Optional[datetime]
        Parsed datetime, or None if parsing fails.
    """
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, DATE_FORMAT)
    except ValueError:
        return None


def _convert_transactions(
    txns: list[dict], processed_date: str
) -> list[Transaction]:
    """Convert raw scraped transactions to Transaction objects.

    Parameters
    ----------
    txns : list[dict]
        Raw transaction dictionaries from the API.
    processed_date : str
        The default processed date (billing date) for these transactions.

    Returns
    -------
    list[Transaction]
        Converted Transaction objects.
    """
    result = []
    for txn in txns:
        # Filter out non-transactions
        if txn.get("dealSumType") == "1":
            continue
        voucher_ratz = txn.get("voucherNumberRatz", "")
        voucher_ratz_outbound = txn.get("voucherNumberRatzOutbound", "")
        if voucher_ratz == "000000000" or voucher_ratz_outbound == "000000000":
            continue

        is_outbound = txn.get("dealSumOutbound", False)

        if is_outbound:
            txn_date_str = txn.get("fullPurchaseDateOutbound", "")
        else:
            txn_date_str = txn.get("fullPurchaseDate", "")

        txn_date = _parse_date(txn_date_str)
        if txn_date is None:
            continue

        # Determine processed date
        full_payment_date = txn.get("fullPaymentDate", "")
        if full_payment_date:
            parsed_payment = _parse_date(full_payment_date)
            current_processed_date = (
                parsed_payment.isoformat() if parsed_payment else processed_date
            )
        else:
            current_processed_date = processed_date

        # Determine identifier
        if is_outbound:
            identifier_raw = voucher_ratz_outbound
        else:
            identifier_raw = voucher_ratz
        try:
            identifier = str(int(identifier_raw))
        except (ValueError, TypeError):
            identifier = identifier_raw or None

        # Determine amounts (API may return strings or numbers)
        if is_outbound:
            original_amount = -float(txn.get("dealSumOutbound", 0))
            charged_amount = -float(txn.get("paymentSumOutbound", 0))
        else:
            original_amount = -float(txn.get("dealSum", 0))
            charged_amount = -float(txn.get("paymentSum", 0))

        # Determine currencies
        original_currency = _convert_currency(
            txn.get("currentPaymentCurrency") or txn.get("currencyId", "")
        )
        charged_currency = _convert_currency(txn.get("currencyId", ""))

        # Determine description
        if is_outbound:
            description = txn.get("fullSupplierNameOutbound", "")
        else:
            description = txn.get("fullSupplierNameHeb", "")

        installments = _get_installments_info(txn)

        result.append(
            Transaction(
                type=_get_transaction_type(txn),
                identifier=identifier,
                date=txn_date.isoformat(),
                processed_date=current_processed_date,
                original_amount=original_amount,
                original_currency=original_currency,
                charged_amount=charged_amount,
                charged_currency=charged_currency,
                description=description,
                memo=txn.get("moreInfo", ""),
                installments=installments,
                status=TransactionStatus.COMPLETED,
            )
        )

    return result


async def _fetch_accounts(
    page, services_url: str, month_date: date
) -> list[dict]:
    """Fetch the list of card accounts for a given month.

    Parameters
    ----------
    page : Page
        The Playwright browser page.
    services_url : str
        The base services proxy URL.
    month_date : date
        The first day of the month to query.

    Returns
    -------
    list[dict]
        List of account dicts with 'index', 'account_number', and 'processed_date'.
    """
    data_url = _get_accounts_url(services_url, month_date)
    logger.debug("Fetching accounts from %s", data_url)

    data = await fetch_get_within_page(page, data_url, ignore_errors=True)

    if (
        data
        and isinstance(data.get("Header"), dict)
        and data["Header"].get("Status") == "1"
        and data.get("DashboardMonthBean")
    ):
        cards_charges = data["DashboardMonthBean"].get("cardsCharges", [])
        if cards_charges:
            accounts = []
            for card in cards_charges:
                billing_date = _parse_date(card.get("billingDate", ""))
                accounts.append({
                    "index": int(card.get("cardIndex", 0)),
                    "account_number": card.get("cardNumber", ""),
                    "processed_date": (
                        billing_date.isoformat() if billing_date else ""
                    ),
                })
            return accounts

    return []


async def _fetch_transactions_for_month(
    page,
    options: ScraperOptions,
    services_url: str,
    start_date: date,
    month_date: date,
) -> dict[str, dict]:
    """Fetch transactions for all cards for a single month.

    Parameters
    ----------
    page : Page
        The Playwright browser page.
    options : ScraperOptions
        Scraper options.
    services_url : str
        The base services proxy URL.
    start_date : date
        Earliest date to keep transactions from.
    month_date : date
        The first day of the month to query.

    Returns
    -------
    dict[str, dict]
        Mapping of account number to dict with 'account_number', 'index', and 'txns'.
    """
    accounts = await _fetch_accounts(page, services_url, month_date)
    data_url = _get_transactions_url(services_url, month_date)

    await sleep(RATE_LIMIT_SLEEP_BETWEEN)
    logger.debug(
        "Fetching transactions from %s for month %s",
        data_url,
        month_date.strftime("%Y-%m"),
    )

    data = await fetch_get_within_page(page, data_url, ignore_errors=True)

    if (
        data
        and isinstance(data.get("Header"), dict)
        and data["Header"].get("Status") == "1"
        and data.get("CardsTransactionsListBean")
    ):
        account_txns: dict[str, dict] = {}
        for account in accounts:
            index_key = f"Index{account['index']}"
            txn_groups_data = data["CardsTransactionsListBean"].get(index_key, {})
            current_card_txns = txn_groups_data.get("CurrentCardTransactions", [])

            if current_card_txns:
                all_txns: list[Transaction] = []
                for txn_group in current_card_txns:
                    israel_txns = txn_group.get("txnIsrael", [])
                    if israel_txns:
                        converted = _convert_transactions(
                            israel_txns, account["processed_date"]
                        )
                        all_txns.extend(converted)

                    abroad_txns = txn_group.get("txnAbroad", [])
                    if abroad_txns:
                        converted = _convert_transactions(
                            abroad_txns, account["processed_date"]
                        )
                        all_txns.extend(converted)

                if not options.combine_installments:
                    all_txns = fix_installments(all_txns)
                all_txns = filter_old_transactions(
                    all_txns, start_date, options.combine_installments
                )

                account_txns[account["account_number"]] = {
                    "account_number": account["account_number"],
                    "index": account["index"],
                    "txns": all_txns,
                }

        return account_txns

    return {}


async def _fetch_all_transactions(
    page,
    options: ScraperOptions,
    services_url: str,
    start_date: date,
) -> list[AccountResult]:
    """Fetch transactions for all months and combine into account results.

    Parameters
    ----------
    page : Page
        The Playwright browser page.
    options : ScraperOptions
        Scraper options.
    services_url : str
        The base services proxy URL.
    start_date : date
        Effective start date for fetching.

    Returns
    -------
    list[AccountResult]
        List of accounts with their transactions.
    """
    future_months = options.future_months_to_scrape
    all_months = get_all_months(start_date, future_months)

    results: list[dict[str, dict]] = []
    for month_date in all_months:
        result = await _fetch_transactions_for_month(
            page, options, services_url, start_date, month_date
        )
        results.append(result)

    # Combine transactions across months
    combined_txns: dict[str, list[Transaction]] = {}
    for result in results:
        for account_number, account_data in result.items():
            if account_number not in combined_txns:
                combined_txns[account_number] = []
            combined_txns[account_number].extend(account_data["txns"])

    accounts = []
    for account_number, txns in combined_txns.items():
        accounts.append(
            AccountResult(
                account_number=account_number,
                transactions=txns,
            )
        )

    return accounts


class IsracardAmexBaseScraper(BrowserScraper):
    """Base scraper for Isracard and Amex credit card providers.

    Uses the Isracard/Amex services API to authenticate and fetch
    transaction data. Subclasses must set BASE_URL and COMPANY_CODE
    class attributes.
    """

    BASE_URL: str = ""
    COMPANY_CODE: str = ""

    def __init__(
        self,
        provider: str,
        credentials: dict,
        options: ScraperOptions | None = None,
    ):
        super().__init__(provider, credentials, options)
        self._services_url = f"{self.BASE_URL}/services/ProxyRequestHandler.ashx"

    async def login(self) -> LoginResult:
        """Execute the Isracard/Amex login flow via API calls.

        Uses request interception to block unwanted scripts, then
        performs login via the ValidateIdData and performLogonI API
        endpoints.

        Returns
        -------
        LoginResult
            The outcome of the login attempt.
        """
        # Set up request interception to block bot-detection scripts
        async def handle_route(route):
            if "detector-dom.min.js" in route.request.url:
                logger.debug(
                    "Blocking request to detector-dom.min.js"
                )
                await route.abort()
            else:
                await route.continue_()

        await self.page.route("**/*", handle_route)

        # Mask headless user agent
        user_agent = await self.page.evaluate("() => navigator.userAgent")
        masked_agent = user_agent.replace("HeadlessChrome/", "Chrome/")
        await self.page.set_extra_http_headers({"User-Agent": masked_agent})

        await self.navigate_to(f"{self.BASE_URL}/personalarea/Login")

        self._emit_progress("logging in")

        credentials = self.credentials
        validate_url = f"{self._services_url}?reqName=ValidateIdData"
        validate_request = {
            "id": credentials["id"],
            "cardSuffix": credentials["card6Digits"],
            "countryCode": COUNTRY_CODE,
            "idType": ID_TYPE,
            "checkLevel": "1",
            "companyCode": self.COMPANY_CODE,
        }

        logger.debug("Logging in with validate request")
        validate_result = await self.fetch_post(
            validate_url, validate_request
        )

        if (
            not validate_result
            or not isinstance(validate_result.get("Header"), dict)
            or validate_result["Header"].get("Status") != "1"
            or not validate_result.get("ValidateIdDataBean")
        ):
            raise Exception("Unknown error during login")

        return_code = validate_result["ValidateIdDataBean"].get("returnCode", "")
        logger.debug("User validate with return code '%s'", return_code)

        if return_code == "1":
            user_name = validate_result["ValidateIdDataBean"].get("userName", "")

            login_url = f"{self._services_url}?reqName=performLogonI"
            login_request = {
                "KodMishtamesh": user_name,
                "MisparZihuy": credentials["id"],
                "Sisma": credentials["password"],
                "cardSuffix": credentials["card6Digits"],
                "countryCode": COUNTRY_CODE,
                "idType": ID_TYPE,
            }

            logger.debug("User login started")
            login_result = await self.fetch_post(login_url, login_request)
            status = login_result.get("status") if login_result else None
            logger.debug("User login with status '%s'", status)

            if login_result and str(status) == "1":
                self._emit_progress("login success")
                return LoginResult.SUCCESS

            if login_result and str(status) == "3":
                self._emit_progress("change password required")
                return LoginResult.CHANGE_PASSWORD

            self._emit_progress("login failed")
            return LoginResult.INVALID_PASSWORD

        if return_code == "4":
            self._emit_progress("change password required")
            return LoginResult.CHANGE_PASSWORD

        self._emit_progress("login failed")
        return LoginResult.INVALID_PASSWORD

    async def fetch_data(self) -> list[AccountResult]:
        """Fetch transaction data from the Isracard/Amex API.

        Fetches transactions month by month from the effective start date
        to the current month.

        Returns
        -------
        list[AccountResult]
            Accounts with their transactions.
        """
        default_start = date.today() - relativedelta(years=1)
        start_date = self.options.start_date or default_start
        effective_start = max(default_start, start_date)

        return await _fetch_all_transactions(
            self.page,
            self.options,
            self._services_url,
            effective_start,
        )
