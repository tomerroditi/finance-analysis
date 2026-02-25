"""
Demo data seeder for the Finance Analysis Dashboard.

Generates realistic-looking financial data spanning 14 months to showcase
every feature of the application: transactions, budgets, tagging rules,
investments, pending refunds, bank balances, and scraping history.
"""

import os
import random
import shutil
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from backend.config import AppConfig

from backend.models.bank_balance import BankBalance
from backend.models.budget import BudgetRule
from backend.models.investment import Investment
from backend.models.pending_refund import PendingRefund, RefundLink
from backend.models.scraping import ScrapingHistory
from backend.models.tagging_rules import TaggingRule
from backend.models.transaction import (
    BankTransaction,
    CashTransaction,
    CreditCardTransaction,
    ManualInvestmentTransaction,
    SplitTransaction,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_rng = random.Random(42)  # deterministic seed for reproducibility


def _date_str(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _rand_day(year: int, month: int) -> date:
    """Random day within a given month."""
    if month == 12:
        max_day = 31
    else:
        next_month = date(year, month + 1, 1)
        max_day = (next_month - timedelta(days=1)).day
    return date(year, month, _rng.randint(1, max_day))


# ---------------------------------------------------------------------------
# Transaction templates  (description, amount_range, category, tag)
# ---------------------------------------------------------------------------

_CC_EXPENSES = [
    ("Shufersal Online Delivery", (-800, -150), "Food", "Groceries"),
    ("Rami Levy Supermarket", (-600, -100), "Food", "Groceries"),
    ("Cafe Cafe TLV", (-120, -35), "Food", "Coffee"),
    ("Aroma Espresso Bar", (-80, -25), "Food", "Coffee"),
    ("Japanika Sushi Bar", (-250, -80), "Food", "Restaurants"),
    ("Oshi Oshi Restaurant", (-350, -120), "Food", "Restaurants"),
    ("Netflix Monthly", (-55, -55), "Subscriptions", "Netflix"),
    ("Spotify Premium", (-30, -30), "Subscriptions", "Spotify"),
    ("ChatGPT Plus", (-75, -75), "Subscriptions", "Chat-GPT"),
    ("Disney+ Subscription", (-35, -35), "Subscriptions", "Disney"),
    ("Castro Fashion", (-450, -80), "Shopping", "Clothes"),
    ("ZARA Israel", (-600, -120), "Shopping", "Clothes"),
    ("KSP Electronics", (-2500, -200), "Shopping", "Electronics"),
    ("Bug Electronics Store", (-1500, -150), "Shopping", "Electronics"),
    ("Hot Mobile Monthly", (-120, -80), "Household", "Phone"),
    ("Partner Internet", (-150, -100), "Household", "Internet"),
    ("Paz Gas Station", (-400, -100), "Transportation", "Gas"),
    ("Sonol Gas Station", (-350, -80), "Transportation", "Gas"),
    ("Waze Carpool", (-50, -20), "Transportation", "Taxi"),
    ("Gett Taxi Service", (-120, -30), "Transportation", "Taxi"),
    ("Superpharm Pharmacy", (-200, -30), "Health", "Medications"),
    ("Maccabi Health Clinic", (-150, -35), "Health", "Doctor"),
    ("Cinema City Movie", (-80, -45), "Entertainment", "Movies"),
    ("Habima Theatre", (-250, -120), "Entertainment", "Events"),
    ("Yes Planet IMAX", (-90, -50), "Entertainment", "Movies"),
    ("Steimatzky Books", (-150, -40), "Entertainment", "Books"),
    ("ACE Home Improvement", (-800, -100), "Household", "Home Improvement"),
    ("IKEA Israel", (-2000, -200), "Household", "Furniture"),
    ("Cleaning Lady Monthly", (-500, -300), "Household", "Cleaning Supplies"),
    ("Gift for Birthday", (-400, -100), "Shopping", "Gifts"),
    ("Snack Bar Airport", (-60, -20), "Food", "Snacks"),
    ("Work Lunch Wolt", (-90, -40), "Food", "Work Lunch"),
    ("10bis Work Lunch", (-80, -35), "Food", "Work Lunch"),
    ("Parking Ahuzat HaHof", (-50, -15), "Transportation", "Parking"),
    ("6 Highway Toll", (-30, -15), "Transportation", "Tolls"),
    ("Bird Scooter Ride", (-25, -8), "Transportation", "Scooter"),
    ("IEC Electricity Bill", (-600, -200), "Household", "Electricity"),
    ("Mekorot Water Bill", (-250, -80), "Household", "Water"),
    ("Haircut Dizengoff", (-120, -60), "Other", "Haircut"),
]

_BANK_EXPENSES = [
    ("Mortgage Payment Leumi", (-8500, -8500), "Household", "Mortgage"),
    ("Arnona Municipal Tax", (-1200, -800), "Household", "Rent"),
    ("Home Insurance Policy", (-350, -350), "Household", "Home Insurance"),
    ("Car Insurance Annual", (-4500, -4500), "Transportation", "Car Insurance"),
    ("Car Maintenance Garage", (-2000, -400), "Transportation", "Car Maintenance"),
    ("Bank Commission Monthly", (-30, -15), "Other", "Bank Commisions"),
    ("Kupat Gemel Transfer", (-2000, -2000), "Investments", "Gemel"),
    ("Medical Insurance HMO", (-400, -300), "Health", "Medical Insurance"),
    ("Therapy Session", (-500, -350), "Health", "Therapy"),
    ("Dentist Treatment", (-1200, -200), "Health", "Dentist"),
    ("Loan Repayment Monthly", (-1500, -1500), "Liabilities", "Loans"),
]

_BANK_INCOME = [
    ("Salary - Tech Company Ltd", (18000, 25000), "Salary", None),
    ("Freelance Payment Client", (3000, 8000), "Other Income", None),
    ("Tax Refund", (500, 3000), "Other Income", None),
]

_CC_REFUNDS = [
    ("Refund - ZARA Return", (120, 400), "Shopping", "Clothes"),
    ("Refund - KSP Electronics", (200, 800), "Shopping", "Electronics"),
    ("Refund - Japanika Order", (80, 150), "Food", "Restaurants"),
]


# ---------------------------------------------------------------------------
# Core seeding functions
# ---------------------------------------------------------------------------


def seed_credit_card_transactions(db: Session, start_date: date, end_date: date) -> list:
    """Seed credit card transactions across the date range."""
    transactions = []
    current = date(start_date.year, start_date.month, 1)

    while current <= end_date:
        y, m = current.year, current.month
        # 25-40 CC transactions per month
        count = _rng.randint(25, 40)
        for _ in range(count):
            template = _rng.choice(_CC_EXPENSES)
            desc, (lo, hi), cat, tag = template
            amount = round(_rng.uniform(lo, hi), 2)
            d = _rand_day(y, m)
            txn = CreditCardTransaction(
                id=f"cc-{d.isoformat()}-{_rng.randint(1000,9999)}",
                date=_date_str(d),
                provider="max",
                account_name="Demo Max Card",
                account_number="1234",
                description=desc,
                amount=amount,
                category=cat,
                tag=tag,
                source="credit_cards",
                type="normal",
                status="completed",
            )
            transactions.append(txn)

        # 8-15 transactions on second card
        count2 = _rng.randint(8, 15)
        for _ in range(count2):
            template = _rng.choice(_CC_EXPENSES)
            desc, (lo, hi), cat, tag = template
            amount = round(_rng.uniform(lo, hi), 2)
            d = _rand_day(y, m)
            txn = CreditCardTransaction(
                id=f"cc2-{d.isoformat()}-{_rng.randint(1000,9999)}",
                date=_date_str(d),
                provider="visa cal",
                account_name="Demo Visa Cal",
                account_number="5678",
                description=desc,
                amount=amount,
                category=cat,
                tag=tag,
                source="credit_cards",
                type="normal",
                status="completed",
            )
            transactions.append(txn)

        # 1-2 refunds per month
        refund_count = _rng.randint(1, 2)
        for _ in range(refund_count):
            template = _rng.choice(_CC_REFUNDS)
            desc, (lo, hi), cat, tag = template
            amount = round(_rng.uniform(lo, hi), 2)
            d = _rand_day(y, m)
            txn = CreditCardTransaction(
                id=f"ccr-{d.isoformat()}-{_rng.randint(1000,9999)}",
                date=_date_str(d),
                provider="max",
                account_name="Demo Max Card",
                account_number="1234",
                description=desc,
                amount=amount,
                category=cat,
                tag=tag,
                source="credit_cards",
                type="normal",
                status="completed",
            )
            transactions.append(txn)

        # Advance to next month
        if m == 12:
            current = date(y + 1, 1, 1)
        else:
            current = date(y, m + 1, 1)

    db.add_all(transactions)
    db.commit()
    return transactions


def seed_bank_transactions(db: Session, start_date: date, end_date: date) -> list:
    """Seed bank transactions: salary, expenses, and CC billing."""
    transactions = []
    current = date(start_date.year, start_date.month, 1)

    while current <= end_date:
        y, m = current.year, current.month

        # Salary - 1st or 10th of each month
        salary_day = min(10, 28)
        sal_template = _BANK_INCOME[0]
        desc, (lo, hi), cat, _ = sal_template
        amount = round(_rng.uniform(lo, hi), 2)
        d = date(y, m, salary_day)
        txn = BankTransaction(
            id=f"bk-{d.isoformat()}-sal",
            date=_date_str(d),
            provider="hapoalim",
            account_name="Demo Checking",
            account_number="12-345-678901",
            description=desc,
            amount=amount,
            category=cat,
            tag=None,
            source="banks",
            type="normal",
            status="completed",
        )
        transactions.append(txn)

        # Occasional freelance income (every 2-3 months)
        if _rng.random() < 0.4:
            template = _BANK_INCOME[1]
            desc, (lo, hi), cat, _ = template
            amount = round(_rng.uniform(lo, hi), 2)
            d = _rand_day(y, m)
            txn = BankTransaction(
                id=f"bk-{d.isoformat()}-free-{_rng.randint(100,999)}",
                date=_date_str(d),
                provider="hapoalim",
                account_name="Demo Checking",
                account_number="12-345-678901",
                description=desc,
                amount=amount,
                category=cat,
                tag=None,
                source="banks",
                type="normal",
                status="completed",
            )
            transactions.append(txn)

        # Bank direct debit expenses (3-6 per month)
        expense_count = _rng.randint(3, 6)
        used_templates = _rng.sample(
            _BANK_EXPENSES, min(expense_count, len(_BANK_EXPENSES))
        )
        for template in used_templates:
            desc, (lo, hi), cat, tag = template
            amount = round(_rng.uniform(lo, hi), 2)
            d = _rand_day(y, m)
            txn = BankTransaction(
                id=f"bk-{d.isoformat()}-{_rng.randint(1000,9999)}",
                date=_date_str(d),
                provider="hapoalim",
                account_name="Demo Checking",
                account_number="12-345-678901",
                description=desc,
                amount=amount,
                category=cat,
                tag=tag,
                source="banks",
                type="normal",
                status="completed",
            )
            transactions.append(txn)

        # Credit card bill payments (internal transfers)
        cc_bill_day = date(y, m, min(15, 28))
        for card_name, bill_amount in [
            ("Demo Max Card", round(_rng.uniform(-8000, -3000), 2)),
            ("Demo Visa Cal", round(_rng.uniform(-4000, -1500), 2)),
        ]:
            txn = BankTransaction(
                id=f"bk-{cc_bill_day.isoformat()}-ccbill-{_rng.randint(100,999)}",
                date=_date_str(cc_bill_day),
                provider="hapoalim",
                account_name="Demo Checking",
                account_number="12-345-678901",
                description=f"Credit Card Payment - {card_name}",
                amount=bill_amount,
                category="Ignore",
                tag="Credit Card Bill",
                source="banks",
                type="normal",
                status="completed",
            )
            transactions.append(txn)

        # Advance to next month
        if m == 12:
            current = date(y + 1, 1, 1)
        else:
            current = date(y, m + 1, 1)

    db.add_all(transactions)
    db.commit()
    return transactions


def seed_cash_transactions(db: Session, start_date: date, end_date: date) -> list:
    """Seed a handful of cash transactions."""
    transactions = []
    current = date(start_date.year, start_date.month, 1)

    cash_items = [
        ("ATM Withdrawal", (-500, -200), "Other", "ATM"),
        ("Shuk HaCarmel Market", (-150, -40), "Food", "Groceries"),
        ("Street Food Falafel", (-40, -15), "Food", "Snacks"),
        ("Taxi Cash Payment", (-80, -30), "Transportation", "Taxi"),
        ("Tip at Restaurant", (-50, -20), "Food", "Restaurants"),
    ]

    while current <= end_date:
        y, m = current.year, current.month
        count = _rng.randint(2, 5)
        for _ in range(count):
            template = _rng.choice(cash_items)
            desc, (lo, hi), cat, tag = template
            amount = round(_rng.uniform(lo, hi), 2)
            d = _rand_day(y, m)
            txn = CashTransaction(
                id=f"cash-{d.isoformat()}-{_rng.randint(1000,9999)}",
                date=_date_str(d),
                provider="cash",
                account_name="Cash Wallet",
                description=desc,
                amount=amount,
                category=cat,
                tag=tag,
                source="cash",
                type="normal",
                status="completed",
            )
            transactions.append(txn)

        if m == 12:
            current = date(y + 1, 1, 1)
        else:
            current = date(y, m + 1, 1)

    db.add_all(transactions)
    db.commit()
    return transactions


def seed_manual_investment_transactions(
    db: Session, start_date: date, end_date: date
) -> list:
    """Seed manual investment transactions for tracking deposits."""
    transactions = []

    inv_items = [
        ("Monthly Kupat Gemel Deposit", (-2000, -2000), "Investments", "Gemel"),
        ("Stock Purchase - TASE", (-5000, -1000), "Investments", "Stocks"),
        ("Pakam Bank Deposit", (-10000, -3000), "Investments", "Pakam"),
    ]

    current = date(start_date.year, start_date.month, 1)
    while current <= end_date:
        y, m = current.year, current.month

        # Gemel every month
        d = date(y, m, min(5, 28))
        txn = ManualInvestmentTransaction(
            id=f"inv-{d.isoformat()}-gemel",
            date=_date_str(d),
            provider="manual",
            account_name="Investment Tracking",
            description="Monthly Kupat Gemel Deposit",
            amount=-2000.0,
            category="Investments",
            tag="Gemel",
            source="manual_investments",
            type="normal",
            status="completed",
        )
        transactions.append(txn)

        # Occasional stock purchases
        if _rng.random() < 0.3:
            template = inv_items[1]
            desc, (lo, hi), cat, tag = template
            amount = round(_rng.uniform(lo, hi), 2)
            d = _rand_day(y, m)
            txn = ManualInvestmentTransaction(
                id=f"inv-{d.isoformat()}-stock-{_rng.randint(100,999)}",
                date=_date_str(d),
                provider="manual",
                account_name="Investment Tracking",
                description=desc,
                amount=amount,
                category=cat,
                tag=tag,
                source="manual_investments",
                type="normal",
                status="completed",
            )
            transactions.append(txn)

        if m == 12:
            current = date(y + 1, 1, 1)
        else:
            current = date(y, m + 1, 1)

    db.add_all(transactions)
    db.commit()
    return transactions


def seed_split_transactions(db: Session, cc_transactions: list) -> list:
    """Create split transactions from some CC parent transactions."""
    splits = []
    # Pick a few larger transactions to split
    splittable = [
        t for t in cc_transactions
        if t.amount < -300 and t.category == "Shopping"
    ]
    to_split = _rng.sample(splittable, min(4, len(splittable)))

    for parent in to_split:
        parent.type = "split_parent"

        total = abs(parent.amount)
        split1_amount = round(total * _rng.uniform(0.3, 0.6), 2)
        split2_amount = round(total - split1_amount, 2)

        split_categories = [
            ("Shopping", "Gifts"),
            ("Household", "Home Improvement"),
            ("Entertainment", "Video Games"),
        ]
        cat1, tag1 = _rng.choice(split_categories)
        cat2, tag2 = _rng.choice(
            [c for c in split_categories if c != (cat1, tag1)]
        )

        s1 = SplitTransaction(
            transaction_id=parent.unique_id,
            source="credit_cards",
            amount=-split1_amount,
            category=cat1,
            tag=tag1,
        )
        s2 = SplitTransaction(
            transaction_id=parent.unique_id,
            source="credit_cards",
            amount=-split2_amount,
            category=cat2,
            tag=tag2,
        )
        splits.extend([s1, s2])

    db.add_all(splits)
    db.commit()
    return splits


def seed_budget_rules(db: Session, end_date: date) -> list:
    """Create monthly and project budget rules."""
    rules = []

    monthly_budgets = [
        ("Total Budget", 15000, None, None),
        ("Food Budget", 3500, "Food", None),
        ("Groceries", 2000, "Food", "Groceries"),
        ("Restaurants & Coffee", 1500, "Food", "Restaurants;Coffee"),
        ("Transportation", 2000, "Transportation", None),
        ("Shopping", 2500, "Shopping", None),
        ("Entertainment", 1000, "Entertainment", None),
        ("Subscriptions", 250, "Subscriptions", None),
        ("Health", 1500, "Health", None),
        ("Household", 3000, "Household", None),
    ]

    # Create budget rules for last 3 months
    for months_back in range(3):
        d = end_date.replace(day=1)
        for _ in range(months_back):
            if d.month == 1:
                d = d.replace(year=d.year - 1, month=12)
            else:
                d = d.replace(month=d.month - 1)

        for name, amount, category, tags in monthly_budgets:
            # Slight variation in older months
            variation = 1.0 if months_back == 0 else _rng.uniform(0.9, 1.1)
            rule = BudgetRule(
                name=name,
                amount=round(amount * variation, 2),
                category=category,
                tags=tags,
                year=d.year,
                month=d.month,
            )
            rules.append(rule)

    # Project budgets (month=NULL, year=NULL)
    project_budgets = [
        ("New Apartment", 50000, "New Apartment", "Furniture;Home Improvement"),
        ("Wedding", 80000, "Wedding", None),
    ]

    for name, amount, category, tags in project_budgets:
        rule = BudgetRule(
            name=name,
            amount=amount,
            category=category,
            tags=tags,
            year=None,
            month=None,
        )
        rules.append(rule)

    db.add_all(rules)
    db.commit()
    return rules


def seed_tagging_rules(db: Session) -> list:
    """Create tagging rules showcasing different condition types."""
    rules = []

    rule_definitions = [
        {
            "name": "Supermarket Auto-Tag",
            "conditions": {
                "type": "OR",
                "subconditions": [
                    {
                        "type": "CONDITION",
                        "field": "description",
                        "operator": "contains",
                        "value": "Shufersal",
                    },
                    {
                        "type": "CONDITION",
                        "field": "description",
                        "operator": "contains",
                        "value": "Rami Levy",
                    },
                ],
            },
            "category": "Food",
            "tag": "Groceries",
        },
        {
            "name": "Coffee Shops",
            "conditions": {
                "type": "OR",
                "subconditions": [
                    {
                        "type": "CONDITION",
                        "field": "description",
                        "operator": "contains",
                        "value": "Cafe",
                    },
                    {
                        "type": "CONDITION",
                        "field": "description",
                        "operator": "contains",
                        "value": "Aroma",
                    },
                    {
                        "type": "CONDITION",
                        "field": "description",
                        "operator": "contains",
                        "value": "Coffee",
                    },
                ],
            },
            "category": "Food",
            "tag": "Coffee",
        },
        {
            "name": "Gas Stations",
            "conditions": {
                "type": "OR",
                "subconditions": [
                    {
                        "type": "CONDITION",
                        "field": "description",
                        "operator": "contains",
                        "value": "Paz Gas",
                    },
                    {
                        "type": "CONDITION",
                        "field": "description",
                        "operator": "contains",
                        "value": "Sonol Gas",
                    },
                    {
                        "type": "CONDITION",
                        "field": "description",
                        "operator": "contains",
                        "value": "Delek",
                    },
                ],
            },
            "category": "Transportation",
            "tag": "Gas",
        },
        {
            "name": "Large Purchases Alert",
            "conditions": {
                "type": "AND",
                "subconditions": [
                    {
                        "type": "CONDITION",
                        "field": "amount",
                        "operator": "lt",
                        "value": "-1000",
                    },
                    {
                        "type": "CONDITION",
                        "field": "service",
                        "operator": "equals",
                        "value": "credit_cards",
                    },
                ],
            },
            "category": "Shopping",
            "tag": "Electronics",
        },
        {
            "name": "Streaming Services",
            "conditions": {
                "type": "OR",
                "subconditions": [
                    {
                        "type": "CONDITION",
                        "field": "description",
                        "operator": "contains",
                        "value": "Netflix",
                    },
                    {
                        "type": "CONDITION",
                        "field": "description",
                        "operator": "contains",
                        "value": "Disney",
                    },
                    {
                        "type": "CONDITION",
                        "field": "description",
                        "operator": "contains",
                        "value": "Spotify",
                    },
                ],
            },
            "category": "Subscriptions",
            "tag": "Netflix",
        },
        {
            "name": "Credit Card Bills",
            "conditions": {
                "type": "AND",
                "subconditions": [
                    {
                        "type": "CONDITION",
                        "field": "description",
                        "operator": "contains",
                        "value": "Credit Card Payment",
                    },
                    {
                        "type": "CONDITION",
                        "field": "service",
                        "operator": "equals",
                        "value": "banks",
                    },
                ],
            },
            "category": "Ignore",
            "tag": "Credit Card Bill",
        },
    ]

    for rule_def in rule_definitions:
        rule = TaggingRule(
            name=rule_def["name"],
            conditions=rule_def["conditions"],
            category=rule_def["category"],
            tag=rule_def["tag"],
        )
        rules.append(rule)

    db.add_all(rules)
    db.commit()
    return rules


def seed_investments(db: Session, start_date: date, end_date: date) -> list:
    """Create investment tracking records."""
    investments = []

    investment_records = [
        {
            "category": "Investments",
            "tag": "Gemel",
            "type": "Pension Fund",
            "name": "Altshuler Shaham Gemel",
            "interest_rate": 7.2,
            "interest_rate_type": "variable",
            "commission_management": 0.5,
            "commission_deposit": 0.0,
            "commission_withdrawal": 0.0,
            "liquidity_date": None,
            "maturity_date": _date_str(
                date(end_date.year + 30, end_date.month, 1)
            ),
            "is_closed": 0,
            "created_date": _date_str(start_date),
            "notes": "Long-term pension savings. Employer matching 6%.",
        },
        {
            "category": "Investments",
            "tag": "Stocks",
            "type": "ETF",
            "name": "S&P 500 Index Fund (TASE)",
            "interest_rate": None,
            "interest_rate_type": "variable",
            "commission_management": 0.15,
            "commission_deposit": 5.0,
            "commission_withdrawal": 5.0,
            "liquidity_date": _date_str(end_date),
            "maturity_date": None,
            "is_closed": 0,
            "created_date": _date_str(start_date),
            "notes": "Monthly DCA into S&P 500 tracker on TASE.",
        },
        {
            "category": "Investments",
            "tag": "Pakam",
            "type": "Term Deposit",
            "name": "Hapoalim Pakam 12M",
            "interest_rate": 4.5,
            "interest_rate_type": "fixed",
            "commission_management": 0.0,
            "commission_deposit": 0.0,
            "commission_withdrawal": 50.0,
            "liquidity_date": _date_str(
                date(end_date.year, end_date.month, 1) + timedelta(days=180)
            ),
            "maturity_date": _date_str(
                date(end_date.year + 1, end_date.month, 1)
            ),
            "is_closed": 0,
            "created_date": _date_str(
                start_date + timedelta(days=60)
            ),
            "notes": "12-month fixed deposit at 4.5% annual.",
        },
        {
            "category": "Investments",
            "tag": "Real Estate",
            "type": "REIT",
            "name": "Azrieli Group REIT",
            "interest_rate": 3.8,
            "interest_rate_type": "variable",
            "commission_management": 0.3,
            "commission_deposit": 15.0,
            "commission_withdrawal": 15.0,
            "liquidity_date": _date_str(end_date),
            "maturity_date": None,
            "is_closed": 0,
            "created_date": _date_str(
                start_date + timedelta(days=30)
            ),
            "notes": "Diversification into Israeli real estate via REIT.",
        },
        {
            "category": "Investments",
            "tag": "Stocks",
            "type": "Individual Stock",
            "name": "Wix.com Shares",
            "interest_rate": None,
            "interest_rate_type": "variable",
            "commission_management": 0.0,
            "commission_deposit": 8.0,
            "commission_withdrawal": 8.0,
            "liquidity_date": _date_str(end_date),
            "maturity_date": None,
            "is_closed": 1,
            "created_date": _date_str(start_date),
            "closed_date": _date_str(
                end_date - timedelta(days=60)
            ),
            "notes": "Sold position after reaching target price.",
        },
    ]

    for record in investment_records:
        inv = Investment(**record)
        investments.append(inv)

    db.add_all(investments)
    db.commit()
    return investments


def seed_pending_refunds(db: Session, cc_transactions: list) -> list:
    """Create pending refund records with various statuses."""
    refunds = []
    links = []

    # Find some expense transactions to mark as pending refund
    refundable = [
        t for t in cc_transactions
        if t.amount < -100 and t.category in ("Shopping", "Food")
        and t.type == "normal"
    ]

    if len(refundable) < 3:
        return []

    selected = _rng.sample(refundable, 3)

    # Pending refund (no links yet)
    pr1 = PendingRefund(
        source_type="transaction",
        source_id=selected[0].unique_id,
        source_table="credit_cards",
        expected_amount=abs(selected[0].amount),
        status="pending",
        notes="Requested refund for defective item. Waiting for store response.",
    )
    refunds.append(pr1)

    # Partial refund (one link, not fully resolved)
    pr2 = PendingRefund(
        source_type="transaction",
        source_id=selected[1].unique_id,
        source_table="credit_cards",
        expected_amount=abs(selected[1].amount),
        status="partial",
        notes="Partial refund received. Remaining amount expected next billing cycle.",
    )
    refunds.append(pr2)

    # Resolved refund (fully linked)
    pr3 = PendingRefund(
        source_type="transaction",
        source_id=selected[2].unique_id,
        source_table="credit_cards",
        expected_amount=abs(selected[2].amount),
        status="resolved",
        notes="Full refund received.",
    )
    refunds.append(pr3)

    db.add_all(refunds)
    db.flush()

    # Find refund transactions to link
    refund_txns = [
        t for t in cc_transactions if t.amount > 0
    ]

    if len(refund_txns) >= 2:
        # Partial link for pr2
        link1 = RefundLink(
            pending_refund_id=pr2.id,
            refund_transaction_id=refund_txns[0].unique_id,
            refund_source="credit_cards",
            amount=round(abs(selected[1].amount) * 0.5, 2),
        )
        links.append(link1)

        # Full link for pr3
        link2 = RefundLink(
            pending_refund_id=pr3.id,
            refund_transaction_id=refund_txns[1].unique_id,
            refund_source="credit_cards",
            amount=abs(selected[2].amount),
        )
        links.append(link2)

    db.add_all(links)
    db.commit()
    return refunds


def seed_bank_balances(db: Session, end_date: date) -> list:
    """Create bank balance snapshots."""
    balances = []

    balance_records = [
        {
            "provider": "hapoalim",
            "account_name": "Demo Checking",
            "balance": 45230.50,
            "prior_wealth_amount": 30000.0,
            "last_manual_update": _date_str(end_date - timedelta(days=2)),
            "last_scrape_update": _date_str(end_date - timedelta(days=1)),
        },
        {
            "provider": "leumi",
            "account_name": "Demo Savings",
            "balance": 125000.00,
            "prior_wealth_amount": 100000.0,
            "last_manual_update": _date_str(end_date - timedelta(days=5)),
            "last_scrape_update": None,
        },
    ]

    for record in balance_records:
        bal = BankBalance(**record)
        balances.append(bal)

    db.add_all(balances)
    db.commit()
    return balances


def seed_scraping_history(db: Session, start_date: date, end_date: date) -> list:
    """Create scraping history entries showing successful and failed attempts."""
    history = []

    accounts = [
        ("credit_cards", "max", "Demo Max Card"),
        ("credit_cards", "visa cal", "Demo Visa Cal"),
        ("banks", "hapoalim", "Demo Checking"),
    ]

    # Generate ~2 scrape entries per account per month
    current = date(start_date.year, start_date.month, 1)
    while current <= end_date:
        y, m = current.year, current.month

        for service, provider, account in accounts:
            # First scrape of the month - usually success
            d = _rand_day(y, m)
            scrape_time = datetime(y, m, d.day, _rng.randint(7, 10), _rng.randint(0, 59))
            status = "SUCCESS" if _rng.random() < 0.9 else "FAILED"
            entry = ScrapingHistory(
                service_name=service,
                provider_name=provider,
                account_name=account,
                date=scrape_time.strftime("%Y-%m-%d %H:%M:%S"),
                status=status,
                start_date=_date_str(date(y, m, 1)),
                error_message="Connection timeout after 300s" if status == "FAILED" else None,
            )
            history.append(entry)

            # Second scrape - later in month
            d2 = _rand_day(y, m)
            while d2 <= d:
                d2 = _rand_day(y, m)
                if d2.day == d.day:
                    d2 = d2.replace(day=min(d.day + _rng.randint(5, 15), 28))
            scrape_time2 = datetime(
                d2.year, d2.month, d2.day,
                _rng.randint(18, 22), _rng.randint(0, 59)
            )
            entry2 = ScrapingHistory(
                service_name=service,
                provider_name=provider,
                account_name=account,
                date=scrape_time2.strftime("%Y-%m-%d %H:%M:%S"),
                status="SUCCESS",
                start_date=_date_str(d),
            )
            history.append(entry2)

        if m == 12:
            current = date(y + 1, 1, 1)
        else:
            current = date(y, m + 1, 1)

    # Add one CANCELED entry for demo
    cancel_date = end_date - timedelta(days=3)
    history.append(
        ScrapingHistory(
            service_name="banks",
            provider_name="hapoalim",
            account_name="Demo Checking",
            date=datetime(
                cancel_date.year, cancel_date.month, cancel_date.day, 9, 30
            ).strftime("%Y-%m-%d %H:%M:%S"),
            status="CANCELED",
            start_date=_date_str(cancel_date - timedelta(days=30)),
        )
    )

    db.add_all(history)
    db.commit()
    return history


# Some untagged transactions to demonstrate the auto-tagging feature
def seed_untagged_transactions(db: Session, end_date: date) -> list:
    """Add a handful of untagged transactions for the current month."""
    transactions = []

    untagged_items = [
        "Payment 4521 Unknown Merchant",
        "Transfer REFERENCE 88712",
        "POS Purchase Dizengoff",
        "Online Payment PAYPAL *STORE",
        "Direct Debit Ref 9912",
    ]

    y, m = end_date.year, end_date.month
    for desc in untagged_items:
        d = _rand_day(y, m)
        amount = round(_rng.uniform(-500, -30), 2)
        txn = CreditCardTransaction(
            id=f"cc-untag-{d.isoformat()}-{_rng.randint(1000,9999)}",
            date=_date_str(d),
            provider="max",
            account_name="Demo Max Card",
            account_number="1234",
            description=desc,
            amount=amount,
            category=None,
            tag=None,
            source="credit_cards",
            type="normal",
            status="completed",
        )
        transactions.append(txn)

    db.add_all(transactions)
    db.commit()
    return transactions


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def _setup_demo_config_files() -> None:
    """Copy demo categories and icons YAML files into the demo environment."""
    config = AppConfig()
    demo_dir = os.path.dirname(os.path.abspath(__file__))

    src_categories = os.path.join(demo_dir, "demo_categories.yaml")
    src_icons = os.path.join(demo_dir, "demo_categories_icons.yaml")

    dst_categories = config.get_categories_path()
    dst_icons = config.get_categories_icons_path()

    os.makedirs(os.path.dirname(dst_categories), exist_ok=True)

    if os.path.exists(src_categories):
        shutil.copy2(src_categories, dst_categories)
    if os.path.exists(src_icons):
        shutil.copy2(src_icons, dst_icons)


def seed_all_demo_data(db: Session) -> dict:
    """
    Seed all demo data into the database.

    Parameters
    ----------
    db : Session
        SQLAlchemy database session (should be pointed at the demo DB).

    Returns
    -------
    dict
        Summary of seeded records.
    """
    today = date.today()
    # 14 months of data: from ~14 months ago to current month
    start_date = date(today.year - 1, today.month, 1)
    if today.month == 1:
        start_date = date(today.year - 2, 12, 1)
    end_date = today

    summary = {}

    # Set up demo YAML config files (categories, icons)
    _setup_demo_config_files()

    # Transactions
    cc_txns = seed_credit_card_transactions(db, start_date, end_date)
    summary["credit_card_transactions"] = len(cc_txns)

    bank_txns = seed_bank_transactions(db, start_date, end_date)
    summary["bank_transactions"] = len(bank_txns)

    cash_txns = seed_cash_transactions(db, start_date, end_date)
    summary["cash_transactions"] = len(cash_txns)

    inv_txns = seed_manual_investment_transactions(db, start_date, end_date)
    summary["manual_investment_transactions"] = len(inv_txns)

    # Splits (needs CC transactions to exist with IDs)
    splits = seed_split_transactions(db, cc_txns)
    summary["split_transactions"] = len(splits)

    # Untagged transactions for demo of auto-tagging
    untagged = seed_untagged_transactions(db, end_date)
    summary["untagged_transactions"] = len(untagged)

    # Budget rules
    budget_rules = seed_budget_rules(db, end_date)
    summary["budget_rules"] = len(budget_rules)

    # Tagging rules
    tagging_rules = seed_tagging_rules(db)
    summary["tagging_rules"] = len(tagging_rules)

    # Investments
    investments = seed_investments(db, start_date, end_date)
    summary["investments"] = len(investments)

    # Pending refunds (needs CC transactions with IDs)
    pending = seed_pending_refunds(db, cc_txns)
    summary["pending_refunds"] = len(pending)

    # Bank balances
    balances = seed_bank_balances(db, end_date)
    summary["bank_balances"] = len(balances)

    # Scraping history
    scrape_history = seed_scraping_history(db, start_date, end_date)
    summary["scraping_history"] = len(scrape_history)

    return summary
