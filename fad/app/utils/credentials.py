"""
This module contains utility functions for handling the credentials in the app.
The credentials are stored in a yaml file and are loaded and saved using the yaml module.
The structure of the credentials dictionary is as follows:
credit_cards:
    provider1:
        account1:
            my_parameter: some_value
            another_parameter: some_other_value
        account2:
            my_parameter: yet_another_value
            another_parameter: and_another_value
    ...
banks:
    provider1:
        account1:
            some_parameter: value_1
            some_other_parameter: value_2
    ...
insurances:
    provider1:
        account1:
            other_parameter: value_3
            yet_another_parameter: value_4
"""

import streamlit as st
import yaml

from streamlit_phone_number import st_phone_number
from typing import Literal
from fad import CREDENTIALS_PATH
from fad.app.naming_conventions import (
    Banks,
    CreditCards,
    Insurances,
    LoginFields,
    DisplayFields,
)


two_fa_providers = [
    'onezero'
]

two_fa_contact = {
    'onezero': 'phoneNumber'
}

two_fa_field_name = {
    'onezero': 'otpLongTermToken'
}


def load_credentials() -> dict:
    """
    Load the credentials from the yaml file and cache the result to prevent reloading the file in every rerun.
    all changes to the returned dictionary object are affecting the cached object.

    Returns
    -------
    dict
        The credentials dictionary
    """
    with open(CREDENTIALS_PATH, 'r') as file:
        return yaml.safe_load(file)


def _save_credentials(credentials: dict) -> None:
    # remove empty accounts/providers credentials - leave an empty dict for unused services
    while True:
        deleted = False
        for service, providers in credentials.items():
            if providers == {}:
                continue
            for provider, accounts in providers.items():
                if len(accounts) == 0:
                    del credentials[service][provider]
                    deleted = True
                    break
                for account, creds in accounts.items():
                    if len(creds) == 0:
                        del credentials[service][provider][account]
                        deleted = True
                        break
        if not deleted:
            break

    # save the credentials to the yaml file
    with open(CREDENTIALS_PATH, 'w') as file:
        yaml.dump(credentials, file, sort_keys=False, indent=4)


def edit_delete_credentials(credentials: dict, service: Literal['credit_cards', 'banks', 'insurances']) -> None:
    """
    Edit or delete credentials for a given service.

    Parameters
    ----------
    credentials : dict
        The credentials dictionary
    service : str
        The service to edit, should be one of 'credit_cards', 'banks', or 'insurance'.
    """
    for provider, accounts in credentials[service].items():
        for account, creds in accounts.items():
            with st.expander(f"{provider} - {account}"):
                _generate_text_input_widgets(provider, account, creds)
                cont_buttons = st.container()
                cont_success = st.container()
                if cont_buttons.button(
                        'Save',
                        key=f'{service}_{provider}_{account}_edit_credentials__save',
                        on_click=_save_credentials,
                        args=(credentials,)
                ):
                    cont_success.success('Credentials saved successfully')

                if cont_buttons.button('Delete', key=f'{provider}_{account}_delete', type='primary'):
                    _delete_account_dialog(credentials, service, provider, account)


