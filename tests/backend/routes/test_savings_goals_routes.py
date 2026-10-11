"""Endpoint tests for the savings goals API."""

from datetime import date

import pytest

from tests.backend.unit.services.savings_goal_helpers import (
    add_txn,
    month_str,
    seed_liquid,
)


def _create(test_client, **body):
    """POST a goal and return the created row from the refreshed list."""
    res = test_client.post("/api/savings-goals/", json=body)
    assert res.status_code == 200, res.text
    return next(g for g in res.json() if g["name"] == body["name"])


def _goal(goals: list[dict], goal_id: int) -> dict:
    """Pick one goal out of a returned goal list."""
    return next(g for g in goals if g["id"] == goal_id)


class TestSavingsGoalsRoutes:
    """CRUD + progress-metric tests for /api/savings-goals."""

    def test_empty_list(self, test_client):
        """A fresh DB returns an empty goals list."""
        res = test_client.get("/api/savings-goals/")
        assert res.status_code == 200
        assert res.json() == []

    def test_create_with_initial_amount(self, test_client):
        """The initial amount is the goal's first entry and counts as saved."""
        goal = _create(
            test_client, name="Vacation", target_amount=10000, initial_amount=2500
        )
        assert goal["progress_pct"] == 25.0
        assert goal["remaining"] == 7500.0
        assert goal["added"] == 2500.0
        assert goal["available"] == 2500.0
        assert goal["is_achieved"] is False
        assert [(e["amount"], e["source"]) for e in goal["entries"]] == [
            (2500.0, "manual")
        ]

        listed = test_client.get("/api/savings-goals/").json()
        assert len(listed) == 1

    def test_create_rejects_non_positive_target(self, test_client):
        """A target of zero or less fails request validation."""
        res = test_client.post(
            "/api/savings-goals/", json={"name": "Bad", "target_amount": 0}
        )
        assert res.status_code == 422

    def test_create_rejects_a_negative_initial_amount(self, test_client):
        """A goal cannot start owing money."""
        res = test_client.post(
            "/api/savings-goals/",
            json={"name": "Bad", "target_amount": 100, "initial_amount": -1},
        )
        assert res.status_code == 422

    def test_monthly_needed_with_target_date(self, test_client):
        """A target date yields a monthly_needed contribution figure."""
        future = f"{date.today().year + 2}-01-01"
        goal = _create(test_client, name="Trip", target_amount=1200, target_date=future)
        assert goal["months_remaining"] > 0
        assert goal["monthly_needed"] > 0
        assert goal["suggested_this_month"] > 0

    def test_update_sets_monthly_amount(self, test_client):
        """The monthly amount drives the month's suggestion."""
        goal = _create(test_client, name="Laptop", target_amount=5000)

        res = test_client.put(
            f"/api/savings-goals/{goal['id']}", json={"monthly_amount": 400}
        )
        assert res.status_code == 200
        updated = _goal(res.json(), goal["id"])
        assert updated["monthly_amount"] == 400
        assert updated["suggested_this_month"] == 400

    def test_delete(self, test_client):
        """Deleting a goal empties the list."""
        goal = _create(test_client, name="Gone", target_amount=100)

        res = test_client.delete(f"/api/savings-goals/{goal['id']}")
        assert res.status_code == 200
        assert res.json()["status"] == "deleted"
        assert test_client.get("/api/savings-goals/").json() == []

    def test_update_missing_returns_404(self, test_client):
        """Updating an unknown goal returns a 404."""
        res = test_client.put("/api/savings-goals/9999", json={"name": "nope"})
        assert res.status_code == 404


