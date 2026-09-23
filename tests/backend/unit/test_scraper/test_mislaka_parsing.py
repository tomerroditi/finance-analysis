"""Tests for the pension clearing house (Mislaka) scraper's parsing.

The portal is exercised through ``MislakaScraper._api``, faked here with
canned responses shaped like the live portal's (all figures synthetic). The
deposit identifiers are the load-bearing part: they must equal what the
HaPhoenix scraper produced for the same deposit, or taking a policy over from
HaPhoenix re-inserts its whole history.
"""

import asyncio
import json

import pytest

from scraper.exceptions import CredentialsError, InvalidOtpError, ScraperError
from scraper.providers.insurances.hafenix import HaPhoenixScraper
from scraper.providers.insurances.mislaka import (
    CLEARING_HOUSE_REPORTS,
    MislakaScraper,
    build_deposit_transactions,
    build_household_report,
    build_loans,
    build_representative,
    build_investment_tracks,
    build_pension_covers,
    build_statement,
    complete_snapshots,
    months_charged_this_year,
    policy_type_of,
    ytd_profit,
)
from scraper.utils.policy_ids import policy_id_key

FULL = 100000002
JULY_KEY = "snap-july"
AUGUST_KEY = "snap-august"


def _deposit(value_date: str, component: str, amount: float, total: int = 3) -> dict:
    """One component row of ``getBDPolicyYearlyDepositsInfo``."""
    return {
        "valueDate": f"{value_date}T00:00:00",
        "moneyComponentName": component,
        "depositAmount": amount,
        "transferingFundName": None,
        "total": total,
    }


def _product(**overrides: object) -> dict:
    """A ``getSavingProductsDetails`` row for a Keren Hishtalmut."""
    product = {
        "policy_Key": 501,
        "productTypeCode": 4,
        "productTypeName": "קרן השתלמות",
        "policyNumber": "7-925-053655-0",
        "policyName": "קרן השתלמות לדוגמה",
        "accumulatedBalance": 12000.0,
        "yealryManagementFeePercentDeposit": 0.0,
        "yealryManagementFeePercentAggregation": 0.6,
        "netYieldPercent": 5.1,
        "pullingMoneyDate": "2032-01-31T00:00:00",
        "calcDate": "2026-08-31T00:00:00",
        "policyStatus": 1,
    }
    product.update(overrides)
    return product


