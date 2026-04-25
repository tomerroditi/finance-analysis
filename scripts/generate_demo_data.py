"""Generate a pre-built demo SQLite database for the finance analysis dashboard.

Creates ~1,200+ transactions for a fictional Israeli family ("The Cohens") over
14 months, along with categories, budgets, investments, tagging rules, and all
supporting records.

Usage
-----
    python scripts/generate_demo_data.py
"""

import json
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — allow importing backend modules from project root
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from backend.models.base import Base  # noqa: E402
from backend.models import (  # noqa: E402
    BankBalance,
    BankTransaction,
    BudgetRule,
    CashBalance,
    CashTransaction,
    Category,
    CreditCardTransaction,
    InsuranceAccount,
    InsuranceTransaction,
    Investment,
    InvestmentBalanceSnapshot,
    Liability,
    ManualInvestmentTransaction,
    PendingRefund,
    RefundLink,
    RetirementGoal,
    ScrapingHistory,
    SplitTransaction,
    TaggingRule,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REFERENCE_DATE = date(2026, 2, 25)
START_DATE = REFERENCE_DATE - timedelta(days=365 * 3 + 1)  # ~3 years back
DB_PATH = PROJECT_ROOT / "backend" / "resources" / "demo_data.db"

random.seed(42)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def rand_amount(lo: float, hi: float) -> float:
    """Return a random float rounded to 2 decimals in [lo, hi]."""
    return round(random.uniform(lo, hi), 2)


def rand_date_in_month(year: int, month: int, day_lo: int = 1, day_hi: int = 28) -> str:
    """Return a random YYYY-MM-DD string within the given month."""
    day = random.randint(day_lo, min(day_hi, 28))
    return date(year, month, day).isoformat()


def month_range(start: date, end: date):
    """Yield (year, month) tuples from *start* to *end* inclusive."""
    current = date(start.year, start.month, 1)
    while current <= end:
        yield current.year, current.month
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)


def next_month(year: int, month: int):
    """Return (year, month) for the following month."""
    if month == 12:
        return year + 1, 1
    return year, month + 1


# ---------------------------------------------------------------------------
# Data definitions
# ---------------------------------------------------------------------------
CATEGORIES_DATA = {
    "Food": (["Groceries", "Restaurants", "Coffee", "Delivery"], "🍔"),
    "Transportation": (["Gas", "Parking", "Public Transportation", "Taxi", "Maintenance"], "🚗"),
    "Household": (["Mortgage", "Electricity", "Water", "Internet", "Cleaning Supplies", "Home Insurance", "National Insurance", "Municipal Tax"], "🏠"),
    "Entertainment": (["Streaming", "Cinema", "Events", "Games"], "🎉"),
    "Health": (["Pharmacy", "Doctor", "Gym", "Dental"], "💊"),
    "Kids": (["Daycare", "Activities", "Clothing", "School Supplies"], "👶"),
    "Shopping": (["Electronics", "Clothing", "Online", "Gifts", "Flea Market"], "🛒"),
    "Education": (["Courses", "Books"], "🎓"),
    "Subscriptions": (["Netflix", "Spotify", "Chat-GPT"], "📱"),
    "Vacations": (["Flights", "Hotel", "Food"], "🌍"),
    "Other": (["ATM", "Bank Commisions", "Haircut", "Tip"], "🙅"),
    "Salary": (["Tech Company", "School District"], "💵"),
    "Other Income": (["Prior Wealth", "Freelance"], "💵"),
    "Investments": (["Stock Market Fund", "Savings Plan", "Corporate Bond"], "💲"),
    "Liabilities": (["Mortgage", "Car Loan"], "💳"),
    "Credit Cards": (["Bill"], "💳"),
    "Ignore": (["Credit Card Bill", "Internal Transactions"], "🚫"),
    "Home Renovation": (["Materials", "Labor", "Furniture"], "🏠"),
    "Wedding": (["Venue", "Catering", "Photography", "Attire", "Rings", "Invitations", "Honeymoon"], "💒"),
}

TAGGING_RULES_DATA = [
    ("Supermarket", {"type": "OR", "subconditions": [
        {"type": "CONDITION", "field": "description", "operator": "contains", "value": "SHUFERSAL"},
        {"type": "CONDITION", "field": "description", "operator": "contains", "value": "RAMI LEVY"},
    ]}, "Food", "Groceries"),
    ("Rides", {"type": "OR", "subconditions": [
        {"type": "CONDITION", "field": "description", "operator": "contains", "value": "UBER"},
        {"type": "CONDITION", "field": "description", "operator": "contains", "value": "GETT"},
    ]}, "Transportation", "Taxi"),
    ("Streaming", {"type": "OR", "subconditions": [
        {"type": "CONDITION", "field": "description", "operator": "contains", "value": "NETFLIX"},
        {"type": "CONDITION", "field": "description", "operator": "contains", "value": "SPOTIFY"},
    ]}, "Subscriptions", "Netflix"),
    ("Gas Station", {"type": "OR", "subconditions": [
        {"type": "CONDITION", "field": "description", "operator": "contains", "value": "PAZ"},
        {"type": "CONDITION", "field": "description", "operator": "contains", "value": "SONOL"},
        {"type": "CONDITION", "field": "description", "operator": "contains", "value": "DELEK"},
    ]}, "Transportation", "Gas"),
    ("Pharmacy", {"type": "CONDITION", "field": "description", "operator": "contains", "value": "SUPER-PHARM"}, "Health", "Pharmacy"),
    ("Daycare", {"type": "AND", "subconditions": [
        {"type": "CONDITION", "field": "description", "operator": "contains", "value": "GAN"},
        {"type": "CONDITION", "field": "amount", "operator": "less_than", "value": "-1000"},
    ]}, "Kids", "Daycare"),
    ("Gym", {"type": "CONDITION", "field": "description", "operator": "contains", "value": "HOLMES PLACE"}, "Health", "Gym"),
    ("Online Shopping", {"type": "OR", "subconditions": [
        {"type": "CONDITION", "field": "description", "operator": "contains", "value": "AMAZON"},
        {"type": "CONDITION", "field": "description", "operator": "contains", "value": "ALIEXPRESS"},
    ]}, "Shopping", "Online"),
    # Operator variety — exercises starts_with, equals, between in the rule preview/editor.
    ("Food Delivery", {"type": "CONDITION", "field": "description", "operator": "starts_with", "value": "WOLT"}, "Food", "Delivery"),
    ("Salary - Tech", {"type": "AND", "subconditions": [
        {"type": "CONDITION", "field": "description", "operator": "equals", "value": "TECH COMPANY LTD - SALARY"},
        {"type": "CONDITION", "field": "provider", "operator": "equals", "value": "hapoalim"},
    ]}, "Salary", "Tech Company"),
    ("Small ATM Fees", {"type": "AND", "subconditions": [
        {"type": "CONDITION", "field": "description", "operator": "contains", "value": "ATM"},
        {"type": "CONDITION", "field": "amount", "operator": "between", "value": ["-25", "-1"]},
    ]}, "Other", "Bank Commisions"),
]


# ---------------------------------------------------------------------------
# Generator functions
# ---------------------------------------------------------------------------


def create_categories(session):
    """Insert all 18 categories."""
    for name, (tags, icon) in CATEGORIES_DATA.items():
        session.add(Category(name=name, tags=tags, icon=icon))
    session.flush()


def create_tagging_rules(session):
    """Insert 8 tagging rules."""
    for name, conditions, category, tag in TAGGING_RULES_DATA:
        session.add(TaggingRule(
            name=name,
            conditions=conditions,
            category=category,
            tag=tag,
        ))
    session.flush()