class TestOrderAndLifecycleRoutes:
    """List order, closing and reopening."""

    def test_reorder_sets_the_list_order(self, test_client):
        """POST /reorder puts the first id at the top of the list."""
        first = _create(test_client, name="A", target_amount=100)
        second = _create(test_client, name="B", target_amount=100)

        res = test_client.post(
            "/api/savings-goals/reorder", json={"goal_ids": [second["id"], first["id"]]}
        )
        assert res.status_code == 200
        assert [g["name"] for g in res.json()] == ["B", "A"]

    def test_reorder_with_unknown_id_returns_404(self, test_client):
        """Reordering with an id that does not exist is rejected."""
        goal = _create(test_client, name="A", target_amount=100)
        res = test_client.post(
            "/api/savings-goals/reorder", json={"goal_ids": [goal["id"], 9999]}
        )
        assert res.status_code == 404

    def test_close_hands_money_back_and_reopen_restores_it(self, test_client):
        """Closing empties the goal with a close entry; reopening undoes it."""
        goal = _create(test_client, name="Done", target_amount=1000, initial_amount=300)

        closed = test_client.post(f"/api/savings-goals/{goal['id']}/close").json()[0]
        assert closed["is_closed"] is True
        assert closed["available"] == 0
        assert [e["source"] for e in closed["entries"]][0] == "close"

        reopened = test_client.post(f"/api/savings-goals/{goal['id']}/reopen").json()[0]
        assert reopened["is_closed"] is False
        assert reopened["available"] == 300

    def test_close_missing_returns_404(self, test_client):
        """Closing an unknown goal returns a 404."""
        assert test_client.post("/api/savings-goals/9999/close").status_code == 404


class TestEntryRoutes:
    """Money put into and taken out of a goal."""

    def test_add_and_take_out(self, test_client):
        """A positive entry adds, a negative one takes back."""
        goal = _create(test_client, name="Trip", target_amount=1000)
        today = date.today().isoformat()

        res = test_client.post(
            f"/api/savings-goals/{goal['id']}/entries",
            json={"amount": 400, "date": today, "note": "bonus"},
        )
        assert res.status_code == 200, res.text
        res = test_client.post(
            f"/api/savings-goals/{goal['id']}/entries", json={"amount": -150}
        )
        assert res.status_code == 200, res.text

        updated = _goal(res.json(), goal["id"])
        assert updated["available"] == 250
        assert [e["amount"] for e in updated["entries"]] == [-150, 400]
        assert updated["entries"][1]["note"] == "bonus"

    def test_taking_out_more_than_held_is_400(self, test_client):
        """A goal cannot hand back money it does not hold."""
        goal = _create(test_client, name="Trip", target_amount=1000, initial_amount=100)

        res = test_client.post(
            f"/api/savings-goals/{goal['id']}/entries", json={"amount": -500}
        )
        assert res.status_code == 400

    def test_zero_amount_is_400(self, test_client):
        """An entry has to move money."""
        goal = _create(test_client, name="Trip", target_amount=1000)

        res = test_client.post(
            f"/api/savings-goals/{goal['id']}/entries", json={"amount": 0}
        )
        assert res.status_code == 400

    def test_entry_on_missing_goal_is_404(self, test_client):
        """An entry needs a goal to belong to."""
        res = test_client.post("/api/savings-goals/9999/entries", json={"amount": 10})
        assert res.status_code == 404

    def test_delete_entry(self, test_client):
        """Deleting an entry takes its money back out of the goal."""
        goal = _create(test_client, name="Trip", target_amount=1000, initial_amount=100)
        entry_id = goal["entries"][0]["id"]

        res = test_client.delete(f"/api/savings-goals/entries/{entry_id}")
        assert res.status_code == 200
        updated = _goal(res.json(), goal["id"])
        assert updated["available"] == 0
        assert updated["entries"] == []

    def test_delete_missing_entry_is_404(self, test_client):
        """Deleting an entry that does not exist is a 404."""
        assert test_client.delete("/api/savings-goals/entries/9999").status_code == 404


