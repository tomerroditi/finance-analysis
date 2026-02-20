"""Unit tests for CredentialsRepository DB-backed credential CRUD operations."""

import pytest
import yaml
from unittest.mock import patch

from backend.errors import EntityNotFoundException
from backend.models.credential import Credential
from backend.repositories.credentials_repository import CredentialsRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_keyring():
    """Mock the keyring module to avoid OS keyring access."""
    with patch("backend.repositories.credentials_repository.keyring") as mk:
        mk.get_password.return_value = "secret123"
        mk.set_password.return_value = None
        mk.delete_password.return_value = None
        yield mk


@pytest.fixture
def seeded_repo(db_session, mock_keyring):
    """Create a CredentialsRepository with two seeded credentials."""
    db_session.add(
        Credential(
            service="banks",
            provider="hapoalim",
            account_name="Main Account",
            fields={"userCode": "test_code"},
        )
    )
    db_session.add(
        Credential(
            service="credit_cards",
            provider="isracard",
            account_name="Account 1",
            fields={"id": "000000000", "card6Digits": "123456"},
        )
    )
    db_session.commit()
    return CredentialsRepository(db_session)


@pytest.fixture
def empty_repo(db_session, mock_keyring):
    """Create a CredentialsRepository with no credentials."""
    return CredentialsRepository(db_session)


# ---------------------------------------------------------------------------
# Class 1: Read operations
# ---------------------------------------------------------------------------


class TestCredentialsRepositoryRead:
    """Tests for reading credentials from the database."""

    def test_get_credentials(self, seeded_repo, mock_keyring):
        """Verify get_credentials returns fields merged with keyring password."""
        result = seeded_repo.get_credentials("banks", "hapoalim", "Main Account")
        assert result["userCode"] == "test_code"
        assert result["password"] == "secret123"

    def test_get_credentials_not_found(self, seeded_repo):
        """Verify get_credentials raises EntityNotFoundException for missing account."""
        with pytest.raises(EntityNotFoundException):
            seeded_repo.get_credentials("banks", "hapoalim", "Nonexistent")

    def test_list_accounts(self, seeded_repo):
        """Verify list_accounts returns flat list of all accounts."""
        accounts = seeded_repo.list_accounts()
        assert len(accounts) == 2
        tuples = {(a["service"], a["provider"], a["account_name"]) for a in accounts}
        assert ("banks", "hapoalim", "Main Account") in tuples
        assert ("credit_cards", "isracard", "Account 1") in tuples

    def test_list_accounts_empty(self, empty_repo):
        """Verify list_accounts returns empty list when no credentials."""
        assert empty_repo.list_accounts() == []

    def test_get_all_credentials(self, seeded_repo, mock_keyring):
        """Verify get_all_credentials returns nested dict with passwords."""
        result = seeded_repo.get_all_credentials()
        assert "banks" in result
        assert "hapoalim" in result["banks"]
        assert "Main Account" in result["banks"]["hapoalim"]
        assert result["banks"]["hapoalim"]["Main Account"]["password"] == "secret123"


# ---------------------------------------------------------------------------
# Class 2: Write operations
# ---------------------------------------------------------------------------


class TestCredentialsRepositoryWrite:
    """Tests for saving and deleting credentials."""

    def test_save_credentials_new(self, empty_repo, mock_keyring):
        """Verify saving a new credential stores fields in DB and password in keyring."""
        empty_repo.save_credentials(
            "banks", "hapoalim", "Main",
            {"userCode": "abc", "password": "mypass"},
        )

        accounts = empty_repo.list_accounts()
        assert len(accounts) == 1
        mock_keyring.set_password.assert_called_once()

    def test_save_credentials_upsert(self, seeded_repo, mock_keyring):
        """Verify saving to existing account updates fields."""
        seeded_repo.save_credentials(
            "banks", "hapoalim", "Main Account",
            {"userCode": "new_code", "password": "newpass"},
        )

        result = seeded_repo.get_credentials("banks", "hapoalim", "Main Account")
        assert result["userCode"] == "new_code"

    def test_save_credentials_extracts_otp_token(self, empty_repo, mock_keyring):
        """Verify otpLongTermToken is stored in keyring, not in DB fields."""
        empty_repo.save_credentials(
            "banks", "onezero", "Account",
            {"email": "test@example.com", "password": "pw", "otpLongTermToken": "token123"},
        )

        # Two keyring calls: password + otpLongTermToken
        assert mock_keyring.set_password.call_count == 2

    def test_delete_credentials(self, seeded_repo, mock_keyring):
        """Verify deleting a credential removes DB row and keyring entries."""
        seeded_repo.delete_credentials("banks", "hapoalim", "Main Account")

        accounts = seeded_repo.list_accounts()
        assert len(accounts) == 1
        assert mock_keyring.delete_password.called

    def test_delete_credentials_not_found(self, seeded_repo):
        """Verify deleting nonexistent credential raises EntityNotFoundException."""
        with pytest.raises(EntityNotFoundException):
            seeded_repo.delete_credentials("banks", "hapoalim", "Nonexistent")


# ---------------------------------------------------------------------------
# Class 3: Migration from YAML
# ---------------------------------------------------------------------------


class TestCredentialsRepositoryMigration:
    """Tests for one-time YAML migration."""

    def test_migrate_from_yaml(self, empty_repo, tmp_path, mock_keyring):
        """Verify YAML credentials are migrated into DB."""
        creds = {
            "banks": {
                "hapoalim": {
                    "Main Account": {"userCode": "test_code", "password": ""},
                }
            },
            "credit_cards": {},
        }
        creds_path = str(tmp_path / "credentials.yaml")
        with open(creds_path, "w") as f:
            yaml.dump(creds, f)

        empty_repo.migrate_from_yaml(creds_path)

        accounts = empty_repo.list_accounts()
        assert len(accounts) == 1
        assert accounts[0]["provider"] == "hapoalim"

    def test_migrate_skips_when_table_not_empty(self, seeded_repo, tmp_path, mock_keyring):
        """Verify migration is skipped when credentials already exist."""
        creds = {"banks": {"leumi": {"New Account": {"userCode": "new"}}}}
        creds_path = str(tmp_path / "credentials.yaml")
        with open(creds_path, "w") as f:
            yaml.dump(creds, f)

        seeded_repo.migrate_from_yaml(creds_path)

        accounts = seeded_repo.list_accounts()
        assert not any(a["provider"] == "leumi" for a in accounts)
