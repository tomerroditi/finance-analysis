from copy import deepcopy

import streamlit as st

from fad.app.data_access.credentials_repository import CredentialsRepository


class CredentialsService:
    def __init__(self):
        self.creds_access = CredentialsRepository()
        self.credentials = self.creds_access.credentials

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
        if provider not in credentials[service].keys():
            return
        if account_name in credentials[service][provider].keys():
            st.error("Account name already exists. Please choose a different name.")

    def save_new_data_source(
        self, credentials: dict, service: str, provider: str, account_name: str
    ) -> None:
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
        del credentials[service][provider][account]
        self.creds_access.save_credentials(credentials)
