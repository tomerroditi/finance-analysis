"""Property tests for the savings-goal engine: random households, every invariant.

Hand-written cases only cover the stories someone thought of. These generate
seeded random households — salaries, spending, investment deposits and
withdrawals, gifts, card purchases billed from the bank — and random goals of
every kind (plain, capped, saved-into, spending, investment, funded
investment, with and without target dates and opening balances), then put
them through random edits: close, reopen, reorder, retarget, move the start,
cap, delete, link and unlink transactions, set a spending rule, switch kind.

After every step the engine must:

- agree with itself: a full rebuild and a plain read report the same goals;
- add up: each goal's history bars sum to what its card says it received;
- stay sane: nothing a goal holds or owes is negative, and nothing is funded
  past its target except money its own bills consumed;
- match the bank: free cash plus everything earmarked is exactly the money in
  the tracked accounts (a manual investment's deposits and its prior wealth
  cancel, as they do in net worth).

Every one of these failed at least once — on real data or on one of these
households — before the engine was fixed.
"""

import random

import pytest
from sqlalchemy import text

from backend.errors import ValidationException
from backend.models.bank_balance import BankBalance
from backend.models.investment import Investment
from backend.models.transaction import (
    BankTransaction,
    CreditCardTransaction,
    ManualInvestmentTransaction,
)
from backend.services.savings_goals import SavingsGoalService
from tests.backend.unit.services.test_savings_goal_allocation import _month_str

EPS = 0.05
GOAL_KINDS = ("plain", "capped", "saved", "spend", "invest", "funded")
EDITS = (
    "close",
    "reopen",
    "reorder",
    "target",
    "start",
    "delete",
    "cap",
    "link",
    "unlink",
    "spend",
    "kind",
)


def _bank_row(db, n, month, amount, category, tag, day):
    """Add one bank transaction."""
    db.add(
        BankTransaction(
            id=f"f{n}",
            date=f"{month}-{day:02d}",
            provider="TestBank",
            account_name="Main",
            description="fuzz",
            amount=amount,
            category=category,
            tag=tag,
            source="bank_transactions",
            type="normal",
            status="completed",
        )
    )


def _household(db, rnd):
    """Seed fifteen months of random cash flow; return the months and the bank total."""
    opening = rnd.choice([0, 5000, 20000, 60000])
    db.add(
        BankBalance(
            provider="TestBank",
            account_name="Main",
            balance=0,
            prior_wealth_amount=opening,
        )
    )
    total = opening
    n = 0
    months = [_month_str(k) for k in range(14, -1, -1)]
    for month in months:
        rows = [
            (rnd.randint(5000, 15000), "Salary", None),
            (-rnd.randint(2000, 16000), "Food", None),
        ]
        if rnd.random() < 0.4:
            tag = rnd.choice(["Pakam", "Stocks"])
            rows.append((-rnd.randint(500, 20000), "Investments", tag))
        if rnd.random() < 0.2:
            rows.append((rnd.randint(500, 15000), "Investments", "Pakam"))
        if rnd.random() < 0.25:
            rows.append((rnd.randint(1000, 40000), "Other Income", "Gift"))
        if rnd.random() < 0.25:
            rows.append((-rnd.randint(500, 20000), "Wedding", None))
        if rnd.random() < 0.15:
            rows.append((rnd.randint(1000, 30000), "Other Income", "Kick"))
        if rnd.random() < 0.4:
            # A card purchase, billed from the bank in the same month.
            spend = -rnd.randint(300, 9000)
            n += 1
            db.add(
                CreditCardTransaction(
                    id=f"c{n}",
                    date=f"{month}-05",
                    provider="TestCard",
                    account_name="Card",
                    description="fuzz",
                    amount=float(spend),
                    category=rnd.choice(["Wedding", "Food"]),
                    source="credit_card_transactions",
                    type="normal",
                )
            )
            rows.append((spend, "Credit Cards", None))
        for amount, category, tag in rows:
            n += 1
            _bank_row(db, n, month, float(amount), category, tag, rnd.randint(1, 27))
            total += amount
    if rnd.random() < 0.5:
        # A manually tracked investment: its deposits and the prior wealth that
        # paid for them, the balanced pair the net-worth chart reads.
        deposits = [rnd.randint(1000, 20000) for _ in range(rnd.randint(1, 4))]
        for i, amount in enumerate(deposits):
            db.add(
                ManualInvestmentTransaction(
                    id=f"m{i}",
                    date=f"{rnd.choice(months)}-12",
                    provider="manual",
                    account_name="Gemel",
                    description="fuzz",
                    amount=float(-amount),
                    category="Investments",
                    tag="Gemel",
                    source="manual_investment_transactions",
                    type="normal",
                )
            )
        db.add(
            Investment(
                category="Investments",
                tag="Gemel",
                type="pension",
                name="Gemel",
                created_date=f"{months[0]}-01",
                prior_wealth_amount=float(sum(deposits)),
            )
        )
    db.commit()
    return months, total


def _goals(service, rnd, months):
    """Create one to five random goals of every kind."""
    taken = set()
    for i in range(rnd.randint(1, 5)):
        kind = rnd.choice(GOAL_KINDS)
        start = rnd.choice(months[:-1])
        fields = {
            "name": f"G{i}-{kind}",
            "target_amount": float(rnd.choice([3000, 10000, 40000, 120000])),
            "start_month": start,
        }
        if rnd.random() < 0.5:
            end = min(len(months) - 1, months.index(start) + rnd.randint(0, 10))
            fields["target_date"] = f"{months[end]}-28"
        if kind == "capped":
            fields["monthly_cap"] = float(rnd.choice([500, 2000]))
        # One income can feed only one goal, and one spending rule one goal.
        if kind == "saved" and "income" not in taken:
            taken |= {"income", "spend"}
            fields.update(
                contribution_category="Other Income",
                contribution_tags="Gift",
                utilization_category="Wedding",
            )
        elif kind == "spend" and "spend" not in taken:
            taken.add("spend")
            fields["utilization_category"] = "Wedding"
        if kind in ("invest", "funded"):
            fields.update(kind="investment", contribution_category="Investments")
        if kind == "funded" and "kick" not in taken:
            taken.add("kick")
            fields.update(funding_category="Other Income", funding_tags="Kick")
        if rnd.random() < 0.2 and fields.get("kind") != "investment":
            fields["opening_balance"] = float(rnd.choice([1000, 5000]))
        service.create(**fields)


