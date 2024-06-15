import streamlit as st
import yaml
import sys

from fad.scraper import TwoFAHandler
from pathlib import Path
from fad import src_path
from typing import Literal
from copy import deepcopy
from threading import Thread


class CredentialsUtils:
    providers = {
        'credit_cards': ['Max', 'Visa Cal', 'Isracard', 'Amex', 'Beyahad Bishvilha', 'Behatsdaa'],
        'banks': ['Hapoalim', 'Leumi', 'Discount', 'Mizrahi', 'Mercantile', 'Otsar Hahayal', 'Union', 'Beinleumi',
                  'Massad', 'Yahav', 'OneZero'],
        'insurances': ['Menora', 'Clal', 'Harel', 'Hafenix']
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
        'hafenix': ['username', 'password']
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

    two_fa_providers = ['onezero']

    two_fa_contact = {
        'onezero': 'phoneNumber'
    }

    two_fa_field_name = {
        'onezero': 'otpLongTermToken'
    }

    # TODO: use a st.dialog for 2FA
    @staticmethod
    def load_credentials():
        with open(Path(src_path) / 'scraper/credentials.yaml', 'r') as file:
            return yaml.safe_load(file)

    @staticmethod
    def save_credentials(credentials: dict):
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
            st.session_state.deleted_account = True
            st.write('Account deleted successfully!')
            st.rerun()
        if st.button('No'):
            st.rerun()

    @staticmethod
    def add_new_data_source(credentials: dict, service: Literal['credit_cards', 'banks', 'insurances']):
        if not st.session_state.get('new_credentials', False) or st.session_state.get('deleted_account', False):
            st.session_state.new_credentials = deepcopy(credentials)
            st.session_state.deleted_account = False
        new_credentials = st.session_state.new_credentials

        if st.button(f"Add a new {service.replace('_', ' ').rstrip('s')} account", key=f"add_new_{service}"):
            st.session_state.add_new_data_source = True

        if st.session_state.get('add_new_data_source', False):
            # select your provider
            provider = st.selectbox('Select a provider', CredentialsUtils.providers[service],
                                    key=f'select_{service}_provider')
            provider = provider.lower() if provider is not None else None

            # add the provider field if it doesn't exist in the credentials
            if provider not in list(new_credentials[service].keys()):
                new_credentials[service][provider] = {}

            # select your account name
            account_name = st.text_input('Account name (how would you like to call the account)',
                                         key=f'new_{service}_account_name')

            if account_name is not None and account_name != '':
                if account_name not in new_credentials[service][provider].keys():
                    new_credentials[service][provider][account_name] = {}
                    st.session_state.checked_account_duplication = True
                elif not st.session_state.get('checked_account_duplication', False):
                    st.error('Account name already exists. Please choose a different name.')
                    st.stop()

                # edit the required fields
                for field in CredentialsUtils.providers_fields[provider]:
                    label = CredentialsUtils.field_display[field]
                    label = CredentialsUtils.format_label(provider, label)
                    new_credentials[service][provider][account_name][field] = (
                        st.text_input(label, key=f'new_{service}_{field}'))
                if st.button('Save new account', key=f'save_new_{service}_data_source_button') or \
                        st.session_state.get(f'save_new_{service}_data_source', False):
                    st.session_state[f'save_new_{service}_data_source'] = True  # for 2fa reruns handling

                    # check if all fields are filled - do not proceed if not
                    if any([v == '' for v in new_credentials[service][provider][account_name].values()]):
                        st.error('Please fill all the fields. Make sure to press enter after filling each field.',
                                 icon="🚨")
                        st.stop()

                    # 2FA handling - get long-term token (only for some providers)
                    if st.session_state.get('long_term_token', None) in ['waiting for token', None]:
                        contact_field = CredentialsUtils.two_fa_contact.get(provider, None)
                        contact_info = new_credentials[service][provider][account_name].get(contact_field, None)
                        CredentialsUtils.handle_two_fa(provider, contact_info)

                    # save the long-term token in the credentials
                    if st.session_state.long_term_token not in ['not required', 'waiting for token', 'aborted']:
                        field_name = CredentialsUtils.two_fa_field_name[provider]
                        sys.stdout.write(f'long-term token: {st.session_state.long_term_token}\n')
                        new_credentials[service][provider][account_name][field_name] = st.session_state.long_term_token
                        st.session_state.long_term_token = 'not required'  # doesn't require 2fa anymore

                    # complete the saving process
                    if st.session_state.long_term_token == 'not required':
                        # save the new credentials to the yaml file
                        CredentialsUtils.save_credentials(new_credentials)
                        # update the credentials with the new ones - prevents reloading the yaml file in every rerun
                        credentials.update(new_credentials)

                    # reset the session state variables related to the new credentials and rerun the script
                    if st.session_state.long_term_token in ['not required', 'aborted']:
                        del st.session_state.add_new_data_source
                        del st.session_state.new_credentials
                        del st.session_state.long_term_token
                        del st.session_state[f'save_new_{service}_data_source']
                        st.rerun()

            if st.button('Cancel', key=f'cancel_add_new_{service}'):
                # reset the session state variables related to the new credentials
                st.session_state.add_new_data_source = False
                del st.session_state.new_credentials
                st.rerun()

    @staticmethod
    def format_label(provider: str, label: str) -> str:
        """
        Format the label to be displayed in the UI

        Parameters
        ----------
        provider : str
            The provider for which to format the label
        label : str
            The label to format

        Returns
        -------
        str
            The formatted label
        """
        if provider == 'onezero':
            if label == 'Phone Number':
                label += ': should be in the following format - +9725XXXXXXXX'
        return label

    @staticmethod
    def handle_two_fa(provider: str, contact_info: str or None):
        """
        Handle two-factor authentication for the given provider. if the provider requires 2FA, the user will be prompted
        to enter the OTP code. If the user cancels the 2FA, the script will stop.
        the function sets the long-term token in the session state as 'long_term_token'

        long_term_token states:
        - 'not required': the provider does not require 2FA
        - 'aborted': the user canceled the 2FA
        - 'waiting for token': the user is prompted to enter the OTP code and the script is waiting for the code
        - '<long-term token>': the long-term token received from the provider

        Parameters
        ----------
        provider : str
            The provider for which to handle two-factor authentication
        contact_info : str | None
            The phone number to which the OTP code will be sent. Required for providers that require 2FA, None otherwise

        Returns
        -------
        None
        """
        if provider not in CredentialsUtils.two_fa_providers:
            st.session_state.long_term_token = 'not required'
            return

        if st.session_state.get('long_term_token', None) is None:
            st.session_state.long_term_token = 'waiting for token'

        if st.session_state.get('tfa_code', None) is None:
            if st.session_state.get('otp_handler', None) is None:
                st.session_state.opt_handler = TwoFAHandler(provider, contact_info)
                st.session_state.thread = Thread(target=st.session_state.opt_handler.handle_2fa)
                st.session_state.thread.start()
            two_fa_dialog(provider)
        elif st.session_state.tfa_code == 'cancel':
            # terminate the thread and set the long-term token to 'aborted'
            st.session_state.opt_handler.process.terminate()
            st.session_state.long_term_token = 'aborted'
        else:
            st.session_state.opt_handler.set_otp_code(st.session_state.tfa_code)
            st.session_state.thread.join()  # wait for the thread to finish
            if st.session_state.opt_handler.error:
                st.error(f'Error getting long-term token: {st.session_state.opt_handler.error}')
                st.stop()
            st.session_state.long_term_token = st.session_state.opt_handler.result

        # we reach here only if the 2FA process is completed successfully
        del st.session_state.tfa_code
        del st.session_state.opt_handler
        del st.session_state.thread


@st.experimental_dialog('Two Factor Authentication')
def two_fa_dialog(provider: str):
    st.write(f'The provider, {provider}, requires 2 factor authentication for adding a new account.')
    st.write('Please enter the code you received.')
    code = st.text_input('Code')
    if st.button('Submit'):
        if code is None or code == '':
            st.error('Please enter a valid code')
            st.stop()
        st.session_state.tfa_code = code
        st.rerun()
    if st.button('Cancel'):
        st.session_state.tfa_code = 'cancel'
        st.rerun()

    st.stop()  # stop the script until the user submits the code


############################################################################################################
# UI
############################################################################################################
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
    if 'credentials' not in st.session_state:
        st.session_state.credentials = CredentialsUtils.load_credentials()
    credentials = st.session_state.credentials

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

