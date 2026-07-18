"""Endpoint tests for the /api/insurance-accounts API."""

from unittest.mock import patch

from backend.models.insurance_account import InsuranceAccount
from backend.models.investment import Investment
from backend.models.investment_balance_snapshot import InvestmentBalanceSnapshot


def _seed_account(db_session, **overrides) -> InsuranceAccount:
    """Insert an insurance account row directly and return it."""
    fields = {
        "provider": "hafenix",
        "policy_id": "pol-001",
        "policy_type": "pension",
        "pension_type": "makifa",
        "account_name": "Phoenix Pension",
        "balance": 150000.0,
        "balance_date": "2026-06-30",
    }
    fields.update(overrides)
    account = InsuranceAccount(**fields)
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)
    return account


class TestGetInsuranceAccounts:
    """Tests for GET /api/insurance-accounts/."""

    def test_get_empty_returns_empty_list(self, test_client):
        """A fresh DB returns an empty account list."""
        response = test_client.get("/api/insurance-accounts/")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_returns_seeded_accounts(self, test_client, db_session):
        """Seeded accounts come back with their metadata fields."""
        _seed_account(db_session)
        _seed_account(
            db_session,
            policy_id="pol-002",
            policy_type="hishtalmut",
            pension_type=None,
            account_name="Phoenix KH",
            liquidity_date="2027-01-01",
        )

        response = test_client.get("/api/insurance-accounts/")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        by_policy = {a["policy_id"]: a for a in data}
        assert by_policy["pol-001"]["policy_type"] == "pension"
        assert by_policy["pol-001"]["balance"] == 150000.0
        assert by_policy["pol-001"]["custom_name"] is None
        assert by_policy["pol-002"]["liquidity_date"] == "2027-01-01"


class TestRenameInsuranceAccount:
    """Tests for PATCH /api/insurance-accounts/{policy_id}/rename."""

    def test_rename_sets_custom_name(self, test_client, db_session):
        """Renaming stores the override and returns the updated record."""
        _seed_account(db_session)

        response = test_client.patch(
            "/api/insurance-accounts/pol-001/rename",
            json={"custom_name": "My Pension"},
        )

        assert response.status_code == 200
        assert response.json()["custom_name"] == "My Pension"
        listed = test_client.get("/api/insurance-accounts/").json()
        assert listed[0]["custom_name"] == "My Pension"

    def test_rename_null_clears_override(self, test_client, db_session):
        """Sending null clears a previously set custom name."""
        _seed_account(db_session, custom_name="Old Name")

        response = test_client.patch(
            "/api/insurance-accounts/pol-001/rename",
            json={"custom_name": None},
        )

        assert response.status_code == 200
        assert response.json()["custom_name"] is None

    def test_rename_whitespace_only_clears_override(self, test_client, db_session):
        """A whitespace-only name normalizes to a cleared override."""
        _seed_account(db_session, custom_name="Old Name")

        response = test_client.patch(
            "/api/insurance-accounts/pol-001/rename",
            json={"custom_name": "   "},
        )

        assert response.status_code == 200
        assert response.json()["custom_name"] is None

    def test_rename_unknown_policy_returns_404(self, test_client):
        """Renaming a nonexistent policy returns 404."""
        response = test_client.patch(
            "/api/insurance-accounts/nope/rename",
            json={"custom_name": "Name"},
        )
        assert response.status_code == 404

    def test_rename_hishtalmut_updates_linked_investment(
        self, test_client, db_session
    ):
        """Renaming a hishtalmut policy renames its linked Investment too."""
        _seed_account(
            db_session,
            policy_id="kh-001",
            policy_type="hishtalmut",
            pension_type=None,
            account_name="Phoenix KH",
        )
        investment = Investment(
            category="Investments",
            tag="Keren Hishtalmut - hafenix (kh-001)",
            type="hishtalmut",
            name="Phoenix KH",
            created_date="2026-01-01",
            insurance_policy_id="kh-001",
        )
        db_session.add(investment)
        db_session.commit()
        db_session.refresh(investment)

        response = test_client.patch(
            "/api/insurance-accounts/kh-001/rename",
            json={"custom_name": "Our KH Fund"},
        )

        assert response.status_code == 200
        db_session.refresh(investment)
        assert investment.name == "Our KH Fund"

    def test_rename_hishtalmut_clear_falls_back_to_account_name(
        self, test_client, db_session
    ):
        """Clearing a hishtalmut rename resets the Investment to scraped name."""
        _seed_account(
            db_session,
            policy_id="kh-001",
            policy_type="hishtalmut",
            pension_type=None,
            account_name="Phoenix KH",
            custom_name="Our KH Fund",
        )
        investment = Investment(
            category="Investments",
            tag="Keren Hishtalmut - hafenix (kh-001)",
            type="hishtalmut",
            name="Our KH Fund",
            created_date="2026-01-01",
            insurance_policy_id="kh-001",
        )
        db_session.add(investment)
        db_session.commit()
        db_session.refresh(investment)

        response = test_client.patch(
            "/api/insurance-accounts/kh-001/rename",
            json={"custom_name": None},
        )

        assert response.status_code == 200
        db_session.refresh(investment)
        assert investment.name == "Phoenix KH"