class FakePortal:
    """Canned portal answering ``MislakaScraper._api`` by endpoint path."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def __call__(self, path: str, body: dict) -> object:
        """Return the canned response for ``path``."""
        self.calls.append((path, body))
        snapshot = body.get("SwiftnessKey") or body.get("swiftnessHandlerId")
        july = snapshot == JULY_KEY
        if path == "api/desktop/getDesktopItems":
            return {
                "desktopEventsItems": [
                    {"swiftnessKey": AUGUST_KEY, "calcDate": "2026-08-31T00:00:00",
                     "dataRecieveStatusCode": FULL, "isDisabled": False},
                    {"swiftnessKey": JULY_KEY, "calcDate": "2026-07-31T00:00:00",
                     "dataRecieveStatusCode": FULL, "isDisabled": False},
                    {"swiftnessKey": "pending", "calcDate": "2026-09-30T00:00:00",
                     "dataRecieveStatusCode": 100000001, "isDisabled": False},
                ]
            }
        if path == "api/holdings/getSavingProductsDetails":
            balance = 10500.0 if july else 12000.0
            return {
                "savingProductsDetails": [
                    _product(accumulatedBalance=balance),
                    _product(policy_Key=502, productTypeCode=2, policyNumber="gemel-1"),
                    _product(
                        policy_Key=503,
                        productTypeCode=22,
                        policyNumber="emptied-pension",
                        policyStatus=2,
                        accumulatedBalance=0.0,
                    ),
                ]
            }
        if path == "api/holdings/getBDPolicyEmployersList":
            return [{"recordKey": 9001, "name": "Acme Ltd"}]
        if path == "api/holdings/getBDPolicyYearlyDepositsInfo":
            rows = [
                _deposit("2026-07-08", 'קה"ש עובד', 392.8, total=4),
                _deposit("2026-07-08", 'קה"ש מעביד', 1178.4, total=4),
            ]
            if not july:
                rows += [
                    _deposit("2026-08-05", 'קה"ש עובד', 392.8, total=4),
                    _deposit("2026-08-05", 'קה"ש מעביד', 1178.4, total=4),
                ]
            return rows
        if path == "api/holdings/getBDPolicyEmployerInvestmentRoute":
            return [
                {"routeName": "S&P 500", "routeAccumulatedBalance": 3000.0,
                 "netYieldPercent": None},
                {"routeName": "S&P 500", "routeAccumulatedBalance": 9000.0,
                 "netYieldPercent": None},
            ]
        if path == "api/holdings/getBDPolicyEmployerOpenBalance":
            return {"endOfLastYearBalanceAmount": 2500.0}
        if path == "api/holdings/getBDPolicyTotalYearlyDepositsInfo":
            return {"employeeTotalDeposits": 2906.72, "employerTotalDeposits": 8720.16,
                    "compensationTotalDeposits": 0.0}
        if path == "api/holdings/getBDPolicyEmployerFees":
            return {"totalManagementFee": 30.5, "totalRiskFeeAmount": 0.0}
        if path == "api/holdings/getSavingConcentrations":
            return {
                "eventInfo": {"numberOfIterations": 2 if july else 3, "allIterations": 7},
                "savingConcentration": {
                    "total_CurrentSavings": 10500.0 if july else 12000.0,
                    "total_AccumulatedOldAgePensions": 9000.0,
                    "total_AccumulatedBalanceForecastOnePayment": 250000.0,
                    "total_WorkDisabilityAmountMonthly": 7000.0,
                },
                "productsDetails": {
                    "savingProductsdetailsList": [
                        {"policy_Key": 501, "actualManagementFeeAmount": 4.2}
                    ]
                },
            }
        if path == "api/holdings/getCorrespondenceShowSpecificIncident":
            return {
                "originalExpireDate": "2027-04-11T00:00:00",
                "monthLeft": 7,
                "licenseHolder": "Some Bank",
            }
        if path == "api/holdings/getPolicyYield":
            return {"netYieldPercent": 5.1, "netProfitPercent": 480.0, "profitTypeName": "רווח"}
        if path == "api/holdings/getPolicyLoans":
            return [
                {
                    "loanAmount": 20000,
                    "loanBalanceAmount": 12500.5,
                    "interestPercent": 3.1,
                    "refundPaymentAmount": 450.0,
                    "paymentsInMonths": 48,
                    "loanReceiveDate": "2025-02-01T00:00:00",
                    "loanEndDate": "2029-02-01T00:00:00",
                    "isLoanExistsState": True,
                    "policyLoanLevelName": "Policy",
                }
            ]
        if path == "api/holdings/getPolicyRepresentative":
            return {
                "hasRepresentativeState": True,
                "representativeName": "Agency Ltd",
                "representativeId": "123",
                "representativeIdentityType": "סוכן",
                "actionExecutionPermission": "כן",
                "agentAppointmentDate": "2025-12-16T00:00:00",
                "representativeExpireDate": "2035-12-16T00:00:00",
            }
        raise AssertionError(f"unexpected endpoint {path}")


def _scraper_with(portal: FakePortal) -> MislakaScraper:
    """A scraper whose API calls are answered by ``portal``."""
    scraper = MislakaScraper("mislaka", {"id": "1", "phoneNumber": "2"})
    scraper._api = portal
    return scraper


class TestSnapshotsAndProductTypes:
    """Which reports are read, and which products are kept."""

    def test_only_fully_delivered_reports_are_read_oldest_first(self):
        """Verify pending reports are dropped and the rest sorted by date."""
        items = asyncio.run(FakePortal()("api/desktop/getDesktopItems", {}))

        keys = [s["swiftnessKey"] for s in complete_snapshots(items)]

        assert keys == [JULY_KEY, AUGUST_KEY]

    @pytest.mark.parametrize(
        ("code", "name", "expected"),
        [
            (4, "קרן השתלמות", ("hishtalmut", None)),
            (22, "פנסיה חדשה מקיפה", ("pension", "makifa")),
            (22, "פנסיה חדשה כללית", ("pension", "mashlima")),
            (2, "קופת גמל", (None, None)),
        ],
    )
    def test_product_type_mapping(self, code, name, expected):
        """Verify product codes map onto our policy and pension types."""
        product = {"productTypeCode": code, "productTypeName": name}

        assert policy_type_of(product) == expected


class TestDeposits:
    """Per-component deposit rows fold into HaPhoenix-shaped deposits."""

    def test_components_are_summed_into_one_deposit(self):
        """Verify one transaction per deposit with the summed total and memo."""
        rows = [
            {**_deposit("2026-08-05", "תגמולים עובד", 1810.22), "_employerKey": 1},
            {**_deposit("2026-08-05", "תגמולים מעביד", 1680.92), "_employerKey": 1},
            {**_deposit("2026-08-05", "פיצויים", 2154.16), "_employerKey": 1},
        ]

        [txn] = build_deposit_transactions("1215029099", rows, {1: "Acme Ltd"})

        assert txn.charged_amount == 5645.3
        assert txn.date == "2026-08-05"
        assert txn.description == "הפקדה - Acme Ltd"
        assert txn.memo == "עובד: 1810 / מעסיק: 1681 / פיצויים: 2154"
        assert txn.identifier == "1215029099_2026-08-05_5645.3"

    def test_identifier_matches_haphoenix_for_the_same_kh_deposit(self):
        """Verify the takeover dedups: both scrapers key a deposit identically."""
        haphoenix = HaPhoenixScraper.__new__(HaPhoenixScraper)
        [phoenix_txn] = haphoenix._build_hishtalmut_deposits(
            policy_id_key("007-925-053655 (9527977)"),
            {"deposits": {"list": [{"list": [
                {"depositDate": "05.08.2026", "totalDeposit": 1571.2},
            ]}]}},
        )
        rows = [
            {**_deposit("2026-08-05", 'קה"ש עובד', 392.8), "_employerKey": 1},
            {**_deposit("2026-08-05", 'קה"ש מעביד', 1178.4), "_employerKey": 1},
        ]

        [mislaka_txn] = build_deposit_transactions(
            policy_id_key("7-925-053655-0"), rows, {}
        )

        assert mislaka_txn.identifier == phoenix_txn.identifier

    def test_transfer_in_is_labelled_with_its_source_fund(self):
        """Verify a transfer from another fund is not called a deposit."""
        row = {**_deposit("2026-03-01", "תגמולים עובד", 5000.0), "_employerKey": 1}
        row["transferingFundName"] = "Other Fund"

        [txn] = build_deposit_transactions("k", [row], {1: "Acme"})

        assert txn.description == "העברה - Other Fund"


class TestMetadataBuilders:
    """Tracks, covers and the year-to-date statement."""

    def test_track_rows_merge_across_components(self):
        """Verify one track per route name with its share of the balance."""
        routes = [
            {"routeName": "A", "routeAccumulatedBalance": 75.0, "netYieldPercent": None},
            {"routeName": "A", "routeAccumulatedBalance": 25.0, "netYieldPercent": None},
            {"routeName": "B", "routeAccumulatedBalance": 100.0, "netYieldPercent": 4.2},
        ]

        tracks = build_investment_tracks(routes, fallback_yield=5.0)

        assert tracks == [
            {"name": "A", "yield_pct": 5.0, "allocation_pct": 50.0, "sum": 100.0},
            {"name": "B", "yield_pct": 4.2, "allocation_pct": 50.0, "sum": 100.0},
        ]

    def test_pension_covers_keep_haphoenix_titles_and_skip_zeroes(self):
        """Verify cover titles match HaPhoenix's and empty covers are dropped."""
        product = {
            "retirementAge": 67.0,
            "monthlyOldAgePensionForecast": 5307.35,
            "accumulatedOldAgePension": 29333.0,
            "accumulatedMateSurvivalPension": 15516.18,
            "accumulatedChildSurvivalPension": 0.0,
        }

        titles = [c["title"] for c in build_pension_covers(product)]

        assert titles == ["קצבה בפרישה", "קצבה בפרישה עם המשך הפקדות", "קצבה לאלמן"]

    def test_statement_reports_fees_as_a_deduction(self):
        """Verify the management fee is negative so the classifier counts it."""
        rows = build_statement(1000.0, 500.0, None, 12.5, None, 8, 1480.0)

        assert {"title": "דמי ניהול", "amount": -12.5} in rows
        assert rows[-1] == {"title": "יתרה נוכחית", "amount": 1480.0}

    def test_monthly_risk_premium_is_extrapolated_over_the_months_charged(self):
        """Verify the one-month premium becomes a titled year-to-date estimate."""
        rows = build_statement(1000.0, 500.0, None, 12.5, 194.39, 8, 1480.0)

        [risk] = [r for r in rows if r["title"].startswith("עלות הביטוח")]
        assert risk == {"title": "עלות הביטוח (הערכה: 8 חודשים)", "amount": -1555.12}

    def test_statement_carries_the_ytd_profit_row(self):
        """Verify year-to-date profit lands in the statement as "רווחים"."""
        rows = build_statement(1000.0, 500.0, 120.0, 12.5, None, 8, 1607.5)

        assert {"title": "רווחים", "amount": 120.0} in rows

    def test_ytd_profit_is_signed_by_the_profit_type(self):
        """Verify a reported loss comes back negative, and no figure as None."""
        assert ytd_profit({"netProfitPercent": 50.0, "profitTypeName": "הפסד"}) == -50.0
        assert ytd_profit({"netYieldPercent": 5.1}) is None

    def test_the_no_loan_placeholder_row_is_dropped(self):
        """Verify the portal's zero-filled "no loan" row yields no loans."""
        placeholder = {
            "loanAmount": 0,
            "loanReceiveDate": "0001-01-01T00:00:00",
            "loanEndDate": "0001-01-01T00:00:00",
            "isLoanExistsState": False,
        }

        assert build_loans([placeholder]) == []
        assert build_loans(None) == []

    def test_representative_is_none_when_no_agent_is_appointed(self):
        """Verify a policy without an agent carries no representative."""
        assert build_representative({"hasRepresentativeState": False}) is None

    def test_household_report_reads_totals_and_subscription(self):
        """Verify the summary maps the portal's totals and subscription fields."""
        report = build_household_report(
            "2026-08-31",
            {
                "eventInfo": {"numberOfIterations": 1, "allIterations": 7},
                "savingConcentration": {"total_DeathAmountMonthlyPartner": 23400.0},
            },
            {"originalExpireDate": "2027-04-11T00:00:00", "monthLeft": 7},
        )

        assert report["survivor_spouse_monthly"] == 23400.0
        assert (report["report_number"], report["report_count"]) == (1, 7)
        assert report["subscription_expires"] == "2027-04-11"

    @pytest.mark.parametrize(
        ("calc_date", "join_date", "expected"),
        [
            ("2026-08-31", "2023-01-04", 8),
            ("2026-08-31", "2026-03-15", 6),
            ("2026-08-31", None, 8),
        ],
    )
    def test_months_charged_start_at_january_or_the_join_month(
        self, calc_date, join_date, expected
    ):
        """Verify a policy joined this year is charged from its join month."""
        assert months_charged_this_year(calc_date, join_date) == expected


