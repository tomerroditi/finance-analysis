"""
Credentials service with pure SQLAlchemy (no Streamlit dependencies).

This module provides business logic for credential management.
"""

import os
from copy import deepcopy
from typing import Dict, Optional, List

from backend.repositories.credentials_repository import (
    CredentialsRepository,
    CREDENTIALS_PATH,
)
from backend.naming_conventions import LoginFields


# In-memory cache for credentials (replaces Streamlit session_state)
_credentials_cache: Optional[Dict] = None


class CredentialsService:
    """
    Service for managing user credentials for financial services.

    Provides methods for retrieving, filtering, saving, and deleting credentials
    for various financial service providers.
    """

    def __init__(self):
        """Initialize the CredentialsService."""
        self.repository = CredentialsRepository()
        self.credentials = self.load_credentials()

    @staticmethod
    def generate_keyring_key(
        service: str, provider: str, account: str, field: str
    ) -> str:
        """Generate a unique key for storing credentials in the keyring."""
        return f"{service}:{provider}:{account}:{field}"

    def load_credentials(self) -> Dict:
        """
        Load credentials with complete business logic.

        Reads credentials from the YAML file, retrieves passwords from keyring.
        """
        global _credentials_cache

        if _credentials_cache is not None:
            return deepcopy(_credentials_cache)

        credentials = self.repository.read_credentials_file()

        if credentials is None:
            credentials = self.repository.read_default_credentials()
            self.repository.write_credentials_file(credentials)

        # Retrieve passwords from keyring
        for service, providers in credentials.items():
            for provider, accounts in providers.items():
                for account, fields in accounts.items():
                    for field, value in fields.items():
                        if field == LoginFields.PASSWORD.value:
                            key = self.generate_keyring_key(
                                service, provider, account, field
                            )
                            password = self.repository.get_password_from_keyring(key)
                            credentials[service][provider][account][field] = (
                                password or ""
                            )

        _credentials_cache = credentials
        return deepcopy(credentials)

    def save_credentials(self, credentials: Dict) -> None:
        """
        Save credentials with complete business logic.

        Stores passwords in keyring and saves non-sensitive parts to YAML.
        """
        global _credentials_cache

        credentials = self._cleanup_empty_entries(credentials)

        # Store passwords in keyring and clear from credentials
        for service, providers in credentials.items():
            for provider, accounts in providers.items():
                for account, fields in accounts.items():
                    for field, value in fields.items():
                        if field == LoginFields.PASSWORD.value:
                            key = self.generate_keyring_key(
                                service, provider, account, field
                            )
                            self.repository.set_password_in_keyring(key, value)
                            credentials[service][provider][account][field] = ""

        self.repository.write_credentials_file(credentials)
        self.repository.set_file_permissions(CREDENTIALS_PATH)

        _credentials_cache = None  # Clear cache to force reload
        self.credentials = self.load_credentials()

    def _cleanup_empty_entries(self, credentials: Dict) -> Dict:
        """Remove empty accounts and providers from credentials."""
        cleaned = deepcopy(credentials)
        services_to_remove = []

        for service, providers in cleaned.items():
            providers_to_remove = []
            for provider, accounts in providers.items():
                accounts_to_remove = []
                for account, fields in accounts.items():
                    if not fields or all(not v for v in fields.values()):
                        accounts_to_remove.append(account)

                for account in accounts_to_remove:
                    del cleaned[service][provider][account]

                if not accounts:
                    providers_to_remove.append(provider)

            for provider in providers_to_remove:
                del cleaned[service][provider]

            if not providers:
                services_to_remove.append(service)

        for service in services_to_remove:
            del cleaned[service]

        return cleaned

    def get_available_data_sources(self) -> List[str]:
        """Get a list of available services based on the credentials."""
        data_sources = []
        for service, providers in self.credentials.items():
            for provider, accounts in providers.items():
                for account in accounts.keys():
                    data_sources.append(f"{service} - {provider} - {account}")
        return data_sources

    def get_data_sources_credentials(self, data_sources: List[str]) -> Dict:
        """Filter credentials based on selected data sources."""
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
        """Delete an account from the credentials."""
        credentials = deepcopy(self.credentials)

        if (
            service in credentials
            and provider in credentials[service]
            and account in credentials[service][provider]
        ):
            del credentials[service][provider][account]
            self.save_credentials(credentials)

    def get_scraper_credentials(self, service, provider, account) -> Dict:
        """Fetch credentials for a specific scraper or multiple scrapers."""
        credentials = deepcopy(self.credentials)

        # Handle single or list parameters
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

    @staticmethod
    def clear_cache() -> None:
        """Clear the in-memory credentials cache."""
        global _credentials_cache
        _credentials_cache = None