class TestSyncInvestments:
    """Tests for POST /api/insurance-accounts/sync-investments."""

    def test_sync_with_no_accounts_returns_zero(self, test_client):
        """With no hishtalmut accounts, nothing is processed."""
        response = test_client.post("/api/insurance-accounts/sync-investments")
        assert response.status_code == 200
        assert response.json() == {"synced": 0}

    def test_sync_creates_investment_for_hishtalmut(self, test_client, db_session):
        """A hishtalmut account backfills an Investment + scraped snapshot."""
        _seed_account(
            db_session,
            policy_id="kh-001",
            policy_type="hishtalmut",
            pension_type=None,
            account_name="Phoenix KH",
            balance=42000.0,
            balance_date="2026-06-30",
        )
        # Pension accounts are ignored by the backfill.
        _seed_account(db_session)

        response = test_client.post("/api/insurance-accounts/sync-investments")

        assert response.status_code == 200
        assert response.json() == {"synced": 1}
        investment = (
            db_session.query(Investment)
            .filter(Investment.insurance_policy_id == "kh-001")
            .one()
        )
        assert investment.name == "Phoenix KH"
        assert investment.type == "hishtalmut"
        snapshots = (
            db_session.query(InvestmentBalanceSnapshot)
            .filter(InvestmentBalanceSnapshot.investment_id == investment.id)
            .all()
        )
        assert len(snapshots) == 1
        assert snapshots[0].balance == 42000.0
        assert snapshots[0].source == "scraped"

    def test_sync_is_idempotent(self, test_client, db_session):
        """Re-running the backfill does not duplicate investments."""
        _seed_account(
            db_session,
            policy_id="kh-001",
            policy_type="hishtalmut",
            pension_type=None,
            account_name="Phoenix KH",
            balance=42000.0,
            balance_date="2026-06-30",
        )

        first = test_client.post("/api/insurance-accounts/sync-investments")
        second = test_client.post("/api/insurance-accounts/sync-investments")

        assert first.json() == {"synced": 1}
        assert second.json() == {"synced": 1}
        count = (
            db_session.query(Investment)
            .filter(Investment.insurance_policy_id == "kh-001")
            .count()
        )
        assert count == 1

    def test_sync_service_error_returns_sanitized_500(self, test_client_no_raise):
        """An unexpected service failure surfaces as a generic 500."""
        with patch(
            "backend.routes.insurance_accounts.InvestmentsService"
        ) as mock_service:
            mock_service.return_value.backfill_from_insurance_accounts.side_effect = (
                RuntimeError("secret db path leaked")
            )
            response = test_client_no_raise.post(
                "/api/insurance-accounts/sync-investments"
            )

        assert response.status_code == 500
        assert "secret db path" not in response.text
