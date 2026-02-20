"""Credentials repository for secure credential storage.

This repository handles DB-based storage for credentials
and OS keyring for sensitive fields (passwords, OTP tokens).
"""

import os
from typing import Dict, List

import keyring
import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import AppConfig
from backend.errors import EntityNotFoundException
from backend.models.credential import Credential

_KEYRING_SERVICE = "finance-analysis-app"
_SENSITIVE_FIELDS = ("password", "otpLongTermToken")


class CredentialsRepository:
    """Repository for credential storage backed by SQLite + OS Keyring."""

    def __init__(self, db: Session):
        """
        Parameters
        ----------
        db : Session
            SQLAlchemy database session used for all ORM operations.
        """
        self.db = db

    @property
    def keyring_service(self) -> str:
        """Keyring service name, with test suffix in test mode.

        Returns
        -------
        str
            Keyring service identifier used to namespace all stored secrets.
            Appends "-test" suffix when the application is running in test mode
            to avoid polluting production keyring entries.
        """
        service = _KEYRING_SERVICE
        if AppConfig().is_test_mode:
            service += "-test"
        return service

    def _keyring_key(
        self, service: str, provider: str, account_name: str, field: str
    ) -> str:
        """Generate a standardized keyring key.

        Parameters
        ----------
        service : str
            Financial service name (e.g. "credit_cards", "banks").
        provider : str
            Provider name within the service (e.g. "isracard", "hapoalim").
        account_name : str
            Identifier of the account.
        field : str
            Credential field name to store (e.g. "password", "otpLongTermToken").

        Returns
        -------
        str
            Colon-delimited key in the format "service:provider:account_name:field"
            used as the username argument when reading or writing keyring entries.
        """
        return f"{service}:{provider}:{account_name}:{field}"

    def _find_credential(
        self, service: str, provider: str, account_name: str
    ) -> Credential:
        """Fetch a credential row or raise EntityNotFoundException.

        Parameters
        ----------
        service : str
            Financial service name (e.g. "credit_cards", "banks").
        provider : str
            Provider name within the service (e.g. "isracard", "hapoalim").
        account_name : str
            Identifier of the account.

        Returns
        -------
        Credential
            The ORM model instance matching the given service, provider, and
            account_name.

        Raises
        ------
        EntityNotFoundException
            If no credential row matching the given combination is found in the
            database.
        """
        cred = self.db.execute(
            select(Credential).where(
                Credential.service == service,
                Credential.provider == provider,
                Credential.account_name == account_name,
            )
        ).scalar_one_or_none()
        if cred is None:
            raise EntityNotFoundException(
                f"Credentials for {service} {provider} {account_name} not found"
            )
        return cred

    def get_credentials(
        self, service: str, provider: str, account_name: str
    ) -> Dict:
        """Get credentials for an account, merging in keyring password.

        Parameters
        ----------
        service : str
            Financial service name (e.g. "credit_cards", "banks").
        provider : str
            Provider name within the service (e.g. "isracard", "hapoalim").
        account_name : str
            Identifier of the account.

        Returns
        -------
        Dict
            Credential fields dict for the account with the password merged in
            from the OS Keyring. The "password" key is always present; it is an
            empty string if no password has been stored in the keyring.

        Raises
        ------
        EntityNotFoundException
            If no credential row for the given account is found in the database.
        """
        cred = self._find_credential(service, provider, account_name)
        result = dict(cred.fields)
        result["password"] = (
            keyring.get_password(
                self.keyring_service,
                self._keyring_key(service, provider, account_name, "password"),
            )
            or ""
        )
        return result

    def save_credentials(
        self,
        service: str,
        provider: str,
        account_name: str,
        credentials: Dict,
    ) -> None:
        """Persist credentials for an account, routing sensitive fields to the OS Keyring.

        Parameters
        ----------
        service : str
            Financial service name (e.g. "credit_cards", "banks").
        provider : str
            Provider name within the service (e.g. "isracard", "hapoalim").
        account_name : str
            Identifier of the account.
        credentials : Dict
            All credential fields for the account, including the password.

        Returns
        -------
        None

        Notes
        -----
        Fields matching ``_SENSITIVE_FIELDS`` (password, otpLongTermToken) are
        stored in the OS Keyring; all remaining fields are persisted to the
        database. This method upserts: it creates a new credential row if one
        does not exist, or updates the fields on the existing row.
        """
        fields = dict(credentials)

        for sensitive_field in _SENSITIVE_FIELDS:
            value = fields.pop(sensitive_field, None)
            if value is not None:
                keyring.set_password(
                    self.keyring_service,
                    self._keyring_key(service, provider, account_name, sensitive_field),
                    value or "",
                )

        existing = self.db.execute(
            select(Credential).where(
                Credential.service == service,
                Credential.provider == provider,
                Credential.account_name == account_name,
            )
        ).scalar_one_or_none()

        if existing is not None:
            existing.fields = fields
        else:
            self.db.add(
                Credential(
                    service=service,
                    provider=provider,
                    account_name=account_name,
                    fields=fields,
                )
            )
        self.db.commit()

    def delete_credentials(
        self, service: str, provider: str, account_name: str
    ) -> None:
        """Delete a credential from DB and clean up keyring entries.

        Parameters
        ----------
        service : str
            Financial service name (e.g. "credit_cards", "banks").
        provider : str
            Provider name within the service (e.g. "isracard", "hapoalim").
        account_name : str
            Identifier of the account.

        Raises
        ------
        EntityNotFoundException
            If no credential row for the given account is found in the database.

        Notes
        -----
        After removing the database row, also attempts to delete the password,
        secret, otp_key, and otpLongTermToken entries from the OS Keyring.
        Keyring entries that do not exist are silently ignored.
        """
        cred = self._find_credential(service, provider, account_name)
        self.db.delete(cred)
        self.db.commit()

        for field in ("password", "secret", "otp_key", "otpLongTermToken"):
            try:
                keyring.delete_password(
                    self.keyring_service,
                    self._keyring_key(service, provider, account_name, field),
                )
            except keyring.errors.PasswordDeleteError:
                pass

    def list_accounts(self) -> List[Dict[str, str]]:
        """Get a flat list of all configured accounts.

        Returns
        -------
        List[Dict[str, str]]
            List of dicts, one per stored credential row, each containing the
            keys: service, provider, and account_name.
        """
        rows = self.db.execute(select(Credential)).scalars().all()
        return [
            {
                "service": row.service,
                "provider": row.provider,
                "account_name": row.account_name,
            }
            for row in rows
        ]

    def get_all_credentials(self) -> Dict:
        """Get all credentials as nested dict with keyring passwords filled in.

        Returns
        -------
        Dict
            Nested dict in the form
            ``{service: {provider: {account_name: {field: value}}}}``
            for all stored credential rows, with the "password" field for each
            account merged in from the OS Keyring. The "password" key is always
            present; it is an empty string if no password has been stored in the
            keyring.
        """
        rows = self.db.execute(select(Credential)).scalars().all()
        result: Dict = {}
        for row in rows:
            result.setdefault(row.service, {}).setdefault(row.provider, {})
            fields = dict(row.fields)
            fields["password"] = (
                keyring.get_password(
                    self.keyring_service,
                    self._keyring_key(
                        row.service, row.provider, row.account_name, "password"
                    ),
                )
                or ""
            )
            result[row.service][row.provider][row.account_name] = fields
        return result

    def migrate_from_yaml(self, credentials_path: str) -> None:
        """One-time migration: import existing YAML credentials into DB.

        Skips if the credentials table already has data.
        Only imports non-sensitive fields; passwords remain in keyring.
        """
        existing = self.db.execute(select(Credential)).first()
        if existing is not None:
            return

        if not os.path.exists(credentials_path):
            return

        with open(credentials_path, "r") as f:
            all_creds = yaml.safe_load(f) or {}

        for service, providers in all_creds.items():
            if not isinstance(providers, dict):
                continue
            for provider, accounts in providers.items():
                if not isinstance(accounts, dict):
                    continue
                for account_name, fields in accounts.items():
                    if not isinstance(fields, dict):
                        continue
                    clean_fields = {
                        k: v
                        for k, v in fields.items()
                        if k not in _SENSITIVE_FIELDS
                    }
                    self.db.add(
                        Credential(
                            service=service,
                            provider=provider,
                            account_name=account_name,
                            fields=clean_fields,
                        )
                    )
        self.db.commit()
