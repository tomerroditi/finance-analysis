"""Unit tests for CredentialsRepository DB-backed credential CRUD operations."""

import pytest
import yaml
from unittest.mock import patch

import keyring.errors as _real_keyring_errors
from sqlalchemy import select

from backend.errors import EntityNotFoundException
from backend.models.credential import Credential
from backend.repositories.credentials_repository import CredentialsRepository
from backend.utils.crypto import ENCRYPTED_MARKER, decrypt_fields, is_encrypted


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_keyring():
    """Mock the keyring module (inside keyring_store) to avoid OS keyring access."""
    with patch("backend.utils.keyring_store.keyring") as mk:
        mk.get_password.return_value = "secret123"
        mk.set_password.return_value = None
        mk.delete_password.return_value = None
        # Preserve real errors module so `except keyring.errors.X` works
        mk.errors = _real_keyring_errors
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


# ---------------------------------------------------------------------------
# Class 4: Migration edge cases
# ---------------------------------------------------------------------------


class TestCredentialsRepositoryMigrationEdgeCases:
    """Tests for YAML migration edge cases."""

    def test_migrate_skips_when_file_not_found(self, empty_repo):
        """Verify migration returns silently when YAML file does not exist."""
        empty_repo.migrate_from_yaml("/nonexistent/path/credentials.yaml")

        accounts = empty_repo.list_accounts()
        assert len(accounts) == 0

    def test_migrate_skips_non_dict_entries(self, empty_repo, tmp_path, mock_keyring):
        """Verify migration skips entries where services, providers, or accounts are not dicts."""
        creds = {
            "banks": {
                "hapoalim": {
                    "Main Account": {"userCode": "abc"},
                    "Bad Account": "not_a_dict",
                },
                "bad_provider": "not_a_dict",
            },
            "bad_service": "not_a_dict",
        }
        creds_path = str(tmp_path / "credentials.yaml")
        with open(creds_path, "w") as f:
            yaml.dump(creds, f)

        empty_repo.migrate_from_yaml(creds_path)

        accounts = empty_repo.list_accounts()
        assert len(accounts) == 1
        assert accounts[0]["account_name"] == "Main Account"


# ---------------------------------------------------------------------------
# Class 5: At-rest field encryption
# ---------------------------------------------------------------------------


class TestCredentialsRepositoryEncryption:
    """Tests for Fernet encryption of the DB fields column."""

    def test_save_stores_encrypted_envelope(self, empty_repo, db_session, mock_keyring):
        """Verify saved fields hit the DB as ciphertext, not plaintext."""
        empty_repo.save_credentials(
            "banks", "hapoalim", "Main",
            {"userCode": "abc", "id": "123456789", "password": "pw"},
        )

        row = db_session.execute(select(Credential)).scalar_one()
        assert set(row.fields.keys()) == {ENCRYPTED_MARKER}
        assert "123456789" not in str(row.fields)

    def test_get_credentials_decrypts_envelope(self, empty_repo, mock_keyring):
        """Verify reads transparently decrypt what save encrypted."""
        empty_repo.save_credentials(
            "banks", "hapoalim", "Main",
            {"userCode": "abc", "password": "pw"},
        )

        result = empty_repo.get_credentials("banks", "hapoalim", "Main")
        assert result["userCode"] == "abc"

    def test_legacy_plaintext_rows_remain_readable(self, seeded_repo):
        """Verify rows written before encryption existed still read fine."""
        result = seeded_repo.get_credentials("banks", "hapoalim", "Main Account")
        assert result["userCode"] == "test_code"

    def test_encrypt_plaintext_rows_migrates_legacy_rows(
        self, seeded_repo, db_session
    ):
        """Verify the startup migration encrypts plaintext rows in place."""
        migrated = seeded_repo.encrypt_plaintext_rows()

        assert migrated == 2
        rows = db_session.execute(select(Credential)).scalars().all()
        assert all(is_encrypted(row.fields) for row in rows)
        # Data survives the rewrite.
        result = seeded_repo.get_credentials("banks", "hapoalim", "Main Account")
        assert result["userCode"] == "test_code"

    def test_encrypt_plaintext_rows_is_idempotent(self, seeded_repo):
        """Verify a second migration pass touches nothing."""
        assert seeded_repo.encrypt_plaintext_rows() == 2
        assert seeded_repo.encrypt_plaintext_rows() == 0

    def test_migrated_yaml_rows_are_encrypted(self, empty_repo, db_session, tmp_path, mock_keyring):
        """Verify YAML-imported rows land encrypted."""
        creds_path = str(tmp_path / "credentials.yaml")
        with open(creds_path, "w") as f:
            yaml.dump({"banks": {"hapoalim": {"Main": {"userCode": "x"}}}}, f)

        empty_repo.migrate_from_yaml(creds_path)

        row = db_session.execute(select(Credential)).scalar_one()
        assert is_encrypted(row.fields)
        assert decrypt_fields(row.fields) == {"userCode": "x"}