class TestFetchData:
    """``fetch_data`` over a faked portal."""

    def test_newest_report_supplies_metadata_and_every_report_its_deposits(self):
        """Verify one KH result (unsupported and emptied products skipped)."""
        portal = FakePortal()

        [account] = asyncio.run(_scraper_with(portal).fetch_data())

        assert account.account_number == "7-925-053655-0"
        assert account.balance == 12000.0
        assert account.balance_date == "2026-08-31"
        assert [t.date for t in account.transactions] == ["2026-07-08", "2026-08-05"]
        meta = account.metadata
        assert meta["provider"] == "mislaka"
        assert meta["policy_type"] == "hishtalmut"
        assert meta["liquidity_date"] == "2032-01-31"
        assert meta["commission_savings_pct"] == 0.6
        assert meta["balance_history"] == [
            {"date": "2026-07-31", "balance": 10500.0},
            {"date": "2026-08-31", "balance": 12000.0},
        ]
        assert json.loads(meta["investment_tracks"]) == [
            {"name": "S&P 500", "yield_pct": 5.1, "allocation_pct": 100.0, "sum": 12000.0}
        ]

    def test_every_report_yields_a_household_summary(self):
        """Verify one summary per report, with the subscription on the newest."""
        scraper = _scraper_with(FakePortal())

        asyncio.run(scraper.fetch_data())

        reports = scraper.extras[CLEARING_HOUSE_REPORTS]
        assert [r["calc_date"] for r in reports] == ["2026-07-31", "2026-08-31"]
        assert [r["total_savings"] for r in reports] == [10500.0, 12000.0]
        assert reports[0]["subscription_expires"] is None
        assert reports[1]["subscription_expires"] == "2027-04-11"

    def test_newest_report_adds_profit_fees_agent_and_loans(self):
        """Verify the per-policy extras land in the details and statement."""
        [account] = asyncio.run(_scraper_with(FakePortal()).fetch_data())

        details = json.loads(account.metadata["details"])
        assert details["ytd_profit"] == 480.0
        assert details["last_month_management_fee"] == 4.2
        assert details["representative"]["name"] == "Agency Ltd"
        assert details["representative"]["can_act"] is True
        assert details["loans"] == [
            {
                "amount": 20000.0,
                "balance": 12500.5,
                "interest_pct": 3.1,
                "monthly_payment": 450.0,
                "payments_months": 48,
                "received": "2025-02-01",
                "ends": "2029-02-01",
                "scope": "Policy",
            }
        ]
        statement = json.loads(account.metadata["insurance_costs"])
        assert {"title": "רווחים", "amount": 480.0} in statement

    def test_details_endpoints_are_only_read_for_the_newest_report(self):
        """Verify older reports cost only the product and deposit reads."""
        portal = FakePortal()

        asyncio.run(_scraper_with(portal).fetch_data())

        route_reads = [
            body for path, body in portal.calls
            if path == "api/holdings/getBDPolicyEmployerInvestmentRoute"
        ]
        assert [b["swiftnessHandlerId"] for b in route_reads] == [AUGUST_KEY]

    def test_no_delivered_report_is_an_error(self):
        """Verify a portal with only pending requests fails the scrape."""
        async def portal(path: str, body: dict) -> dict:
            return {"desktopEventsItems": []}

        with pytest.raises(ScraperError, match="no completed information request"):
            asyncio.run(_scraper_with(portal).fetch_data())