class TestFundAndCoverRoutes:
    """Funding the month's suggestions and covering a free-cash shortfall."""

    def test_fund_puts_the_suggestion_in(self, test_client, db_session):
        """POST /fund adds each goal's suggestion, within free cash."""
        seed_liquid(db_session, 1000)
        first = _create(test_client, name="A", target_amount=5000, monthly_amount=300)
        second = _create(test_client, name="B", target_amount=5000, monthly_amount=200)

        res = test_client.post("/api/savings-goals/fund", json={})
        assert res.status_code == 200, res.text
        goals = res.json()
        assert _goal(goals, first["id"])["available"] == 300
        assert _goal(goals, second["id"])["available"] == 200

    def test_fund_only_the_named_goals(self, test_client, db_session):
        """``goal_ids`` limits funding to those goals."""
        seed_liquid(db_session, 1000)
        first = _create(test_client, name="A", target_amount=5000, monthly_amount=300)
        second = _create(test_client, name="B", target_amount=5000, monthly_amount=200)

        res = test_client.post(
            "/api/savings-goals/fund", json={"goal_ids": [second["id"]]}
        )
        goals = res.json()
        assert _goal(goals, first["id"])["available"] == 0
        assert _goal(goals, second["id"])["available"] == 200

    def test_free_cash_shape_and_cover(self, test_client, db_session):
        """Goals holding more than the bank leave free cash negative until covered.

        Entries are not capped by free cash, so putting 1,500 into a goal
        while the bank holds 1,000 is how a shortfall arises here.
        """
        seed_liquid(db_session, 1000)
        goal = _create(test_client, name="A", target_amount=5000, initial_amount=1500)

        free = test_client.get("/api/savings-goals/free-cash").json()
        assert free == {
            "free_cash": -500.0,
            "earmarked": 1500.0,
            "liquid": 1000.0,
            "has_goals": True,
            "shortfall": 500.0,
            "cover_plan": [{"goal_id": goal["id"], "name": "A", "amount": 500.0}],
        }

        res = test_client.post("/api/savings-goals/free-cash/cover")
        assert res.status_code == 200, res.text
        covered = _goal(res.json(), goal["id"])
        assert covered["available"] == 1000
        assert covered["entries"][0]["source"] == "cover"

        after = test_client.get("/api/savings-goals/free-cash").json()
        assert after["free_cash"] == 0
        assert after["cover_plan"] == []

    def test_free_cash_without_goals(self, test_client):
        """With no goals nothing is earmarked."""
        body = test_client.get("/api/savings-goals/free-cash").json()
        assert body["has_goals"] is False
        assert body["cover_plan"] == []


class TestMonthAndTimelineRoutes:
    """The month view the budget page reads, and the timeline."""

    def test_month_shape(self, test_client):
        """The month endpoint lists what moved in each goal."""
        goal = _create(test_client, name="A", target_amount=1000, initial_amount=250)
        today = date.today()

        res = test_client.get(f"/api/savings-goals/month/{today.year}/{today.month}")
        assert res.status_code == 200
        body = res.json()
        assert body["year"] == today.year
        assert body["month"] == today.month
        assert body["total_added"] == 250
        assert body["total_change"] == 250
        row = body["goals"][0]
        assert row["goal_id"] == goal["id"]
        assert {"added", "income", "spent", "change", "name", "priority", "status"} <= (
            set(row)
        )

    def test_quiet_month_is_empty(self, test_client):
        """A month nothing moved in lists no goals."""
        _create(test_client, name="A", target_amount=100)

        body = test_client.get("/api/savings-goals/month/2020/1").json()
        assert body["goals"] == []
        assert body["total_added"] == 0

    def test_timeline_shape(self, test_client):
        """The timeline endpoint reports months, goals and the full length."""
        goal = _create(test_client, name="A", target_amount=100, initial_amount=40)

        res = test_client.get("/api/savings-goals/timeline")
        assert res.status_code == 200
        body = res.json()
        assert body["has_goals"] is True
        assert body["total_months"] == len(body["months"]) == 1
        month = body["months"][0]
        assert set(month) == {"month", "free_cash", "goals"}
        assert month["goals"] == [{"goal_id": goal["id"], "balance": 40, "change": 40}]
        assert [g["name"] for g in body["goals"]] == ["A"]

    def test_timeline_window_is_bounded(self, test_client):
        """`months` trims the window; zero asks for the whole history."""
        _create(test_client, name="A", target_amount=100, start_month="2020-01")

        windowed = test_client.get("/api/savings-goals/timeline?months=3").json()
        assert len(windowed["months"]) == 3
        assert windowed["total_months"] > 3

        everything = test_client.get("/api/savings-goals/timeline?months=0").json()
        assert len(everything["months"]) == everything["total_months"]

    def test_timeline_rejects_a_negative_window(self, test_client):
        """A negative month count fails request validation rather than silently passing."""
        assert (
            test_client.get("/api/savings-goals/timeline?months=-1").status_code == 422
        )

    def test_timeline_without_goals(self, test_client):
        """With no goals there is nothing to chart."""
        body = test_client.get("/api/savings-goals/timeline").json()
        assert body == {
            "has_goals": False,
            "total_months": 0,
            "months": [],
            "goals": [],
        }


