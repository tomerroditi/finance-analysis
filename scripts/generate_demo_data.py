"""Generate a pre-built demo SQLite database for the finance analysis dashboard.

Creates ~1,200+ transactions for a fictional Israeli family ("The Cohens") over
14 months, along with categories, budgets, investments, tagging rules, and all
supporting records.

Usage
-----
    python scripts/generate_demo_data.py
"""

import json
import os
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — allow importing backend modules from project root
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from backend.models.base import Base
from backend.models import (
    BankBalance,
    BankTransaction,
    BudgetRule,
    CashBalance,
    CashTransaction,
    Category,
    CreditCardTransaction,
    Investment,
    InvestmentBalanceSnapshot,
    Liability,
    ManualInvestmentTransaction,
    PendingRefund,
    RefundLink,
    ScrapingHistory,
    SplitTransaction,
    TaggingRule,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REFERENCE_DATE = date(2026, 2, 25)
START_DATE = REFERENCE_DATE - timedelta(days=420)  # ~14 months back
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
    "Transportation": (["Gas", "Parking", "Public Transportation", "Taxi"], "🚗"),
    "Household": (["Mortgage", "Electricity", "Water", "Internet", "Cleaning Supplies", "Home Insurance"], "🏠"),
    "Entertainment": (["Streaming", "Cinema", "Events", "Games"], "🎉"),
    "Health": (["Pharmacy", "Doctor", "Gym", "Dental"], "💊"),
    "Kids": (["Daycare", "Activities", "Clothing", "School Supplies"], "👶"),
    "Shopping": (["Electronics", "Clothing", "Online", "Gifts"], "🛒"),
    "Education": (["Courses", "Books"], "🎓"),
    "Subscriptions": (["Netflix", "Spotify", "Chat-GPT"], "📱"),
    "Vacations": (["Flights", "Hotel", "Food"], "🌍"),
    "Other": (["ATM", "Bank Commisions", "Haircut"], "🙅"),
    "Salary": (["Tech Company", "School District"], "💵"),
    "Other Income": (["Prior Wealth", "Freelance"], "💵"),
    "Investments": (["Stock Market Fund", "Savings Plan", "Corporate Bond"], "💲"),
    "Liabilities": (["Mortgage", "Car Loan"], "💳"),
    "Credit Cards": ([], None),
    "Ignore": (["Credit Card Bill", "Internal Transactions"], "🚫"),
    "Home Renovation": (["Materials", "Labor", "Furniture"], "🏠"),
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

        # Home Renovation — last 6 months only, on Max card
        month_date = date(year, month, 15)
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
            txn = BankTransaction(
                id=f"demo-bank-{bank_counter:04d}",
                date=rand_date_in_month(year, month, 10, 20),
                provider="hapoalim",
                account_name="Main Account",
                description=desc,
                amount=amt,
                category="Household",
                tag=None,
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
                    tag=None,
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
                    tag=None,
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

    session.flush()
    return all_bank_txns


def create_liabilities(session):
    """Create liability records for Mortgage and Car Loan."""
    car_loan_start = START_DATE + timedelta(days=240)

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

    session.flush()


def generate_cash_transactions(session):
    """Generate ~50-70 cash transactions over 14 months."""
    cash_counter = 0
    months = list(month_range(START_DATE, REFERENCE_DATE))

    cash_templates = [
        ("Cash Market Purchase", "Food", "Groceries", -60, -20),
        ("Tip", "Other", None, -50, -10),
        ("Flea Market", "Shopping", None, -100, -30),
    ]

    for year, month in months:
        count = random.randint(3, 5)
        for _ in range(count):
            cash_counter += 1
            desc, cat, tag, lo, hi = random.choice(cash_templates)
            amt = rand_amount(lo, hi)
            txn = CashTransaction(
                id=f"demo-cash-{cash_counter:04d}",
                date=rand_date_in_month(year, month),
                provider="cash",
                account_name="Petty Cash",
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
        base_growth = cumulative_deposits * (1 + 0.085 / 12) ** months_elapsed / (
            (1 + 0.085 / 12) ** months_elapsed
            if months_elapsed > 0
            else 1
        )
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
    bond_created = START_DATE + timedelta(days=30)
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
    """Create monthly budgets for last 3 months + project budget."""
    monthly_budgets = [
        ("Total Budget", 28000, "Total Budget", None),
        ("Food Budget", 5000, "Food", None),
        ("Transportation Budget", 1800, "Transportation", None),
        ("Household Budget", 8000, "Household", None),
        ("Entertainment Budget", 800, "Entertainment", None),
        ("Health Budget", 600, "Health", None),
        ("Kids Budget", 3500, "Kids", None),
        ("Shopping Budget", 2000, "Shopping", None),
    ]

    # Last 3 months before REFERENCE_DATE
    ref = REFERENCE_DATE
    budget_months = []
    current = ref
    for _ in range(3):
        # Go to previous month
        current = current.replace(day=1) - timedelta(days=1)
        budget_months.append((current.year, current.month))
    # Also include the current month
    budget_months.append((ref.year, ref.month))
    # Sort chronologically
    budget_months.sort()
    # Take last 3
    budget_months = budget_months[-3:]

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

    # Project budget
    session.add(BudgetRule(
        name="Home Renovation",
        amount=30000,
        category="Home Renovation",
        tags="Materials;Labor;Furniture",
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

    session.flush()


def create_bank_balance(session):
    """Create bank balance record."""
    session.add(BankBalance(
        provider="hapoalim",
        account_name="Main Account",
        balance=85000.0,
        prior_wealth_amount=50000.0,
        last_scrape_update=(REFERENCE_DATE - timedelta(days=1)).isoformat(),
    ))
    session.flush()


def create_cash_balance(session):
    """Create cash balance record."""
    session.add(CashBalance(
        account_name="Petty Cash",
        balance=520.0,
        prior_wealth_amount=1000.0,
        last_manual_update=(REFERENCE_DATE - timedelta(days=7)).isoformat(),
    ))
    session.flush()


def create_pending_refunds(session, cc_txns, bank_txns):
    """Create pending refund records covering all statuses for demo testing.

    Creates:
    1. Pending refund (no links) - jacket return
    2. Partial refund (one link, not fully covered) - electronics partial return
    3. Resolved refund (fully linked) - duplicate charge
    4. Closed refund (user accepted partial) - restaurant dispute
    """
    # 1. Pending refund: recent shopping item, no links
    recent_shopping = [
        t for t in cc_txns
        if t.category == "Shopping" and t.tag == "Online" and t.type == "normal"
        and t.amount < -100
    ]
    if recent_shopping:
        source_txn = recent_shopping[-1]
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
        and t.amount < -200
    ]
    if electronics:
        source_txn = electronics[-1]
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
        and t.amount < -100 and t not in recent_shopping
    ]
    if resolved_shopping:
        source_txn = resolved_shopping[-1]
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
        and t.amount < -150
    ]
    if restaurant:
        source_txn = restaurant[-1]
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

    session.flush()


def create_scraping_history(session):
    """Create 5 scraping history records."""
    now = datetime.now()
    recent = REFERENCE_DATE - timedelta(days=1)
    older = REFERENCE_DATE - timedelta(days=21)

    # 3 recent successful scrapes
    session.add(ScrapingHistory(
        service_name="banks",
        provider_name="hapoalim",
        account_name="Main Account",
        date=datetime(recent.year, recent.month, recent.day, 8, 30, 0).isoformat(),
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
        untagged_txns = generate_untagged_transactions(session, monthly_cc_totals)

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

        session.commit()
        print("\nDemo database created successfully!")

        # Print summary counts
        print("\n--- Row Counts ---")
        tables = [
            "bank_transactions",
            "credit_card_transactions",
            "cash_transactions",
            "manual_investment_transactions",
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