# ---------------------------------------------------------------------------
# Class 6: Legacy YAML removal
# ---------------------------------------------------------------------------


class TestCredentialsRepositoryYamlRemoval:
    """Tests for deleting the legacy plaintext credentials YAML."""

    def test_yaml_removed_after_migration(self, empty_repo, tmp_path, mock_keyring):
        """Verify the YAML file is deleted once its data is imported."""
        creds_path = tmp_path / "credentials.yaml"
        with open(creds_path, "w") as f:
            yaml.dump({"banks": {"hapoalim": {"Main": {"userCode": "x"}}}}, f)

        empty_repo.migrate_from_yaml(str(creds_path))

        assert empty_repo.list_accounts()
        assert not creds_path.exists()

    def test_yaml_removed_when_migration_skipped(
        self, seeded_repo, tmp_path, mock_keyring
    ):
        """Verify a lingering YAML is deleted even on already-migrated installs."""
        creds_path = tmp_path / "credentials.yaml"
        with open(creds_path, "w") as f:
            yaml.dump({"banks": {"leumi": {"Old": {"userCode": "y"}}}}, f)

        seeded_repo.migrate_from_yaml(str(creds_path))

        assert not creds_path.exists()

    def test_missing_yaml_is_a_noop(self, empty_repo):
        """Verify migration with no YAML file neither raises nor imports."""
        empty_repo.migrate_from_yaml("/nonexistent/credentials.yaml")
        assert empty_repo.list_accounts() == []


# ---------------------------------------------------------------------------
# Class 7: Keyring edge cases
# ---------------------------------------------------------------------------


class TestCredentialsRepositoryKeyringEdgeCases:
    """Tests for keyring error handling via the keyring store."""

    def test_delete_credentials_handles_keyring_error(self, seeded_repo, mock_keyring):
        """Verify keyring.PasswordDeleteError is silently caught during delete."""
        mock_keyring.delete_password.side_effect = _real_keyring_errors.PasswordDeleteError(
            "No password found"
        )

        seeded_repo.delete_credentials("banks", "hapoalim", "Main Account")

        accounts = seeded_repo.list_accounts()
        assert len(accounts) == 1

    def test_save_uses_demo_namespace_in_demo_mode(
        self, empty_repo, mock_keyring
    ):
        """Verify passwords land in the '-demo' keyring service in demo mode."""
        with patch("backend.utils.keyring_store.AppConfig") as MockConfig:
            MockConfig.return_value.is_demo_mode = True

            empty_repo.save_credentials(
                "banks", "hapoalim", "Main", {"userCode": "x", "password": "pw"}
            )

        service_name, entry_name, _ = mock_keyring.set_password.call_args[0]
        assert service_name == "finance-analysis-app-demo"
        assert entry_name == "banks_hapoalim_Main_password"