class TestRemovedRoutes:
    """The automatic ledger's endpoints are gone."""

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("post", "/api/savings-goals/rebuild"),
            ("get", "/api/savings-goals/free-cash/before?month=2026-01"),
            ("get", "/api/savings-goals/allocations/2026/1"),
        ],
    )
    def test_removed_route_is_not_served(self, test_client, method, path):
        """Each retired route answers 404 or 405, never 200."""
        res = getattr(test_client, method)(path)
        assert res.status_code in (404, 405)


class TestLinkRoutes:
    """Transaction linking."""

    def test_link_and_unlink_an_incoming_transaction(self, test_client, db_session):
        """Income can be saved into a goal and then detached."""
        goal = _create(test_client, name="Trip", target_amount=1000)
        txn = add_txn(db_session, month_str(0), 400, "Other Income", day=1)

        res = test_client.post(
            f"/api/savings-goals/{goal['id']}/links",
            json={
                "source_type": "transaction",
                "source_id": txn.unique_id,
                "source_table": "bank_transactions",
                "link_type": "contribution",
            },
        )
        assert res.status_code == 200, res.text
        assert _goal(res.json(), goal["id"])["income"] == 400

        links = test_client.get("/api/savings-goals/links").json()
        assert len(links) == 1
        assert links[0]["link_type"] == "contribution"

        res = test_client.delete(f"/api/savings-goals/links/{links[0]['id']}")
        assert res.status_code == 200
        assert test_client.get("/api/savings-goals/links").json() == []

    def test_contribution_on_an_outgoing_transaction_is_400(
        self, test_client, db_session
    ):
        """Money going out cannot be saved into a goal; that is an entry."""
        goal = _create(test_client, name="Trip", target_amount=1000)
        txn = add_txn(db_session, month_str(0), -400, "Food", day=1)

        res = test_client.post(
            f"/api/savings-goals/{goal['id']}/links",
            json={
                "source_type": "transaction",
                "source_id": txn.unique_id,
                "source_table": "bank_transactions",
                "link_type": "contribution",
            },
        )
        assert res.status_code == 400
        assert test_client.get("/api/savings-goals/links").json() == []

    def test_outgoing_transaction_can_be_spent_out_of_a_goal(
        self, test_client, db_session
    ):
        """A utilization link on a purchase is accepted."""
        goal = _create(test_client, name="Trip", target_amount=1000)
        txn = add_txn(db_session, month_str(0), -400, "Travel", day=1)

        res = test_client.post(
            f"/api/savings-goals/{goal['id']}/links",
            json={
                "source_type": "transaction",
                "source_id": txn.unique_id,
                "source_table": "bank_transactions",
                "link_type": "utilization",
            },
        )
        assert res.status_code == 200, res.text

    def test_link_rejects_an_unknown_link_type(self, test_client):
        """Only contribution and utilization are accepted."""
        goal = _create(test_client, name="Trip", target_amount=1000)

        res = test_client.post(
            f"/api/savings-goals/{goal['id']}/links",
            json={
                "source_type": "transaction",
                "source_id": 42,
                "source_table": "bank_transactions",
                "link_type": "something_else",
            },
        )
        assert res.status_code == 422

    def test_link_to_missing_goal_returns_404(self, test_client):
        """Linking to a goal that does not exist is rejected."""
        res = test_client.post(
            "/api/savings-goals/9999/links",
            json={
                "source_type": "transaction",
                "source_id": 42,
                "source_table": "bank_transactions",
                "link_type": "contribution",
            },
        )
        assert res.status_code == 404


