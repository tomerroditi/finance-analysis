"""Route tests for imported-accounts endpoints."""

from fastapi.testclient import TestClient


VALID_MAPPING = {
    "skip_rows": 0,
    "date": {"column": "date", "format": "iso"},
    "description": {"column": "description"},
    "amount": {
        "mode": "single",
        "column": "amount",
        "sign_convention": "positive_is_income",
    },
    "category": {"column": None},
    "tag": {"column": None},
    "account_number": {"column": None},
}


CSV = (
    b"date,description,amount\n"
    b"2026-03-01,Coffee shop,-12.50\n"
    b"2026-03-03,Salary,8500.00\n"
)


class TestImportedAccountsRoutes:
    """Endpoint-level smoke tests."""

    def test_create_and_list(self, test_client: TestClient):
        """POST then GET returns the created row."""
        resp = test_client.post("/api/imported-accounts/", json={
            "service": "banks",
            "provider": "Hapoalim",
            "account_name": "Checking",
            "mapping": VALID_MAPPING,
        })
        assert resp.status_code == 200, resp.text
        created = resp.json()
        assert created["id"]

        listed = test_client.get("/api/imported-accounts/").json()
        assert len(listed) == 1
        assert listed[0]["account_name"] == "Checking"

    def test_create_duplicate_returns_400(self, test_client: TestClient):
        """Creating the same triple twice returns 400."""
        body = {
            "service": "banks", "provider": "H", "account_name": "A",
            "mapping": VALID_MAPPING,
        }
        test_client.post("/api/imported-accounts/", json=body)
        resp = test_client.post("/api/imported-accounts/", json=body)
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"]

    def test_update_mapping(self, test_client: TestClient):
        """PUT updates the saved mapping."""
        created = test_client.post("/api/imported-accounts/", json={
            "service": "banks", "provider": "H", "account_name": "A",
            "mapping": VALID_MAPPING,
        }).json()
        new_mapping = {**VALID_MAPPING, "skip_rows": 2}
        resp = test_client.put(
            f"/api/imported-accounts/{created['id']}",
            json={"mapping": new_mapping},
        )
        assert resp.status_code == 200
        assert resp.json()["mapping"]["skip_rows"] == 2

    def test_delete(self, test_client: TestClient):
        """DELETE removes the imported account."""
        created = test_client.post("/api/imported-accounts/", json={
            "service": "banks", "provider": "H", "account_name": "A",
            "mapping": VALID_MAPPING,
        }).json()
        resp = test_client.delete(f"/api/imported-accounts/{created['id']}")
        assert resp.status_code == 200
        assert test_client.get("/api/imported-accounts/").json() == []

    def test_upload(self, test_client: TestClient):
        """POST /upload runs the import and returns the summary."""
        created = test_client.post("/api/imported-accounts/", json={
            "service": "banks", "provider": "H", "account_name": "A",
            "mapping": VALID_MAPPING,
        }).json()
        resp = test_client.post(
            f"/api/imported-accounts/{created['id']}/upload",
            files={"file": ("test.csv", CSV, "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        summary = resp.json()
        assert summary["inserted"] == 2

    def test_preview(self, test_client: TestClient):
        """POST /preview returns mapped rows + dropped count + raw headers."""
        import json
        resp = test_client.post(
            "/api/imported-accounts/preview",
            files={"file": ("test.csv", CSV, "text/csv")},
            data={"mapping": json.dumps(VALID_MAPPING)},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["rows"]) == 2
        assert body["dropped_invalid"] == 0
        assert "date" in body["raw_headers"]

    def test_template(self, test_client: TestClient):
        """GET /template returns a CSV starter file."""
        resp = test_client.get("/api/imported-accounts/template")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        body = resp.content.decode("utf-8")
        assert body.startswith("date,description,amount,category,tag")
