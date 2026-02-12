"""
Credentials service with pure SQLAlchemy (no Streamlit dependencies).

This module provides business logic for credential management.
"""

from copy import deepcopy
from typing import Dict, List, Optional

from backend.config import AppConfig
from backend.naming_conventions import Fields, bank_providers, cc_providers
from backend.repositories.credentials_repository import CredentialsRepository

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
            credentials = self.repository.generate_default_credentials()

        # Retrieve passwords from keyring
        for service, providers in credentials.items():
            for provider, accounts in providers.items():
                for account, fields in accounts.items():
                    for field, value in fields.items():
                        if field == Fields.PASSWORD.value:
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
                        if field == Fields.PASSWORD.value:
                            key = self.generate_keyring_key(
                                service, provider, account, field
                            )
                            self.repository.set_password_in_keyring(key, value)
                            credentials[service][provider][account][field] = ""

        self.repository.write_credentials_file(credentials)
        self.repository.set_file_permissions(AppConfig().get_credentials_path())

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

    def get_safe_credentials(self) -> Dict:
        """Get all credentials with sensitive data removed."""
        credentials = self.repository.read_credentials_file()
        if credentials is None:
            return {}

        safe_credentials = {}
        for service, providers in credentials.items():
            safe_credentials[service] = {}
            for provider, accounts in providers.items():
                safe_credentials[service][provider] = list(accounts.keys())

        return safe_credentials

    def get_accounts_list(self) -> List[Dict[str, str]]:
        """Get a flat list of all configured accounts."""
        credentials = self.repository.read_credentials_file()
        if credentials is None:
            return []

        accounts = []
        for service, providers in credentials.items():
            for provider, account_dict in providers.items():
                for account_name in account_dict.keys():
                    accounts.append(
                        {
                            "service": service,
                            "provider": provider,
                            "account_name": account_name,
                        }
                    )
        return accounts

    @staticmethod
    def get_available_providers() -> Dict[str, List[str]]:
        """Get available providers filtered by test/production mode."""
        is_test = AppConfig().is_test_mode
        banks = [p for p in bank_providers if ("test_" in p) == is_test]
        ccs = [p for p in cc_providers if ("test_" in p) == is_test]
        return {"banks": banks, "credit_cards": ccs}

    def delete_credential(self, service: str, provider: str, account_name: str) -> None:
        """Delete a credential from YAML and clean up keyring entries."""
        credentials = self.repository.read_credentials_file()
        if credentials is None:
            raise ValueError("No credentials found")

        del credentials[service][provider][account_name]

        # Clean up empty structures
        if not credentials[service][provider]:
            del credentials[service][provider]
        if not credentials[service]:
            del credentials[service]

        self.repository.write_credentials_file(credentials)

        # Delete from Keyring (best effort)
        for key in ["password", "secret", "otp_key"]:
            keyring_key = f"{service}_{provider}_{account_name}_{key}"
            self.repository.delete_password_from_keyring(keyring_key)

    def seed_test_credentials(self) -> None:
        """Seed dummy credentials for test mode."""
        from backend.errors import EntityNotFoundException

        def ensure_dummy_cred(service, provider, account, creds_payload):
            try:
                self.repository.get_credentials(service, provider, account)
            except EntityNotFoundException:
                service_creds = self.credentials
                if service not in service_creds:
                    service_creds[service] = {}
                if provider not in service_creds[service]:
                    service_creds[service][provider] = {}

                formatted_creds = {}
                if "username" in creds_payload:
                    formatted_creds[Fields.USERNAME.value] = creds_payload["username"]
                if "password" in creds_payload:
                    formatted_creds[Fields.PASSWORD.value] = creds_payload["password"]
                if "otpLongTermToken" in creds_payload:
                    formatted_creds["otpLongTermToken"] = creds_payload[
                        "otpLongTermToken"
                    ]
                elif "email" in creds_payload:
                    formatted_creds[Fields.EMAIL.value] = creds_payload["email"]
                    formatted_creds[Fields.PHONE_NUMBER.value] = creds_payload.get(
                        "phoneNumber", ""
                    )

                if not formatted_creds:
                    formatted_creds = creds_payload

                service_creds[service][provider][account] = formatted_creds
                self.save_credentials(service_creds)

        # Banks
        ensure_dummy_cred(
            "banks",
            "test_bank",
            "Test Bank",
            {"username": "test", "password": "password"},
        )
        ensure_dummy_cred(
            "banks",
            "test_bank_2fa",
            "Test Bank 2FA",
            {
                "email": "test@example.com",
                "password": "password",
                "phoneNumber": "12345678",
            },
        )

        # Credit Cards
        ensure_dummy_cred(
            "credit_cards",
            "test_credit_card",
            "Test Credit Card",
            {"username": "test", "password": "password"},
        )
        ensure_dummy_cred(
            "credit_cards",
            "test_credit_card_2fa",
            "Test Credit Card 2FA",
            {
                "email": "test@example.com",
                "password": "password",
                "phoneNumber": "12345678",
            },
        )

    @staticmethod
    def clear_cache() -> None:
        """Clear the in-memory credentials cache."""
        global _credentials_cache
        _credentials_cache = None
