"""Scraper for the Israeli pension clearing house (המסלקה הפנסיונית).

The clearing house's saver portal (run by Swiftness) aggregates every pension
fund and Keren Hishtalmut a person holds, across all providers. It does not
serve live data: the user subscribes to a monthly information request, and each
fulfilled request is a *snapshot* as of a month end (``calcDate``) that the
portal keeps for about two months before deleting it.

Login is ID number + mobile phone, then a 6-digit SMS code, on
``auth.swiftness.co.il`` (behind reCAPTCHA v3 and F5 bot protection, hence a
real browser). On success the page redirects to ``savernew.swiftness.co.il``
with a JWT that the portal keeps in ``localStorage.auth_token`` and sends as a
bearer token to ``portalapi.swiftness.co.il``.

Every read on that API is a ``POST``, and so are the paid actions — ordering a
request, cancelling a broker authorization, paying through CreditGuard. The
scraper therefore only ever calls the fixed, read-only endpoints in
``_READ_ENDPOINTS``; anything else raises before a request is made.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any, Optional

from scraper.base import OTP_CANCEL_SENTINEL, BrowserScraper, OtpCanceledError
from scraper.exceptions import CredentialsError, InvalidOtpError, ScraperError
from scraper.models.account import AccountResult
from scraper.models.result import LoginResult
from scraper.models.transaction import Transaction, TransactionStatus, TransactionType
from scraper.utils import wait_until_element_found
from scraper.utils.policy_ids import normalize_policy_id, policy_id_key

logger = logging.getLogger(__name__)

PROVIDER = "mislaka"

LOGIN_URL = "https://auth.swiftness.co.il/login"
PORTAL_HOST = "savernew.swiftness.co.il"
API_BASE = "https://portalapi.swiftness.co.il/"

# Login step 1. The form opens on the e-mail method; the SMS button swaps the
# e-mail field for the phone field.
SMS_METHOD_SELECTOR = "#telephoneNumberBtn"
ID_FIELD_SELECTOR = "input#idNumber"
PHONE_FIELD_SELECTOR = "input#phone"
SUBMIT_SELECTOR = "button.submit_btn"

# Login step 2: six one-digit boxes (``formControlName`` "1".."6"). There is no
# submit button — the page verifies the code the moment the last box fills,
# moving focus to the next empty box after every digit.
OTP_FIRST_BOX_SELECTOR = '[formcontrolname="1"] input, input#ontimeInput1'

CREATE_OTP_PATH = "api/auth/createOtp"
LOGIN_WITH_OTP_PATH = "api/auth/loginwithotp"

# ``createOtp`` ``errorNum`` values the login page treats as a refusal
# (shown under the form), and the one that switches to the post-office code
# used only for first-time registration.
_CREATE_OTP_REFUSALS = {0, 3, -1, -2, -3, -4, -5}
_CREATE_OTP_POSTAL = 4

# ``loginwithotp`` ``loginStatus`` values (the portal's own enum).
_LOGIN_SUCCESS = 1
_LOGIN_EXPIRED = 0
_LOGIN_LOCKED = -1
_LOGIN_FAILURE = -2
_LOGIN_NO_SAVER = -4
_LOGIN_OTP_FAILURE = -6

_READ_ENDPOINTS = frozenset(
    {
        "api/desktop/getDesktopItems",
        "api/holdings/getSavingProductsDetails",
        "api/holdings/getBDPolicyEmployersList",
        "api/holdings/getBDPolicyYearlyDepositsInfo",
        "api/holdings/getBDPolicyEmployerInvestmentRoute",
        "api/holdings/getBDPolicyEmployerFees",
        "api/holdings/getBDPolicyEmployerOpenBalance",
        "api/holdings/getBDPolicyTotalYearlyDepositsInfo",
        "api/holdings/getCoversPolicies",
        "api/holdings/getSavingConcentrations",
        "api/holdings/getCorrespondenceShowSpecificIncident",
        "api/holdings/getPolicyYield",
        "api/holdings/getPolicyRepresentative",
        "api/holdings/getPolicyLoans",
        "api/holdings/getPolicyRetirementAgeForecast",
        "api/holdings/getPolicyRetirementAgeForecastFunds",
    }
)

# Key under which ``ScrapingResult.extras`` carries the per-report household
# summaries (see ``build_household_report``).
CLEARING_HOUSE_REPORTS = "clearing_house_reports"

# ``dataRecieveStatusCode`` of a request whose data arrived in full.
_FULL_DATA_STATUS = 100000002

_PRODUCT_KEREN_HISHTALMUT = 4
_PRODUCT_NEW_PENSION = 22

_POLICY_ACTIVE = 1

_DEPOSITS_PAGE_SIZE = 100

# The portal's own requests: JSON body, bearer token, and no cookies — the API
# host is cross-site and never asked for credentials, so ``fetch_post``'s
# ``credentials: 'include'`` would only invite a CORS rejection.
_API_POST_JS = """
async ([url, body, token]) => {
    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'BEARER ' + token,
            },
            body: JSON.stringify(body),
        });
        return {status: response.status, text: await response.text()};
    } catch (e) {
        return {status: 0, error: String(e)};
    }
}
"""


def _iso_date(value: Optional[str]) -> Optional[str]:
    """Return the ``YYYY-MM-DD`` part of a portal timestamp.

    The portal sends ``"0001-01-01T00:00:00"`` for "no date", which is
    treated as missing.
    """
    if not value or value.startswith("0001-"):
        return None
    return value.split("T")[0]


def _money(value: Any) -> float:
    """Coerce a portal amount (number, numeric string or null) to a float."""
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def complete_snapshots(desktop_items: dict) -> list[dict]:
    """Return the fully delivered information requests, oldest first.

    Parameters
    ----------
    desktop_items : dict
        ``getDesktopItems`` response.

    Returns
    -------
    list[dict]
        Items whose data arrived in full, sorted by ``calcDate``.
    """
    items = desktop_items.get("desktopEventsItems") or []
    complete = [
        item
        for item in items
        if item.get("dataRecieveStatusCode") == _FULL_DATA_STATUS
        and not item.get("isDisabled")
        and item.get("swiftnessKey")
        and _iso_date(item.get("calcDate"))
    ]
    return sorted(complete, key=lambda item: item["calcDate"])


def policy_type_of(product: dict) -> tuple[Optional[str], Optional[str]]:
    """Map a Mislaka product to our ``(policy_type, pension_type)``.

    Parameters
    ----------
    product : dict
        One ``getSavingProductsDetails`` row.

    Returns
    -------
    tuple
        ``("hishtalmut", None)``, ``("pension", "makifa" | "mashlima")``, or
        ``(None, None)`` for a product type we do not model yet (provident
        funds, executive insurance, investment gemel).
    """
    code = product.get("productTypeCode")
    if code == _PRODUCT_KEREN_HISHTALMUT:
        return "hishtalmut", None
    if code == _PRODUCT_NEW_PENSION:
        name = product.get("productTypeName") or ""
        return "pension", "makifa" if "מקיפה" in name else "mashlima"
    return None, None


def is_emptied(product: dict) -> bool:
    """Return whether a product is an inactive policy with nothing left in it.

    Such a policy's money moved to another fund (that transfer shows up as a
    deposit on the receiving policy), so it would only add a zero-balance
    account.

    Parameters
    ----------
    product : dict
        One ``getSavingProductsDetails`` row.

    Returns
    -------
    bool
        ``True`` for an inactive policy with a zero balance.
    """
    return (
        product.get("policyStatus") != _POLICY_ACTIVE
        and _money(product.get("accumulatedBalance")) == 0
    )


def _component_bucket(component_name: str) -> str:
    """Classify a money component as employee, employer or severance."""
    if "פיצויים" in component_name:
        return "compensation"
    if "עובד" in component_name:
        return "employee"
    return "employer"


def build_deposit_transactions(
    policy_key: str, deposit_rows: list[dict], employer_names: dict[Any, str]
) -> list[Transaction]:
    """Fold per-component deposit rows into one transaction per deposit.

    The portal reports each deposit as one row per money component
    (employee / employer / severance). HaPhoenix — whose history these rows
    must dedup against — stored one row per deposit, dated on the value date
    and keyed ``"<policy key>_<date>_<total>"``, so the rows are summed per
    (employer, value date) into exactly that shape.

    Parameters
    ----------
    policy_key : str
        ``policy_id_key`` of the policy; prefixes each identifier.
    deposit_rows : list[dict]
        ``getBDPolicyYearlyDepositsInfo`` rows, each tagged with the
        ``_employerKey`` it was fetched for.
    employer_names : dict
        Employer name by ``policyEmployerKey``.

    Returns
    -------
    list[Transaction]
        One completed transaction per deposit, positive amounts.
    """
    groups: dict[tuple[Any, str], dict[str, Any]] = {}
    for row in deposit_rows:
        value_date = _iso_date(row.get("valueDate"))
        if value_date is None:
            logger.warning(
                "Mislaka: dropping deposit row without a value date for policy %s",
                policy_key,
            )
            continue
        group = groups.setdefault(
            (row.get("_employerKey"), value_date),
            {"employee": 0.0, "employer": 0.0, "compensation": 0.0, "transfer": None},
        )
        bucket = _component_bucket(row.get("moneyComponentName") or "")
        group[bucket] += _money(row.get("depositAmount"))
        if row.get("transferingFundName"):
            group["transfer"] = row["transferingFundName"]

    transactions: list[Transaction] = []
    for (employer_key, value_date), group in sorted(
        groups.items(), key=lambda g: g[0][1]
    ):
        total = round(group["employee"] + group["employer"] + group["compensation"], 2)
        if total == 0:
            continue
        employer = employer_names.get(employer_key, "")
        if group["transfer"]:
            description = f"העברה - {group['transfer']}"
        else:
            description = f"הפקדה - {employer}" if employer else "הפקדה"
        memo_parts = [
            f"{label}: {group[key]:.0f}"
            for key, label in (
                ("employee", "עובד"),
                ("employer", "מעסיק"),
                ("compensation", "פיצויים"),
            )
            if group[key]
        ]
        transactions.append(
            Transaction(
                type=TransactionType.NORMAL,
                status=TransactionStatus.COMPLETED,
                date=value_date,
                processed_date=value_date,
                original_amount=total,
                original_currency="ILS",
                charged_amount=total,
                charged_currency="ILS",
                description=description,
                identifier=f"{policy_key}_{value_date}_{total}",
                memo=" / ".join(memo_parts) or None,
            )
        )
    return transactions


def build_investment_tracks(
    routes: list[dict], fallback_yield: Optional[float]
) -> list[dict]:
    """Aggregate per-component route rows into one entry per investment track.

    A track appears once per money component (and per employer); its share of
    the policy is its summed balance over the policy's total.

    Parameters
    ----------
    routes : list[dict]
        ``getBDPolicyEmployerInvestmentRoute`` rows across the policy's
        employers.
    fallback_yield : float, optional
        The policy's net yield, used when the route carries none.

    Returns
    -------
    list[dict]
        ``[{name, yield_pct, allocation_pct, sum}]`` in the shape the
        Insurances page reads.
    """
    sums: dict[str, float] = defaultdict(float)
    yields: dict[str, Optional[float]] = {}
    for route in routes:
        name = route.get("routeName") or ""
        sums[name] += _money(route.get("routeAccumulatedBalance"))
        if route.get("netYieldPercent") is not None:
            yields[name] = float(route["netYieldPercent"])
    total = sum(sums.values())
    return [
        {
            "name": name,
            "yield_pct": yields.get(name, fallback_yield),
            "allocation_pct": round(amount / total * 100, 2) if total else None,
            "sum": round(amount, 2),
        }
        for name, amount in sums.items()
    ]


def build_pension_covers(product: dict) -> list[dict]:
    """Return the pension's forecast payout and survivor/disability covers.

    Titles match what HaPhoenix stored, so a policy moving between the two
    providers keeps rendering the same rows.

    Parameters
    ----------
    product : dict
        One ``getSavingProductsDetails`` row for a pension product.

    Returns
    -------
    list[dict]
        ``[{title, desc, sum}]`` rows with a non-zero amount.
    """
    age = product.get("retirementAge")
    age_text = f" בגיל {age:.0f}" if isinstance(age, (int, float)) else ""
    rows = [
        (
            "קצבה בפרישה",
            f"קצבה חודשית הצפויה לך בפרישה{age_text}, ללא המשך הפקדות",
            product.get("monthlyOldAgePensionForecast"),
        ),
        (
            "קצבה בפרישה עם המשך הפקדות",
            f"קצבה חודשית הצפויה לך בפרישה{age_text} אם ההפקדות יימשכו",
            product.get("accumulatedOldAgePension"),
        ),
        (
            "קצבה לאלמן",
            "קצבה חודשית לאלמן/ה במקרה של מוות",
            product.get("accumulatedMateSurvivalPension"),
        ),
        (
            "קצבה ליתום",
            "קצבה חודשית ליתום במקרה של מוות",
            product.get("accumulatedChildSurvivalPension"),
        ),
        (
            "קצבה להורה נתמך",
            "קצבה חודשית להורה נתמך במקרה של מוות",
            product.get("accumulatedParentSurvivalPension"),
        ),
        (
            "קצבת נכות",
            "קצבה חודשית במקרה של נכות מלאה",
            product.get("accumulatedDisabilityPension"),
        ),
    ]
    return [
        {"title": title, "desc": desc, "sum": _money(amount)}
        for title, desc, amount in rows
        if _money(amount)
    ]


def months_charged_this_year(calc_date: str, join_date: Optional[str]) -> int:
    """Count the monthly charges a policy has paid this year up to a report.

    Parameters
    ----------
    calc_date : str
        The report's ``YYYY-MM-DD`` date.
    join_date : str, optional
        The policy's ``YYYY-MM-DD`` join date; charges start in its month
        when it falls in the report's year.

    Returns
    -------
    int
        Months from January (or the join month) through the report month.
    """
    year, month = int(calc_date[:4]), int(calc_date[5:7])
    first_month = 1
    if join_date and int(join_date[:4]) == year:
        first_month = int(join_date[5:7])
    return max(month - first_month + 1, 0)


def build_statement(
    opening_balance: Optional[float],
    yearly_deposits: float,
    profit: Optional[float],
    management_fee: Optional[float],
    monthly_risk_fee: Optional[float],
    months_charged: int,
    closing_balance: float,
) -> list[dict]:
    """Build the year-to-date movement statement the Insurances page classifies.

    The portal's management fee is year-to-date, but its risk premium is the
    latest *month's* charge (it stays flat from one report to the next while
    the fee grows). The page reports risk costs for the year, so the premium
    is extrapolated over the months charged — an estimate, and titled as one.
    The portal's actuarial figure is a one-off adjustment to last year's
    closing balance, not a movement of this year, so it is left out.

    Parameters
    ----------
    opening_balance : float, optional
        Balance at the end of last year.
    yearly_deposits : float
        Deposits since the start of the year.
    profit : float, optional
        Year-to-date profit net of fees (negative for a loss).
    management_fee : float, optional
        Management fees charged since the start of the year.
    monthly_risk_fee : float, optional
        Risk-insurance premium charged in the report's month.
    months_charged : int
        Months the premium has been charged this year.
    closing_balance : float
        Balance at the snapshot date.

    Returns
    -------
    list[dict]
        ``[{title, amount}]`` rows (see ``insurance_accounts.insurance_costs``).
    """
    rows = []
    if opening_balance is not None:
        rows.append({"title": "יתרה לתחילת שנה", "amount": opening_balance})
    if yearly_deposits:
        rows.append({"title": "הפקדות", "amount": yearly_deposits})
    if profit:
        rows.append({"title": "רווחים", "amount": profit})
    if management_fee:
        rows.append({"title": "דמי ניהול", "amount": -abs(management_fee)})
    if monthly_risk_fee and months_charged:
        rows.append(
            {
                "title": f"עלות הביטוח (הערכה: {months_charged} חודשים)",
                "amount": -round(abs(monthly_risk_fee) * months_charged, 2),
            }
        )
    rows.append({"title": "יתרה נוכחית", "amount": closing_balance})
    return rows


def ytd_profit(policy_yield: Optional[dict]) -> Optional[float]:
    """Return a policy's year-to-date profit (negative for a loss).

    The portal names the field ``netProfitPercent`` but it is an amount: it
    equals the standard file's ``REVACH-HEFSED-BENIKOI-HOZAHOT`` (profit net
    of fees) and HaPhoenix's "רווחים" row for the same months.

    Parameters
    ----------
    policy_yield : dict, optional
        ``getPolicyYield`` response.

    Returns
    -------
    float or None
        The signed amount, or ``None`` when the policy reports none.
    """
    if not policy_yield or policy_yield.get("netProfitPercent") is None:
        return None
    amount = _money(policy_yield["netProfitPercent"])
    return -amount if policy_yield.get("profitTypeName") == "הפסד" else amount


def build_loans(loans: Optional[list]) -> list[dict]:
    """Summarize the loans taken against a policy.

    The portal answers with a placeholder row even when there is no loan
    (zero amounts, ``0001-01-01`` dates, ``isLoanExistsState`` false); only
    rows describing a real loan are kept.

    Parameters
    ----------
    loans : list, optional
        ``getPolicyLoans`` response.

    Returns
    -------
    list[dict]
        One entry per loan: amount, outstanding balance, interest, monthly
        repayment, number of payments, start and end dates, and scope.
    """
    return [
        {
            "amount": _money(loan.get("loanAmount")),
            "balance": _money(loan.get("loanBalanceAmount")),
            "interest_pct": loan.get("interestPercent"),
            "monthly_payment": _money(loan.get("refundPaymentAmount")),
            "payments_months": loan.get("paymentsInMonths"),
            "received": _iso_date(loan.get("loanReceiveDate")),
            "ends": _iso_date(loan.get("loanEndDate")),
            "scope": loan.get("policyLoanLevelName"),
        }
        for loan in loans or []
        if loan.get("isLoanExistsState") or _money(loan.get("loanAmount"))
    ]


def build_representative(representative: Optional[dict]) -> Optional[dict]:
    """Summarize who holds power of attorney over a policy.

    Parameters
    ----------
    representative : dict, optional
        ``getPolicyRepresentative`` response.

    Returns
    -------
    dict or None
        Name, id, role, whether they may act, and the appointment window;
        ``None`` when no one is appointed.
    """
    if not representative or not representative.get("hasRepresentativeState"):
        return None
    return {
        "name": representative.get("representativeName"),
        "id": representative.get("representativeId"),
        "role": representative.get("representativeIdentityType"),
        "can_act": representative.get("actionExecutionPermission") == "כן",
        "appointed": _iso_date(representative.get("agentAppointmentDate")),
        "expires": _iso_date(representative.get("representativeExpireDate")),
    }


def build_household_report(
    calc_date: str, concentrations: dict, incident: Optional[dict] = None
) -> dict:
    """Build one monthly report's household-wide summary.

    Parameters
    ----------
    calc_date : str
        The report's ``YYYY-MM-DD`` date.
    concentrations : dict
        ``getSavingConcentrations`` response for the report.
    incident : dict, optional
        ``getCorrespondenceShowSpecificIncident`` response, for the
        subscription's expiry (only read for the newest report).

    Returns
    -------
    dict
        Totals at retirement, current savings, disability and survivor cover,
        and subscription status — the fields of ``clearing_house_reports``.
    """
    totals = concentrations.get("savingConcentration") or {}
    event = concentrations.get("eventInfo") or {}
    incident = incident or {}
    return {
        "calc_date": calc_date,
        "total_savings": _money(totals.get("total_CurrentSavings")),
        "forecast_total_balance": _money(
            totals.get("total_AccumulatedBalanceForecasts")
        ),
        "forecast_monthly_pension": _money(
            totals.get("total_AccumulatedOldAgePensions")
        ),
        "forecast_lump_sum": _money(
            totals.get("total_AccumulatedBalanceForecastOnePayment")
        ),
        "disability_monthly": _money(totals.get("total_WorkDisabilityAmountMonthly")),
        "survivor_spouse_monthly": _money(
            totals.get("total_DeathAmountMonthlyPartner")
        ),
        "survivor_child_monthly": _money(totals.get("total_DeathAmountMonthlyChild")),
        "death_lump_sum": _money(totals.get("total_LifeInsuranceOneTimePayment")),
        "report_number": event.get("numberOfIterations"),
        "report_count": event.get("allIterations"),
        "subscription_expires": _iso_date(incident.get("originalExpireDate")),
        "subscription_months_left": incident.get("monthLeft"),
        "license_holder": incident.get("licenseHolder"),
    }


def build_details(product: dict, calc_date: str) -> dict:
    """Collect the product facts we keep without a dedicated column.

    Parameters
    ----------
    product : dict
        One ``getSavingProductsDetails`` row.
    calc_date : str
        The snapshot's ``YYYY-MM-DD`` date.

    Returns
    -------
    dict
        Status, manufacturer, employer, forecasts and last-deposit split.
    """
    return {
        "source_date": calc_date,
        "status": product.get("policyStatusName"),
        "manufacturer": product.get("manufacturerName"),
        "product_type": product.get("productTypeName"),
        "plan_name": product.get("planName"),
        "join_date": _iso_date(product.get("joinDate")),
        "employer": product.get("employerName"),
        "employer_status": product.get("employerStatusName"),
        "last_deposit_date": _iso_date(product.get("lastDepositDate")),
        "last_deposit": {
            "employee": _money(product.get("employeeLastDeposit")),
            "employer": _money(product.get("employerLastDeposit")),
            "compensation": _money(product.get("compensationLastDeposit")),
        },
        "calculated_salary": product.get("calculatedSalary"),
        "net_yield_pct": product.get("netYieldPercent"),
        "retirement_age": product.get("retirementAge"),
        "balance_forecast": product.get("accumulatedBalanceForecast"),
        "balance_forecast_no_deposits": product.get(
            "accumulatedBalanceForecastNoPremium"
        ),
        "monthly_pension_forecast": product.get("accumulatedOldAgePension"),
        "monthly_pension_forecast_no_deposits": product.get(
            "monthlyOldAgePensionForecast"
        ),
        "death_insurance_monthly": product.get("deathInsuranceAmountMonthly"),
        "disability_cover_pct": product.get("weightedDisabilityPercent"),
        "pledge": product.get("pledge"),
        "confiscation": product.get("confiscation"),
    }


class MislakaScraper(BrowserScraper):
    """Scraper for the pension clearing house saver portal.

    Login: ID number + mobile phone -> SMS code. Data: every product in every
    fully delivered monthly snapshot, as one ``AccountResult`` per pension /
    Keren Hishtalmut policy. The newest snapshot supplies balances and
    metadata; every snapshot contributes its deposits (each covers only its
    own calendar year) and a month-end balance point.
    """

    _token: Optional[str] = None
    _last_month_fees: dict = {}

    async def login(self) -> LoginResult:
        """Authenticate with ID number, phone and an SMS code.

        Returns
        -------
        LoginResult
            ``SUCCESS`` once the portal holds a session token. Wrong ID/phone
            combinations and refused codes raise their classified errors.

        Raises
        ------
        CredentialsError
            The portal does not know this ID/phone pair.
        InvalidOtpError
            The SMS code was wrong or expired.
        OtpCanceledError
            The user cancelled at the code prompt.
        """
        self._emit_progress("navigating to login page")
        await self.navigate_to(LOGIN_URL, wait_until="domcontentloaded")
        await wait_until_element_found(
            self.page, SMS_METHOD_SELECTOR, only_visible=True, timeout=30000
        )
        await self._human_delay(1.0, 2.0)
        await self._human_mouse_move()
        await self._human_delay(0.3, 0.8)

        self._emit_progress("filling login credentials")
        await self.page.click(SMS_METHOD_SELECTOR)
        await wait_until_element_found(
            self.page, PHONE_FIELD_SELECTOR, only_visible=True, timeout=10000
        )
        await self._human_delay(0.4, 0.9)
        await self.page.click(ID_FIELD_SELECTOR)
        await self._type_like_human(
            ID_FIELD_SELECTOR, str(self.credentials["id"]).strip()
        )
        await self._human_delay(0.5, 1.2)
        await self.page.click(PHONE_FIELD_SELECTOR)
        await self._type_like_human(
            PHONE_FIELD_SELECTOR, str(self.credentials["phoneNumber"]).strip()
        )
        await self._human_delay(0.5, 1.0)

        self._emit_progress("requesting SMS code")
        await self.page.wait_for_selector(
            f"{SUBMIT_SELECTOR}:not([disabled])", timeout=10000
        )
        async with self.page.expect_response(
            lambda r: CREATE_OTP_PATH in r.url and r.request.method == "POST",
            timeout=30000,
        ) as create_otp:
            await self.page.click(SUBMIT_SELECTOR)
        self._check_create_otp(await (await create_otp.value).json())

        await wait_until_element_found(
            self.page, OTP_FIRST_BOX_SELECTOR, only_visible=True, timeout=30000
        )
        if self.on_otp_request is None:
            return self._fail_login(
                LoginResult.UNKNOWN_ERROR,
                "the portal sent an SMS code but no code prompt was available "
                "(on_otp_request callback not set)",
            )
        self._emit_progress("waiting for OTP code")
        otp_code = await self.on_otp_request()
        if otp_code == OTP_CANCEL_SENTINEL:
            raise OtpCanceledError("two-factor authentication canceled by the user")

        # With a visible browser the user can finish the code step by hand
        # while we wait for them to relay it; the boxes are gone by then.
        if PORTAL_HOST not in self.page.url:
            self._emit_progress("submitting OTP code")
            await self.page.click(OTP_FIRST_BOX_SELECTOR)
            async with self.page.expect_response(
                lambda r: LOGIN_WITH_OTP_PATH in r.url and r.request.method == "POST",
                timeout=30000,
            ) as login_with_otp:
                await self.page.keyboard.type(otp_code.strip(), delay=120)
            self._check_login_with_otp(await (await login_with_otp.value).json())

        self._emit_progress("waiting for login to complete")
        await self.page.wait_for_url(lambda url: PORTAL_HOST in url, timeout=30000)
        await self.page.wait_for_function(
            "() => !!localStorage.getItem('auth_token')", timeout=30000
        )
        self._token = await self.page.evaluate(
            "() => localStorage.getItem('auth_token')"
        )
        logger.info("Mislaka login successful")
        return LoginResult.SUCCESS

    @staticmethod
    def _check_create_otp(response: dict) -> None:
        """Raise when the portal refused to send an SMS code.

        Raises
        ------
        CredentialsError
            The portal refused the ID/phone pair, or the account needs the
            post-office registration code rather than an SMS.
        """
        error_num = response.get("errorNum")
        detail = response.get("errorDescription") or f"errorNum={error_num}"
        if error_num == _CREATE_OTP_POSTAL:
            raise CredentialsError(
                "the clearing house asks for a post-office registration code; "
                f"finish registering in the portal first ({detail})"
            )
        if error_num in _CREATE_OTP_REFUSALS or response.get("isSuccess") is False:
            raise CredentialsError(
                f"the clearing house refused to send a code: {detail}"
            )

    @staticmethod
    def _check_login_with_otp(response: dict) -> None:
        """Raise unless the code was accepted.

        Raises
        ------
        InvalidOtpError
            Wrong, failed or expired code.
        CredentialsError
            Unknown ID/phone pair, or a locked account.
        ScraperError
            Any other refusal.
        """
        status = response.get("loginStatus")
        if status == _LOGIN_SUCCESS:
            return
        detail = response.get("errorMsg") or f"loginStatus={status}"
        if status in (_LOGIN_FAILURE, _LOGIN_EXPIRED, _LOGIN_OTP_FAILURE):
            raise InvalidOtpError(f"the clearing house rejected the code: {detail}")
        if status in (_LOGIN_NO_SAVER, _LOGIN_LOCKED):
            raise CredentialsError(f"the clearing house refused the login: {detail}")
        raise ScraperError(f"the clearing house login failed: {detail}")

    async def _api(self, path: str, body: dict) -> Any:
        """POST to a read-only portal endpoint with the session token.

        Parameters
        ----------
        path : str
            Endpoint path relative to the API host; must be in
            ``_READ_ENDPOINTS``.
        body : dict
            JSON request body.

        Returns
        -------
        Any
            The decoded JSON response.

        Raises
        ------
        ValueError
            ``path`` is not a known read-only endpoint.
        """
        if path not in _READ_ENDPOINTS:
            raise ValueError(
                f"refusing to call non-allowlisted Mislaka endpoint {path!r}"
            )
        result = await self.page.evaluate(
            _API_POST_JS, [API_BASE + path, body, self._token]
        )
        status = result.get("status")
        if result.get("error") or not 200 <= (status or 0) < 300:
            raise ScraperError(
                f"Mislaka {path} failed: {result.get('error') or f'HTTP {status}'}"
            )
        text = result.get("text")
        return json.loads(text) if text else None

    async def fetch_data(self) -> list[AccountResult]:
        """Fetch every pension and Keren Hishtalmut policy.

        Returns
        -------
        list[AccountResult]
            One result per supported policy, from the newest snapshot, with
            deposits and month-end balances gathered from every snapshot.

        Raises
        ------
        ScraperError
            No fully delivered snapshot exists yet.
        """
        self._emit_progress("listing monthly reports")
        snapshots = complete_snapshots(
            await self._api("api/desktop/getDesktopItems", {})
        )
        if not snapshots:
            raise ScraperError(
                "the clearing house has no completed information request yet; "
                "order one in the portal and scrape again once it arrives"
            )

        policies: dict[str, dict[str, Any]] = {}
        reports: list[dict] = []
        for index, snapshot in enumerate(snapshots):
            is_latest = index == len(snapshots) - 1
            calc_date = _iso_date(snapshot["calcDate"])
            self._emit_progress(f"reading report as of {calc_date}")
            reports.append(
                await self._household_report(
                    snapshot["swiftnessKey"], calc_date, is_latest
                )
            )
            products = (
                await self._api(
                    "api/holdings/getSavingProductsDetails",
                    {"SwiftnessKey": snapshot["swiftnessKey"]},
                )
            ).get("savingProductsDetails") or []
            for product in products:
                policy_type, pension_type = policy_type_of(product)
                policy_id = normalize_policy_id(product.get("policyNumber"))
                if policy_type is None or not policy_id:
                    logger.info(
                        "Mislaka: skipping unsupported product type %s (%s)",
                        product.get("productTypeCode"),
                        product.get("productTypeName"),
                    )
                    continue
                if is_emptied(product):
                    logger.info("Mislaka: skipping emptied inactive policy")
                    continue
                entry = policies.setdefault(
                    policy_id,
                    {"deposits": {}, "balance_history": {}, "latest": None},
                )
                entry["balance_history"][calc_date] = _money(
                    product.get("accumulatedBalance")
                )
                await self._collect_policy(
                    entry, snapshot["swiftnessKey"], calc_date, product, is_latest
                )
                if is_latest:
                    entry["latest"] = (product, calc_date, policy_type, pension_type)

        self.extras[CLEARING_HOUSE_REPORTS] = reports
        return [
            self._to_account_result(policy_id, entry)
            for policy_id, entry in policies.items()
            if entry["latest"] is not None
        ]

    async def _household_report(
        self, swiftness_key: str, calc_date: str, is_latest: bool
    ) -> dict:
        """Read one report's household summary (and, if newest, subscription).

        Also remembers the newest report's last-month management fee per
        policy, which the portal only serves inside this response.

        Parameters
        ----------
        swiftness_key : str
            The report being read.
        calc_date : str
            The report's date.
        is_latest : bool
            Whether this is the newest report.

        Returns
        -------
        dict
            See ``build_household_report``.
        """
        concentrations = (
            await self._api(
                "api/holdings/getSavingConcentrations", {"SwiftnessKey": swiftness_key}
            )
            or {}
        )
        incident = None
        if is_latest:
            incident = await self._api(
                "api/holdings/getCorrespondenceShowSpecificIncident",
                {"swiftnessKey": swiftness_key},
            )
            products = (concentrations.get("productsDetails") or {}).get(
                "savingProductsdetailsList"
            ) or []
            self._last_month_fees = {
                p.get("policy_Key"): p.get("actualManagementFeeAmount")
                for p in products
            }
        return build_household_report(calc_date, concentrations, incident)

    async def _collect_policy(
        self,
        entry: dict[str, Any],
        swiftness_key: str,
        calc_date: str,
        product: dict,
        is_latest: bool,
    ) -> None:
        """Gather one policy's deposits (and, for the newest report, details).

        Parameters
        ----------
        entry : dict
            Accumulator for the policy across snapshots; mutated in place.
        swiftness_key : str
            The snapshot being read.
        calc_date : str
            The snapshot's date.
        product : dict
            The policy's ``getSavingProductsDetails`` row.
        is_latest : bool
            Whether this is the newest snapshot — the only one whose tracks,
            fees and statement are kept.
        """
        policy_key = product["policy_Key"]
        ids = {"policyKey": policy_key, "swiftnessHandlerId": swiftness_key}
        employers = await self._api("api/holdings/getBDPolicyEmployersList", ids) or []
        employer_names = {e.get("recordKey"): e.get("name") or "" for e in employers}

        deposit_rows: list[dict] = []
        routes: list[dict] = []
        opening_balance: Optional[float] = None
        yearly_deposits = 0.0
        management_fee: Optional[float] = None
        risk_fee: Optional[float] = None
        for employer in employers:
            employer_ids = {**ids, "policyEmployerKey": employer.get("recordKey")}
            for row in await self._fetch_all_deposits(employer_ids):
                deposit_rows.append({**row, "_employerKey": employer.get("recordKey")})
            if not is_latest:
                continue
            routes.extend(
                await self._api(
                    "api/holdings/getBDPolicyEmployerInvestmentRoute", employer_ids
                )
                or []
            )
            opening = await self._api(
                "api/holdings/getBDPolicyEmployerOpenBalance", employer_ids
            )
            if opening and opening.get("endOfLastYearBalanceAmount") is not None:
                opening_balance = (opening_balance or 0.0) + _money(
                    opening["endOfLastYearBalanceAmount"]
                )
            totals = await self._api(
                "api/holdings/getBDPolicyTotalYearlyDepositsInfo", employer_ids
            )
            if totals:
                yearly_deposits += sum(
                    _money(totals.get(key))
                    for key in (
                        "employeeTotalDeposits",
                        "employerTotalDeposits",
                        "compensationTotalDeposits",
                    )
                )
            fees = await self._api("api/holdings/getBDPolicyEmployerFees", employer_ids)
            if fees and fees.get("totalManagementFee") is not None:
                management_fee = (management_fee or 0.0) + _money(
                    fees["totalManagementFee"]
                )
            if fees and fees.get("totalRiskFeeAmount") is not None:
                risk_fee = (risk_fee or 0.0) + _money(fees["totalRiskFeeAmount"])

        key = policy_id_key(product.get("policyNumber"))
        for txn in build_deposit_transactions(key, deposit_rows, employer_names):
            entry["deposits"][txn.identifier] = txn

        if is_latest:
            profit = ytd_profit(await self._api("api/holdings/getPolicyYield", ids))
            entry["tracks"] = build_investment_tracks(
                routes, product.get("netYieldPercent")
            )
            entry["statement"] = build_statement(
                opening_balance,
                round(yearly_deposits, 2),
                profit,
                management_fee,
                risk_fee,
                months_charged_this_year(calc_date, _iso_date(product.get("joinDate"))),
                _money(product.get("accumulatedBalance")),
            )
            details = build_details(product, calc_date)
            details["ytd_profit"] = profit
            details["last_month_management_fee"] = self._last_month_fees.get(policy_key)
            details["representative"] = build_representative(
                await self._api("api/holdings/getPolicyRepresentative", ids)
            )
            details["loans"] = build_loans(
                await self._api("api/holdings/getPolicyLoans", ids)
            )
            if product.get("productTypeCode") == _PRODUCT_NEW_PENSION:
                risks = await self._api("api/holdings/getCoversPolicies", ids) or []
                details["plan_risks"] = [
                    r.get("riskName") for r in risks if r.get("riskName")
                ]
                details["forecast_yield_pct"] = await self._forecast_yield(ids)
            entry["details"] = details

    async def _forecast_yield(self, ids: dict) -> Optional[float]:
        """Return the return rate the pension's retirement forecast assumes.

        Parameters
        ----------
        ids : dict
            ``policyKey`` and ``swiftnessHandlerId``.

        Returns
        -------
        float or None
            The assumed annual return, in percent.
        """
        forecasts = await self._api("api/holdings/getPolicyRetirementAgeForecast", ids)
        if not forecasts:
            return None
        funds = (
            await self._api(
                "api/holdings/getPolicyRetirementAgeForecastFunds",
                {
                    **ids,
                    "policyRetirementAgeForecastKey": forecasts[0].get("recordKey"),
                },
            )
            or []
        )
        return next(
            (f["yieldForecastPercent"] for f in funds if f.get("yieldForecastPercent")),
            None,
        )

    async def _fetch_all_deposits(self, employer_ids: dict) -> list[dict]:
        """Page through one employer's deposits for the snapshot's year.

        Parameters
        ----------
        employer_ids : dict
            ``policyKey``, ``swiftnessHandlerId`` and ``policyEmployerKey``.

        Returns
        -------
        list[dict]
            Every deposit row across pages.
        """
        rows: list[dict] = []
        page = 1
        while True:
            batch = (
                await self._api(
                    "api/holdings/getBDPolicyYearlyDepositsInfo",
                    {
                        **employer_ids,
                        "PageSize": _DEPOSITS_PAGE_SIZE,
                        "CurrentPage": page,
                    },
                )
                or []
            )
            rows.extend(batch)
            total = batch[0].get("total", 0) if batch else 0
            if not batch or len(rows) >= total or len(batch) < _DEPOSITS_PAGE_SIZE:
                return rows
            page += 1

    @staticmethod
    def _to_account_result(policy_id: str, entry: dict[str, Any]) -> AccountResult:
        """Assemble a policy's ``AccountResult`` from its gathered data.

        Parameters
        ----------
        policy_id : str
            Normalized policy number.
        entry : dict
            The policy's accumulator from ``fetch_data``.

        Returns
        -------
        AccountResult
            Deposits, newest balance and ``insurance_accounts`` metadata.
        """
        product, calc_date, policy_type, pension_type = entry["latest"]
        balance = _money(product.get("accumulatedBalance"))
        details = entry.get("details") or {}
        is_pension = policy_type == "pension"
        return AccountResult(
            account_number=policy_id,
            transactions=sorted(entry["deposits"].values(), key=lambda t: t.date),
            balance=balance,
            balance_date=calc_date,
            metadata={
                "provider": PROVIDER,
                "policy_id": policy_id,
                "policy_type": policy_type,
                "pension_type": pension_type,
                "account_name": product.get("policyName")
                or product.get("productTypeName")
                or policy_id,
                "balance": balance,
                "balance_date": calc_date,
                "investment_tracks": json.dumps(
                    entry.get("tracks") or [], ensure_ascii=False
                ),
                "commission_deposits_pct": product.get(
                    "yealryManagementFeePercentDeposit"
                ),
                "commission_savings_pct": product.get(
                    "yealryManagementFeePercentAggregation"
                ),
                "insurance_covers": (
                    json.dumps(build_pension_covers(product), ensure_ascii=False)
                    if is_pension
                    else None
                ),
                "insurance_costs": json.dumps(
                    entry.get("statement") or [], ensure_ascii=False
                ),
                "liquidity_date": None
                if is_pension
                else _iso_date(product.get("pullingMoneyDate")),
                "details": json.dumps(details, ensure_ascii=False),
                "balance_history": [
                    {"date": date, "balance": amount}
                    for date, amount in sorted(entry["balance_history"].items())
                ],
            },
        )