class TestApiSafety:
    """The scraper cannot reach the portal's paid or mutating endpoints."""

    def test_non_allowlisted_endpoint_is_refused_before_any_request(self):
        """Verify an endpoint outside the read allowlist raises."""
        scraper = MislakaScraper("mislaka", {"id": "1", "phoneNumber": "2"})

        with pytest.raises(ValueError, match="non-allowlisted"):
            asyncio.run(scraper._api("api/events/SaveEvent", {}))


class TestLoginResponses:
    """The portal's login answers map onto classified errors."""

    def test_refused_sms_is_a_credentials_error(self):
        """Verify a createOtp refusal surfaces the portal's description."""
        with pytest.raises(CredentialsError, match="unknown saver"):
            MislakaScraper._check_create_otp(
                {"isSuccess": False, "errorNum": -1, "errorDescription": "unknown saver"}
            )

    def test_postal_registration_code_is_reported(self):
        """Verify an unregistered saver is told to finish registration."""
        with pytest.raises(CredentialsError, match="registration"):
            MislakaScraper._check_create_otp({"isSuccess": True, "errorNum": 4})

    def test_sent_code_passes(self):
        """Verify a successful createOtp raises nothing."""
        MislakaScraper._check_create_otp({"isSuccess": True, "errorNum": 1})

    @pytest.mark.parametrize("status", [0, -2, -6])
    def test_wrong_or_expired_code_is_an_invalid_otp(self, status):
        """Verify failed, expired and OTP-failure statuses are wrong-code errors."""
        with pytest.raises(InvalidOtpError):
            MislakaScraper._check_login_with_otp({"loginStatus": status})

    def test_unknown_saver_is_a_credentials_error(self):
        """Verify an ID/phone pair the portal does not know is a login error."""
        with pytest.raises(CredentialsError):
            MislakaScraper._check_login_with_otp({"loginStatus": -4})

    def test_accepted_code_passes(self):
        """Verify loginStatus 1 raises nothing."""
        MislakaScraper._check_login_with_otp({"loginStatus": 1})
