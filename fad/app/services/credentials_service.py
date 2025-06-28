from copy import deepcopy

import streamlit as st

from fad.app.data_access.credentials_repository import CredentialsRepository


class CredentialsService:
    """
    Service class for managing user credentials for various financial services.

    This class provides methods for retrieving, filtering, saving, and deleting
    credential information for different financial services like banks, credit cards,
    and insurance companies.

    Attributes
    ----------
    creds_access : CredentialsRepository
        Repository instance for accessing and persisting credentials.
    credentials : dict
        Dictionary containing all user credentials.
    """
    def __init__(self):
        """
        Initialize the CredentialsService.

        Creates an instance of CredentialsRepository and loads the credentials.
        """
        self.creds_access = CredentialsRepository()
        self.credentials = self.creds_access.credentials
    
    def save_credentials(self, credentials: dict):
        self.creds_access.save_credentials(credentials)

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
        self.creds_access.save_credentials(credentials)
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
        self.creds_access.save_credentials(credentials)

