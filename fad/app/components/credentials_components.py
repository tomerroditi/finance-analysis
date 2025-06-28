import streamlit as st
from streamlit_phone_number import st_phone_number
from typing import Literal

from fad.app.services.credentials_service import CredentialsService
from fad.app.naming_conventions import Banks, CreditCards, Insurances, LoginFields, DisplayFields


class CredentialsComponents:
    """
    A utility class providing various components and functionalities for managing user
    credentials across different services.

    This class includes static methods to handle data interaction for services like
    credit cards, banks, and insurances. It enables operations such as editing or
    deleting existing credentials, adding new data sources, and rendering relevant
    user interface components. The class relies on integrations with other utility
    and service classes to streamline interaction, persistence, and validation of user data.

    Attributes
    ----------
    credentials_service : CredentialsService
        An instance of `CredentialsService` used for credential
        operations like saving and deleting accounts.
    credentials_repository : CredentialsRepository
        An instance of `CredentialsRepository` used for
        interacting with the persistence layer.
    """
    def __init__(self):
        """
        Initialize the CredentialsComponents class.

        Creates instances of CredentialsService and CredentialsRepository for handling
        credential operations and data persistence.
        """
        self.credentials_service = CredentialsService()

    @st.fragment
    def edit_delete_credentials(self, credentials: dict, service: Literal['credit_cards', 'banks', 'insurances']) -> None:
        """
        Render UI components for editing or deleting existing credentials.

        This method creates expandable sections for each account under the specified service,
        allowing users to edit credential details or delete accounts.

        Parameters
        ----------
        credentials : dict
            Dictionary containing all user credentials organized by service, provider, and account.
        service : {'credit_cards', 'banks', 'insurances'}
            The type of service for which to display credentials.

        Returns
        -------
        None
        """
        for provider, accounts in credentials[service].items():
            for account, creds in accounts.items():
                with st.expander(f"{provider} - {account}"):
                    CredentialsComponents._generate_text_input_widgets(provider, account, creds)
                    cont_buttons = st.container()
                    cont_success = st.container()
                    if cont_buttons.button(
                            'Save',
                            key=f'{service}_{provider}_{account}_edit_credentials__save',
                            on_click=self.credentials_service.save_credentials,
                            args=(credentials,)
                    ):
                        cont_success.success('Credentials saved successfully')
                    if cont_buttons.button('Delete', key=f'{provider}_{account}_delete', type='primary'):
                        CredentialsComponents._delete_account_dialog(credentials, service, provider, account)

    @staticmethod
    @st.fragment
    def _generate_text_input_widgets(provider: str, account: str, creds: dict[str, str]) -> None:
        """
        Generate text input widgets for credential fields.

        Creates appropriate Streamlit input widgets for each credential field,
        handling special cases like passwords with masked input.

        Parameters
        ----------
        provider : str
            The name of the service provider (e.g., bank name, credit card company).
        account : str
            The name of the specific account.
        creds : dict[str, str]
            Dictionary of credential field names and their values.

        Returns
        -------
        None
        """
        for field, value in creds.items():
            label = DisplayFields.get_display(field)
            if label == 'otpLongTermToken':
                continue
            elif label == 'Password':
                creds[field] = st.text_input(label, value, key=f'{provider}_{account}_{field}', type='password')
            else:
                creds[field] = st.text_input(label, value, key=f'{provider}_{account}_{field}')

    @staticmethod
    @st.dialog('verify deletion')
    def _delete_account_dialog(credentials: dict, service: str, provider: str, account: str) -> None:
        """
        Display a confirmation dialog for account deletion.

        Creates a Streamlit dialog asking the user to confirm deletion of an account,
        with options to proceed or cancel.

        Parameters
        ----------
        credentials : dict
            Dictionary containing all user credentials.
        service : str
            The type of service (e.g., 'banks', 'credit_cards', 'insurances').
        provider : str
            The name of the service provider.
        account : str
            The name of the account to be deleted.

        Returns
        -------
        None
        """
        st.write('Are you sure you want to delete this account?')
        if st.button(
                'Yes',
                key=f'delete_{service}_{provider}_{account}',
                on_click=CredentialsService().delete_account,
                args=(credentials, service, provider, account)
        ):
            st.rerun()
        if st.button('Cancel', key=f'cancel_delete_{service}_{provider}_{account}'):
            st.rerun()

    @staticmethod
    @st.fragment
    def add_new_data_source(credentials: dict, service: Literal['credit_cards', 'banks', 'insurances']) -> None:
        """
        Render UI components for adding a new data source (account).

        Creates a form-like interface for users to add a new account for the specified service,
        with appropriate input fields based on the selected provider.

        Parameters
        ----------
        credentials : dict
            Dictionary containing all user credentials.
        service : {'credit_cards', 'banks', 'insurances'}
            The type of service for which to add a new account.

        Returns
        -------
        None
        """
        if st.button(
                f"Add a new {service.replace('_', ' ').rstrip('s')} account",
                key=f"add_new_{service}_button"
        ):
            st.session_state[f'add_new_{service}'] = True

        if not st.session_state.get(f'add_new_{service}', False):
            return

        enum_class = Banks if service == 'banks' else CreditCards if service == 'credit_cards' else Insurances
        provider = st.selectbox('Select a provider', options=[provider.value for provider in enum_class],
                                key=f'select_{service}_provider')
        provider = provider.lower() if provider is not None else None

        if provider not in list(credentials[service].keys()):
            credentials[service][provider] = {}

        account_name = st.text_input(
            'Account name (how would you like to call the account)',
            key=f'new_{service}_account_name',
            on_change=CredentialsService().check_accounts_duplication,
            args=(
                credentials,
                service,
                provider,
                st.session_state.get(f'new_{service}_account_name', '')
            )
        )

        if account_name is None or account_name == '':
            if st.button('Cancel', key=f'cancel_add_new_{service}'):
                st.session_state.clear()
                st.rerun()
            return

        credentials[service][provider][account_name] = {}
        for field in LoginFields.get_fields(provider):
            label = DisplayFields.get_display(field)
            if 'phone' in label.lower():
                number: dict = st_phone_number(label, default_country='IL', key=f'new_{service}_{field}')
                if number is not None:
                    number: str = number['number']
                    if not number.startswith('+9725') and len(number) != 13:
                        st.error('Please enter a valid Israeli phone number')
                        st.stop()
                    else:
                        credentials[service][provider][account_name][field] = number
            else:
                credentials[service][provider][account_name][field] = (
                    st.text_input(
                        label,
                        key=f'new_{service}_{field}',
                        type='password' if 'password' in label.lower() else 'default'
                    )
                )

        if st.button('Save new account', key=f'save_new_{service}_data_source_button'):
            CredentialsService().save_new_data_source(credentials, service, provider, account_name)
            st.rerun()

        if st.button('Cancel', key=f'cancel_add_new_{service}'):
            del st.session_state[f'add_new_{service}']
            st.rerun()
