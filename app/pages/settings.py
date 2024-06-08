import streamlit as st
import yaml
from pathlib import Path
from src import src_path
from typing import Literal


class CredentialsUtils:
    providers = {
        'credit_cards': ['Max', 'Visa Cal', 'Isracard', 'Amex', 'Beyahad Bishvilha', 'Behatsdaa'],
        'banks': ['Hapoalim', 'Leumi', 'Discount', 'Mizrahi', 'Mercantile', 'Otsar Hahayal', 'Union', 'Beinleumi',
                  'Massad', 'Yahav', 'OneZero'],
        'insurances': ['Menora', 'Clal', 'Harel', 'Haphenix']
    }

    providers_fields = {
        # cards
        'max': ['username', 'password'],
        'visa cal': ['username', 'password'],
        'isracard': ['id', 'card6Digits', 'password'],
        'amex': ['id', 'card6Digits', 'password'],
        'beyahad bishvilha': ['id', 'password'],
        'behatsdaa': ['id', 'password'],
        # banks
        'hapoalim': ['userCode', 'password'],
        'leumi': ['username', 'password'],
        'mizrahi': ['username', 'password'],
        'discount': ['id', 'password', 'num'],
        'mercantile': ['id', 'password', 'num'],
        'otsar hahayal': ['username', 'password'],
        'union': ['username', 'password'],
        'beinleumi': ['username', 'password'],
        'massad': ['username', 'password'],
        'yahav': ['username', 'nationalID', 'password'],
        'onezero': ['email', 'password', 'phoneNumber'],
        # insurances
        'menora': ['username', 'password'],
        'clal': ['username', 'password'],
        'harel': ['username', 'password'],
        'haphenix': ['username', 'password']
    }

    field_display = {
        'id': 'ID',
        'card6Digits': 'Card 6 Digits',
        'password': 'Password',
        'username': 'Username',
        'userCode': 'User Code',
        'num': 'Num',
        'nationalID': 'National ID',
        'email': 'Email',
        'phoneNumber': 'Phone Number'
    }

    # TODO: use a st.dialog for 2FA
    @staticmethod
    def load_credentials():
        with open(Path(src_path) / 'scraper/credentials.yaml', 'r') as file:
            return yaml.safe_load(file)

    @staticmethod
    def save_credentials(credentials: dict):
        with open(Path(src_path) / 'scraper/credentials.yaml', 'w') as file:
            yaml.dump(credentials, file, sort_keys=False, indent=4)

    @staticmethod
    def edit_delete_credentials(credentials: dict, service: Literal['credit_cards', 'banks', 'insurances']):
        """
        Edit or delete credentials for a given service.

        Parameters
        ----------
        credentials : dict
            The credentials dictionary, should have the following structure:
            credit_cards:
                provider1:
                    account1:
                        my_parameter: '1234'
                        another_parameter: '123456'
                        password: 'password'
                ...
            banks:
                provider1:
                    account1:
                        some_parameter: '1234'
                        password: 'password'
                ...
            insurance:
                provider1:
                    account1:
                        other_parameter '1234'
                        password: 'password'
        service : str
            The service to edit, should be one of 'credit_cards', 'banks', or 'insurance'.

        """
        for provider, accounts in credentials[service].items():
            for account, data in accounts.items():
                with st.expander(f"{provider} - {account}"):
                    for field, value in data.items():
                        label = CredentialsUtils.field_display.get(field, field)
                        if label == 'otpLongTermToken':
                            continue
                        elif label == 'Password':
                            data[field] = st.text_input(label, value, key=f'{provider}_{account}_{field}',
                                                        type='password')
                        else:
                            data[field] = st.text_input(label, value, key=f'{provider}_{account}_{field}')
                    # delete button
                    if st.button('Delete', key=f'{provider}_{account}_delete'):
                        CredentialsUtils.assert_delete_account(credentials, service, provider, account)

    @staticmethod
    @st.experimental_dialog('verify deletion')
    def assert_delete_account(credentials: dict, service: str, provider: str, account: str):
        st.write('Are you sure you want to delete this account?')
        if st.button('Yes'):
            del credentials[service][provider][account]
            CredentialsUtils.save_credentials(credentials)
            st.write('Account deleted successfully!')
            st.rerun()
        if st.button('No'):
            st.rerun()

    @staticmethod
    def add_new_data_source(credentials: dict, service: Literal['credit_cards', 'banks', 'insurances']):
        if st.button(f"Add a new {service.replace('_', ' ').rstrip('s')} account", key=f"add_new_{service}"):
            st.session_state.add_new_data_source = True

        if st.session_state.get('add_new_data_source', False):
            # select your provider
            provider = st.selectbox('Select a provider', CredentialsUtils.providers[service],
                                        key=f'select_{service}_provider')
            provider = provider.lower() if provider is not None else None

            # add the provider field if it doesn't exist in the credentials
            if provider not in list(credentials[service].keys()):
                credentials[service][provider] = {}

            # select your account name
            account_name = st.text_input('Account name (how would you like to call the account)',
                                         key=f'new_{service}_account_name')

            if account_name is not None and account_name != '':
                if account_name not in credentials[service][provider].keys():
                    credentials[service][provider][account_name] = {}
                else:
                    st.error('Account name already exists. Please choose a different name.')
                    st.stop()

                # edit the required fields
                for field in CredentialsUtils.providers_fields[provider]:
                    label = CredentialsUtils.field_display[field]
                    if provider == 'onezero' and label == 'Phone Number':
                        label += ': should be in the following format - 9725XXXXXXXX'
                    credentials[service][provider][account_name][field] = (
                        st.text_input(label, key=f'new_{service}_{field}'))
                if st.button('Save new account'):
                    CredentialsUtils.save_credentials(credentials)
                    st.session_state.add_new_data_source = False
                    st.rerun()


            if st.button('Cancle', key=f'cancel_new_{service}'):
                st.session_state.add_new_data_source = False
                st.rerun()


st.title('App Settings and Credentials')
st.write("This page contains all the settings for the app and credentials for banks, credit cards and insurance "
         "companies. You can edit your credentials here.")

settings_tab, credentials_tab = st.tabs(['Settings', 'Credentials'])

with settings_tab:
    st.write('Settings')
    st.write('Coming soon...')

with credentials_tab:
    """After editing the credentials, click the Save button to save the changes."""
    # Load credentials
    credentials = CredentialsUtils.load_credentials()

    # global Save button
    if st.button('Save'):
        try:
            CredentialsUtils.save_credentials(credentials)
            st.success('Credentials saved successfully!')
        except yaml.YAMLError as e:
            st.error(f'Error saving credentials: {e}')

    cards_tab, banks_tab, insurance_tab = st.tabs(['Credit Cards', 'Banks', 'Insurance'])

    with cards_tab:
        CredentialsUtils.edit_delete_credentials(credentials, 'credit_cards')
        CredentialsUtils.add_new_data_source(credentials, 'credit_cards')

    with banks_tab:
        CredentialsUtils.edit_delete_credentials(credentials, 'banks')
        CredentialsUtils.add_new_data_source(credentials, 'banks')

    with insurance_tab:
        CredentialsUtils.edit_delete_credentials(credentials, 'insurances')
        CredentialsUtils.add_new_data_source(credentials, 'insurances')