def _edit(db, service, rnd, months):
    """Apply one random edit and name it; refusals the engine raises on purpose are fine."""
    goals = service.get_all()
    if not goals:
        return "none"
    goal = rnd.choice(goals)
    op = rnd.choice(EDITS)
    open_cash = not goal["is_closed"] and goal["kind"] == "cash"
    try:
        if op == "close" and not goal["is_closed"]:
            service.close(goal["id"])
        elif op == "reopen" and goal["is_closed"]:
            service.reopen(goal["id"])
        elif op == "reorder":
            ids = [g["id"] for g in goals]
            rnd.shuffle(ids)
            service.reorder(ids)
        elif op == "target" and not goal["is_closed"]:
            service.update(goal["id"], target_amount=float(rnd.choice([2000, 15000, 80000])))
        elif op == "start" and not goal["is_closed"]:
            service.update(goal["id"], start_month=rnd.choice(months[:-1]))
        elif op == "cap" and open_cash and not goal["contribution_category"]:
            service.update(goal["id"], monthly_cap=float(rnd.choice([300, 3000])))
        elif op == "delete":
            service.delete(goal["id"])
        elif op == "link" and open_cash:
            # A bill paid out of the goal, or a gift given to it. (A transfer
            # out linked as a contribution moves money to savings the bank
            # no longer holds, so it would break the bank check by design.)
            link_type = rnd.choice(["utilization", "contribution"])
            categories = (
                "('Wedding', 'Food')" if link_type == "utilization" else "('Other Income')"
            )
            ids = [
                row[0]
                for row in db.execute(
                    text(
                        "select unique_id from bank_transactions "
                        f"where category in {categories}"
                    )
                ).fetchall()
            ]
            if ids:
                service.link_transaction(
                    goal_id=goal["id"],
                    source_type="transaction",
                    source_id=rnd.choice(ids),
                    source_table="bank_transactions",
                    link_type=link_type,
                )
        elif op == "unlink":
            links = service.repo.get_links()
            if not links.empty:
                service.unlink_transaction(int(rnd.choice(list(links["id"]))))
        elif op == "spend" and open_cash:
            service.set_spending_link(goal["id"], rnd.choice(["Wedding", "Food", None]))
        elif op == "kind" and not goal["is_closed"]:
            kind = "investment" if goal["kind"] == "cash" else "cash"
            service.update(goal["id"], kind=kind)
    except ValidationException:
        pass
    return f"{op} {goal['name']}"


def _violations(db, service, bank_total):
    """Return every invariant the engine breaks right now."""
    service.rebuild()
    rebuilt = service.get_all()
    rebuilt_pool = service.get_free_cash()
    read = SavingsGoalService(db).get_all()
    pool = SavingsGoalService(db).get_free_cash()
    problems = []
    for x, y in zip(rebuilt, read, strict=True):
        for key in ("funded", "allocated", "contributed", "utilized", "owed", "to_invest"):
            if abs(x[key] - y[key]) > EPS:
                problems.append(f"rebuild != read: {x['name']} {key} {x[key]} vs {y[key]}")
    if abs(rebuilt_pool["free_cash"] - pool["free_cash"]) > EPS:
        problems.append(f"free cash rebuild {rebuilt_pool['free_cash']} read {pool['free_cash']}")
    months = SavingsGoalService(db).get_timeline(None)["months"]
    for goal in read:
        bars = sum(r["total"] for m in months for r in m["goals"] if r["goal_id"] == goal["id"])
        received = goal["funded"] - goal["opening_balance"]
        if abs(bars - received) > EPS:
            problems.append(f"bars {goal['name']} {bars} vs card {received}")
        for key in ("funded", "available", "to_invest", "owed"):
            if goal[key] < -EPS:
                problems.append(f"negative {key}: {goal['name']} {goal[key]}")
        ceiling = max(goal["target_amount"], goal["opening_balance"], goal["utilized"])
        if goal["funded"] > ceiling + EPS:
            problems.append(f"over target: {goal['name']} {goal['funded']} > {ceiling}")
    # With no goals the pool is not computed at all, so there is nothing to match.
    if pool["has_goals"] and abs(pool["liquid"] - bank_total) > EPS:
        problems.append(f"liquid {pool['liquid']} != bank {bank_total}")
    return problems


class TestRandomHouseholds:
    """Seeded random households keep every invariant through random edits."""

    @pytest.mark.parametrize("seed", range(60))
    def test_every_invariant_holds_through_random_edits(self, db_session, seed):
        """Rebuild equals read, bars equal the card, nothing negative, liquid equals bank."""
        rnd = random.Random(seed)
        service = SavingsGoalService(db_session)
        months, bank_total = _household(db_session, rnd)
        _goals(service, rnd, months)
        problems = _violations(db_session, service, bank_total)
        for step in range(4):
            if problems:
                break
            edit = _edit(db_session, service, rnd, months)
            problems = [
                f"after edit {step} ({edit}): {p}"
                for p in _violations(db_session, service, bank_total)
            ]
        assert not problems, f"seed {seed}:\n" + "\n".join(problems)
