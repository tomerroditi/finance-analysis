import streamlit as st
from streamlit_phone_number import st_phone_number
from typing import Literal

from fad.app.services.credentials_service import CredentialsService
from fad.app.data_access.credentials_repository import CredentialsRepository
from fad.app.naming_conventions import Banks, CreditCards, Insurances, LoginFields, DisplayFields

class CredentialsComponents:
    def __init__(self):
        self.credentials_service = CredentialsService()
        self.credentials_repository = CredentialsRepository()

    @staticmethod
    @st.fragment
    def edit_delete_credentials(credentials: dict, service: Literal['credit_cards', 'banks', 'insurances']) -> None:
        repo = CredentialsRepository()  # Create an instance for saving
        for provider, accounts in credentials[service].items():
            for account, creds in accounts.items():
                with st.expander(f"{provider} - {account}"):
                    CredentialsComponents._generate_text_input_widgets(provider, account, creds)
                    cont_buttons = st.container()
                    cont_success = st.container()
                    if cont_buttons.button(
                            'Save',
                            key=f'{service}_{provider}_{account}_edit_credentials__save',
                            on_click=repo.save_credentials,
                            args=(credentials,)
                    ):
                        cont_success.success('Credentials saved successfully')
                    if cont_buttons.button('Delete', key=f'{provider}_{account}_delete', type='primary'):
                        CredentialsComponents._delete_account_dialog(credentials, service, provider, account)

    @staticmethod
    @st.fragment
    def _generate_text_input_widgets(provider: str, account: str, creds: dict[str, str]) -> None:
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
                number = st_phone_number(label, default_country='IL', key=f'new_{service}_{field}')
                if number is not None:
                    number = number['number']
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