class TestSpendingLinkRoutes:
    """PUT /api/savings-goals/{id}/spending-link links a category/tags rule."""

    def test_link_and_detach_a_category(self, test_client, seed_project_transactions):
        """The goal reports its rule, and ``null`` clears it."""
        goal = _create(test_client, name="Wedding fund", target_amount=100000)

        res = test_client.put(
            f"/api/savings-goals/{goal['id']}/spending-link",
            json={"category": "Wedding"},
        )
        assert res.status_code == 200, res.text
        linked = _goal(res.json(), goal["id"])
        assert linked["utilization_category"] == "Wedding"

        res = test_client.put(
            f"/api/savings-goals/{goal['id']}/spending-link", json={"category": None}
        )
        assert res.status_code == 200, res.text
        detached = _goal(res.json(), goal["id"])
        assert detached["utilization_category"] is None

    def test_tags_are_stored_semicolon_joined(self, test_client):
        """A yearly envelope's tag list is stored the way budget rules store it."""
        goal = _create(test_client, name="Trip", target_amount=5000)
        res = test_client.put(
            f"/api/savings-goals/{goal['id']}/spending-link",
            json={"category": "Leisure", "tags": ["Vacation", "Flights"]},
        )
        assert res.status_code == 200, res.text
        linked = _goal(res.json(), goal["id"])
        assert linked["utilization_tags"] == "Flights;Vacation"

    def test_missing_goal_returns_404(self, test_client, seed_project_transactions):
        """Linking a category to an unknown goal is a 404."""
        res = test_client.put(
            "/api/savings-goals/9999/spending-link", json={"category": "Wedding"}
        )
        assert res.status_code == 404


class TestBudgetAnalysisCarriesGoalMoves:
    """The monthly budget analysis carries what moved in each goal that month."""

    def test_analysis_includes_a_savings_goals_block(self, test_client):
        """The budget page reads goal movements off the analysis it already fetches.

        Giving the section its own per-month endpoint call made it one more
        straggler on every refresh of the same screen, which pushed the budget
        page's post-mutation refresh past its deadline.
        """
        today = date.today()
        res = test_client.get(f"/api/budget/analysis/{today.year}/{today.month}")

        assert res.status_code == 200
        block = res.json()["savings_goals"]
        assert block["year"] == today.year
        assert block["month"] == today.month
        assert block["goals"] == []

    def test_analysis_reports_money_put_into_a_goal(self, test_client):
        """A goal that received money this month shows up in the block."""
        goal = _create(test_client, name="Trip", target_amount=1000, initial_amount=100)
        today = date.today()

        res = test_client.get(f"/api/budget/analysis/{today.year}/{today.month}")

        block = res.json()["savings_goals"]
        assert [row["goal_id"] for row in block["goals"]] == [goal["id"]]
        assert block["total_added"] == 100


class TestYearlySavingsRoutes:
    """The yearly savings view and its per-year target."""

    def test_get_returns_the_current_year(self, test_client):
        """GET /yearly lists the current year even with no transactions."""
        res = test_client.get("/api/savings-goals/yearly")

        assert res.status_code == 200
        body = res.json()
        assert body["years"][-1]["is_current"] is True
        assert body["pace"] is None

    def test_put_sets_and_clears_a_target(self, test_client):
        """PUT /yearly/{year}/target stores the target and returns the view."""
        year = 2026
        res = test_client.put(
            f"/api/savings-goals/yearly/{year}/target", json={"target_amount": 120000}
        )
        assert res.status_code == 200
        assert (
            next(r for r in res.json()["years"] if r["year"] == year)["target"]
            == 120000
        )

        res = test_client.put(
            f"/api/savings-goals/yearly/{year}/target", json={"target_amount": None}
        )
        assert (
            next(
                (r for r in res.json()["years"] if r["year"] == year), {"target": None}
            )["target"]
            is None
        )

    def test_put_rejects_a_non_positive_target(self, test_client):
        """A zero target is a validation error."""
        res = test_client.put(
            "/api/savings-goals/yearly/2026/target", json={"target_amount": 0}
        )
        assert res.status_code == 422
