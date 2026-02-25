"""Credentials service with pure SQLAlchemy (no Streamlit dependencies).

This module provides business logic for credential management.
"""

from copy import deepcopy
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from backend.config import AppConfig
from backend.constants.providers import Fields, bank_providers, cc_providers
from backend.repositories.credentials_repository import CredentialsRepository

# In-memory cache for credentials
_credentials_cache: Optional[Dict] = None


class CredentialsService:
    """
    Service for managing user credentials for financial services.

    Credentials are stored in a DB-backed repository (non-sensitive fields)
    with passwords kept in the OS Keyring. An in-memory cache
    (``_credentials_cache``) avoids repeated DB/Keyring lookups. All
    mutation operations invalidate the cache.
    """

    def __init__(self, db: Session):
        """
        Initialize the credentials service.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.repository = CredentialsRepository(db)
        self.credentials = self.load_credentials()

    def load_credentials(self) -> Dict:
        """
        Load all credentials with passwords retrieved from the OS Keyring.

        Uses the in-memory cache if available; otherwise fetches from the
        repository (which reads the YAML and Keyring) and populates the cache.

        Returns
        -------
        dict
            Deep copy of the full credentials dict in the form
            ``{service: {provider: {account_name: {field: value}}}}``.
        """
        global _credentials_cache

        if _credentials_cache is not None:
            return deepcopy(_credentials_cache)

        credentials = self.repository.get_all_credentials()
        _credentials_cache = credentials
        return deepcopy(credentials)

    def save_credentials(self, credentials: Dict) -> None:
        """
        Save credentials for all provided accounts.

        Iterates the nested credentials dict and persists each account's fields.
        Passwords are stored in the OS Keyring; other fields go to the DB via
        the repository. Empty accounts (no non-empty fields) are skipped.
        Invalidates the cache after saving.

        Parameters
        ----------
        credentials : dict
            Nested credentials in the form
            ``{service: {provider: {account_name: {field: value}}}}``.
        """
        global _credentials_cache

        for service, providers in credentials.items():
            if not isinstance(providers, dict):
                continue
            for provider, accounts in providers.items():
                if not isinstance(accounts, dict):
                    continue
                for account_name, fields in accounts.items():
                    if not isinstance(fields, dict):
                        continue
                    if not fields or all(not v for v in fields.values()):
                        continue
                    self.repository.save_credentials(
                        service, provider, account_name, dict(fields)
                    )

        _credentials_cache = None
        self.credentials = self.load_credentials()

    def get_available_data_sources(self) -> List[str]:
        """
        Get a flat list of all configured data source identifiers.

        Returns
        -------
        list[str]
            Strings in the format ``"service - provider - account_name"``
            for every account in the loaded credentials.
        """
        data_sources = []
        for service, providers in self.credentials.items():
            for provider, accounts in providers.items():
                for account in accounts.keys():
                    data_sources.append(f"{service} - {provider} - {account}")
        return data_sources

    def get_data_sources_credentials(self, data_sources: List[str]) -> Dict:
        """
        Filter the credentials dict to only include the selected data sources.

        Parameters
        ----------
        data_sources : list[str]
            Account identifiers in the form ``"service - provider - account_name"``
            to keep.

        Returns
        -------
        dict
            Filtered credentials dict containing only the specified accounts.
        """
        credentials = deepcopy(self.credentials)

        for service, providers in list(credentials.items()):
            for provider, accounts in list(providers.items()):
                for account in list(accounts.keys()):
                    if f"{service} - {provider} - {account}" not in data_sources:
                        del credentials[service][provider][account]

                if not accounts:
                    del credentials[service][provider]

            if not providers:
                del credentials[service]

        return credentials

    def delete_account(self, service: str, provider: str, account: str) -> None:
        """
        Delete an account's credentials from the repository and invalidate the cache.

        Parameters
        ----------
        service : str
            Service type (e.g. ``"banks"``).
        provider : str
            Provider identifier.
        account : str
            Account name.
        """
        self.repository.delete_credentials(service, provider, account)
        self._invalidate_cache()

    def get_scraper_credentials(self, service, provider, account) -> Dict:
        """
        Fetch credentials for a specific scraper (or multiple scrapers).

        Accepts string or list for each parameter and returns only the
        matching subset of the credentials dict.

        Parameters
        ----------
        service : str or list[str]
            Service type(s) to include.
        provider : str or list[str]
            Provider identifier(s) to include.
        account : str or list[str]
            Account name(s) to include.

        Returns
        -------
        dict
            Filtered credentials dict containing only the requested accounts.
        """
        credentials = deepcopy(self.credentials)

        services = [service] if isinstance(service, str) else service
        providers = [provider] if isinstance(provider, str) else provider
        accounts = [account] if isinstance(account, str) else account

        filtered = {}
        for svc in services:
            if svc not in credentials:
                continue
            filtered[svc] = {}
            for prov in providers:
                if prov not in credentials[svc]:
                    continue
                filtered[svc][prov] = {}
                for acc in accounts:
                    if acc in credentials[svc][prov]:
                        filtered[svc][prov][acc] = credentials[svc][prov][acc]

        return filtered

    def get_safe_credentials(self) -> Dict:
        """
        Get all credentials with sensitive data (passwords) removed.

        Returns only account names, not any field values.

        Returns
        -------
        dict
            Nested dict in the form ``{service: {provider: [account_names]}}``.
        """
        accounts = self.repository.list_accounts()
        safe: Dict = {}
        for a in accounts:
            safe.setdefault(a["service"], {}).setdefault(a["provider"], [])
            safe[a["service"]][a["provider"]].append(a["account_name"])
        return safe

    def get_accounts_list(self) -> List[Dict[str, str]]:
        """
        Get a flat list of all configured accounts.

        Returns
        -------
        list[dict]
            List of account dicts with ``service``, ``provider``, and
            ``account_name`` keys.
        """
        return self.repository.list_accounts()

    @staticmethod
    def get_available_providers() -> Dict[str, List[str]]:
        """
        Get available providers filtered by the current demo/production mode.

        Providers whose names contain ``"test_"`` are only shown in demo mode,
        and excluded in production mode.

        Returns
        -------
        dict
            Dictionary with keys ``"banks"`` and ``"credit_cards"``, each
            containing a list of provider identifier strings.
        """
        is_demo = AppConfig().is_demo_mode
        banks = [p for p in bank_providers if ("test_" in p) == is_demo]
        ccs = [p for p in cc_providers if ("test_" in p) == is_demo]
        return {"banks": banks, "credit_cards": ccs}

    def delete_credential(self, service: str, provider: str, account_name: str) -> None:
        """
        Delete a credential and clean up associated Keyring entries.

        Parameters
        ----------
        service : str
            Service type (e.g. ``"banks"``).
        provider : str
            Provider identifier.
        account_name : str
            Account name whose credentials should be deleted.
        """
        self.repository.delete_credentials(service, provider, account_name)
        self._invalidate_cache()

    def seed_demo_credentials(self) -> None:
        """
        Seed dummy credentials for all demo scrapers if not already present.

        Creates credentials for ``test_bank``, ``test_bank_2fa``,
        ``test_credit_card``, and ``test_credit_card_2fa`` providers.
        Each credential is only inserted if not already in the repository.
        """
        from backend.errors import EntityNotFoundException

        def ensure_dummy_cred(service, provider, account, creds_payload):
            try:
                self.repository.get_credentials(service, provider, account)
            except EntityNotFoundException:
                self.repository.save_credentials(
                    service, provider, account, creds_payload
                )
                self._invalidate_cache()

        ensure_dummy_cred(
            "banks", "test_bank", "Test Bank",
            {Fields.USERNAME.value: "test", Fields.PASSWORD.value: "password"},
        )
        ensure_dummy_cred(
            "banks", "test_bank_2fa", "Test Bank 2FA",
            {
                Fields.EMAIL.value: "test@example.com",
                Fields.PASSWORD.value: "password",
                Fields.PHONE_NUMBER.value: "12345678",
            },
        )
        ensure_dummy_cred(
            "credit_cards", "test_credit_card", "Test Credit Card",
            {Fields.USERNAME.value: "test", Fields.PASSWORD.value: "password"},
        )
        ensure_dummy_cred(
            "credit_cards", "test_credit_card_2fa", "Test Credit Card 2FA",
            {
                Fields.EMAIL.value: "test@example.com",
                Fields.PASSWORD.value: "password",
                Fields.PHONE_NUMBER.value: "12345678",
            },
        )

    def _invalidate_cache(self) -> None:
        """Clear cache and reload."""
        global _credentials_cache
        _credentials_cache = None
        self.credentials = self.load_credentials()

    @staticmethod
    def clear_cache() -> None:
        """Clear the in-memory credentials cache."""
        global _credentials_cache
        _credentials_cache = None
