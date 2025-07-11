from copy import deepcopy
from typing import Dict

import streamlit as st

from fad import CREDENTIALS_PATH
from fad.app.data_access.credentials_repository import CredentialsRepository
from fad.app.naming_conventions import LoginFields


class CredentialsService:
    """
    Service class for managing user credentials for various financial services.

    This class provides methods for retrieving, filtering, saving, and deleting
    credential information for different financial services like banks, credit cards,
    and insurance companies. Contains all business logic for credential management.

    Attributes
    ----------
    creds_repository : CredentialsRepository
        Repository instance for accessing and persisting credentials.
    credentials : dict
        Dictionary containing all user credentials.
    """
    def __init__(self):
        """
        Initialize the CredentialsService.

        Creates an instance of CredentialsRepository and loads the credentials.
        """
        self.creds_repository = CredentialsRepository()
        self.credentials = self.load_credentials()

    def generate_keyring_key(self, service: str, provider: str, account: str, field: str) -> str:
        """
        Generate a unique key for storing credentials in the keyring.

        Creates a colon-separated string that uniquely identifies a credential field.

        Parameters
        ----------
        service : str
            The type of service (e.g., 'banks', 'credit_cards', 'insurances').
        provider : str
            The name of the service provider.
        account : str
            The name of the account.
        field : str
            The specific credential field (e.g., 'password', 'username').

        Returns
        -------
        str
            A unique key string in the format "service:provider:account:field".
        """
        return f"{service}:{provider}:{account}:{field}"

    def load_credentials(self) -> Dict:
        """
        Load credentials with complete business logic.

        Reads credentials from the YAML file, ensuring the file exists and has the correct
        structure. Creates a default file if none exists. Retrieves passwords from the
        system keyring and injects a placeholder ("***") into the credentials dictionary
        for password fields, unless explicitly needed for authentication.

        Returns
        -------
        Dict
            A dictionary containing all user credentials with the structure:
            {service: {provider: {account: {field: value}}}}
            Password fields are set to '***' for security.
        """
        # Read existing credentials or create default
        credentials = self.creds_repository.read_credentials_file()

        if credentials is None:
            # Create default credentials file
            credentials = self.creds_repository.read_default_credentials()
            self.creds_repository.write_credentials_file(credentials)
            self.creds_repository.set_file_permissions(CREDENTIALS_PATH)

        # Ensure all expected login fields are present and inject password placeholders
        for service, providers in credentials.items():
            for provider, accounts in providers.items():
                for account, fields in accounts.items():
                    # Get expected login fields for this provider
                    expected_fields = LoginFields.get_fields(provider)
                    for field in expected_fields:
                        if field not in fields:
                            fields[field] = ""
                        if 'password' in field.lower():
                            # Do not inject the real password, use a placeholder
                            fields[field] = "***"

        return credentials

    def save_credentials(self, credentials: Dict) -> None:
        """
        Save credentials with complete business logic.

        Cleans up the credentials dictionary by removing empty entries, securely stores
        passwords in the system keyring, and saves the non-sensitive parts to the YAML file.
        Sets appropriate file permissions on the saved file.

        Parameters
        ----------
        credentials : Dict
            The credentials dictionary to save, with the structure:
            {service: {provider: {account: {field: value}}}}
        """
        # Clean up empty entries
        credentials = self._cleanup_empty_entries(credentials)

        # Store passwords in keyring, save placeholder in YAML
        credentials_to_save = {}
        for service, providers in credentials.items():
            credentials_to_save.setdefault(service, {})
            for provider, accounts in providers.items():
                credentials_to_save[service].setdefault(provider, {})
                for account, fields in accounts.items():
                    credentials_to_save[service][provider].setdefault(account, {})
                    for field, value in fields.items():
                        if 'password' in field.lower():
                            key = self.generate_keyring_key(service, provider, account, field)
                            self.creds_repository.set_password_in_keyring(key, value or "")
                            credentials_to_save[service][provider][account][field] = "your password is safely stored"
                        else:
                            credentials_to_save[service][provider][account][field] = value

        # Save to file and set permissions
        self.creds_repository.write_credentials_file(credentials_to_save)
        self.creds_repository.set_file_permissions(CREDENTIALS_PATH)

    def _cleanup_empty_entries(self, credentials: Dict) -> Dict:
        """
        Remove empty accounts and providers from credentials.

        Parameters
        ----------
        credentials : Dict
            The credentials dictionary to clean up.

        Returns
        -------
        Dict
            The cleaned credentials dictionary.
        """
        # Create a copy to avoid modifying during iteration
        cleaned_credentials = deepcopy(credentials)

        # Remove empty accounts/providers
        while True:
            deleted = False
            for service, providers in cleaned_credentials.items():
                if providers == {}:
                    continue
                for provider, accounts in list(providers.items()):
                    if len(accounts) == 0:
                        del cleaned_credentials[service][provider]
                        deleted = True
                        break
                    for account, fields in list(accounts.items()):
                        if len(fields) == 0:
                            del cleaned_credentials[service][provider][account]
                            deleted = True
                            break
            if not deleted:
                break

        return cleaned_credentials

    def get_available_data_sources(self) -> list[str]:
        """
        Get a list of available services based on the credentials.

        Returns
        -------
        list[str]
            A list of available data sources in the format of "Service - Provider - Account"
        """
        available_scrapers = []
        for service, providers in self.credentials.items():
            for provider, accounts in providers.items():
                for account in accounts.keys():
                    available_scrapers.append(f"{service} - {provider} - {account}")

        return available_scrapers

    def get_data_sources_credentials(self, data_sources: list[str]) -> dict:
        """
        This method filters the stored credentials based on the provided list of
        data sources. It removes credentials for accounts that are not included
        in the list of data sources.

        Parameters
        ----------
        data_sources : list[str]
            A list of strings representing the data sources for which credentials should be retained. The format is
            "Service - Provider - Account".

        Returns
        -------
        dict:
            A deep copy of the filtered credentials dictionary where only the relevant credentials for the given data
            sources are included.
        """
        creds_to_use = deepcopy(self.credentials)
        for service, providers in self.credentials.items():
            for provider, accounts in providers.items():
                for account, cred in accounts.items():
                    if f"{service} - {provider} - {account}" not in data_sources:
                        creds_to_use[service][provider].pop(account, None)

        return creds_to_use

    def check_accounts_duplication(
        self, credentials: dict, service: str, provider: str, account_name: str
    ) -> None:
        """
        Check if an account name already exists for a given provider and service.

        This method is used as a callback for Streamlit input fields to validate
        that new account names don't duplicate existing ones.

        Parameters
        ----------
        credentials : dict
            Dictionary containing all user credentials.
        service : str
            The type of service (e.g., 'banks', 'credit_cards', 'insurances').
        provider : str
            The name of the service provider.
        account_name : str
            The name of the account to check for duplication.

        Returns
        -------
        None
            Displays an error message if the account name already exists.
        """
        if provider not in credentials[service].keys():
            return
        if account_name in credentials[service][provider].keys():
            st.error("Account name already exists. Please choose a different name.")

    def save_new_data_source(
        self, credentials: dict, service: str, provider: str, account_name: str
    ) -> None:
        """
        Save a new data source (account) to the credentials.

        Validates that all required fields are filled before saving the new account.
        Clears the session state after successful save to reset the form.

        Parameters
        ----------
        credentials : dict
            Dictionary containing all user credentials.
        service : str
            The type of service (e.g., 'banks', 'credit_cards', 'insurances').
        provider : str
            The name of the service provider.
        account_name : str
            The name of the new account to save.

        Returns
        -------
        None
            Displays an error message if validation fails, otherwise saves the credentials.
        """
        if any(
            [(v == "" or v is None) for v in credentials[service][provider][account_name].values()]
        ):
            st.error("Please fill all the displayed fields.", icon="🚨")
            st.stop()
        self.save_credentials(credentials)
        st.session_state.clear()

    def delete_account(
        self, credentials: dict, service: str, provider: str, account: str
    ) -> None:
        """
        Delete an account from the credentials.

        Removes the specified account from the credentials dictionary and saves the updated credentials.

        Parameters
        ----------
        credentials : dict
            Dictionary containing all user credentials.
        service : str
            The type of service (e.g., 'banks', 'credit_cards', 'insurances').
        provider : str
            The name of the service provider.
        account : str
            The name of the account to delete.

        Returns
        -------
        None
        """
        del credentials[service][provider][account]
        self.save_credentials(credentials)

    def get_scraper_credentials(self, service, provider, account):
        """
        Fetch credentials for a specific scraper or multiple scrapers.

        Parameters
        ----------
        service : str or list[str]
            The service name(s) (e.g., 'banks', 'credit_cards', etc.).
        provider : str or list[str]
            The provider name(s).
        account : str or list[str]
            The account name(s).

        Returns
        -------
        dict
            A credentials dictionary containing only the requested credentials, structured as:
            {service: {provider: {account: {fields...}}}}
        """
        # Normalize to lists
        if isinstance(service, str):
            service = [service]
        if isinstance(provider, str):
            provider = [provider]
        if isinstance(account, str):
            account = [account]
        result = {}
        for s in service:
            if s not in self.credentials:
                continue
            for p in provider:
                if p not in self.credentials[s]:
                    continue
                for a in account:
                    if a not in self.credentials[s][p]:
                        continue
                    result.setdefault(s, {}).setdefault(p, {})[a] = self.credentials[s][p][a]
        return result
