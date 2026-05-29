"""Endpoint tests for the savings goals API."""


class TestSavingsGoalsRoutes:
    """CRUD + progress-metric tests for /api/savings-goals."""

    def test_empty_list(self, test_client):
        """A fresh DB returns an empty goals list."""
        res = test_client.get("/api/savings-goals/")
        assert res.status_code == 200
        assert res.json() == []

    def test_create_and_list(self, test_client):
        """Creating a goal returns it with derived progress metrics."""
        res = test_client.post(
            "/api/savings-goals/",
            json={"name": "Vacation", "target_amount": 10000, "current_amount": 2500},
        )
        assert res.status_code == 200
        goal = res.json()
        assert goal["name"] == "Vacation"
        assert goal["progress_pct"] == 25.0
        assert goal["remaining"] == 7500.0
        assert goal["is_achieved"] is False

        listed = test_client.get("/api/savings-goals/").json()
        assert len(listed) == 1

    def test_monthly_needed_with_target_date(self, test_client):
        """A target date yields a monthly_needed contribution figure."""
        res = test_client.post(
            "/api/savings-goals/",
            json={
                "name": "Car",
                "target_amount": 12000,
                "current_amount": 0,
                "target_date": "2099-12-31",
            },
        )
        goal = res.json()
        assert goal["months_remaining"] is not None
        assert goal["monthly_needed"] is not None
        assert goal["monthly_needed"] > 0

    def test_update_marks_achieved(self, test_client):
        """Updating current_amount to the target marks the goal achieved."""
        goal = test_client.post(
            "/api/savings-goals/",
            json={"name": "Fund", "target_amount": 5000},
        ).json()
        updated = test_client.put(
            f"/api/savings-goals/{goal['id']}", json={"current_amount": 5000}
        ).json()
        assert updated["is_achieved"] is True
        assert updated["progress_pct"] == 100.0

    def test_delete(self, test_client):
        """Deleting a goal removes it from the list."""
        goal = test_client.post(
            "/api/savings-goals/", json={"name": "Temp", "target_amount": 100}
        ).json()
        assert test_client.delete(f"/api/savings-goals/{goal['id']}").status_code == 200
        assert test_client.get("/api/savings-goals/").json() == []

    def test_update_missing_returns_404(self, test_client):
        """Updating a nonexistent goal returns 404."""
        res = test_client.put("/api/savings-goals/9999", json={"current_amount": 1})
        assert res.status_code == 404