@st.fragment
def _generate_text_input_widgets(provider: str, account: str, creds: dict[str: str]) -> None:
    """
    Generate text input widgets for the given credentials. the function updates the credentials dictionary with the
    new values.

    Parameters
    ----------
    provider : str
        The provider for which to generate the text input widgets
    account : str
        The account for which to generate the text input widgets
    creds : dict
        The credentials for the given provider and account

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


@st.dialog('verify deletion')
def _delete_account_dialog(credentials: dict, service: str, provider: str, account: str) -> None:
    """
    Display a dialog to verify the deletion of the account. if the user confirms the deletion, the account will be
    deleted from the credentials dictionary and saved to the yaml file. if the user cancels the deletion, the script
    will rerun.

    Parameters
    ----------
    credentials : dict
        The credentials dictionary
    service : str
        The service to which the account belongs
    provider : str
        The provider to which the account belongs
    account : str
        The account to delete

    Returns
    -------
    None
    """
    st.write('Are you sure you want to delete this account?')
    if st.button(
            'Yes',
            key=f'delete_{service}_{provider}_{account}',
            on_click=_delete_account,
            args=(credentials, service, provider, account)
    ):
        st.rerun()
    if st.button('Cancel', key=f'cancel_delete_{service}_{provider}_{account}'):
        st.rerun()


def _delete_account(credentials: dict, service: str, provider: str, account: str) -> None:
    """
    Delete the account from the credentials dictionary and save the changes to the yaml file.

    Parameters
    ----------
    credentials : dict
        The credentials dictionary
    service : str
        The service to which the account belongs
    provider :
        The provider to which the account belongs
    account :
        The account to delete

    Returns
    -------
    None

    """
    del credentials[service][provider][account]
    _save_credentials(credentials)


@st.fragment
def add_new_data_source(credentials: dict, service: Literal['credit_cards', 'banks', 'insurances']) -> None:
    """
    Add a new account for the given service. The user will be prompted to enter the required fields for the new
    account. The function will save the new account to the credentials dictionary and save the changes to the yaml
    file.

    Parameters
    ----------
    credentials : dict
        The credentials dictionary
    service : str
        The service for which to add a new account. Should be one of 'credit_cards', 'banks', or 'insurances'.

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

    # select your provider
    enum_class = Banks if service == 'banks' else CreditCards if service == 'credit_cards' else Insurances
    provider = st.selectbox('Select a provider', options=[provider.value for provider in enum_class],
                            key=f'select_{service}_provider')
    provider = provider.lower() if provider is not None else None

    # add the provider field if it doesn't exist in the credentials
    if provider not in list(credentials[service].keys()):
        credentials[service][provider] = {}

    # select your account name
    account_name = st.text_input(
        'Account name (how would you like to call the account)',
        key=f'new_{service}_account_name',
        on_change=_check_accounts_duplication,
        args=(
            credentials,
            service,
            provider,
            st.session_state.get(f'new_{service}_account_name', '')
        )
    )

    if account_name is None or account_name == '':  # if the user didn't enter an account name
        if st.button('Cancel', key=f'cancel_add_new_{service}'):
            CacheUtils.clear_session_state()
            st.rerun()
        return

    # edit the required fields when the provider is selected and is valid
    credentials[service][provider][account_name] = {}
    for field in LoginFields.get_fields(provider):
        label = DisplayFields.get_display(field)
        if 'phone' in label.lower():  # use the phone number widget for phone fields
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

    # save the new account button
    if st.button('Save new account', key=f'save_new_{service}_data_source_button'):
        _save_new_data_source(credentials, service, provider, account_name)
        st.rerun()

    # cancel adding a new account button
    if st.button('Cancel', key=f'cancel_add_new_{service}'):
        # reset the session state variables related to the new credentials
        del st.session_state[f'add_new_{service}']
        st.rerun()


def _check_accounts_duplication(credentials: dict, service: str, provider: str, account_name: str) -> None:
    """
    Check if the account name already exists in the credentials. If the account name already exists, the script will
    stop and prompt the user to choose a different name.

    Parameters
    ----------
    credentials : dict
        The credentials dictionary
    service : str
        The service for which to add a new account
    provider : str
        The provider for which to add a new account
    account_name : str
        The account name to check for duplication

    Returns
    -------
    None
    """
    if provider not in credentials[service].keys():
        return
    if account_name in credentials[service][provider].keys():
        st.error('Account name already exists. Please choose a different name.')


def _save_new_data_source(credentials: dict, service: str, provider: str, account_name: str) -> None:
    # check if all fields are filled - do not proceed if not
    if any([(v == '' or v is None) for v in credentials[service][provider][account_name].values()]):
        st.error('Please fill all the displayed fields.',
                 icon="🚨")
        st.stop()
    _save_credentials(credentials)
    st.session_state.clear()
