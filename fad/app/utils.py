import streamlit as st
import yaml
import sqlite3

from streamlit_phone_number import st_phone_number
from typing import Literal
from threading import Thread
from datetime import datetime, timedelta

from fad.app.naming_conventions import Banks, CreditCards, Insurances, LoginFields, DisplayFields
from fad.scraper import TwoFAHandler, BankScraper, CreditCardScraper
from fad import CREDENTIALS_PATH


class CredentialsUtils:
    """
    This class contains utility functions for handling the credentials in the app.
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

    two_fa_providers = [
        'onezero'
    ]

    two_fa_contact = {
        'onezero': 'phoneNumber'
    }

    two_fa_field_name = {
        'onezero': 'otpLongTermToken'
    }

    @staticmethod
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

    @staticmethod
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
        st.success('Credentials saved successfully!')

    @staticmethod
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
                    with st.form(key=f'{provider}_{account}_form', border=False):
                        # edit the credentials
                        CredentialsUtils._generate_text_input_widgets(provider, account, creds)
                        # save edited credentials button
                        st.form_submit_button('Save', on_click=CredentialsUtils._save_credentials, args=(credentials,))
                    # delete account button
                    if st.button('Delete', key=f'{provider}_{account}_delete', type='primary'):
                        # we can't use the on_click parameter here due to how the dialog works. the callback function
                        # is called preliminary to the rerun (after every button click), which causes the dialog to be
                        # set, then the script is rerun and the dialog object is deleted (but still displayed in the
                        # frontend) and this causes a RuntimeError when trying to use the widgets in the dialog. (?)
                        CredentialsUtils._delete_account_dialog(credentials, service, provider, account)

    @staticmethod
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

    @staticmethod
    @st.experimental_dialog('verify deletion')
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
        if st.button('Yes', key=f'delete_{service}_{provider}_{account}', on_click=CredentialsUtils._delete_account,
                     args=(credentials, service, provider, account)):
            st.rerun()
        if st.button('Cancel', key=f'cancel_delete_{service}_{provider}_{account}'):
            st.rerun()

    @staticmethod
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
        CredentialsUtils._save_credentials(credentials)

    @staticmethod
    @st.experimental_fragment
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
        if st.button(f"Add a new {service.replace('_', ' ').rstrip('s')} account", key=f"add_new_{service}_button"):
            st.session_state[f'add_new_{service}'] = True

        if not st.session_state.get(f'add_new_{service}', False):
            # hide the form if the user didn't click the button
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
        account_name = st.text_input('Account name (how would you like to call the account)',
                                     key=f'new_{service}_account_name')

        if account_name is not None and account_name != '':
            if account_name not in credentials[service][provider].keys():
                credentials[service][provider][account_name] = {}
                st.session_state.checked_account_duplication = True
            elif not st.session_state.get('checked_account_duplication', False):
                st.error('Account name already exists. Please choose a different name.')
                st.stop()
        else:
            return

        # edit the required fields when the provider is selected and is valid
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
                    st.text_input(label, key=f'new_{service}_{field}',
                                  type='password' if 'password' in label.lower() else 'default')
                )

        # save the new account button
        st.button('Save new account', key=f'save_new_{service}_data_source_button',
                  on_click=CredentialsUtils._save_new_data_source,
                  args=(credentials, service, provider, account_name))  # initiate the saving process
        if st.session_state.get('saving_credentials_in_progress', False):  # 2fa handling in progress
            CredentialsUtils._save_new_data_source(credentials, service, provider, account_name)

        # cancel adding a new account button
        if st.button('Cancel', key=f'cancel_add_new_{service}'):
            # reset the session state variables related to the new credentials
            del st.session_state[f'add_new_{service}']
            st.rerun()

    @staticmethod
    def _save_new_data_source(credentials: dict, service: str, provider: str, account_name: str) -> None:
        # check if all fields are filled - do not proceed if not
        if any([(v == '' or v is None) for v in credentials[service][provider][account_name].values()]):
            st.error('Please fill all the displayed fields.',
                     icon="🚨")
            st.stop()

        st.session_state.long_term_token = 'waiting for token' if provider in CredentialsUtils.two_fa_providers \
            else 'not required'

        # 2FA handling - get long-term token (only for some providers)
        if st.session_state.long_term_token == 'waiting for token':
            contact_field = CredentialsUtils.two_fa_contact[provider]
            contact_info = credentials[service][provider][account_name][contact_field]
            CredentialsUtils._handle_two_fa(provider, contact_info)
            st.session_state.saving_credentials_in_progress = True

        # save the long-term token in the credentials
        if st.session_state.long_term_token not in ['not required', 'waiting for token', 'aborted']:
            field_name = CredentialsUtils.two_fa_field_name[provider]
            credentials[service][provider][account_name][field_name] = st.session_state.long_term_token
            st.session_state.long_term_token = 'completed'  # doesn't require 2fa anymore

        # complete the saving process when 2fa is completed or not required
        if st.session_state.long_term_token in ['completed', 'not required']:
            CredentialsUtils._save_credentials(credentials)

        # reset the session state variables related to the new credentials and rerun the script to clear the form
        if st.session_state.long_term_token in ['not required', 'completed', 'aborted']:
            del st.session_state.long_term_token
            del st.session_state[f'add_new_{service}']
            del st.session_state.saving_credentials_in_progress
            st.rerun()

    @staticmethod
    def _handle_two_fa(provider: str, contact_info: str or None):
        """
        Handle two-factor authentication for the given provider. if the provider requires 2FA, the user will be prompted
        to enter the OTP code. If the user cancels the 2FA, the script will stop.
        the function sets the long-term token in the session state as 'long_term_token'

        long_term_token states:
        - 'not required': the provider does not require 2FA
        - 'aborted': the user canceled the 2FA
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
        # TODO: still missing handling for when the user is pressing esc or the X button on the dialog
        # first call of this function
        if st.session_state.get('tfa_code', None) is None:
            st.session_state.tfa_code = 'waiting for token'
            st.session_state.opened_2fa_dialog = False

        if st.session_state.tfa_code == 'waiting for token':
            # prompt the user to enter the OTP code, the user can either submit the code or cancel the 2FA which will
            # set the tfa_code session state variable to 'cancel' or the code entered by the user and rerun the script
            if not st.session_state.opened_2fa_dialog:
                st.session_state.otp_handler = TwoFAHandler(provider, contact_info)
                st.session_state.thread = Thread(target=st.session_state.otp_handler.handle_2fa)
                st.session_state.thread.start()
                CredentialsUtils._two_fa_dialog(provider)
                st.session_state.opened_2fa_dialog = True
        elif st.session_state.tfa_code == 'cancel':
            # terminate the thread and set the long-term token to 'aborted'
            st.session_state.otp_handler.process.terminate()
            st.session_state.long_term_token = 'aborted'
        else:
            # fetch the long term token using the OTP code entered by the user
            st.session_state.otp_handler.set_otp_code(st.session_state.tfa_code)
            st.session_state.thread.join()  # wait for the thread to finish
            if st.session_state.otp_handler.error:
                st.error(f'Error getting long-term token: {st.session_state.otp_handler.error}')
                st.stop()
            st.session_state.long_term_token = st.session_state.otp_handler.result

        if st.session_state.long_term_token != 'waiting for token':
            # we reach here only if the 2FA process is completed successfully or aborted
            del st.session_state.tfa_code
            del st.session_state.otp_handler
            del st.session_state.thread
            del st.session_state.opened_2fa_dialog

    @staticmethod
    @st.experimental_dialog('Two Factor Authentication')
    def _two_fa_dialog(provider: str):
        """
        Display a dialog for the user to enter the OTP code for the given provider. The dialog will stop the script
        until the user submits the code. If the user cancels the 2FA the tfa_code session state variable will be set to
        'cancel' and the script will rerun, otherwise the tfa_code session state variable will be set to the code
        entered by the user and the script will rerun as well.

        Parameters
        ----------
        provider

        Returns
        -------

        """
        st.write(f'The provider, {provider}, requires 2 factor authentication for adding a new account.')
        st.write('Please enter the code you received.')
        st.write(st.session_state.tfa_code)
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

        # st.stop()  # stop the script until the user submits the code


class DataUtils:

    @staticmethod
    def pull_data(start_date: datetime | str, credentials: dict):
        """
        Pull data from the data sources and save it to the database
        """
        for service, providers in credentials.items():
            match service:
                case 'credit_cards':
                    scraper = CreditCardScraper(providers)
                case 'banks':
                    scraper = BankScraper(providers)
                case 'insurances':
                    scraper = None
                case _:
                    raise ValueError(f'Invalid service: {service}')

            if scraper is not None:
                scraper.pull_data_to_db(start_date)

    @staticmethod
    def get_latest_data_date(conn: sqlite3.Connection) -> datetime.date:
        """
        Get the latest date in the database
        """
        query = 'SELECT MAX(date) FROM credit_card_transactions'
        try:
            cursor = conn.cursor()
            cursor.execute(query)
            latest_date = cursor.fetchone()[0]
        except sqlite3.OperationalError as e:
            if 'no such table' in str(e):
                return datetime.today() - timedelta(days=365)
            else:
                raise e

        latest_date = datetime.strptime(latest_date, '%Y-%m-%d %H:%M:%S').date()
        return latest_date