def generate_cc_transactions(session):
    """Generate credit card transactions and return monthly totals per card.

    Returns
    -------
    dict
        {(year, month): {"max": total, "visa_cal": total}}
    list
        All CreditCardTransaction objects (flushed, unique_ids available)
    """
    monthly_totals: dict[tuple[int, int], dict[str, float]] = {}
    all_cc_txns: list[CreditCardTransaction] = []
    cc_counter = 0

    months = list(month_range(START_DATE, REFERENCE_DATE))

    # Track which months are in the last 6 for home renovation
    six_months_ago = REFERENCE_DATE - timedelta(days=180)
    # Wedding planning: roughly last 10 months — gradual vendor payments.
    # Use a generous threshold so the schedule's earliest entry (months_back=10) isn't
    # dropped just because the mid-month anchor falls slightly before the 300-day mark.
    ten_months_ago = REFERENCE_DATE - timedelta(days=330)

    # Wedding vendor schedule (CC card, roughly one per month in the last 10 months).
    # Bigger payments (venue, catering) go via the bank — see generate_bank_transactions.
    wedding_cc_schedule = {
        10: ("TIFFANY RINGS ISRAEL", "Rings", -9800.0),
        9:  ("PHOTOGRAPHER BOOKING", "Photography", -2500.0),
        8:  ("WEDDING DRESS - ROTEM", "Attire", -5800.0),
        7:  ("GROOM SUIT - HUGO BOSS", "Attire", -3600.0),
        6:  ("INVITATIONS - PAPER KING", "Invitations", -1450.0),
        5:  ("WEDDING BAND - MUSIC DUO", "Catering", -2800.0),
        4:  ("PHOTOGRAPHER - FINAL", "Photography", -3500.0),
        3:  ("HAIR & MAKEUP TRIAL", "Attire", -900.0),
        2:  ("WEDDING FAVORS - ETSY", "Invitations", -680.0),
        1:  ("HONEYMOON FLIGHTS", "Honeymoon", -9400.0),
    }

    for year, month in months:
        max_total = 0.0
        visa_total = 0.0

        # ---- MAX (Family Card) ----

        # Groceries 10-14
        for _ in range(random.randint(10, 14)):
            cc_counter += 1
            desc = random.choice(["SHUFERSAL DEAL", "RAMI LEVY", "MEGA MARKET", "AM:PM"])
            amt = rand_amount(-350, -80)
            txn = CreditCardTransaction(
                id=f"demo-cc-{cc_counter:04d}",
                date=rand_date_in_month(year, month),
                provider="max",
                account_name="Family Card",
                description=desc,
                amount=amt,
                category="Food",
                tag="Groceries",
                source="credit_card_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_cc_txns.append(txn)
            max_total += amt

        # Restaurants 5-8
        for _ in range(random.randint(5, 8)):
            cc_counter += 1
            desc = random.choice(["CAFE CAFE", "AROMA", "MCDONALDS", "PIZZA HUT", "JAPANIKA"])
            amt = rand_amount(-250, -60)
            txn = CreditCardTransaction(
                id=f"demo-cc-{cc_counter:04d}",
                date=rand_date_in_month(year, month),
                provider="max",
                account_name="Family Card",
                description=desc,
                amount=amt,
                category="Food",
                tag="Restaurants",
                source="credit_card_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_cc_txns.append(txn)
            max_total += amt

        # Gas 3-4
        for _ in range(random.randint(3, 4)):
            cc_counter += 1
            desc = random.choice(["SONOL", "PAZ", "DELEK"])
            amt = rand_amount(-350, -150)
            txn = CreditCardTransaction(
                id=f"demo-cc-{cc_counter:04d}",
                date=rand_date_in_month(year, month),
                provider="max",
                account_name="Family Card",
                description=desc,
                amount=amt,
                category="Transportation",
                tag="Gas",
                source="credit_card_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_cc_txns.append(txn)
            max_total += amt

        # Daycare 1
        cc_counter += 1
        amt = rand_amount(-3000, -2500)
        txn = CreditCardTransaction(
            id=f"demo-cc-{cc_counter:04d}",
            date=rand_date_in_month(year, month, 1, 5),
            provider="max",
            account_name="Family Card",
            description="GAN YELADIM SHEMESH",
            amount=amt,
            category="Kids",
            tag="Daycare",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        )
        session.add(txn)
        all_cc_txns.append(txn)
        max_total += amt

        # Pharmacy 1-2
        for _ in range(random.randint(1, 2)):
            cc_counter += 1
            amt = rand_amount(-150, -30)
            txn = CreditCardTransaction(
                id=f"demo-cc-{cc_counter:04d}",
                date=rand_date_in_month(year, month),
                provider="max",
                account_name="Family Card",
                description="SUPER-PHARM",
                amount=amt,
                category="Health",
                tag="Pharmacy",
                source="credit_card_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_cc_txns.append(txn)
            max_total += amt

        # Gym 1
        cc_counter += 1
        txn = CreditCardTransaction(
            id=f"demo-cc-{cc_counter:04d}",
            date=rand_date_in_month(year, month, 1, 5),
            provider="max",
            account_name="Family Card",
            description="HOLMES PLACE",
            amount=-249.0,
            category="Health",
            tag="Gym",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        )
        session.add(txn)
        all_cc_txns.append(txn)
        max_total += -249.0

        # Parking 2-3
        for _ in range(random.randint(2, 3)):
            cc_counter += 1
            desc = random.choice(["PARKING LOT", "PANGO PARKING"])
            amt = rand_amount(-40, -15)
            txn = CreditCardTransaction(
                id=f"demo-cc-{cc_counter:04d}",
                date=rand_date_in_month(year, month),
                provider="max",
                account_name="Family Card",
                description=desc,
                amount=amt,
                category="Transportation",
                tag="Parking",
                source="credit_card_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_cc_txns.append(txn)
            max_total += amt

        # Coffee 3-5
        for _ in range(random.randint(3, 5)):
            cc_counter += 1
            desc = random.choice(["AROMA COFFEE", "COFIX"])
            amt = rand_amount(-25, -12)
            txn = CreditCardTransaction(
                id=f"demo-cc-{cc_counter:04d}",
                date=rand_date_in_month(year, month),
                provider="max",
                account_name="Family Card",
                description=desc,
                amount=amt,
                category="Food",
                tag="Coffee",
                source="credit_card_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_cc_txns.append(txn)
            max_total += amt

        # Delivery 2-4
        for _ in range(random.randint(2, 4)):
            cc_counter += 1
            desc = random.choice(["WOLT DELIVERY", "TENBIS", "WOLT"])
            amt = rand_amount(-120, -40)
            txn = CreditCardTransaction(
                id=f"demo-cc-{cc_counter:04d}",
                date=rand_date_in_month(year, month),
                provider="max",
                account_name="Family Card",
                description=desc,
                amount=amt,
                category="Food",
                tag="Delivery",
                source="credit_card_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_cc_txns.append(txn)
            max_total += amt

        # Public Transportation 2-4
        for _ in range(random.randint(2, 4)):
            cc_counter += 1
            desc = random.choice(["RAV-KAV LOAD", "ISRAEL RAILWAYS"])
            amt = rand_amount(-30, -10)
            txn = CreditCardTransaction(
                id=f"demo-cc-{cc_counter:04d}",
                date=rand_date_in_month(year, month),
                provider="max",
                account_name="Family Card",
                description=desc,
                amount=amt,
                category="Transportation",
                tag="Public Transportation",
                source="credit_card_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_cc_txns.append(txn)
            max_total += amt

        # Kids Activities 1-2
        for _ in range(random.randint(1, 2)):
            cc_counter += 1
            desc = random.choice(["GYMBOREE", "SWIMMING LESSONS", "KARATE CLASS"])
            amt = rand_amount(-250, -80)
            txn = CreditCardTransaction(
                id=f"demo-cc-{cc_counter:04d}",
                date=rand_date_in_month(year, month),
                provider="max",
                account_name="Family Card",
                description=desc,
                amount=amt,
                category="Kids",
                tag="Activities",
                source="credit_card_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_cc_txns.append(txn)
            max_total += amt

        # Haircut / Other 1-2
        for _ in range(random.randint(1, 2)):
            cc_counter += 1
            desc = random.choice(["HAIRCUT SALON", "ATM WITHDRAWAL FEE", "BANK COMMISION"])
            if "HAIRCUT" in desc:
                amt = rand_amount(-80, -40)
            else:
                amt = rand_amount(-20, -5)
            txn = CreditCardTransaction(
                id=f"demo-cc-{cc_counter:04d}",
                date=rand_date_in_month(year, month),
                provider="max",
                account_name="Family Card",
                description=desc,
                amount=amt,
                category="Other",
                tag="Haircut" if "HAIRCUT" in desc else "Bank Commisions",
                source="credit_card_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_cc_txns.append(txn)
            max_total += amt

        # Home Insurance 0-1 (quarterly-ish)
        if month % 3 == 0:
            cc_counter += 1
            amt = rand_amount(-400, -200)
            txn = CreditCardTransaction(
                id=f"demo-cc-{cc_counter:04d}",
                date=rand_date_in_month(year, month, 1, 10),
                provider="max",
                account_name="Family Card",
                description="HOME INSURANCE PREMIUM",
                amount=amt,
                category="Household",
                tag="Home Insurance",
                source="credit_card_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_cc_txns.append(txn)
            max_total += amt

        month_date = date(year, month, 15)

        # Kids school supplies surge in August–September
        if month in (8, 9):
            for _ in range(random.randint(1, 3)):
                cc_counter += 1
                desc = random.choice(["KRAVITZ SCHOOL", "OFFICE DEPOT BACK-TO-SCHOOL", "SHILAV"])
                amt = rand_amount(-350, -120)
                txn = CreditCardTransaction(
                    id=f"demo-cc-{cc_counter:04d}",
                    date=rand_date_in_month(year, month, 15, 28),
                    provider="max",
                    account_name="Family Card",
                    description=desc,
                    amount=amt,
                    category="Kids",
                    tag="School Supplies",
                    source="credit_card_transactions",
                    type="normal",
                    status="completed",
                )
                session.add(txn)
                all_cc_txns.append(txn)
                max_total += amt

        # Kids birthday parties — twice a year (March + October)
        if month in (3, 10):
            cc_counter += 1
            amt = rand_amount(-1200, -600)
            txn = CreditCardTransaction(
                id=f"demo-cc-{cc_counter:04d}",
                date=rand_date_in_month(year, month),
                provider="max",
                account_name="Family Card",
                description="KIDS BIRTHDAY - PARTY HALL",
                amount=amt,
                category="Kids",
                tag="Activities",
                source="credit_card_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_cc_txns.append(txn)
            max_total += amt

        # Summer family vacation — August each year, on Visa Cal (online bookings)
        if month == 8:
            # Flights
            cc_counter += 1
            flights_amt = rand_amount(-7500, -5500)
            destination = random.choice(["GREECE", "CYPRUS", "ITALY"])
            txn = CreditCardTransaction(
                id=f"demo-cc-{cc_counter:04d}",
                date=rand_date_in_month(year, month, 1, 10),
                provider="visa cal",
                account_name="Online Shopping",
                description=f"EL AL FLIGHTS - {destination}",
                amount=flights_amt,
                category="Vacations",
                tag="Flights",
                source="credit_card_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_cc_txns.append(txn)
            visa_total += flights_amt

            # Hotel
            cc_counter += 1
            hotel_amt = rand_amount(-6500, -4500)
            txn = CreditCardTransaction(
                id=f"demo-cc-{cc_counter:04d}",
                date=rand_date_in_month(year, month, 5, 15),
                provider="visa cal",
                account_name="Online Shopping",
                description="BOOKING.COM HOTEL",
                amount=hotel_amt,
                category="Vacations",
                tag="Hotel",
                source="credit_card_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_cc_txns.append(txn)
            visa_total += hotel_amt

            # Vacation food (a few charges)
            for _ in range(random.randint(3, 5)):
                cc_counter += 1
                amt = rand_amount(-450, -120)
                txn = CreditCardTransaction(
                    id=f"demo-cc-{cc_counter:04d}",
                    date=rand_date_in_month(year, month, 15, 28),
                    provider="max",
                    account_name="Family Card",
                    description=f"RESTAURANT - {destination}",
                    amount=amt,
                    category="Vacations",
                    tag="Food",
                    source="credit_card_transactions",
                    type="normal",
                    status="completed",
                )
                session.add(txn)
                all_cc_txns.append(txn)
                max_total += amt

        # Short winter getaway — December each year (domestic, hotel only)
        if month == 12:
            cc_counter += 1
            amt = rand_amount(-2800, -1800)
            resort = random.choice(["DEAD SEA RESORT", "EILAT ISROTEL", "GALILEE LODGE"])
            txn = CreditCardTransaction(
                id=f"demo-cc-{cc_counter:04d}",
                date=rand_date_in_month(year, month, 20, 28),
                provider="visa cal",
                account_name="Online Shopping",
                description=resort,
                amount=amt,
                category="Vacations",
                tag="Hotel",
                source="credit_card_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_cc_txns.append(txn)
            visa_total += amt

        # Extra holiday gifts in December (Hanukkah) and March/April (Passover)
        if month in (12, 3, 4):
            for _ in range(random.randint(2, 4)):
                cc_counter += 1
                amt = rand_amount(-400, -120)
                desc = random.choice(["HAMASHBIR GIFTS", "TOYS R US", "HOLIDAY GIFT SHOP"])
                txn = CreditCardTransaction(
                    id=f"demo-cc-{cc_counter:04d}",
                    date=rand_date_in_month(year, month),
                    provider="visa cal",
                    account_name="Online Shopping",
                    description=desc,
                    amount=amt,
                    category="Shopping",
                    tag="Gifts",
                    source="credit_card_transactions",
                    type="normal",
                    status="completed",
                )
                session.add(txn)
                all_cc_txns.append(txn)
                visa_total += amt

        # Car service — annual in spring
        if month == 4:
            cc_counter += 1
            amt = rand_amount(-2500, -1200)
            txn = CreditCardTransaction(
                id=f"demo-cc-{cc_counter:04d}",
                date=rand_date_in_month(year, month, 5, 20),
                provider="max",
                account_name="Family Card",
                description="CAR SERVICE - ANNUAL",
                amount=amt,
                category="Transportation",
                tag="Maintenance",
                source="credit_card_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_cc_txns.append(txn)
            max_total += amt

        # Wedding planning — last 10 months on Max card (one vendor per month).
        if month_date >= ten_months_ago:
            months_back = (REFERENCE_DATE.year - year) * 12 + (REFERENCE_DATE.month - month)
            vendor = wedding_cc_schedule.get(months_back)
            if vendor:
                desc, tag, amt = vendor
                cc_counter += 1
                txn = CreditCardTransaction(
                    id=f"demo-cc-{cc_counter:04d}",
                    date=rand_date_in_month(year, month, 10, 25),
                    provider="max",
                    account_name="Family Card",
                    description=desc,
                    amount=amt,
                    category="Wedding",
                    tag=tag,
                    source="credit_card_transactions",
                    type="normal",
                    status="completed",
                )
                session.add(txn)
                all_cc_txns.append(txn)
                max_total += amt

        # Home Renovation — last 6 months only, on Max card
        if month_date >= six_months_ago:
            # 1-2 renovation transactions per qualifying month (to get ~15 total)
            reno_count = random.randint(1, 3)
            for _ in range(reno_count):
                cc_counter += 1
                reno_type = random.choice(["materials", "labor", "furniture"])
                if reno_type == "materials":
                    desc = random.choice(["ACE HARDWARE", "HOME CENTER"])
                    amt = rand_amount(-3000, -500)
                    tag = "Materials"
                elif reno_type == "labor":
                    desc = random.choice(["PLUMBER SERVICES", "ELECTRICIAN", "PAINTER"])
                    amt = rand_amount(-5000, -2000)
                    tag = "Labor"
                else:
                    desc = random.choice(["IKEA", "POTTERY BARN"])
                    amt = rand_amount(-4000, -1000)
                    tag = "Furniture"
                txn = CreditCardTransaction(
                    id=f"demo-cc-{cc_counter:04d}",
                    date=rand_date_in_month(year, month),
                    provider="max",
                    account_name="Family Card",
                    description=desc,
                    amount=amt,
                    category="Home Renovation",
                    tag=tag,
                    source="credit_card_transactions",
                    type="normal",
                    status="completed",
                )
                session.add(txn)
                all_cc_txns.append(txn)
                max_total += amt

        # ---- VISA CAL (Online Shopping) ----

        # Netflix
        cc_counter += 1
        txn = CreditCardTransaction(
            id=f"demo-cc-{cc_counter:04d}",
            date=rand_date_in_month(year, month, 1, 5),
            provider="visa cal",
            account_name="Online Shopping",
            description="NETFLIX.COM",
            amount=-49.90,
            category="Subscriptions",
            tag="Netflix",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        )
        session.add(txn)
        all_cc_txns.append(txn)
        visa_total += -49.90

        # Spotify
        cc_counter += 1
        txn = CreditCardTransaction(
            id=f"demo-cc-{cc_counter:04d}",
            date=rand_date_in_month(year, month, 1, 5),
            provider="visa cal",
            account_name="Online Shopping",
            description="SPOTIFY",
            amount=-29.90,
            category="Subscriptions",
            tag="Spotify",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        )
        session.add(txn)
        all_cc_txns.append(txn)
        visa_total += -29.90

        # ChatGPT
        cc_counter += 1
        txn = CreditCardTransaction(
            id=f"demo-cc-{cc_counter:04d}",
            date=rand_date_in_month(year, month, 1, 5),
            provider="visa cal",
            account_name="Online Shopping",
            description="OPENAI CHATGPT",
            amount=-75.0,
            category="Subscriptions",
            tag="Chat-GPT",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        )
        session.add(txn)
        all_cc_txns.append(txn)
        visa_total += -75.0

        # Amazon/AliExpress/Shein 4-7
        for _ in range(random.randint(4, 7)):
            cc_counter += 1
            desc = random.choice(["AMAZON.COM", "ALIEXPRESS", "SHEIN"])
            amt = rand_amount(-500, -50)
            txn = CreditCardTransaction(
                id=f"demo-cc-{cc_counter:04d}",
                date=rand_date_in_month(year, month),
                provider="visa cal",
                account_name="Online Shopping",
                description=desc,
                amount=amt,
                category="Shopping",
                tag="Online",
                source="credit_card_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_cc_txns.append(txn)
            visa_total += amt

        # Electronics 0-1
        if random.random() < 0.5:
            cc_counter += 1
            desc = random.choice(["KSP COMPUTERS", "BUG ELECTRONICS"])
            amt = rand_amount(-2000, -200)
            txn = CreditCardTransaction(
                id=f"demo-cc-{cc_counter:04d}",
                date=rand_date_in_month(year, month),
                provider="visa cal",
                account_name="Online Shopping",
                description=desc,
                amount=amt,
                category="Shopping",
                tag="Electronics",
                source="credit_card_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_cc_txns.append(txn)
            visa_total += amt

        # Kids Clothing 2-3
        for _ in range(random.randint(2, 3)):
            cc_counter += 1
            desc = random.choice(["NEXT KIDS", "H&M KIDS"])
            amt = rand_amount(-300, -80)
            txn = CreditCardTransaction(
                id=f"demo-cc-{cc_counter:04d}",
                date=rand_date_in_month(year, month),
                provider="visa cal",
                account_name="Online Shopping",
                description=desc,
                amount=amt,
                category="Kids",
                tag="Clothing",
                source="credit_card_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_cc_txns.append(txn)
            visa_total += amt

        # Internet 1
        cc_counter += 1
        txn = CreditCardTransaction(
            id=f"demo-cc-{cc_counter:04d}",
            date=rand_date_in_month(year, month, 1, 10),
            provider="visa cal",
            account_name="Online Shopping",
            description="HOT INTERNET",
            amount=-119.0,
            category="Household",
            tag="Internet",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        )
        session.add(txn)
        all_cc_txns.append(txn)
        visa_total += -119.0

        # Electricity 1
        cc_counter += 1
        amt = rand_amount(-450, -250)
        txn = CreditCardTransaction(
            id=f"demo-cc-{cc_counter:04d}",
            date=rand_date_in_month(year, month, 10, 20),
            provider="visa cal",
            account_name="Online Shopping",
            description="ELECTRIC COMPANY",
            amount=amt,
            category="Household",
            tag="Electricity",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        )
        session.add(txn)
        all_cc_txns.append(txn)
        visa_total += amt

        # Water 1
        cc_counter += 1
        amt = rand_amount(-120, -80)
        txn = CreditCardTransaction(
            id=f"demo-cc-{cc_counter:04d}",
            date=rand_date_in_month(year, month, 10, 20),
            provider="visa cal",
            account_name="Online Shopping",
            description="WATER CORP",
            amount=amt,
            category="Household",
            tag="Water",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        )
        session.add(txn)
        all_cc_txns.append(txn)
        visa_total += amt

        # Cinema 0-1
        if random.random() < 0.5:
            cc_counter += 1
            desc = random.choice(["YES PLANET", "CINEMA CITY"])
            amt = rand_amount(-120, -60)
            txn = CreditCardTransaction(
                id=f"demo-cc-{cc_counter:04d}",
                date=rand_date_in_month(year, month),
                provider="visa cal",
                account_name="Online Shopping",
                description=desc,
                amount=amt,
                category="Entertainment",
                tag="Cinema",
                source="credit_card_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_cc_txns.append(txn)
            visa_total += amt

        # Gifts / Clothing 1-3
        for _ in range(random.randint(1, 3)):
            cc_counter += 1
            gift_type = random.choice(["gift", "clothing"])
            if gift_type == "gift":
                desc = random.choice(["TOY R US", "HAMASHBIR", "GIFT SHOP"])
                amt = rand_amount(-200, -50)
                tag = "Gifts"
            else:
                desc = random.choice(["ZARA", "H&M", "CASTRO"])
                amt = rand_amount(-300, -80)
                tag = "Clothing"
            txn = CreditCardTransaction(
                id=f"demo-cc-{cc_counter:04d}",
                date=rand_date_in_month(year, month),
                provider="visa cal",
                account_name="Online Shopping",
                description=desc,
                amount=amt,
                category="Shopping",
                tag=tag,
                source="credit_card_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_cc_txns.append(txn)
            visa_total += amt

        # Education 0-1
        if random.random() < 0.4:
            cc_counter += 1
            desc = random.choice(["UDEMY COURSE", "BOOKDEPOSITORY", "STEIMATZKY BOOKS"])
            is_course = "UDEMY" in desc
            amt = rand_amount(-200, -40) if is_course else rand_amount(-120, -30)
            txn = CreditCardTransaction(
                id=f"demo-cc-{cc_counter:04d}",
                date=rand_date_in_month(year, month),
                provider="visa cal",
                account_name="Online Shopping",
                description=desc,
                amount=amt,
                category="Education",
                tag="Courses" if is_course else "Books",
                source="credit_card_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_cc_txns.append(txn)
            visa_total += amt

        # Games / Entertainment 0-1
        if random.random() < 0.3:
            cc_counter += 1
            desc = random.choice(["STEAM GAMES", "APPLE APP STORE", "GOOGLE PLAY"])
            amt = rand_amount(-80, -15)
            txn = CreditCardTransaction(
                id=f"demo-cc-{cc_counter:04d}",
                date=rand_date_in_month(year, month),
                provider="visa cal",
                account_name="Online Shopping",
                description=desc,
                amount=amt,
                category="Entertainment",
                tag="Games",
                source="credit_card_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_cc_txns.append(txn)
            visa_total += amt

        # School Supplies 0-1
        if random.random() < 0.35:
            cc_counter += 1
            desc = random.choice(["OFFICE DEPOT", "KRAVITZ SCHOOL SUPPLIES"])
            amt = rand_amount(-150, -30)
            txn = CreditCardTransaction(
                id=f"demo-cc-{cc_counter:04d}",
                date=rand_date_in_month(year, month),
                provider="visa cal",
                account_name="Online Shopping",
                description=desc,
                amount=amt,
                category="Kids",
                tag="School Supplies",
                source="credit_card_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_cc_txns.append(txn)
            visa_total += amt

        # Doctor / Dental 0-1
        if random.random() < 0.25:
            cc_counter += 1
            is_dental = random.random() < 0.4
            desc = "DR. DENTAL CLINIC" if is_dental else "MACCABI HEALTH"
            amt = rand_amount(-500, -100) if is_dental else rand_amount(-200, -50)
            txn = CreditCardTransaction(
                id=f"demo-cc-{cc_counter:04d}",
                date=rand_date_in_month(year, month),
                provider="visa cal",
                account_name="Online Shopping",
                description=desc,
                amount=amt,
                category="Health",
                tag="Dental" if is_dental else "Doctor",
                source="credit_card_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_cc_txns.append(txn)
            visa_total += amt

        monthly_totals[(year, month)] = {"max": max_total, "visa_cal": visa_total}

    # Flush so unique_ids are assigned
    session.flush()
    return monthly_totals, all_cc_txns


def generate_untagged_transactions(session, monthly_cc_totals: dict):
    """Generate 8 untagged CC transactions in recent months.

    Also updates *monthly_cc_totals* so that CC bill amounts remain consistent.
    """
    # Use the last 2 months for untagged transactions
    recent_month_1 = (REFERENCE_DATE.year, REFERENCE_DATE.month)
    prev = REFERENCE_DATE.replace(day=1) - timedelta(days=1)
    recent_month_2 = (prev.year, prev.month)

    untagged_specs = [
        ("SHUFERSAL DEAL RAANANA", "max", "Family Card", rand_amount(-280, -120), recent_month_1),
        ("UBER TRIP 1234", "max", "Family Card", rand_amount(-45, -25), recent_month_2),
        ("NETFLIX.COM", "visa cal", "Online Shopping", -49.90, recent_month_1),
        ("PAZ STATION HERZLIYA", "max", "Family Card", rand_amount(-300, -180), recent_month_2),
        ("SUPER-PHARM DIZENGOFF", "max", "Family Card", rand_amount(-120, -40), recent_month_1),
        ("AMAZON.COM ORDER", "visa cal", "Online Shopping", rand_amount(-350, -100), recent_month_2),
        ("GAN YELADIM", "max", "Family Card", -2800.0, recent_month_1),
        ("HOLMES PLACE MEMBERSHIP", "max", "Family Card", -249.0, recent_month_2),
    ]

    untagged_txns = []
    for i, (desc, provider, account, amt, (y, m)) in enumerate(untagged_specs):
        txn = CreditCardTransaction(
            id=f"demo-untagged-{i + 1:03d}",
            date=rand_date_in_month(y, m, 5, 25),
            provider=provider,
            account_name=account,
            description=desc,
            amount=amt,
            category=None,
            tag=None,
            source="credit_card_transactions",
            type="normal",
            status="completed",
        )
        session.add(txn)
        untagged_txns.append(txn)

        # Update monthly CC totals so bank bills stay in sync
        card_key = "max" if provider == "max" else "visa_cal"
        if (y, m) in monthly_cc_totals:
            monthly_cc_totals[(y, m)][card_key] += amt

    session.flush()
    return untagged_txns


def generate_bank_transactions(session, monthly_cc_totals: dict):
    """Generate bank transactions including salaries, mortgage, CC bills, freelance."""
    bank_counter = 0
    all_bank_txns: list[BankTransaction] = []
    months = list(month_range(START_DATE, REFERENCE_DATE))

    # Pick 3-4 random months for freelance income
    freelance_months = random.sample(months, min(4, len(months)))

    for year, month in months:
        # Salary 1 - 18,000 on the 1st
        bank_counter += 1
        txn = BankTransaction(
            id=f"demo-bank-{bank_counter:04d}",
            date=date(year, month, 1).isoformat(),
            provider="hapoalim",
            account_name="Main Account",
            description="TECH COMPANY LTD - SALARY",
            amount=18000.0,
            category="Salary",
            tag="Tech Company",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        session.add(txn)
        all_bank_txns.append(txn)

        # Salary 2 - 12,000 on the 5th
        bank_counter += 1
        txn = BankTransaction(
            id=f"demo-bank-{bank_counter:04d}",
            date=date(year, month, 5).isoformat(),
            provider="hapoalim",
            account_name="Main Account",
            description="SCHOOL DISTRICT - SALARY",
            amount=12000.0,
            category="Salary",
            tag="School District",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        session.add(txn)
        all_bank_txns.append(txn)

        # Mortgage payment on the 15th (constant: matches amortization schedule)
        bank_counter += 1
        txn = BankTransaction(
            id=f"demo-bank-{bank_counter:04d}",
            date=date(year, month, 15).isoformat(),
            provider="hapoalim",
            account_name="Main Account",
            description="MORTGAGE PAYMENT - LEUMI",
            amount=-2609.82,
            category="Liabilities",
            tag="Mortgage",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        session.add(txn)
        all_bank_txns.append(txn)

        # Occasional direct debit / standing orders (every other month)
        if month % 2 == 0:
            bank_counter += 1
            desc = random.choice(["BITUACH LEUMI - NATIONAL INSURANCE", "ARNONA - MUNICIPAL TAX"])
            amt = rand_amount(-600, -300)
            tag = "National Insurance" if "BITUACH LEUMI" in desc else "Municipal Tax"
            txn = BankTransaction(
                id=f"demo-bank-{bank_counter:04d}",
                date=rand_date_in_month(year, month, 10, 20),
                provider="hapoalim",
                account_name="Main Account",
                description=desc,
                amount=amt,
                category="Household",
                tag=tag,
                source="bank_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_bank_txns.append(txn)

        # Freelance income (3-4 times over 14 months)
        if (year, month) in freelance_months:
            bank_counter += 1
            amt = rand_amount(1000, 2500)
            txn = BankTransaction(
                id=f"demo-bank-{bank_counter:04d}",
                date=rand_date_in_month(year, month, 10, 25),
                provider="hapoalim",
                account_name="Main Account",
                description="FREELANCE PAYMENT - CLIENT",
                amount=amt,
                category="Other Income",
                tag="Freelance",
                source="bank_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_bank_txns.append(txn)

        # Annual tech-company bonus — every December
        if month == 12:
            bank_counter += 1
            bonus = round(rand_amount(26000, 35000), 2)
            txn = BankTransaction(
                id=f"demo-bank-{bank_counter:04d}",
                date=date(year, month, 20).isoformat(),
                provider="hapoalim",
                account_name="Main Account",
                description="TECH COMPANY LTD - ANNUAL BONUS",
                amount=bonus,
                category="Salary",
                tag="Tech Company",
                source="bank_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_bank_txns.append(txn)

        # Big wedding vendor payments via bank transfer (last 8 months).
        # Paired with the CC-side schedule above — these are the large deposits
        # that don't fit on a credit card.
        wedding_bank_schedule = {
            8: ("WEDDING VENUE - DEPOSIT", "Venue", -20000.0),
            5: ("CATERING - DEPOSIT", "Catering", -12000.0),
            2: ("CATERING - FINAL PAYMENT", "Catering", -18000.0),
            1: ("VENUE - BALANCE PAYMENT", "Venue", -15000.0),
        }
        months_back = (REFERENCE_DATE.year - year) * 12 + (REFERENCE_DATE.month - month)
        wedding_payment = wedding_bank_schedule.get(months_back)
        if wedding_payment:
            bank_counter += 1
            desc, tag, amt = wedding_payment
            txn = BankTransaction(
                id=f"demo-bank-{bank_counter:04d}",
                date=rand_date_in_month(year, month, 10, 25),
                provider="hapoalim",
                account_name="Main Account",
                description=desc,
                amount=amt,
                category="Wedding",
                tag=tag,
                source="bank_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)
            all_bank_txns.append(txn)

        # CC bill payments — posted on the 2nd of the NEXT month
        ny, nm = next_month(year, month)
        # Only create the bill if the next month is within our range (or at most one month past)
        bill_date = date(ny, nm, 2).isoformat()

        if (year, month) in monthly_cc_totals:
            totals = monthly_cc_totals[(year, month)]

            # Max CC bill
            if totals["max"] != 0:
                bank_counter += 1
                # Add 2-5% variance to the CC bill
                variance = random.uniform(0.98, 1.03)
                bill_amount = round(totals["max"] * variance, 2)
                txn = BankTransaction(
                    id=f"demo-bank-{bank_counter:04d}",
                    date=bill_date,
                    provider="hapoalim",
                    account_name="Main Account",
                    description="CREDIT CARD BILL - MAX",
                    amount=bill_amount,
                    category="Credit Cards",
                    tag="Bill",
                    source="bank_transactions",
                    type="normal",
                    status="completed",
                )
                session.add(txn)
                all_bank_txns.append(txn)

            # Visa Cal CC bill
            if totals["visa_cal"] != 0:
                bank_counter += 1
                variance = random.uniform(0.98, 1.03)
                bill_amount = round(totals["visa_cal"] * variance, 2)
                txn = BankTransaction(
                    id=f"demo-bank-{bank_counter:04d}",
                    date=bill_date,
                    provider="hapoalim",
                    account_name="Main Account",
                    description="CREDIT CARD BILL - VISA CAL",
                    amount=bill_amount,
                    category="Credit Cards",
                    tag="Bill",
                    source="bank_transactions",
                    type="normal",
                    status="completed",
                )
                session.add(txn)
                all_bank_txns.append(txn)

    # Mortgage receipt — ONE TIME, early in the period
    bank_counter += 1
    receipt_date = (START_DATE + timedelta(days=5)).isoformat()
    txn = BankTransaction(
        id=f"demo-bank-{bank_counter:04d}",
        date=receipt_date,
        provider="hapoalim",
        account_name="Main Account",
        description="MORTGAGE RECEIPT - LEUMI",
        amount=450000.0,
        category="Liabilities",
        tag="Mortgage",
        source="bank_transactions",
        type="normal",
        status="completed",
    )
    session.add(txn)
    all_bank_txns.append(txn)

    # Car loan receipt — 8 months into the period
    car_loan_start = START_DATE + timedelta(days=240)
    bank_counter += 1
    txn = BankTransaction(
        id=f"demo-bank-{bank_counter:04d}",
        date=car_loan_start.isoformat(),
        provider="hapoalim",
        account_name="Main Account",
        description="CAR LOAN RECEIPT - MIZRAHI",
        amount=120000.0,
        category="Liabilities",
        tag="Car Loan",
        source="bank_transactions",
        type="normal",
        status="completed",
    )
    session.add(txn)
    all_bank_txns.append(txn)

    # Car loan monthly payments — from the month after receipt
    car_start_y, car_start_m = car_loan_start.year, car_loan_start.month
    car_ny, car_nm = next_month(car_start_y, car_start_m)
    car_months = list(month_range(date(car_ny, car_nm, 1), REFERENCE_DATE))
    for year, month in car_months:
        bank_counter += 1
        # Constant payment matching amortization schedule
        txn = BankTransaction(
            id=f"demo-bank-{bank_counter:04d}",
            date=date(year, month, 10).isoformat(),
            provider="hapoalim",
            account_name="Main Account",
            description="CAR LOAN PAYMENT - MIZRAHI",
            amount=-2275.56,
            category="Liabilities",
            tag="Car Loan",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        session.add(txn)
        all_bank_txns.append(txn)

    # One-time "Prior Wealth" deposit early in the period — exercises the Sankey
    # path that treats Other Income/Prior Wealth tagged transactions as a separate
    # source (excluded from recurring income but added to the Prior Wealth bucket).
    bank_counter += 1
    pw_date = (START_DATE + timedelta(days=12)).isoformat()
    pw_txn = BankTransaction(
        id=f"demo-bank-{bank_counter:04d}",
        date=pw_date,
        provider="hapoalim",
        account_name="Main Account",
        description="OPENING DEPOSIT - SAVINGS TRANSFER",
        amount=15000.0,
        category="Other Income",
        tag="Prior Wealth",
        source="bank_transactions",
        type="normal",
        status="completed",
    )
    session.add(pw_txn)
    all_bank_txns.append(pw_txn)

    # Secondary bank account: Leumi Savings Account — monthly transfers from Main
    # Demonstrates multi-account bank support (per-account balances, separate
    # account tile on Data Sources).
    months = list(month_range(START_DATE, REFERENCE_DATE))
    for year, month in months:
        # Outgoing transfer from Main Account (treated as an internal transfer)
        bank_counter += 1
        transfer_date = date(year, month, 20).isoformat()
        out_txn = BankTransaction(
            id=f"demo-bank-{bank_counter:04d}",
            date=transfer_date,
            provider="hapoalim",
            account_name="Main Account",
            description="TRANSFER TO LEUMI SAVINGS",
            amount=-2000.0,
            category="Ignore",
            tag="Internal Transactions",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        session.add(out_txn)
        all_bank_txns.append(out_txn)

        # Matching deposit into Leumi Savings
        bank_counter += 1
        savings_txn = BankTransaction(
            id=f"demo-bank-{bank_counter:04d}",
            date=transfer_date,
            provider="leumi",
            account_name="Savings Account",
            description="INCOMING TRANSFER - HAPOALIM",
            amount=2000.0,
            category="Ignore",
            tag="Internal Transactions",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        session.add(savings_txn)
        all_bank_txns.append(savings_txn)

    session.flush()
    return all_bank_txns


def create_liabilities(session):
    """Create liability records for Mortgage, Car Loan, and a paid-off Personal Loan."""
    car_loan_start = START_DATE + timedelta(days=240)
    personal_loan_start = START_DATE
    personal_loan_paid_off = REFERENCE_DATE - timedelta(days=90)

    mortgage = Liability(
        name="Home Mortgage",
        lender="Bank Leumi",
        category="Liabilities",
        tag="Mortgage",
        principal_amount=450000.0,
        interest_rate=3.5,
        term_months=240,
        start_date=START_DATE.isoformat(),
        is_paid_off=0,
        notes="20-year fixed rate mortgage for apartment in Tel Aviv",
        created_date=START_DATE.isoformat(),
    )
    session.add(mortgage)

    car_loan = Liability(
        name="Car Loan",
        lender="Bank Mizrahi",
        category="Liabilities",
        tag="Car Loan",
        principal_amount=120000.0,
        interest_rate=5.2,
        term_months=60,
        start_date=car_loan_start.isoformat(),
        is_paid_off=0,
        notes="5-year car loan for family car",
        created_date=car_loan_start.isoformat(),
    )
    session.add(car_loan)

    personal_loan = Liability(
        name="Personal Loan",
        lender="Bank Discount",
        category="Liabilities",
        tag="Personal Loan",
        principal_amount=25000.0,
        interest_rate=6.0,
        term_months=12,
        start_date=personal_loan_start.isoformat(),
        is_paid_off=1,
        paid_off_date=personal_loan_paid_off.isoformat(),
        notes="Short-term personal loan, paid off early",
        created_date=personal_loan_start.isoformat(),
    )
    session.add(personal_loan)

    session.flush()


def generate_cash_transactions(session):
    """Generate ~50-70 cash transactions across two envelopes over 14 months."""
    cash_counter = 0
    months = list(month_range(START_DATE, REFERENCE_DATE))

    petty_templates = [
        ("Cash Market Purchase", "Food", "Groceries", -60, -20),
        ("Tip", "Other", "Tip", -50, -10),
        ("Flea Market", "Shopping", "Flea Market", -100, -30),
    ]
    kids_templates = [
        ("Kids Allowance", "Kids", "Activities", -50, -20),
        ("School Lunch Money", "Kids", "School Supplies", -40, -15),
        ("Ice Cream Outing", "Food", "Restaurants", -60, -25),
    ]

    envelopes = [
        ("Petty Cash", petty_templates, 3, 5),
        ("Kids Envelope", kids_templates, 1, 3),
    ]

    for year, month in months:
        for account_name, templates, lo_count, hi_count in envelopes:
            count = random.randint(lo_count, hi_count)
            for _ in range(count):
                cash_counter += 1
                desc, cat, tag, lo, hi = random.choice(templates)
                amt = rand_amount(lo, hi)
                txn = CashTransaction(
                    id=f"demo-cash-{cash_counter:04d}",
                    date=rand_date_in_month(year, month),
                    provider="cash",
                    account_name=account_name,
                    description=desc,
                    amount=amt,
                    category=cat,
                    tag=tag,
                    source="cash_transactions",
                    type="normal",
                    status="completed",
                )
                session.add(txn)

    session.flush()


def generate_investment_transactions(session):
    """Generate investment transactions (~30 total)."""
    inv_counter = 0
    months = list(month_range(START_DATE, REFERENCE_DATE))
    savings_start = START_DATE + timedelta(days=60)
    bond_deposit_date = REFERENCE_DATE - timedelta(days=365)
    bond_withdrawal_date = REFERENCE_DATE - timedelta(days=180)

    for year, month in months:
        # Stock Market Fund — -2,000 every month
        inv_counter += 1
        txn = ManualInvestmentTransaction(
            id=f"demo-inv-{inv_counter:04d}",
            date=rand_date_in_month(year, month, 1, 10),
            provider="manual",
            account_name="Investments",
            description="Stock Market Fund - Monthly Deposit",
            amount=-2000.0,
            category="Investments",
            tag="Stock Market Fund",
            source="manual_investment_transactions",
            type="normal",
            status="completed",
        )
        session.add(txn)

        # Savings Plan — -1,500 starting 2 months after START_DATE
        month_start = date(year, month, 1)
        if month_start >= date(savings_start.year, savings_start.month, 1):
            inv_counter += 1
            txn = ManualInvestmentTransaction(
                id=f"demo-inv-{inv_counter:04d}",
                date=rand_date_in_month(year, month, 1, 10),
                provider="manual",
                account_name="Investments",
                description="Savings Plan - Monthly Deposit",
                amount=-1500.0,
                category="Investments",
                tag="Savings Plan",
                source="manual_investment_transactions",
                type="normal",
                status="completed",
            )
            session.add(txn)

    # Corporate Bond - one-time deposit 12 months before REFERENCE_DATE
    inv_counter += 1
    txn = ManualInvestmentTransaction(
        id=f"demo-inv-{inv_counter:04d}",
        date=bond_deposit_date.isoformat(),
        provider="manual",
        account_name="Investments",
        description="Corporate Bond - Initial Deposit",
        amount=-50000.0,
        category="Investments",
        tag="Corporate Bond",
        source="manual_investment_transactions",
        type="normal",
        status="completed",
    )
    session.add(txn)

    # Corporate Bond - withdrawal 6 months before REFERENCE_DATE
    inv_counter += 1
    txn = ManualInvestmentTransaction(
        id=f"demo-inv-{inv_counter:04d}",
        date=bond_withdrawal_date.isoformat(),
        provider="manual",
        account_name="Investments",
        description="Corporate Bond - Maturity Withdrawal",
        amount=53800.0,
        category="Investments",
        tag="Corporate Bond",
        source="manual_investment_transactions",
        type="normal",
        status="completed",
    )
    session.add(txn)

    session.flush()


def create_investments(session):
    """Create 3 investment instruments."""
    stock_fund = Investment(
        category="Investments",
        tag="Stock Market Fund",
        type="mutual_fund",
        name="Stock Market Fund",
        interest_rate=0.085,
        interest_rate_type="variable",
        commission_management=0.005,
        is_closed=0,
        created_date=(START_DATE + timedelta(days=30)).isoformat(),
        notes="Tracking S&P 500 index fund",
        prior_wealth_amount=0.0,
    )
    session.add(stock_fund)

    savings_plan = Investment(
        category="Investments",
        tag="Savings Plan",
        type="savings",
        name="Savings Plan",
        interest_rate=0.042,
        interest_rate_type="fixed",
        is_closed=0,
        created_date=(START_DATE + timedelta(days=60)).isoformat(),
        maturity_date=(REFERENCE_DATE + timedelta(days=365)).isoformat(),
        notes="Fixed-rate bank savings plan",
        prior_wealth_amount=0.0,
    )
    session.add(savings_plan)

    bond = Investment(
        category="Investments",
        tag="Corporate Bond",
        type="bond",
        name="Corporate Bond",
        interest_rate=0.038,
        interest_rate_type="fixed",
        is_closed=1,
        created_date=(START_DATE + timedelta(days=30)).isoformat(),
        closed_date=(REFERENCE_DATE - timedelta(days=180)).isoformat(),
        maturity_date=(REFERENCE_DATE - timedelta(days=180)).isoformat(),
        notes="Matured corporate bond",
        prior_wealth_amount=0.0,
    )
    session.add(bond)

    session.flush()

    # Recalculate prior_wealth_amount per investment from its transactions —
    # mirrors backend's recalculate_prior_wealth (`-sum(all inv txns)`). Without
    # this, the Sankey "Prior Wealth" node and the Overview total_income KPI
    # under-report investment-side prior wealth.
    for inv in (stock_fund, savings_plan, bond):
        total = (
            session.query(ManualInvestmentTransaction)
            .filter(
                ManualInvestmentTransaction.category == inv.category,
                ManualInvestmentTransaction.tag == inv.tag,
            )
            .all()
        )
        inv.prior_wealth_amount = -sum(t.amount for t in total)
    session.flush()

    return stock_fund, savings_plan, bond


def create_investment_snapshots(session, stock_fund, savings_plan, bond):
    """Create balance snapshots for all 3 investments."""
    months = list(month_range(START_DATE, REFERENCE_DATE))

    # --- Stock Market Fund: monthly snapshots with ~8% annual growth + variance ---
    cumulative_deposits = 0.0
    for i, (year, month) in enumerate(months):
        cumulative_deposits += 2000.0
        # Base growth: 8% annual, compounded monthly
        months_elapsed = i + 1
        # Simpler: cumulative deposits + growth with monthly variance
        growth_factor = 1 + (0.085 * months_elapsed / 12) + random.uniform(-0.03, 0.05) * (months_elapsed / len(months))
        balance = round(cumulative_deposits * growth_factor, 2)
        # Ensure balance is at least slightly above deposits (realistic for overall uptrend)
        balance = max(balance, cumulative_deposits * 0.95)
        balance = round(balance, 2)

        snapshot_date = date(year, month, 28).isoformat()
        session.add(InvestmentBalanceSnapshot(
            investment_id=stock_fund.id,
            date=snapshot_date,
            balance=balance,
            source="manual",
        ))

    # --- Savings Plan: daily compounding at 4.2% annual, monthly snapshots ---
    savings_start = START_DATE + timedelta(days=60)
    savings_start_month = date(savings_start.year, savings_start.month, 1)
    daily_rate = (1 + 0.042) ** (1 / 365) - 1
    savings_cumulative = 0.0
    savings_month_index = 0

    for year, month in months:
        month_start = date(year, month, 1)
        if month_start < savings_start_month:
            continue

        savings_month_index += 1
        savings_cumulative += 1500.0
        days_since_start = (date(year, month, 28) - savings_start).days
        if days_since_start < 0:
            continue

        # Simple approach: apply daily compounding to cumulative deposits
        # Each deposit earns interest from its deposit date
        # Approximate: total_balance = sum over each monthly deposit of deposit * (1+r)^days
        balance = 0.0
        for dep_idx in range(savings_month_index):
            dep_date = savings_start + timedelta(days=30 * dep_idx)
            days_earning = max(0, (date(year, month, 28) - dep_date).days)
            balance += 1500.0 * (1 + daily_rate) ** days_earning
        balance = round(balance, 2)

        session.add(InvestmentBalanceSnapshot(
            investment_id=savings_plan.id,
            date=date(year, month, 28).isoformat(),
            balance=balance,
            source="calculated",
        ))

    # --- Corporate Bond: 6 monthly snapshots before closure, then 0 ---
    bond_deposit_date = REFERENCE_DATE - timedelta(days=365)
    bond_closed_date = REFERENCE_DATE - timedelta(days=180)

    # Find months between bond deposit and closure (about 6 months)
    bond_start_month = date(bond_deposit_date.year, bond_deposit_date.month, 1)
    bond_end_month = date(bond_closed_date.year, bond_closed_date.month, 1)

    bond_months = []
    current = bond_start_month
    while current <= bond_end_month:
        bond_months.append((current.year, current.month))
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    daily_bond_rate = (1 + 0.038) ** (1 / 365) - 1
    for i, (year, month) in enumerate(bond_months[:-1]):
        # bond_months[:-1] excludes the closure month — we handle that separately
        days = (date(year, month, 28) - bond_deposit_date).days
        if days < 0:
            days = 0
        balance = round(50000.0 * (1 + daily_bond_rate) ** days, 2)
        session.add(InvestmentBalanceSnapshot(
            investment_id=bond.id,
            date=date(year, month, 28).isoformat(),
            balance=balance,
            source="manual",
        ))

    # 0-balance snapshot on the last transaction date (the withdrawal date)
    session.add(InvestmentBalanceSnapshot(
        investment_id=bond.id,
        date=bond_closed_date.isoformat(),
        balance=0.0,
        source="manual",
    ))

    session.flush()


def create_budget_rules(session):
    """Create monthly budgets for the last 6 months + two project budgets."""
    monthly_budgets = [
        # Category-level rules — "all_tags" sentinel means "every tag in the category".
        # Storing None/empty leaves the rule matching no transactions, so they all
        # spill into the auto-generated "Other Expenses" bucket.
        ("Total Budget", 28000, "Total Budget", "all_tags"),
        ("Food Budget", 5000, "Food", "all_tags"),
        ("Transportation Budget", 1800, "Transportation", "all_tags"),
        ("Household Budget", 8000, "Household", "all_tags"),
        ("Entertainment Budget", 800, "Entertainment", "all_tags"),
        ("Health Budget", 600, "Health", "all_tags"),
        ("Kids Budget", 3500, "Kids", "all_tags"),
        ("Shopping Budget", 2000, "Shopping", "all_tags"),
        ("Vacations Budget", 4000, "Vacations", "all_tags"),
        # Tag-level rules — exercises per-tag breakdown within categories
        ("Groceries", 2800, "Food", "Groceries"),
        ("Restaurants", 1200, "Food", "Restaurants"),
        ("Gas", 1200, "Transportation", "Gas"),
        ("Online Shopping", 1500, "Shopping", "Online"),
    ]

    # Last 6 months ending with the current REFERENCE_DATE month
    budget_months = []
    current = date(REFERENCE_DATE.year, REFERENCE_DATE.month, 1)
    for _ in range(6):
        budget_months.append((current.year, current.month))
        current = current.replace(day=1) - timedelta(days=1)
    budget_months.sort()

    for year, month in budget_months:
        for name, amount, category, tags in monthly_budgets:
            session.add(BudgetRule(
                name=name,
                amount=amount,
                category=category,
                tags=tags,
                year=year,
                month=month,
            ))

    # Project budgets
    session.add(BudgetRule(
        name="Home Renovation",
        amount=30000,
        category="Home Renovation",
        tags="Materials;Labor;Furniture",
        year=None,
        month=None,
    ))
    session.add(BudgetRule(
        name="Our Wedding",
        amount=120000,
        category="Wedding",
        tags="Venue;Catering;Photography;Attire;Rings;Invitations;Honeymoon",
        year=None,
        month=None,
    ))

    session.flush()


def create_split_transactions(session, cc_txns: list[CreditCardTransaction]):
    """Create 3 split transaction examples."""
    # 1. Find a large grocery transaction on Max (~-300 to -350 range)
    max_groceries = [
        t for t in cc_txns
        if t.provider == "max" and t.category == "Food" and t.tag == "Groceries"
        and t.amount <= -300 and t.type == "normal"
    ]
    if max_groceries:
        parent = max_groceries[0]
        parent.type = "split_parent"
        session.add(SplitTransaction(
            transaction_id=parent.unique_id,
            source="credit_card_transactions",
            amount=round(parent.amount * 0.7, 2),
            category="Food",
            tag="Groceries",
        ))
        session.add(SplitTransaction(
            transaction_id=parent.unique_id,
            source="credit_card_transactions",
            amount=round(parent.amount * 0.3, 2),
            category="Household",
            tag="Cleaning Supplies",
        ))

    # 2. Find a Visa Cal electronics or large shopping transaction to repurpose as vacation
    visa_large = [
        t for t in cc_txns
        if t.provider == "visa cal" and t.category == "Shopping"
        and t.amount <= -400 and t.type == "normal"
    ]
    if visa_large:
        parent = visa_large[0]
        parent.type = "split_parent"
        parent.description = "BOOKING.COM HOTEL"
        parent.category = "Vacations"
        parent.tag = "Hotel"
        session.add(SplitTransaction(
            transaction_id=parent.unique_id,
            source="credit_card_transactions",
            amount=round(parent.amount * 0.8, 2),
            category="Vacations",
            tag="Hotel",
        ))
        session.add(SplitTransaction(
            transaction_id=parent.unique_id,
            source="credit_card_transactions",
            amount=round(parent.amount * 0.2, 2),
            category="Entertainment",
            tag="Events",
        ))

    # 3. Find an online order on Visa Cal (~-400 to -500)
    visa_online = [
        t for t in cc_txns
        if t.provider == "visa cal" and t.category == "Shopping" and t.tag == "Online"
        and t.amount <= -300 and t.type == "normal"
    ]
    if visa_online:
        parent = visa_online[0]
        parent.type = "split_parent"
        session.add(SplitTransaction(
            transaction_id=parent.unique_id,
            source="credit_card_transactions",
            amount=round(parent.amount * 0.6, 2),
            category="Shopping",
            tag="Online",
        ))
        session.add(SplitTransaction(
            transaction_id=parent.unique_id,
            source="credit_card_transactions",
            amount=round(parent.amount * 0.4, 2),
            category="Kids",
            tag="Clothing",
        ))

    # 4. Split on a cash transaction — exercises non-CC split source variety.
    cash_candidates = (
        session.query(CashTransaction)
        .filter(CashTransaction.amount <= -40, CashTransaction.type == "normal")
        .order_by(CashTransaction.unique_id.desc())
        .limit(1)
        .all()
    )
    if cash_candidates:
        parent = cash_candidates[0]
        parent.type = "split_parent"
        parent.description = "Mixed Cash Purchase"
        session.add(SplitTransaction(
            transaction_id=parent.unique_id,
            source="cash_transactions",
            amount=round(parent.amount * 0.5, 2),
            category="Food",
            tag="Groceries",
        ))
        session.add(SplitTransaction(
            transaction_id=parent.unique_id,
            source="cash_transactions",
            amount=round(parent.amount * 0.5, 2),
            category="Other",
            tag="Haircut",
        ))

    session.flush()


def create_bank_balance(session):
    """Create bank balance records for all tracked bank accounts."""
    session.add(BankBalance(
        provider="hapoalim",
        account_name="Main Account",
        balance=85000.0,
        prior_wealth_amount=50000.0,
        last_scrape_update=(REFERENCE_DATE - timedelta(days=1)).isoformat(),
    ))
    # Savings account: starts with 5k prior wealth + 14 months of 2k transfers
    session.add(BankBalance(
        provider="leumi",
        account_name="Savings Account",
        balance=33000.0,
        prior_wealth_amount=5000.0,
        last_scrape_update=(REFERENCE_DATE - timedelta(days=1)).isoformat(),
    ))
    session.flush()


def create_cash_balance(session):
    """Create cash balance records for all envelopes."""
    session.add(CashBalance(
        account_name="Petty Cash",
        balance=520.0,
        prior_wealth_amount=1000.0,
        last_manual_update=(REFERENCE_DATE - timedelta(days=7)).isoformat(),
    ))
    session.add(CashBalance(
        account_name="Kids Envelope",
        balance=180.0,
        prior_wealth_amount=300.0,
        last_manual_update=(REFERENCE_DATE - timedelta(days=14)).isoformat(),
    ))
    session.flush()


def create_pending_refunds(session, cc_txns, bank_txns):
    """Create pending refund records covering all statuses for demo testing.

    Creates:
    1. Pending refund (no links) - jacket return
    2. Partial refund (one link, not fully covered) - electronics partial return
    3. Resolved refund (fully linked) - duplicate charge
    4. Closed refund (user accepted partial) - restaurant dispute
    5. Partial refund with multiple links - expensive item with 2 refund txns
    6. Partial refund for auto-split testing - 80 ILS remaining, 150 ILS refund available
    """
    used = set()  # Track used CC transaction unique_ids

    # 1. Pending refund: recent shopping item, no links
    recent_shopping = [
        t for t in cc_txns
        if t.category == "Shopping" and t.tag == "Online" and t.type == "normal"
        and t.amount < -100 and t.unique_id not in used
    ]
    if recent_shopping:
        source_txn = recent_shopping[-1]
        used.add(source_txn.unique_id)
        session.add(PendingRefund(
            source_type="transaction",
            source_id=source_txn.unique_id,
            source_table="credit_card_transactions",
            expected_amount=abs(source_txn.amount),
            status="pending",
            notes="Returned jacket, waiting for refund",
        ))

    # 2. Partial refund: electronics item with one partial link
    electronics = [
        t for t in cc_txns
        if t.category == "Shopping" and t.tag == "Electronics" and t.type == "normal"
        and t.amount < -200 and t.unique_id not in used
    ]
    if electronics:
        source_txn = electronics[-1]
        used.add(source_txn.unique_id)
        expected = abs(source_txn.amount)
        partial_amount = round(expected * 0.4, 2)

        partial_refund = PendingRefund(
            source_type="transaction",
            source_id=source_txn.unique_id,
            source_table="credit_card_transactions",
            expected_amount=expected,
            status="partial",
            notes="Partial refund for defective item, store credit pending",
        )
        session.add(partial_refund)
        session.flush()

        partial_refund_txn = BankTransaction(
            id="demo-bank-refund-partial",
            date=rand_date_in_month(REFERENCE_DATE.year, REFERENCE_DATE.month, 5, 15),
            provider="hapoalim",
            account_name="Main Account",
            description="PARTIAL REFUND - VISA CAL",
            amount=partial_amount,
            category="Shopping",
            tag="Electronics",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        session.add(partial_refund_txn)
        session.flush()

        session.add(RefundLink(
            pending_refund_id=partial_refund.id,
            refund_transaction_id=partial_refund_txn.unique_id,
            refund_source="bank_transactions",
            amount=partial_amount,
        ))

    # 3. Resolved refund: fully linked
    resolved_shopping = [
        t for t in cc_txns
        if t.category == "Shopping" and t.tag == "Online" and t.type == "normal"
        and t.amount < -100 and t.unique_id not in used
    ]
    if resolved_shopping:
        source_txn = resolved_shopping[-1]
        used.add(source_txn.unique_id)
        refund_amount = abs(source_txn.amount)

        resolved_refund = PendingRefund(
            source_type="transaction",
            source_id=source_txn.unique_id,
            source_table="credit_card_transactions",
            expected_amount=refund_amount,
            status="resolved",
            notes="Duplicate charge refunded",
        )
        session.add(resolved_refund)
        session.flush()

        refund_txn = BankTransaction(
            id="demo-bank-refund-001",
            date=rand_date_in_month(REFERENCE_DATE.year, REFERENCE_DATE.month, 1, 20),
            provider="hapoalim",
            account_name="Main Account",
            description="REFUND - VISA CAL",
            amount=refund_amount,
            category="Shopping",
            tag="Online",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        session.add(refund_txn)
        session.flush()

        session.add(RefundLink(
            pending_refund_id=resolved_refund.id,
            refund_transaction_id=refund_txn.unique_id,
            refund_source="bank_transactions",
            amount=refund_amount,
        ))

    # 4. Closed refund: user accepted partial, closed it
    restaurant = [
        t for t in cc_txns
        if t.category == "Food" and t.tag == "Restaurants" and t.type == "normal"
        and t.amount < -150 and t.unique_id not in used
    ]
    if restaurant:
        source_txn = restaurant[-1]
        used.add(source_txn.unique_id)
        expected = abs(source_txn.amount)
        closed_partial = round(expected * 0.5, 2)

        closed_refund = PendingRefund(
            source_type="transaction",
            source_id=source_txn.unique_id,
            source_table="credit_card_transactions",
            expected_amount=expected,
            status="closed",
            notes="Restaurant dispute - accepted 50% settlement",
        )
        session.add(closed_refund)
        session.flush()

        closed_refund_txn = BankTransaction(
            id="demo-bank-refund-closed",
            date=rand_date_in_month(REFERENCE_DATE.year, REFERENCE_DATE.month, 10, 20),
            provider="hapoalim",
            account_name="Main Account",
            description="SETTLEMENT - RESTAURANT DISPUTE",
            amount=closed_partial,
            category="Food",
            tag="Restaurants",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        session.add(closed_refund_txn)
        session.flush()

        session.add(RefundLink(
            pending_refund_id=closed_refund.id,
            refund_transaction_id=closed_refund_txn.unique_id,
            refund_source="bank_transactions",
            amount=closed_partial,
        ))

    # 5. Partial refund with multiple links (test multi-link scenario)
    # Source: an expensive CC transaction, linked to 2 partial refund bank transactions
    expensive_shopping = [
        t for t in cc_txns
        if t.category == "Shopping" and t.type == "normal"
        and t.amount < -300 and t.unique_id not in used
    ]
    if expensive_shopping:
        source_txn = expensive_shopping[-1]
        used.add(source_txn.unique_id)
        expected = abs(source_txn.amount)
        link1_amount = round(expected * 0.3, 2)
        link2_amount = round(expected * 0.25, 2)

        multi_link_refund = PendingRefund(
            source_type="transaction",
            source_id=source_txn.unique_id,
            source_table="credit_card_transactions",
            expected_amount=expected,
            status="partial",
            notes="Multiple partial refunds received, more expected",
        )
        session.add(multi_link_refund)
        session.flush()

        refund_txn_1 = BankTransaction(
            id="demo-bank-refund-multi-1",
            date=rand_date_in_month(REFERENCE_DATE.year, REFERENCE_DATE.month, 3, 8),
            provider="hapoalim",
            account_name="Main Account",
            description="REFUND 1/3 - STORE CREDIT",
            amount=link1_amount,
            category="Shopping",
            tag="Online",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        refund_txn_2 = BankTransaction(
            id="demo-bank-refund-multi-2",
            date=rand_date_in_month(REFERENCE_DATE.year, REFERENCE_DATE.month, 10, 15),
            provider="hapoalim",
            account_name="Main Account",
            description="REFUND 2/3 - STORE CREDIT",
            amount=link2_amount,
            category="Shopping",
            tag="Online",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        session.add_all([refund_txn_1, refund_txn_2])
        session.flush()

        session.add(RefundLink(
            pending_refund_id=multi_link_refund.id,
            refund_transaction_id=refund_txn_1.unique_id,
            refund_source="bank_transactions",
            amount=link1_amount,
        ))
        session.add(RefundLink(
            pending_refund_id=multi_link_refund.id,
            refund_transaction_id=refund_txn_2.unique_id,
            refund_source="bank_transactions",
            amount=link2_amount,
        ))

    # 6. Pending refund with small remaining (test auto-split linking)
    # Source: any CC transaction. We set expected=200, link 120, leaving 80 remaining.
    # A 150 ILS bank refund is available — linking it should auto-split to 80 + 70.
    autosplit_candidates = [
        t for t in cc_txns
        if t.type == "normal" and t.amount < -100 and t.unique_id not in used
    ]
    if autosplit_candidates:
        source_txn = autosplit_candidates[-1]
        used.add(source_txn.unique_id)
        expected = 200.0
        first_link = 120.0

        autosplit_refund = PendingRefund(
            source_type="transaction",
            source_id=source_txn.unique_id,
            source_table="credit_card_transactions",
            expected_amount=expected,
            status="partial",
            notes="Overcharged ride fare - link the 150 ILS refund to test auto-split (remaining: 80)",
        )
        session.add(autosplit_refund)
        session.flush()

        first_refund_txn = BankTransaction(
            id="demo-bank-refund-autosplit-1",
            date=rand_date_in_month(REFERENCE_DATE.year, REFERENCE_DATE.month, 5, 10),
            provider="hapoalim",
            account_name="Main Account",
            description="RIDE REFUND - PARTIAL",
            amount=first_link,
            category="Transportation",
            tag="Taxi",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        session.add(first_refund_txn)
        session.flush()

        session.add(RefundLink(
            pending_refund_id=autosplit_refund.id,
            refund_transaction_id=first_refund_txn.unique_id,
            refund_source="bank_transactions",
            amount=first_link,
        ))

        # This 150 ILS refund is available for linking — should auto-split to 80 + 70
        autosplit_candidate = BankTransaction(
            id="demo-bank-refund-autosplit-candidate",
            date=rand_date_in_month(REFERENCE_DATE.year, REFERENCE_DATE.month, 18, 25),
            provider="hapoalim",
            account_name="Main Account",
            description="RIDE REFUND - REMAINING (150, will auto-split to 80+70)",
            amount=150.0,
            category="Transportation",
            tag="Taxi",
            source="bank_transactions",
            type="normal",
            status="completed",
        )
        session.add(autosplit_candidate)

    # 7. Pending refund on a SPLIT (source_type='split') — exercises refund tracking
    # against a sub-portion of a split parent rather than a raw transaction.
    split_target = (
        session.query(SplitTransaction)
        .filter(SplitTransaction.source == "credit_card_transactions",
                SplitTransaction.amount <= -100)
        .first()
    )
    if split_target:
        session.add(PendingRefund(
            source_type="split",
            source_id=split_target.id,
            source_table="credit_card_transactions",
            expected_amount=abs(split_target.amount),
            status="pending",
            notes="Refund expected on split portion — supplier offered store credit",
        ))

    session.flush()


def create_retirement_goal(session):
    """Create a retirement goal record for FIRE page testing.

    Based on the Cohen family profile: two incomes, mortgage, KH + pension
    balances from the insurance accounts. Target is early retirement at 55.

    The KH balance/contribution numbers below are the SUM of the three
    Keren Hishtalmut accounts seeded in generate_insurance_data
    (active tech + spouse + previous employer). Keep these in sync with
    the InsuranceAccount balances and the per-employee KH percentages
    derived from Israeli law (2.5% employee + 7.5% employer of gross,
    capped at the 15,712 ILS/month tax-exempt cap for the tech employee).
    """
    # KH totals must match generate_insurance_data:
    #   tech:  110,000 balance, 1,571/mo contribution (capped)
    #   teacher: 95,000 balance, 1,400/mo
    #   old:    50,000 balance, frozen (no current contribution)
    kh_total_balance = 110_000.0 + 95_000.0 + 50_000.0  # 255,000
    kh_total_monthly = 1_571.0 + 1_400.0                # 2,971

    session.add(RetirementGoal(
        current_age=38,
        gender="male",
        target_retirement_age=55,
        life_expectancy=90,
        monthly_expenses_in_retirement=20000.0,
        inflation_rate=0.025,
        expected_return_rate=0.045,
        withdrawal_rate=0.035,
        pension_monthly_payout_estimate=8500.0,
        keren_hishtalmut_balance=kh_total_balance,
        keren_hishtalmut_monthly_contribution=kh_total_monthly,
        bituach_leumi_eligible=1,
        bituach_leumi_monthly_estimate=2800.0,
        other_passive_income=0.0,
    ))
    session.flush()


def create_scraping_history(session):
    """Create 5 scraping history records."""
    recent = REFERENCE_DATE - timedelta(days=1)
    older = REFERENCE_DATE - timedelta(days=21)

    # 4 recent successful scrapes (two bank accounts + two CC accounts)
    session.add(ScrapingHistory(
        service_name="banks",
        provider_name="hapoalim",
        account_name="Main Account",
        date=datetime(recent.year, recent.month, recent.day, 8, 30, 0).isoformat(),
        status="SUCCESS",
        start_date=(recent - timedelta(days=30)).isoformat(),
    ))
    session.add(ScrapingHistory(
        service_name="banks",
        provider_name="leumi",
        account_name="Savings Account",
        date=datetime(recent.year, recent.month, recent.day, 8, 32, 0).isoformat(),
        status="SUCCESS",
        start_date=(recent - timedelta(days=30)).isoformat(),
    ))
    session.add(ScrapingHistory(
        service_name="credit_cards",
        provider_name="max",
        account_name="Family Card",
        date=datetime(recent.year, recent.month, recent.day, 8, 35, 0).isoformat(),
        status="SUCCESS",
        start_date=(recent - timedelta(days=30)).isoformat(),
    ))
    session.add(ScrapingHistory(
        service_name="credit_cards",
        provider_name="visa cal",
        account_name="Online Shopping",
        date=datetime(recent.year, recent.month, recent.day, 8, 40, 0).isoformat(),
        status="SUCCESS",
        start_date=(recent - timedelta(days=30)).isoformat(),
    ))

    # 1 older failed scrape (3 weeks ago)
    session.add(ScrapingHistory(
        service_name="banks",
        provider_name="hapoalim",
        account_name="Main Account",
        date=datetime(older.year, older.month, older.day, 9, 0, 0).isoformat(),
        status="FAILED",
        start_date=(older - timedelta(days=30)).isoformat(),
        error_message="Timeout waiting for page load",
    ))

    # 1 older successful scrape (3 weeks ago)
    session.add(ScrapingHistory(
        service_name="credit_cards",
        provider_name="max",
        account_name="Family Card",
        date=datetime(older.year, older.month, older.day, 9, 5, 0).isoformat(),
        status="SUCCESS",
        start_date=(older - timedelta(days=30)).isoformat(),
    ))

    session.flush()


# ---------------------------------------------------------------------------
# Insurance accounts & transactions
# ---------------------------------------------------------------------------

def generate_insurance_data(session):
    """Generate insurance accounts (pension + keren hishtalmut) and monthly deposit transactions.

    Creates:
    - Tech employee: pension makifa + pension mashlima (because gross > Makifa cap)
    - School employee: pension makifa only (gross < Makifa cap)
    - 2 active keren hishtalmut accounts (one per spouse, Tech's is capped)
    - 1 inactive keren hishtalmut (Tech's previous employer, no recent transactions)

    Israeli pension/KH law (see .claude/skills/israeli-salary-knowledge for
    the full write-up — keep these numbers in sync with that reference)
    ---------------------------------------------------------------------
    All percentages are applied to the employee's GROSS salary. Employer
    shares are added on top of the gross, not deducted from it.

    Pension (18.5% of gross, legal minimum since 2017):
        - Employee (תגמולי עובד):         6.0%
        - Employer savings (תגמולי מעסיק): 6.5%
        - Employer severance (פיצויים):    6.0%

    Makifa vs Mashlima split:
        - The first ~25,000 ILS/month of gross salary (= 2× שכר ממוצע במשק)
          goes to Keren Pensia Makifa (קרן פנסיה מקיפה). Makifa is the
          main fund and carries disability + life-insurance coverage.
        - Excess salary above the cap routes the SAME 18.5% percentages
          into Keren Pensia Mashlima (קרן פנסיה משלימה), which is a pure
          savings plan with no insurance component.
        - A worker below the cap has ONLY a Makifa account.
        - A worker above the cap has BOTH (each fed from its own slice
          of the gross).

    Keren Hishtalmut (10% of gross):
        - Employee: 2.5% of gross
        - Employer: 7.5% of gross
        - Tax-exempt gross-salary cap (2026): 15,712 ILS/month.
          Deposits above the cap are allowed but taxable for the
          employee, so most payrolls cap them at this base — which is
          what we model.

    Demo couple:
        - Tech employee:  28,000 ILS gross  (≈ 18,000 net after pension,
                          KH, income tax, Bituach Leumi) — ABOVE Makifa cap
        - Teacher:        14,000 ILS gross  (≈ 11,000 net)
                          — BELOW Makifa cap, no Mashlima account

    Each individual's pension and KH accounts are funded exclusively from
    THAT individual's gross salary. Spouses' accounts are never pooled.

    Account balances reflect ~5 years of contributions (2 prior + 3 tracked)
    with a realistic ~5-6%/year real return.
    """
    months = list(month_range(START_DATE, REFERENCE_DATE))
    txn_counter = 0

    # --- Gross monthly salaries (see skill doc for net-calculation example) ---
    tech_gross = 28_000.0       # above Makifa cap → gets Makifa + Mashlima
    teacher_gross = 14_000.0    # below Makifa cap → Makifa only

    # --- Legal thresholds (2026 — update with annual indexation) ---
    # Makifa deposit cap expressed as a monthly salary (≈ 2× שכר ממוצע).
    # Deposits on gross above this amount route to Mashlima instead.
    makifa_salary_cap = 25_000.0
    # KH tax-exempt monthly gross salary base.
    kh_cap = 15_712.0

    # Pension shares (legal minimum since 2017).
    pn_employee_pct = 0.06
    pn_employer_pct = 0.065
    pn_severance_pct = 0.06
    pn_total_pct = pn_employee_pct + pn_employer_pct + pn_severance_pct  # 0.185

    # KH shares.
    kh_employee_pct = 0.025
    kh_employer_pct = 0.075
    kh_total_pct = kh_employee_pct + kh_employer_pct  # 0.10

    # --- Per-individual pension bases after the Makifa cap split ---
    tech_makifa_base = min(tech_gross, makifa_salary_cap)               # 25,000
    tech_mashlima_base = max(0.0, tech_gross - makifa_salary_cap)       # 3,000
    teacher_makifa_base = min(teacher_gross, makifa_salary_cap)         # 14,000
    teacher_mashlima_base = max(0.0, teacher_gross - makifa_salary_cap)  # 0 → no account

    # --- Monthly deposit amounts derived from the rules above ---
    # Tech employee — Makifa (first 25k)
    pn_tech_makifa_employee = round(tech_makifa_base * pn_employee_pct, 2)    # 1,500
    pn_tech_makifa_employer = round(tech_makifa_base * pn_employer_pct, 2)    # 1,625
    pn_tech_makifa_severance = round(tech_makifa_base * pn_severance_pct, 2)  # 1,500
    pn_tech_makifa_total = round(tech_makifa_base * pn_total_pct, 2)          # 4,625

    # Tech employee — Mashlima (the 3k above the cap)
    pn_tech_mashlima_employee = round(tech_mashlima_base * pn_employee_pct, 2)    # 180
    pn_tech_mashlima_employer = round(tech_mashlima_base * pn_employer_pct, 2)    # 195
    pn_tech_mashlima_severance = round(tech_mashlima_base * pn_severance_pct, 2)  # 180
    pn_tech_mashlima_total = round(tech_mashlima_base * pn_total_pct, 2)          # 555

    # Teacher — Makifa only (below cap)
    pn_teacher_makifa_employee = round(teacher_makifa_base * pn_employee_pct, 2)     # 840
    pn_teacher_makifa_employer = round(teacher_makifa_base * pn_employer_pct, 2)     # 910
    pn_teacher_makifa_severance = round(teacher_makifa_base * pn_severance_pct, 2)   # 840
    pn_teacher_makifa_total = round(teacher_makifa_base * pn_total_pct, 2)           # 2,590

    # KH for tech employee — capped at the tax-exempt base.
    kh_tech_base = min(tech_gross, kh_cap)
    kh_tech_total = round(kh_tech_base * kh_total_pct, 2)               # 1,571

    # KH for teacher — below cap, full gross.
    kh_teacher_total = round(teacher_gross * kh_total_pct, 2)           # 1,400

    # --- Insurance Accounts ---
    # Balances reflect ~5 years of contributions (2 prior + 3 tracked)
    # plus ~5-6%/year real growth. Rough target: monthly × 60 × 1.13..1.19.
    pension_tech_makifa = InsuranceAccount(
        provider="hafenix",
        policy_id="PN-DEMO-001",
        policy_type="pension",
        pension_type="makifa",
        account_name="Pension Comprehensive - Tech Company",
        balance=330_000.0,  # ≈ 4,625 × 60 × 1.19
        balance_date=REFERENCE_DATE.isoformat(),
        investment_tracks=json.dumps([
            {"name": "General Track", "yield_pct": 5.8, "allocation_pct": 100, "sum": 330000.0},
        ]),
        commission_deposits_pct=1.49,
        commission_savings_pct=0.22,
        insurance_covers=json.dumps([
            {"title": "Disability Insurance", "desc": "75% of salary (up to cap)", "sum": 18750},
            {"title": "Life Insurance", "desc": "Lump sum to beneficiaries", "sum": 500000},
        ]),
        insurance_costs=json.dumps([
            {"title": "Life insurance premium", "amount": 85},
            {"title": "Disability premium", "amount": 120},
        ]),
    )
    session.add(pension_tech_makifa)

    # Tech's Mashlima — opened when gross first crossed the Makifa cap
    # (i.e. only the slice above 25,000 has been routed here). Much smaller
    # balance than the Makifa account because the contribution base is small.
    pension_tech_mashlima = InsuranceAccount(
        provider="hafenix",
        policy_id="PN-DEMO-003",
        policy_type="pension",
        pension_type="mashlima",
        account_name="Pension Supplementary - Tech Company",
        balance=38_000.0,   # ≈ 555 × 60 × 1.14
        balance_date=REFERENCE_DATE.isoformat(),
        investment_tracks=json.dumps([
            {"name": "Equity Track", "yield_pct": 6.8, "allocation_pct": 100, "sum": 38000.0},
        ]),
        commission_deposits_pct=1.35,
        commission_savings_pct=0.20,
        # Mashlima is pure savings — no disability/life coverage (insurance
        # is carried by the Makifa account).
    )
    session.add(pension_tech_mashlima)

    # Teacher's Makifa — she is below the cap, so no Mashlima account at all.
    # The policy_id slot PN-DEMO-002 was previously a (wrong) Mashlima account;
    # reusing the id to stay stable across regenerations.
    pension_teacher_makifa = InsuranceAccount(
        provider="hafenix",
        policy_id="PN-DEMO-002",
        policy_type="pension",
        pension_type="makifa",
        account_name="Pension Comprehensive - School District",
        balance=175_000.0,  # ≈ 2,590 × 60 × 1.13
        balance_date=REFERENCE_DATE.isoformat(),
        investment_tracks=json.dumps([
            {"name": "Bonds Track", "yield_pct": 3.5, "allocation_pct": 60, "sum": 105000.0},
            {"name": "Equity Track", "yield_pct": 6.5, "allocation_pct": 40, "sum": 70000.0},
        ]),
        commission_deposits_pct=1.25,
        commission_savings_pct=0.18,
        insurance_covers=json.dumps([
            {"title": "Disability Insurance", "desc": "75% of salary (up to cap)", "sum": 10500},
            {"title": "Life Insurance", "desc": "Lump sum to beneficiaries", "sum": 250000},
        ]),
        insurance_costs=json.dumps([
            {"title": "Disability premium", "amount": 55},
        ]),
    )
    session.add(pension_teacher_makifa)

    kh_active = InsuranceAccount(
        provider="hafenix",
        policy_id="KH-DEMO-001",
        policy_type="hishtalmut",
        account_name="Keren Hishtalmut - Tech Company",
        balance=110_000.0,  # ≈ 1,571 × 60 × 1.17
        balance_date=REFERENCE_DATE.isoformat(),
        investment_tracks=json.dumps([
            {"name": "S&P 500 Track", "yield_pct": 8.2, "allocation_pct": 70, "sum": 77000.0},
            {"name": "Israel Bond Track", "yield_pct": 3.2, "allocation_pct": 30, "sum": 33000.0},
        ]),
        commission_deposits_pct=0.0,
        commission_savings_pct=0.74,
        liquidity_date=(REFERENCE_DATE + timedelta(days=365 * 2)).isoformat(),
    )
    session.add(kh_active)

    kh_spouse = InsuranceAccount(
        provider="hafenix",
        policy_id="KH-DEMO-002",
        policy_type="hishtalmut",
        account_name="Keren Hishtalmut - School District",
        balance=95_000.0,   # ≈ 1,400 × 60 × 1.13
        balance_date=REFERENCE_DATE.isoformat(),
        investment_tracks=json.dumps([
            {"name": "General Track", "yield_pct": 5.4, "allocation_pct": 100, "sum": 95000.0},
        ]),
        commission_deposits_pct=0.0,
        commission_savings_pct=0.85,
        liquidity_date=(REFERENCE_DATE - timedelta(days=180)).isoformat(),
    )
    session.add(kh_spouse)

    # Inactive KH — Tech employee's previous employer (gross ~12k at that job)
    # for ~3 years, then frozen. Modest growth ≈ 4%/yr since then.
    kh_old = InsuranceAccount(
        provider="hafenix",
        policy_id="KH-DEMO-OLD",
        policy_type="hishtalmut",
        account_name="Keren Hishtalmut - Previous Employer",
        balance=50_000.0,   # 1,200 × 36 + ~4%/yr growth since freeze
        balance_date=(REFERENCE_DATE - timedelta(days=200)).isoformat(),
        investment_tracks=json.dumps([
            {"name": "Default Track", "yield_pct": 4.5, "allocation_pct": 100, "sum": 50000.0},
        ]),
        commission_deposits_pct=0.0,
        commission_savings_pct=0.95,
        liquidity_date=(REFERENCE_DATE - timedelta(days=365)).isoformat(),
    )
    session.add(kh_old)

    # --- Monthly deposit transactions ---
    # Memo format matches the pension fund convention:
    #   "עובד: <employee> / מעסיק: <employer savings> / פיצויים: <severance>"
    # The three Hebrew sub-amounts MUST sum to the transaction's `amount`.
    pn_tech_makifa_memo = (
        f"עובד: {pn_tech_makifa_employee:.0f} / "
        f"מעסיק: {pn_tech_makifa_employer:.0f} / "
        f"פיצויים: {pn_tech_makifa_severance:.0f}"
    )
    pn_tech_mashlima_memo = (
        f"עובד: {pn_tech_mashlima_employee:.0f} / "
        f"מעסיק: {pn_tech_mashlima_employer:.0f} / "
        f"פיצויים: {pn_tech_mashlima_severance:.0f}"
    )
    pn_teacher_makifa_memo = (
        f"עובד: {pn_teacher_makifa_employee:.0f} / "
        f"מעסיק: {pn_teacher_makifa_employer:.0f} / "
        f"פיצויים: {pn_teacher_makifa_severance:.0f}"
    )

    deposit_configs = [
        ("PN-DEMO-001", "Pension Comprehensive - Tech Company", pn_tech_makifa_total,
         "הפקדה - Cohen Technologies", pn_tech_makifa_memo),
        ("PN-DEMO-003", "Pension Supplementary - Tech Company", pn_tech_mashlima_total,
         "הפקדה - Cohen Technologies", pn_tech_mashlima_memo),
        ("PN-DEMO-002", "Pension Comprehensive - School District", pn_teacher_makifa_total,
         "הפקדה - Tel Aviv School District", pn_teacher_makifa_memo),
        ("KH-DEMO-001", "Keren Hishtalmut - Tech Company", kh_tech_total,
         "הפקדה - Cohen Technologies", None),
        ("KH-DEMO-002", "Keren Hishtalmut - School District", kh_teacher_total,
         "הפקדה - Tel Aviv School District", None),
    ]

    for policy_id, account_name, monthly_amount, description, memo in deposit_configs:
        for year, month_num in months:
            txn_counter += 1
            amount = monthly_amount
            txn = InsuranceTransaction(
                id=f"demo-ins-{txn_counter:04d}",
                date=rand_date_in_month(year, month_num, 1, 10),
                provider="hafenix",
                account_name=account_name,
                account_number=policy_id,
                description=description,
                amount=amount,
                category="Ignore",
                tag="Internal Transactions",
                source="insurance_transactions",
                type="normal",
                status="completed",
                memo=memo,
            )
            session.add(txn)

    # Old KH — only has transactions from 6+ months ago. Previous gross of
    # 12,000 → KH deposit of 1,200/month before the account froze.
    old_kh_monthly = 12_000.0 * kh_total_pct  # 1,200
    old_months = [(y, m) for y, m in months
                  if date(y, m, 1) < (REFERENCE_DATE - timedelta(days=180))]
    for year, month_num in old_months:
        txn_counter += 1
        txn = InsuranceTransaction(
            id=f"demo-ins-{txn_counter:04d}",
            date=rand_date_in_month(year, month_num, 1, 10),
            provider="hafenix",
            account_name="Keren Hishtalmut - Previous Employer",
            account_number="KH-DEMO-OLD",
            description="הפקדה",
            amount=old_kh_monthly,
            category="Ignore",
            tag="Internal Transactions",
            source="insurance_transactions",
            type="normal",
            status="completed",
        )
        session.add(txn)

    session.flush()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    """Generate the complete demo database."""
    # Remove existing DB if present
    if DB_PATH.exists():
        DB_PATH.unlink()

    print(f"Creating demo database at: {DB_PATH}")

    # Create engine and tables
    engine = create_engine(
        f"sqlite:///{DB_PATH}",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # 1. Categories
        print("  Creating categories...")
        create_categories(session)

        # 2. Tagging rules
        print("  Creating tagging rules...")
        create_tagging_rules(session)

        # 3. Credit card transactions (must come first for CC bill totals)
        print("  Generating credit card transactions...")
        monthly_cc_totals, cc_txns = generate_cc_transactions(session)

        # 4. Untagged transactions (updates monthly_cc_totals for bill consistency)
        print("  Generating untagged transactions...")
        generate_untagged_transactions(session, monthly_cc_totals)

        # 5. Bank transactions (uses CC totals for bill amounts)
        print("  Generating bank transactions...")
        bank_txns = generate_bank_transactions(session, monthly_cc_totals)

        # 6. Cash transactions
        print("  Generating cash transactions...")
        generate_cash_transactions(session)

        # 7. Investment transactions
        print("  Generating investment transactions...")
        generate_investment_transactions(session)

        # 8. Investments (instruments)
        print("  Creating investments...")
        stock_fund, savings_plan, bond = create_investments(session)

        # 9. Investment balance snapshots
        print("  Creating investment balance snapshots...")
        create_investment_snapshots(session, stock_fund, savings_plan, bond)

        # 10. Budget rules
        print("  Creating budget rules...")
        create_budget_rules(session)

        # 11. Split transactions
        print("  Creating split transactions...")
        create_split_transactions(session, cc_txns)

        # 12. Bank balance
        print("  Creating bank balance...")
        create_bank_balance(session)

        # 13. Cash balance
        print("  Creating cash balance...")
        create_cash_balance(session)

        # 14. Pending refunds
        print("  Creating pending refunds...")
        create_pending_refunds(session, cc_txns, bank_txns)

        # 15. Liabilities
        print("  Creating liabilities...")
        create_liabilities(session)

        # 16. Scraping history
        print("  Creating scraping history...")
        create_scraping_history(session)

        # 17. Insurance accounts & transactions
        print("  Generating insurance data...")
        generate_insurance_data(session)

        # 18. Retirement goal
        print("  Creating retirement goal...")
        create_retirement_goal(session)

        session.commit()

        # 18. Link hishtalmut policies to Investment records. Done after
        # commit because the generator inserts InsuranceAccount rows directly
        # (bypassing the scraper's _post_save_hook that normally triggers this).
        print("  Syncing hishtalmut investments...")
        from backend.services.investments_service import InvestmentsService
        synced = InvestmentsService(session).backfill_from_insurance_accounts()
        session.commit()
        print(f"    Synced {synced} hishtalmut policies to investments")

        print("\nDemo database created successfully!")

        # Print summary counts
        print("\n--- Row Counts ---")
        tables = [
            "bank_transactions",
            "credit_card_transactions",
            "cash_transactions",
            "manual_investment_transactions",
            "insurance_transactions",
            "insurance_accounts",
            "categories",
            "budget_rules",
            "tagging_rules",
            "investments",
            "investment_balance_snapshots",
            "pending_refunds",
            "refund_links",
            "scraping_history",
            "bank_balances",
            "cash_balances",
            "split_transactions",
            "liabilities",
            "retirement_goals",
        ]
        from sqlalchemy import text
        for table in tables:
            count = session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            print(f"  {table}: {count}")

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


if __name__ == "__main__":
    main()
