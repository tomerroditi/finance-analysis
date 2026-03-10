"""Unit tests for the Credential ORM model."""

import pytest
from sqlalchemy.exc import IntegrityError

from backend.models.credential import Credential


class TestCredentialModel:
    """Tests for Credential model constraints and defaults."""

    def test_create_credential(self, db_session):
        """Verify credential created with service, provider, account, and fields."""
        cred = Credential(
            service="banks",
            provider="hapoalim",
            account_name="Main Account",
            fields={"userCode": "test_code", "num": "12345"},
        )
        db_session.add(cred)
        db_session.commit()
        db_session.refresh(cred)

        assert cred.id is not None
        assert cred.service == "banks"
        assert cred.provider == "hapoalim"
        assert cred.account_name == "Main Account"
        assert cred.fields == {"userCode": "test_code", "num": "12345"}
        assert cred.created_at is not None

    def test_default_empty_fields(self, db_session):
        """Verify fields defaults to empty dict."""
        cred = Credential(
            service="banks", provider="hapoalim", account_name="Test"
        )
        db_session.add(cred)
        db_session.commit()
        db_session.refresh(cred)

        assert cred.fields == {}

    def test_unique_constraint(self, db_session):
        """Verify duplicate service+provider+account_name raises IntegrityError."""
        db_session.add(
            Credential(service="banks", provider="hapoalim", account_name="Main")
        )
        db_session.commit()

        db_session.add(
            Credential(service="banks", provider="hapoalim", account_name="Main")
        )
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_different_accounts_same_provider(self, db_session):
        """Verify different account names for same provider are allowed."""
        db_session.add(
            Credential(service="banks", provider="hapoalim", account_name="Main")
        )
        db_session.add(
            Credential(service="banks", provider="hapoalim", account_name="Savings")
        )
        db_session.commit()

        creds = db_session.query(Credential).all()
        assert len(creds) == 2
