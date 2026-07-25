"""Tests for the /api/credentials API endpoints."""

import pytest
from unittest.mock import MagicMock


@pytest.fixture(autouse=True)
def mock_credentials_deps(monkeypatch):
    """Mock credential dependencies to avoid filesystem/keyring access."""
    mock_service = MagicMock()
    mock_service.get_safe_credentials.return_value = {
        "credit_cards": {"isracard": ["Main Card"]},
        "banks": {"hapoalim": ["Checking"]},
    }
    mock_service.get_accounts_list.return_value = [
        {
            "service": "credit_cards",
            "provider": "isracard",
            "account_name": "Main Card",
        },
        {
            "service": "banks",
            "provider": "hapoalim",
            "account_name": "Checking",
        },
    ]
    mock_service.get_available_providers.return_value = {
        "credit_cards": ["isracard", "max", "visa cal"],
        "banks": ["hapoalim", "leumi", "discount"],
    }
    mock_service.get_masked_credentials.return_value = {
        "username": "test_user",
        "password": "__unchanged__",
    }
    mock_service.save_credentials.return_value = None
    mock_service.delete_credential.return_value = {"transactions_deleted": 0}

    # Create a callable mock that acts as both a class (with static methods)
    # and a constructor (returns instance when called).
    mock_cls = MagicMock()
    mock_cls.return_value = mock_service
    mock_cls.get_available_providers.return_value = {
        "credit_cards": ["isracard", "max", "visa cal"],
        "banks": ["hapoalim", "leumi", "discount"],
    }

    monkeypatch.setattr(
        "backend.routes.credentials.CredentialsService",
        mock_cls,
    )
    return mock_service


class TestCredentialsRoutes:
    """Tests for credential management endpoints."""

    def test_get_credentials(self, test_client):
        """GET /api/credentials/ returns safe credentials without passwords."""
        response = test_client.get("/api/credentials/")
        assert response.status_code == 200
        data = response.json()
        assert "credit_cards" in data
        assert "isracard" in data["credit_cards"]

    def test_get_accounts(self, test_client):
        """GET /api/credentials/accounts returns accounts list."""
        response = test_client.get("/api/credentials/accounts")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["service"] == "credit_cards"

    def test_get_providers(self, test_client):
        """GET /api/credentials/providers returns available providers dict."""
        response = test_client.get("/api/credentials/providers")
        assert response.status_code == 200
        data = response.json()
        assert "credit_cards" in data
        assert "banks" in data

    def test_get_provider_fields(self, test_client):
        """GET /api/credentials/fields/{provider} returns required login fields."""
        response = test_client.get("/api/credentials/fields/hapoalim")
        assert response.status_code == 200
        data = response.json()
        assert "fields" in data
        assert "userCode" in data["fields"]
        assert "password" in data["fields"]

    def test_get_credential_details(self, test_client):
        """GET /api/credentials/{service}/{provider}/{account_name} returns masked details."""
        response = test_client.get("/api/credentials/banks/hapoalim/Checking")
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "test_user"
        assert data["password"] == "__unchanged__"

    def test_get_credential_details_not_found(self, test_client, monkeypatch):
        """GET returns 404 for non-existent credentials."""
        mock_service = MagicMock()
        mock_service.get_masked_credentials.return_value = {}
        mock_cls = MagicMock()
        mock_cls.return_value = mock_service
        monkeypatch.setattr(
            "backend.routes.credentials.CredentialsService",
            mock_cls,
        )
        response = test_client.get("/api/credentials/banks/unknown/NoAccount")
        assert response.status_code == 404

    def test_create_credential(self, test_client):
        """POST /api/credentials/ creates or updates a credential."""
        payload = {
            "service": "banks",
            "provider": "hapoalim",
            "account_name": "New Account",
            "credentials": {"userCode": "mycode", "password": "secret"},
        }
        response = test_client.post("/api/credentials/", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_delete_credential(self, test_client):
        """DELETE /api/credentials/{service}/{provider}/{account_name} deletes credential."""
        response = test_client.delete(
            "/api/credentials/credit_cards/isracard/Main Card"
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"


class TestDeleteAccountDataChoice:
    """The delete endpoint distinguishes disconnecting from erasing."""

    def test_defaults_to_keeping_data(self, test_client, mock_credentials_deps):
        """No query param means delete_data=False — the safe default."""
        response = test_client.delete(
            "/api/credentials/banks/hapoalim/Main"
        )
        assert response.status_code == 200
        assert response.json()["transactions_deleted"] == 0
        _, kwargs = mock_credentials_deps.delete_credential.call_args
        assert kwargs["delete_data"] is False

    def test_delete_data_true_is_forwarded(
        self, test_client, mock_credentials_deps
    ):
        """delete_data=true reaches the service and the count is returned."""
        mock_credentials_deps.delete_credential.return_value = {
            "transactions_deleted": 7
        }
        response = test_client.delete(
            "/api/credentials/banks/hapoalim/Main?delete_data=true"
        )
        assert response.status_code == 200
        assert response.json()["transactions_deleted"] == 7
        _, kwargs = mock_credentials_deps.delete_credential.call_args
        assert kwargs["delete_data"] is True
