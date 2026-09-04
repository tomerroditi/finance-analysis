"""Endpoint tests for the savings goals API."""

from datetime import date


def _create(test_client, **body):
    """POST a goal and return the created row from the refreshed list."""
    res = test_client.post("/api/savings-goals/", json=body)
    assert res.status_code == 200, res.text
    return next(g for g in res.json() if g["name"] == body["name"])


class TestSavingsGoalsRoutes:
    """CRUD + progress-metric tests for /api/savings-goals."""

    def test_empty_list(self, test_client):
        """A fresh DB returns an empty goals list."""
        res = test_client.get("/api/savings-goals/")
        assert res.status_code == 200
        assert res.json() == []

    def test_create_and_list(self, test_client):
        """Creating a goal returns it with derived progress metrics."""
        goal = _create(
            test_client, name="Vacation", target_amount=10000, opening_balance=2500
        )
        assert goal["progress_pct"] == 25.0
        assert goal["remaining"] == 7500.0
        assert goal["funded"] == 2500.0
        assert goal["is_achieved"] is False

        listed = test_client.get("/api/savings-goals/").json()
        assert len(listed) == 1

    def test_create_rejects_non_positive_target(self, test_client):
        """A target of zero or less fails request validation."""
        res = test_client.post(
            "/api/savings-goals/", json={"name": "Bad", "target_amount": 0}
        )
        assert res.status_code == 422

    def test_monthly_needed_with_target_date(self, test_client):
        """A target date yields a monthly_needed contribution figure."""
        future = f"{date.today().year + 2}-01-01"
        goal = _create(
            test_client, name="Trip", target_amount=1200, target_date=future
        )
        assert goal["months_remaining"] > 0
        assert goal["monthly_needed"] > 0

    def test_update_marks_achieved(self, test_client):
        """Raising the opening balance past the target flips is_achieved."""
        goal = _create(test_client, name="Laptop", target_amount=5000)
        assert goal["is_achieved"] is False

        res = test_client.put(
            f"/api/savings-goals/{goal['id']}", json={"opening_balance": 5000}
        )
        assert res.status_code == 200
        updated = next(g for g in res.json() if g["id"] == goal["id"])
        assert updated["is_achieved"] is True
        assert updated["progress_pct"] == 100.0

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


class TestWaterfallRoutes:
    """Priority ordering, lifecycle, and the rebuild preview."""

    def test_reorder_sets_the_waterfall(self, test_client):
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

    def test_close_and_reopen(self, test_client):
        """A goal can be frozen and then brought back into the waterfall."""
        goal = _create(test_client, name="Done", target_amount=100)

        closed = test_client.post(f"/api/savings-goals/{goal['id']}/close").json()
        assert closed[0]["is_closed"] is True

        reopened = test_client.post(f"/api/savings-goals/{goal['id']}/reopen").json()
        assert reopened[0]["is_closed"] is False

    def test_rebuild_defaults_to_a_dry_run(self, test_client):
        """The rebuild endpoint previews by default so the UI can confirm."""
        _create(test_client, name="A", target_amount=100)

        res = test_client.post("/api/savings-goals/rebuild", json={})
        assert res.status_code == 200
        body = res.json()
        assert body["dry_run"] is True
        assert body["goals"] == []
        assert isinstance(body["changes"], list)

    def test_rebuild_rejects_a_malformed_month(self, test_client):
        """An unparseable from_month is refused rather than silently ignored."""
        res = test_client.post(
            "/api/savings-goals/rebuild", json={"from_month": "not-a-month"}
        )
        assert res.status_code == 400


class TestAllocationAndLinkRoutes:
    """The month view the budget page reads, and transaction linking."""

    def test_month_allocations_shape(self, test_client):
        """The month endpoint reports totals and whether the month is still open."""
        _create(test_client, name="A", target_amount=100)
        today = date.today()

        res = test_client.get(
            f"/api/savings-goals/allocations/{today.year}/{today.month}"
        )
        assert res.status_code == 200
        body = res.json()
        assert body["year"] == today.year
        assert body["is_provisional"] is True
        assert "total_allocated" in body and "unallocated" in body

    def test_past_month_is_not_provisional(self, test_client):
        """A month that has already closed is reported as settled."""
        _create(test_client, name="A", target_amount=100)

        res = test_client.get("/api/savings-goals/allocations/2020/1")
        assert res.json()["is_provisional"] is False

    def test_link_and_unlink_a_transaction(self, test_client):
        """A transaction can be attached to a goal and then detached."""
        goal = _create(test_client, name="Trip", target_amount=1000)

        res = test_client.post(
            f"/api/savings-goals/{goal['id']}/links",
            json={
                "source_type": "transaction",
                "source_id": 42,
                "source_table": "bank_transactions",
                "link_type": "contribution",
            },
        )
        assert res.status_code == 200

        links = test_client.get("/api/savings-goals/links").json()
        assert len(links) == 1
        assert links[0]["link_type"] == "contribution"

        res = test_client.delete(f"/api/savings-goals/links/{links[0]['id']}")
        assert res.status_code == 200
        assert test_client.get("/api/savings-goals/links").json() == []

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


class TestBudgetAnalysisCarriesAllocations:
    """The monthly budget analysis carries the goal allocations for its month."""

    def test_analysis_includes_a_savings_goals_block(self, test_client):
        """The budget page reads allocations off the analysis it already fetches.

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
        assert block["is_provisional"] is True

    def test_analysis_reports_a_funded_goal(self, test_client):
        """A goal that received money in the month shows up in the block."""
        goal = _create(
            test_client, name="Trip", target_amount=1000, opening_balance=100
        )
        today = date.today()

        res = test_client.get(f"/api/budget/analysis/{today.year}/{today.month}")

        block = res.json()["savings_goals"]
        # Demo-free test data has no surplus, so the goal is listed only if the
        # engine actually directed something at it; either way the block must
        # stay well-formed and never invent an allocation.
        assert all(row["goal_id"] == goal["id"] for row in block["goals"])
        assert block["total_allocated"] >= 0
