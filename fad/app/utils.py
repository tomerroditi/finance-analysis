import streamlit as st
import yaml
import sqlite3
import sqlalchemy
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit_antd_components as sac
from plotly.subplots import make_subplots
from streamlit_tags import st_tags
from sqlalchemy.sql import text

from streamlit_phone_number import st_phone_number
from streamlit.connections import SQLConnection
from typing import Literal
from threading import Thread
from datetime import datetime, timedelta
from fad.scraper import TwoFAHandler, BankScraper, CreditCardScraper
from fad import CREDENTIALS_PATH, CATEGORIES_PATH
from fad.app.naming_conventions import (Banks,
                                        CreditCards,
                                        Insurances,
                                        LoginFields,
                                        DisplayFields,
                                        CreditCardTableFields,
                                        Tables,
                                        BankTableFields,
                                        TagsTableFields,
                                        NonExpensesCategories,
                                        TransactionsTableFields,
                                        Services
                                        )

tags_table = Tables.TAGS.value
credit_card_table = Tables.CREDIT_CARD.value
bank_table = Tables.BANK.value
category_col = TagsTableFields.CATEGORY.value
tag_col = TagsTableFields.TAG.value
name_col = TagsTableFields.NAME.value
service_col = TagsTableFields.SERVICE.value
account_number_col = TagsTableFields.ACCOUNT_NUMBER.value
cc_desc_col = CreditCardTableFields.DESCRIPTION.value
cc_tag_col = CreditCardTableFields.TAG.value
cc_category_col = CreditCardTableFields.CATEGORY.value
cc_name_col = CreditCardTableFields.DESCRIPTION.value
cc_id_col = CreditCardTableFields.ID.value
cc_date_col = CreditCardTableFields.DATE.value
cc_provider_col = CreditCardTableFields.PROVIDER.value
cc_account_name_col = CreditCardTableFields.ACCOUNT_NAME.value
cc_account_number_col = CreditCardTableFields.ACCOUNT_NUMBER.value
cc_amount_col = CreditCardTableFields.AMOUNT.value
bank_desc_col = BankTableFields.DESCRIPTION.value
bank_tag_col = BankTableFields.TAG.value
bank_category_col = BankTableFields.CATEGORY.value
bank_name_col = BankTableFields.DESCRIPTION.value
bank_id_col = BankTableFields.ID.value
bank_account_number_col = BankTableFields.ACCOUNT_NUMBER.value
bank_date_col = BankTableFields.DATE.value
bank_provider_col = BankTableFields.PROVIDER.value
bank_account_name_col = BankTableFields.ACCOUNT_NAME.value
bank_amount_col = BankTableFields.AMOUNT.value


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
        # TODO: figure out why the function is called again after the dialog is opened (before submitting the otp)
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
            print("deleting otp properties")
            # we reach here only if the 2FA process is completed successfully or aborted
            del st.session_state.tfa_code
            del st.session_state.otp_handler
            del st.session_state.thread
            del st.session_state.opened_2fa_dialog

    @staticmethod
    @st.dialog('Two Factor Authentication')
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
        code = st.text_input('Code', key=f'tfa_code_{provider}')
        if st.button('Submit', key="two_fa_dialog_submit"):
            if code is None or code == '':
                st.error('Please enter a valid code')
                st.stop()
            st.session_state.tfa_code = code
            st.rerun()
        if st.button('Cancel', key="two_fa_dialog_cancel"):
            st.session_state.tfa_code = 'cancel'
            st.rerun()


class DataUtils:
    @staticmethod
    def get_db_connection() -> SQLConnection:
        """
        Get a connection to the database

        Returns
        -------
        SQLConnection
            The connection to the app database
        """
        if 'conn' not in st.session_state:
            st.session_state['conn'] = st.connection('data', 'sql')
        return st.session_state['conn']

    @staticmethod
    def assure_tags_table(conn: SQLConnection):
        """create the tags table if it doesn't exist"""
        with conn.session as s:
            s.execute(text(f'CREATE TABLE IF NOT EXISTS {tags_table} ({name_col} TEXT PRIMARY KEY, {category_col}'
                           f' TEXT, {tag_col} TEXT, {service_col} TEXT, {account_number_col} TEXT);'))
            s.commit()

    @staticmethod
    def get_table(conn: SQLConnection, table_name: str) -> pd.DataFrame:
        """
        Get the data from the given table

        Parameters
        ----------
        conn : SQLConnection
            The connection to the database
        table_name : str
            The name of the table to get the data from

        Returns
        -------
        pd.DataFrame
            The data from the table
        """
        try:
            return conn.query(f'SELECT * FROM {table_name};', ttl=0)
        except sqlalchemy.exc.OperationalError:
            return pd.DataFrame()

    @staticmethod
    def get_categories_and_tags() -> dict:
        """
        Get the categories and tags from the yaml file

        Returns
        -------
        dict
            The categories and tags dictionary
        """
        if 'categories_and_tags' not in st.session_state:
            with open(CATEGORIES_PATH, 'r') as file:
                st.session_state['categories_and_tags'] = yaml.load(file, Loader=yaml.FullLoader)
        return st.session_state['categories_and_tags']

    @staticmethod
    def pull_data(start_date: datetime | str, credentials: dict, db_path: str = None) -> None:
        """
        Pull data from the data sources, from the given date to present, and save it to the database file.

        Parameters
        ----------
        start_date : datetime | str
            The date from which to start pulling the data
        credentials : dict
            The credentials dictionary
        db_path : str
            The path to the database file. If None the database file will be created in the folder of fad package
            with the name 'data.db'

        Returns
        -------
        None
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
                scraper.pull_data_to_db(start_date, db_path)

    @staticmethod
    def get_latest_data_date(conn: SQLConnection) -> datetime.date:
        """
        Get the latest date in the database

        Parameters
        ----------
        conn : sqlite3.Connection
            The connection to the database

        Returns
        -------
        datetime.date:
            The latest date in the database
        """
        cc_table = Tables.CREDIT_CARD.value
        bank_table = Tables.BANK.value
        date_col_cc = CreditCardTableFields.DATE.value
        date_col_bank = BankTableFields.DATE.value

        query_cc = f'SELECT MAX({date_col_cc}) FROM {cc_table}'
        query_bank = f'SELECT MAX({date_col_bank}) FROM {bank_table}'
        try:
            latest_date_cc = conn.query(query_cc, ttl=0).iloc[0, 0]
            latest_date_bank = conn.query(query_bank, ttl=0).iloc[0, 0]
        except sqlalchemy.exc.OperationalError as e:
            if 'no such table' in str(e):
                return datetime.today() - timedelta(days=365)
            else:
                raise e

        latest_date_cc = datetime.strptime(latest_date_cc, '%Y-%m-%d')
        latest_date_bank = datetime.strptime(latest_date_bank, '%Y-%m-%d')
        latest_date = max(latest_date_cc, latest_date_bank)
        return latest_date

    @staticmethod
    def update_db_table(conn: SQLConnection, table_name: str, edited_rows: pd.DataFrame) -> None:
        """
        Update the database table with the edited rows

        Parameters
        ----------
        conn : SQLConnection
            The connection to the database
        table_name : str
            The name of the table to update
        edited_rows : pd.DataFrame
            The edited rows

        Returns
        -------
        None
        """
        if edited_rows.empty:
            return
        match table_name:
            case Tables.CREDIT_CARD.value:
                id_col = CreditCardTableFields.ID.value
            case Tables.BANK.value:
                id_col = BankTableFields.ID.value
            case Tables.INSURANCE.value:
                raise NotImplementedError('Insurance table update is not implemented yet')
            case _:
                raise ValueError(f'Invalid table name: {table_name}')

        columns = edited_rows.columns.tolist()
        with conn.session as s:
            for i, row in edited_rows.iterrows():
                set_clause = ', '.join([f"{col}=:{col}" for col in columns])
                query = sqlalchemy.text(f"UPDATE {table_name} SET {set_clause} WHERE {id_col}=:id_col")
                params = {col: row[col] for col in columns}
                params['id_col'] = row[id_col]
                s.execute(query, params)
            s.commit()

    @staticmethod
    def format_category_or_tag_strings(*args) -> tuple[str | None] | str | None:
        """
        format the category and tag to be title case

        Parameters
        ----------
        args: tuple[str | None]
            sequence of strings to format to title case

        Returns
        -------
        tuple
            the formatted category and tag
        """
        assert all(
            isinstance(arg, str) or arg is None or np.isnan(arg) for arg in args), 'all arguments should be strings'
        strings = tuple(arg.title() if isinstance(arg, str) and arg != '' else None for arg in args)
        if len(strings) == 1:
            return strings[0]
        return strings  # type: ignore


class PlottingUtils:
    @staticmethod
    def bar_plot_by_categories(df: pd.DataFrame, values_col: str, category_col: str) -> go.Figure:
        """
        Plot the expenses by categories

        Parameters
        ----------
        df : pd.DataFrame
            The data to plot
        values_col : str
            The column name of the values to plot
        category_col : str
            The column name of the category to group by the data into bars

        Returns
        -------
        None
        """
        df = df.copy()
        df[values_col] = df[values_col] * -1
        df = df.groupby(category_col).sum(numeric_only=True).reset_index()
        fig = go.Figure(
            go.Bar(
                x=df[values_col],
                y=df[category_col],
                orientation='h',
                text=df[values_col].round(2),
                textposition='auto'
            )
        )
        fig.update_layout(
            title='Expenses Recap',
            xaxis_title='Outcome [₪]',
            yaxis_title='Category',
            annotations=[
                dict(
                    x=0,  # position along the x-axis, slightly outside the plot
                    y=-0.2,  # position along the y-axis, slightly above the plot
                    xref='paper',
                    yref='paper',
                    text='* Negative values represent income',
                    showarrow=False
                )
            ]
        )
        return fig

    @staticmethod
    def bar_plot_by_categories_over_time(df: pd.DataFrame, values_col: str, category_col: str, date_col: str,
                                         time_interval: str) -> go.Figure:
        """
        Plot the expenses by categories over time as a stacked bar plot

        Parameters
        ----------
        df : pd.DataFrame
            The data to plot
        values_col : str
            The column name of the values to plot
        category_col : str
            The column name of the category
        date_col : str
            The column name of the date
        time_interval : str
            The time interval to group the data by. Should be one of "1W", "1M", "1Y"

        Returns
        -------
        None
        """
        df = df.copy()
        df[values_col] = df[values_col] * -1
        df[date_col] = pd.to_datetime(df[date_col])
        df = df.groupby(pd.Grouper(key=date_col, freq=time_interval))
        time_str_format = '%Y-%m-%d' if time_interval == '1D' else '%Y-%m' if time_interval == '1M' else '%Y'
        fig = go.Figure()
        for date, data in df:
            curr_date_df = data.groupby(category_col).sum(numeric_only=True).reset_index()
            fig.add_trace(
                go.Bar(
                    x=curr_date_df[values_col],
                    y=curr_date_df[category_col],
                    name=date.strftime(time_str_format),  # noqa, date is a datetime object (pandas sets it as hashable)
                    orientation='h'
                )
            )
        title_time_period = 'Days' if time_interval == '1D' else 'Months' if time_interval == '1M' else 'Years'
        fig.update_layout(
            barmode='stack',
            title=f'Expenses Recap Over {title_time_period}',
            xaxis_title='Outcome [₪]',
            yaxis_title='Category',
            xaxis_tickformat=',d',
            annotations=[
                dict(
                    x=0,  # position along the x-axis, slightly outside the plot
                    y=-0.2,  # position along the y-axis, slightly above the plot
                    xref='paper',
                    yref='paper',
                    text='* Negative values represent income',
                    showarrow=False
                )
            ]
        )
        return fig

    @staticmethod
    def pie_plot_by_categories(df: pd.DataFrame, values_col: str, category_col: str) -> go.Figure:
        """
        Plot the expenses by categories

        Parameters
        ----------
        df : pd.DataFrame
            The data to plot
        values_col : str
            The column name of the values to plot
        category_col : str
            The column name of the category to group by the data into bars

        Returns
        -------
        None
        """
        df = df.copy()
        df[values_col] = df[values_col] * -1

        # Get negative and positive values categories
        df_neg = df[df[values_col] < 0].copy()
        df_pos = df[df[values_col] >= 0].copy()

        df_neg = df_neg.groupby(category_col).sum(numeric_only=True).reset_index()
        df_pos = df_pos.groupby(category_col).sum(numeric_only=True).reset_index()

        fig = make_subplots(
            rows=1, cols=2,
            specs=[[{'type': 'pie'}, {'type': 'pie'}]],
            subplot_titles=['Outcome [₪]', 'Refunds & Paybacks [₪]']
        )

        fig.add_trace(
            go.Pie(
                labels=df_pos[category_col],
                values=df_pos[values_col],
                textinfo='label+percent',
                hole=0.3,
                name="Outcome"
            ),
            row=1, col=1
        )

        fig.add_trace(
            go.Pie(
                labels=df_neg[category_col] if not df_neg.empty else ['No refunds & paybacks'],
                values=df_neg[values_col] * -1 if not df_neg.empty else [1],
                textinfo='label+percent',
                hole=0.3,
                name="Refunds & Paybacks"
            ),
            row=1, col=2
        )

        fig.update_layout(
            title_text='Expenses Recap',
        )

        return fig


class CategoriesAndTags:
    def __init__(self, conn: SQLConnection):
        """
        Initialize the CategoriesAndTags object

        Parameters
        ----------
        conn : SQLConnection
            The connection to the database
        """
        self.categories_and_tags = DataUtils.get_categories_and_tags()
        self.conn = conn

        # DataUtils.assure_tags_table(self.conn)

    ########################################################
    # categories and tags editing functions
    ########################################################
    def edit_categories_and_tags(self) -> None:
        """
        The main function to edit the categories and tags. The function displays the categories and tags in the UI and
        allows the user to edit them. The function also allows the user to add new categories, reallocate tags between
        categories, and delete categories.

        Returns
        -------
        None

        """
        add_cat_col, reallocate_tags_col, _ = st.columns([0.2, 0.2, 0.6])
        # add new categories
        with add_cat_col:
            st.button('New Category', key='add_new_category', on_click=self._add_new_category,
                      args=(self.categories_and_tags, CATEGORIES_PATH))

        # reallocate tags
        with reallocate_tags_col:
            st.button('Reallocate Tags', key='reallocate_tags', on_click=self._reallocate_tags,
                      args=(self.categories_and_tags, self.conn, CATEGORIES_PATH))

        # Iterate over a copy of the dictionary's items and display the categories and tags and allow editing
        for category, tags in list(self.categories_and_tags.items()):
            self._view_and_edit_tags(category)

            # delete category
            disable = True if category in [e.value for e in NonExpensesCategories] else False
            st.button(f'Delete {category}', key=f'my_{category}_delete', disabled=disable,
                      on_click=self._delete_category,
                      args=(self.categories_and_tags, category, self.conn, CATEGORIES_PATH))

    @st.fragment
    def _view_and_edit_tags(self, category: str) -> None:
        """
        Display the tags of the given category and allow the user to edit them

        Parameters
        ----------
        category : str
            The category to display its tags

        Returns
        -------
        None
        """
        # TODO: change st_tags to something else due to internal bug in the package that causes many undesired reruns.
        st.subheader(category, divider="gray")
        if category == "Ignore":
            st.write(
                "Transactions that you don't want to consider in the analysis. For example credit card bills in "
                "you bank account (which are already accounted for in the credit card transactions tracking), "
                "internal transfers, etc.")
        if category == "Salary":
            st.write("Transactions that are your salary income. we advise using the employer's name as the tag.")
        if category == "Other Income":
            st.write("Transactions that are income other than your salary. For example, rental income, dividends, "
                     "refunds, etc.")
        if category == "Investments":
            st.write("Transactions for investments you made. For example, depositing money into some fund, buying "
                     "stocks, real estate, etc.")
        tags = self.categories_and_tags[category]
        new_tags = st_tags(label='', value=tags, key=f'{category}_tags')
        if new_tags != tags:
            new_tags = [DataUtils.format_category_or_tag_strings(tag) for tag in new_tags]
            self.categories_and_tags[category] = new_tags
            # save changes and rerun to update the UI
            self._update_yaml_and_rerun()

    @st.dialog('Add New Category')
    def _add_new_category(self) -> None:
        """
        A dialog to add a new category. The user will be prompted to enter the new category name. If the user confirms
        the addition, the new category will be added to the categories and tags dictionary, the yaml file will be
        updated and the script will rerun. If the user cancels the addition, the script will rerun.
        rerunning the script causes the dialog to be closed.

        Returns
        -------
        None
        """
        existing_categories = [k.lower() for k in self.categories_and_tags.keys()]
        new_category = st.text_input('New Category Name', key='new_category')

        if st.button('Cancel'):
            st.rerun()

        if st.button('Continue') and new_category != '' and new_category is not None:
            if new_category.lower() in existing_categories:
                st.warning(f'The category "{new_category}" already exists. Please choose a different name.')
                st.stop()
            self.categories_and_tags[DataUtils.format_category_or_tag_strings(new_category)] = []
            self._update_yaml_and_rerun()

    @st.dialog('Reallocate Tags')
    def _reallocate_tags(self) -> None:
        """
        A dialog to reallocate tags from one category to another. The user will be prompted to select the current
        category and the tags to reallocate, then select the new category to reallocate the tags to. If the user
        confirms the reallocation, the tags will be updated in the database and the yaml file and the script will rerun.
        If the user cancels the reallocation, the script will rerun.
        rerunning the script causes the dialog to be closed.

        Returns
        -------
        None
        """
        all_categories = list(self.categories_and_tags.keys())
        old_category = st.selectbox('Select current category', all_categories, index=None,
                                    key='old_category')
        tags_to_select = self.categories_and_tags[old_category] if old_category is not None else []
        tags_to_reallocate = st.multiselect('Select tags to reallocate', tags_to_select, key='reallocate_tags')
        if old_category is None:
            st.stop()

        all_categories.remove(old_category)
        new_category = st.selectbox('Select new category', all_categories, key='new_category', index=None)
        if old_category is not None and new_category is not None and tags_to_reallocate:
            if st.button('Continue', key='continue_reallocate_tags'):
                # update the tags in the database
                for table in [tags_table, credit_card_table, bank_table]:
                    match table:
                        case Tables.TAGS.value:
                            curr_tag_col = tag_col
                            curr_category_col = category_col
                        case Tables.CREDIT_CARD.value:
                            curr_tag_col = cc_tag_col
                            curr_category_col = cc_category_col
                        case Tables.BANK.value:
                            curr_tag_col = bank_tag_col
                            curr_category_col = bank_category_col
                        case _:
                            raise ValueError(f"Invalid table name: {table}")
                    with (self.conn.session as s):
                        for tag in tags_to_reallocate:
                            query = text(
                                f'UPDATE {table} SET {curr_category_col}=:new_category WHERE {curr_tag_col}=:tag AND '
                                f'{curr_category_col}=:old_category;')
                            s.execute(query, {'new_category': new_category, 'tag': tag,
                                              'old_category': old_category})
                            s.commit()

                self.categories_and_tags[new_category].extend(tags_to_reallocate)
                _ = [self.categories_and_tags[old_category].remove(tag) for tag in tags_to_reallocate]
                self._update_yaml_and_rerun()

    @st.dialog('Confirm Deletion')
    def _delete_category(self, category: str) -> None:
        """
        A dialog to confirm the deletion of the given category. If the user confirms the deletion, the category will be
        deleted from the categories and tags dictionary, the yaml file and raw data tables are updated accordingly and
        the script will rerun. If the user cancels the deletion, the script will rerun.
        rerunning the script causes the dialog to be closed.

        Parameters
        ----------
        category : str
            The category to delete

        Returns
        -------
        None
        """
        st.write(f'Are you sure you want to delete the "{category}" category?')
        st.write('Deleting a category deletes it from the auto tagger rules as well.')
        delete_tags_of_logged_data = st.checkbox('Delete tags of logged data', key=f'delete_tags_of_logged_data')
        confirm_button = st.button('Continue', key=f'continue_delete_category')
        cancel_button = st.button('Cancel', key=f'cancel_delete_category')

        if confirm_button:
            data_to_delete = self.conn.query(f'SELECT {name_col} FROM {tags_table} WHERE {category_col}=:category',
                                             params={'category': category}, ttl=0)

            with self.conn.session as s:
                for i, row in data_to_delete.iterrows():
                    query = text(f"UPDATE {tags_table} SET {category_col}=Null, {tag_col}=Null WHERE {name_col}=:name")
                    s.execute(query, {'name': row[name_col]})
                    s.commit()

            if delete_tags_of_logged_data:
                self._update_raw_data_deleted_category(category)

            del self.categories_and_tags[category]
            self._update_yaml_and_rerun()

        if cancel_button:
            st.rerun()

    def _update_raw_data_deleted_category(self, category: str) -> None:
        """
        Updates tags and category of deleted category in the raw data tables to Null

        Parameters
        ----------
        category: str
            the category to delete

        Returns
        -------
        None
        """
        for table in [credit_card_table, bank_table]:
            match table:
                case Tables.CREDIT_CARD.value:
                    curr_tag_col = cc_tag_col
                    curr_category_col = cc_category_col
                case Tables.BANK.value:
                    curr_tag_col = bank_tag_col
                    curr_category_col = bank_category_col
                case _:
                    raise ValueError(f"Invalid table name: {table}")
            with self.conn.session as s:
                query = text(f"UPDATE {table} SET {curr_category_col}=Null, {curr_tag_col}=Null "
                             f"WHERE {curr_category_col}=:category")
                s.execute(query, {'category': category})
                s.commit()

    def _update_yaml_and_rerun(self) -> None:
        """
        update the yaml file with the current state of the categories and tags and rerun the app.

        Returns
        -------
        None
        """
        # sort the categories and tags by alphabetical order
        categories_and_tags = {category: sorted(list(set(tags))) for category, tags in self.categories_and_tags.items()}
        categories_and_tags = dict(sorted(categories_and_tags.items()))
        st.session_state["categories_and_tags"] = categories_and_tags

        # del the tags editing widgets state to prevent overwriting the changes
        for category in categories_and_tags.keys():
            try:
                del st.session_state[f"{category}_tags"]
            except KeyError:  # new category doesn't have a state yet
                pass

        # save the changes to the yaml file
        with open(CATEGORIES_PATH, 'w') as file:
            yaml.dump(categories_and_tags, file)
        st.rerun()  # TODO: remove this rerun after verifying that it is safe

    ########################################################
    # auto tagger functions
    ########################################################
    def pull_new_transactions_names(self) -> None:
        """
        pull new transactions names from the credit card and bank tables and insert them into the tags table

        Returns
        -------
        None
        """
        self._pull_new_cc_names()
        self._pull_new_bank_names()

    def _pull_new_cc_names(self):
        """pull new credit card transactions names from the credit card table and insert them into the tags table"""
        current_cc_names = self.conn.query(
            f"SELECT {name_col} FROM {tags_table} WHERE {service_col}='credit_card';", ttl=0
        )
        cc_names = self.conn.query(f"SELECT {cc_desc_col} FROM {credit_card_table};", ttl=0)
        new_cc_names = cc_names.loc[~cc_names[cc_desc_col].isin(current_cc_names[name_col]), cc_desc_col].unique()
        with self.conn.session as s:
            for name in new_cc_names:
                s.execute(
                    text(f'INSERT INTO {tags_table} ({name_col}, {service_col}) VALUES (:curr_name, "credit_card");'),
                    {'curr_name': name})
            s.commit()

    def _pull_new_bank_names(self):
        """pull new bank transactions names from the bank table and insert them into the tags table"""
        current_banks_names = self.conn.query(
            f"SELECT {name_col}, {account_number_col} FROM {tags_table} WHERE {service_col} = 'bank';", ttl=0
        )
        bank_names = self.conn.query(f"SELECT {bank_desc_col}, {bank_account_number_col} FROM {bank_table};", ttl=0)
        new_bank_names = bank_names.loc[~bank_names[bank_desc_col].isin(current_banks_names[name_col]) &
                                        ~bank_names[bank_account_number_col].isin(
                                            current_banks_names[account_number_col]),
        [bank_desc_col, bank_account_number_col]].drop_duplicates()
        with self.conn.session as s:
            for i, row in new_bank_names.iterrows():
                s.execute(text(f'INSERT INTO {tags_table} ({name_col}, {account_number_col}, {service_col})'
                               f' VALUES (:curr_name, :curr_account_number, "bank");'),
                          {'curr_name': row[bank_desc_col], 'curr_account_number': row[bank_account_number_col]})
            s.commit()

    def edit_auto_tagger_data(self, service: Literal['credit card', 'bank']):
        """edit tagged credit card data within the tags table"""
        match service:
            case 'credit card':
                service = Services.CREDIT_CARD.value
            case 'bank':
                service = Services.BANK.value
            case _:
                raise ValueError(f"Invalid service name: {service}")

        tagged_data = self.conn.query(
            f"SELECT * FROM {tags_table} "
            f"WHERE {category_col} is not Null "
            f"AND {service_col}=:service;",
            params={'service': service},
            ttl=0)
        if tagged_data.empty:
            st.write("No data to edit")
            return

        # editable table to edit the tagged data
        edited_tagged_data = st.data_editor(tagged_data[[name_col, category_col, tag_col]],
                                            hide_index=True, width=800, key=f'edit_{service}_tagged_data')
        if st.button('Save', key=f'save_edited_{service}_tagged_data'):
            # keep only the modified rows
            edited_tagged_data = edited_tagged_data[(edited_tagged_data[category_col] != tagged_data[category_col]) |
                                                    (edited_tagged_data[tag_col] != tagged_data[tag_col])]
            # save the edited data to the database
            with self.conn.session as s:
                for i, row in edited_tagged_data.iterrows():
                    category, tag = DataUtils.format_category_or_tag_strings(row[category_col], row[tag_col])
                    self._verify_category_and_tag(category, tag)

                    query = text(f'UPDATE {tags_table} SET {category_col}=:category, {tag_col}=:tag'
                                 f' WHERE {name_col}=:name AND {service_col}=:service;')
                    params = {
                        'category': category if category != '' else None,
                        'tag': tag if category != '' else None,
                        'name': row[name_col],
                        'service': service
                    }
                    s.execute(query, params)
                    s.commit()
            st.rerun()

    def tag_new_cc_data(self):
        """tag new credit card data"""

        df_tags = self.conn.query(f"""
            SELECT * FROM {tags_table}
            WHERE ({category_col} IS NULL OR {tag_col} IS NULL) AND {service_col} = 'credit_card';
            """,
                                  ttl=0
                                  )
        if df_tags.empty:
            st.write("No data to tag")
            return

        # editable table to tag the data
        categories = list(self.categories_and_tags.keys())
        tags = [f'{category}: {tag}' for category in categories for tag in self.categories_and_tags[category]]
        df_tags['new tag'] = ''
        tags_col = st.column_config.SelectboxColumn('new tag', options=tags)
        edited_df_tags = st.data_editor(df_tags[[name_col, 'new tag']], hide_index=True, width=800,
                                        column_config={'new tag': tags_col})

        # save the edited data
        if st.button('Save', key='save_cc_tagged_data'):
            edited_df_tags = edited_df_tags.loc[edited_df_tags['new tag'] != '']
            if not edited_df_tags.empty:
                edited_df_tags[category_col] = edited_df_tags['new tag'].apply(lambda x: x.split(': ', 1)[0])
                edited_df_tags[tag_col] = edited_df_tags['new tag'].apply(lambda x: x.split(': ', 1)[1])
                edited_df_tags = edited_df_tags.drop('new tag', axis=1)
                with self.conn.session as s:
                    for i, row in edited_df_tags.iterrows():
                        query = text(f"""
                                UPDATE {tags_table}
                                SET {category_col} = :category_val, {tag_col} = :tag_val
                                WHERE {name_col} = :name_val
                            """)
                        params = {
                            'category_val': row[category_col],
                            'tag_val': row[tag_col],
                            'name_val': row[name_col]
                        }
                        s.execute(query, params)
                    s.commit()
            st.rerun()

    def tag_new_bank_data(self):
        """tag new bank data"""
        df_tags = self.conn.query(f"""
            SELECT * FROM {tags_table}
            WHERE ({category_col} IS NULL OR {tag_col} IS NULL)
            AND {service_col} = 'bank';
            """,
                                  ttl=0)
        if df_tags.empty:
            st.write("No data to tag")
            return

        # editable table to tag the data
        categories = list(self.categories_and_tags.keys())
        tags = [f'{category}: {tag}' for category in categories for tag in self.categories_and_tags[category]]
        df_tags['new tag'] = ''
        tags_col = st.column_config.SelectboxColumn('new tag', options=tags)
        edited_df_tags = st.data_editor(df_tags[[name_col, account_number_col, 'new tag']], hide_index=True, width=800,
                                        column_config={'new tag': tags_col})

        # save the edited data
        if st.button('Save', key='save_bank_tagged_data'):
            edited_df_tags = edited_df_tags.loc[edited_df_tags['new tag'] != '']
            if not edited_df_tags.empty:
                edited_df_tags[category_col] = edited_df_tags['new tag'].apply(lambda x: x.split(': ', 1)[0])
                edited_df_tags[tag_col] = edited_df_tags['new tag'].apply(lambda x: x.split(': ', 1)[1])
                edited_df_tags = edited_df_tags.drop('new tag', axis=1)
                with self.conn.session as s:
                    for i, row in edited_df_tags.iterrows():
                        query = text(f"""
                                UPDATE {tags_table}
                                SET {category_col} = :category_val, {tag_col} = :tag_val
                                WHERE {name_col} = :name_val AND {account_number_col} = :account_number_val
                            """)
                        params = {
                            'category_val': row[category_col],
                            'tag_val': row[tag_col],
                            'name_val': row[name_col],
                            'account_number_val': row[account_number_col]
                        }
                        s.execute(query, params)
                    s.commit()
            st.rerun()

    def set_auto_tagger_rules(self, service: Literal['credit_card', 'bank']):
        """tag new credit card data"""
        df_tags = self.conn.query(
            f"""
            SELECT * FROM {tags_table}
            WHERE ({category_col} IS NULL OR {tag_col} IS NULL) AND {service_col} = :service;
            """,
            params={'service': service},
            ttl=0
        )

        st.subheader(f'Set new auto tagger rules')

        if df_tags.empty:
            st.write("No transactions to set new rules to")
            return

        df_tags = df_tags.sort_values(by=name_col)
        idx = sac.buttons(
            items=df_tags[name_col].tolist(),
            index=0,
            radius='lg',
            variant='outline',
            label='Select transaction to set its rule for the auto tagger',
            return_index=True,
            color='red',
            use_container_width=True,
        )

        if idx is not None:
            row = df_tags.iloc[idx]
            account_number = row[account_number_col] if service == 'bank' else None
            self._auto_tagger_editing_window(row[name_col], service, account_number, show_description=False)

    def edit_auto_tagger_rules(self, service: Literal['credit_card', 'bank']):
        """edit the auto tagger rules"""
        df_tags = self.conn.query(
            f"""
            SELECT * FROM {tags_table}
            WHERE ({category_col} IS NOT NULL OR {tag_col} IS NOT NULL) AND {service_col} = :service;
            """,
            params={'service': service},
            ttl=0
        )

        st.subheader(f'Edit auto tagger rules')

        if df_tags.empty:
            st.write("No rules to edit")
            return

        df_tags = df_tags.sort_values(by=name_col)
        changes = st.dataframe(
            df_tags,
            on_select='rerun',
            selection_mode='multi-row',
            column_order=[name_col, category_col, tag_col],
            hide_index=True,
            use_container_width=True
        )

        indices = changes['selection']['rows']
        for idx in indices:
            row = df_tags.iloc[idx]
            account_number = row[account_number_col] if service == 'bank' else None
            self._auto_tagger_editing_window(row[name_col], service, account_number, row[category_col], row[tag_col])

    @st.fragment
    def _auto_tagger_editing_window(
            self,
            description: str,
            service: Literal['credit_card', 'bank'],
            account_number: str | None = None,
            default_category: str | None = None,
            default_tag: str | None = None,
            show_description: bool = True
    ):
        """
        a fragment to tag new data for the auto tagger. The fragment displays the description of the transaction and
        allow the user to select the category and tag for the transaction. it contains a save button to save the
        selection.

        Parameters
        ----------
        description : str
            the description of the transaction
        service : Literal['credit_card', 'bank']
            the service of the transaction. Should be one of 'credit_card' or 'bank'.
        account_number : str | None
            the account number of the transaction. If None, the transaction is a credit card transaction. If not None,
            the transaction is a bank transaction

        Returns
        -------
        None
        """
        if service == 'bank' and account_number is None:
            raise ValueError("account_number should be provided for bank transactions tagging")

        # Columns for layout
        if service == 'credit_card':
            if show_description:
                desc_col_, catg_col_, tag_col_, update_method_col_, save_col_ = st.columns([0.2, 0.2, 0.2, 0.2, 0.2])
            else:
                catg_col_, tag_col_, update_method_col_, save_col_ = st.columns([0.2, 0.2, 0.2, 0.2])
        elif service == 'bank':
            if show_description:
                desc_col_, acc_num_col_, catg_col_, tag_col_, update_method_col_, save_col_ = \
                    st.columns([0.2, 0.2, 0.15, 0.15, 0.15, 0.15])
            else:
                acc_num_col_, catg_col_, tag_col_, update_method_col_, save_col_ = st.columns([0.2, 0.2, 0.2, 0.2, 0.2])
        else:
            raise ValueError(f"Invalid service name: {service}")

        if show_description:
            with desc_col_:  # noqa, desc_col_ is defined in case show_description is True
                st.markdown("<br>", unsafe_allow_html=True)  # Add space before text for better UI alignment
                st.markdown(
                    f"<div style='background-color: #82e0aa; padding: 10px; "
                    f"border-radius: 5px; color: white;'>{description}</div>",
                    unsafe_allow_html=True
                )

        if service == 'bank':
            with acc_num_col_:  # noqa, acc_num_col_ is defined in case account_number is not None
                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown(
                    f"<div style='background-color: #82e0aa; padding: 10px; "
                    f"border-radius: 5px; color: white;'>account: {account_number}</div>",
                    unsafe_allow_html=True
                )

        with catg_col_:
            categories = list(self.categories_and_tags.keys())
            category = st.selectbox(
                label="Select a Category",
                label_visibility="hidden",
                options=categories,
                index=None if default_category is None else categories.index(default_category),
                placeholder='Category',
                key=f'select_category_{description}_{service}_{account_number}_auto_tagger'
            )

        with tag_col_:
            tags = self.categories_and_tags.get(category, [])
            tag = st.selectbox(
                label="Select a Tag",
                label_visibility="hidden",
                options=tags,
                index=None if default_tag is None else tags.index(default_tag),
                placeholder='Tag',
                key=f'select_tag_{description}_{service}_{account_number}_auto_tagger'
            )

        with update_method_col_:
            method = st.selectbox(
                label='method',
                label_visibility="hidden",
                options=["All", "From now on"],
                index=None,
                placeholder="How to update",
                key=f'select_method_{description}_{service}_{account_number}_auto_tagger',
                help="Select 'All' to tag all of this transaction's occurrences. Select 'From now on'"
                     " to keep old tags and tag only future occurrences.")

        with save_col_:
            st.markdown("<br>", unsafe_allow_html=True)  # Add space before button
            if st.button('Save', key=f'save_{description}_{service}_{account_number}_auto_tagger'):
                if category is None or tag is None:
                    st.error('Please select both a category and a tag before saving.')

                # self._update_auto_tagger_table(description, category, tag, service, method, account_number)
                st.rerun()

    def _update_auto_tagger_table(self, name: str, category: str, tag: str, service: Literal['credit_card', 'bank'],
                                  method: Literal['All', 'From now on'], account_number: str | None = None) -> None:
        """update the auto tagger rules in the database"""
        with self.conn.session as s:
            params = {
                'category_val': category,
                'tag_val': tag,
                'name_val': name,
                'service_val': service
            }

            if service == 'credit_card':
                my_query = f"""
                    UPDATE {tags_table}
                    SET {category_col} = :category_val, {tag_col} = :tag_val
                    WHERE {name_col} = :name_val AND {service_col} = :service_val
                """
            elif service == 'bank':
                if account_number is None:
                    raise ValueError("account_number should be provided for bank transactions tagging")
                my_query = f"""
                    UPDATE {tags_table}
                    SET {category_col} = :category_val, {tag_col} = :tag_val
                    WHERE {name_col} = :name_val AND {service_col} = :service_val AND {account_number_col} = :account_number_val
                """
                params['account_number_val'] = account_number

            s.execute(text(my_query), params)
            s.commit()

        if method == 'All':
            self._update_raw_data_tags(name, category, tag, service, account_number)
        elif method == 'From now on':
            pass  # do nothing
        else:
            raise ValueError(f"Invalid auto tagger update method: {method}")

    def _update_raw_data_tags(self, name: str, category: str, tag: str, service: Literal['credit_card', 'bank'],
                              account_number: str | None = None) -> None:
        """
        update the tags of the raw data in the credit card and bank tables. If overwrite is True, all occurrences of the
        transaction with the name supplied will be updated. If overwrite is False, only transactions without a tag will
        be updated.

        Parameters
        ----------
        name : str
            the name of the transaction
        category : str
            the category to tag the transaction with
        tag : str
            the tag to tag the transaction with
        service : str
            the service of the transaction, should be one of 'credit_card' or 'bank'
        account_number : str | None
            the account number of the transaction, only used for bank transactions. If None, all transactions with the
            name supplied will be updated

        Returns
        -------
        None
        """
        if service == 'credit_card':
            table = credit_card_table
            name_col_ = cc_desc_col
            tag_col_ = cc_tag_col
            category_col_ = cc_category_col
        elif service == 'bank':
            table = bank_table
            name_col_ = bank_desc_col
            tag_col_ = bank_tag_col
            category_col_ = bank_category_col
        else:
            raise ValueError(f"Invalid service name: {service}")

        with self.conn.session as s:
            params = {
                'category_val': category,
                'tag_val': tag,
                'name_val': name
            }

            if service == 'credit_card':
                my_query = f"""
                    UPDATE {table}
                    SET {category_col_} = :category_val, {tag_col_} = :tag_val
                    WHERE {name_col_} = :name_val
                """
            elif service == 'bank':
                if account_number is None:
                    raise ValueError("account_number should be provided for bank transactions tagging")
                my_query = f"""
                    UPDATE {table}
                    SET {category_col_} = :category_val, {tag_col_} = :tag_val
                    WHERE {name_col_} = :name_val AND {bank_account_number_col} = :account_number_val
                """
                params['account_number_val'] = account_number

            s.execute(text(my_query), params)
            s.commit()

    ########################################################
    # manual tagging functions
    ########################################################
    def edit_raw_data_tags(self):
        """edit the tags of the raw data in the credit card and bank tables"""
        credit_card_data = DataUtils.get_table(self.conn, credit_card_table)
        bank_data = DataUtils.get_table(self.conn, bank_table)

        columns_order = [TransactionsTableFields.PROVIDER.value,
                         TransactionsTableFields.ACCOUNT_NAME.value,
                         TransactionsTableFields.ACCOUNT_NUMBER.value,
                         TransactionsTableFields.DATE.value,
                         TransactionsTableFields.DESCRIPTION.value,
                         TransactionsTableFields.AMOUNT.value,
                         TransactionsTableFields.CATEGORY.value,
                         TransactionsTableFields.TAG.value,
                         TransactionsTableFields.ID.value,
                         TransactionsTableFields.STATUS.value,
                         TransactionsTableFields.TYPE.value]

        # display the data
        widgets_map = {
            TransactionsTableFields.AMOUNT.value: 'number_range',
            TransactionsTableFields.DATE.value: 'date_range',
            TransactionsTableFields.PROVIDER.value: 'multiselect',
            TransactionsTableFields.ACCOUNT_NAME.value: 'multiselect',
            TransactionsTableFields.ACCOUNT_NUMBER.value: 'multiselect',
            TransactionsTableFields.DESCRIPTION.value: 'multiselect',
            TransactionsTableFields.CATEGORY.value: 'multiselect',
            TransactionsTableFields.TAG.value: 'multiselect',
            TransactionsTableFields.STATUS.value: 'multiselect',
            TransactionsTableFields.TYPE.value: 'multiselect',
        }

        table_type = st.selectbox(
            'Select data table to edit:',
            [credit_card_table.replace('_', ' '), bank_table.replace('_', ' ')],
            key="tagging_raw_data_table_type"
        )
        table_type = table_type.replace(' ', '_')
        # select the desired table you want to edit
        if table_type == credit_card_table:
            df_data = credit_card_data
            prefix = 'cc_'
        else:
            df_data = bank_data
            prefix = 'bank_'

        widget_col, data_col = st.columns([0.2, 0.8])

        # filter the data according to the user's input
        with widget_col:
            df_filter = PandasFilterWidgets(df_data, widgets_map, keys_prefix=prefix)
            df_data = df_filter.filter_df()

        # display the data and bulk edit it
        with data_col:
            selections = st.dataframe(
                df_data,
                key=f'{prefix}transactions_editor',
                column_order=columns_order,
                hide_index=False,
                on_select='rerun',
                selection_mode='single-row',
            )

            indices = selections['selection']['rows']
            service = table_type.replace('_transactions', '')
            for idx in indices:
                row = df_data.iloc[idx]
                self._manual_tagger_editing_window(row, service)

            # edited_data = edited_data.merge(df_data, how='outer', indicator=True)
            # edited_data = edited_data[edited_data['_merge'] == 'left_only'].drop('_merge', axis=1)
            # if not edited_data.empty:
            #     edited_data[[category_col, tag_col]] = edited_data.apply(
            #         lambda row:
            #         pd.Series(DataUtils.format_category_or_tag_strings(row[category_col], row[tag_col])),
            #         axis=1
            #     )
            #     verifications = edited_data.apply(
            #         lambda row: self._verify_category_and_tag(row[category_col], row[tag_col]), axis=1
            #     )
            #     if not verifications.all():
            #         st.error('Please fix the errors before saving the data.')
            #
            # if st.form_submit_button(label='Save'):
            #     if not edited_data.empty:
            #         if verifications.all():
            #             DataUtils.update_db_table(self.conn, table_type, edited_data)
            #         else:
            #             st.stop()
            #     st.rerun()

    @st.fragment
    def _manual_tagger_editing_window(self, row: pd.Series, service: Literal['credit_card', 'bank']):
        """
        a fragment to tag new data for the manual tagger. The fragment displays the description of the transaction and
        allow the user to select the category and tag for the transaction. it contains a save button to save the
        selection.

        Parameters
        ----------
        row : pd.Series
            the row of the transaction
        service : Literal['credit_card', 'bank']
            the service of the transaction. Should be one of 'credit_card' or 'bank'.

        Returns
        -------
        None
        """
        if service == 'bank':
            name_col_ = bank_desc_col
            amount_col_ = bank_amount_col
            tag_col_ = bank_tag_col
            category_col_ = bank_category_col
            id_col_ = bank_id_col
        elif service == 'credit_card':
            name_col_ = cc_desc_col
            amount_col_ = cc_amount_col
            tag_col_ = cc_tag_col
            category_col_ = cc_category_col
            id_col_ = cc_id_col
        else:
            raise ValueError(f"Invalid service name: {service}")

        if st.button("Split Transaction"):
            st.write("Coming Soon...")
            st.button("Back", key='back_from_split_transaction')
        else:
            # Columns for layout
            col_cat, col_tag, col_save = st.columns([0.4, 0.4, 0.2])

            with col_cat:
                categories = list(self.categories_and_tags.keys())
                category = st.selectbox(
                    label="Edit Category",
                    options=categories,
                    index=categories.index(row[category_col_]) if row[category_col_] in categories else None,
                    placeholder='Category',
                    key=f'manual_tagger_select_category_{row[name_col_]}'
                )

            with col_tag:
                tags = self.categories_and_tags.get(category, [])
                tag = st.selectbox(
                    label="Edit Tag",
                    options=tags,
                    index=tags.index(row[tag_col_]) if row[tag_col_] in tags else None,
                    placeholder='Tag',
                    key=f'manual_tagger_select_tag_{row[name_col_]}'
                )

            with col_save:
                st.markdown("<br>", unsafe_allow_html=True)  # Add space before button
                if st.button('Save', key=f'save_{row[name_col_]}'):
                    self._update_data_table(service, row[id_col_], category, tag)
                    st.rerun()

    def _update_data_table(self, service: Literal['credit_card', 'bank'], id_: int, category: str, tag: str) -> None:
        """
        update the tags of the raw data in the credit card and bank tables.

        Parameters
        ----------
        service : Literal['credit_card', 'bank']
            the service of the transaction, should be one of 'credit_card' or 'bank'
        id_ : int
            the id of the transaction
        category : str
            the category to tag the transaction with
        tag : str
            the tag to tag the transaction with

        Returns
        -------
        None
        """
        if service == 'credit_card':
            table = credit_card_table
            id_col_ = cc_id_col
            tag_col_ = cc_tag_col
            category_col_ = cc_category_col
        elif service == 'bank':
            table = bank_table
            id_col_ = bank_id_col
            tag_col_ = bank_tag_col
            category_col_ = bank_category_col
        else:
            raise ValueError(f"Invalid service name: {service}")

        with self.conn.session as s:
            params = {
                'category_val': category,
                'tag_val': tag,
                'id_val': id_
            }

            my_query = f"""
                UPDATE {table}
                SET {category_col_} = :category_val, {tag_col_} = :tag_val
                WHERE {id_col_} = :id_val
            """

            s.execute(text(my_query), params)
            s.commit()

    ########################################################
    # helper functions
    ########################################################
    def _verify_category_and_tag(self, category: str, tag: str) -> bool:
        """
        verify that the category and tag are valid

        Parameters
        ----------
        category: str
            the category to verify
        tag: str
            the tag to verify

        Returns
        -------
        bool
            True if the category and tag are valid, False otherwise
        """
        if category is None and tag is None:
            return True

        if (category is None and tag is not None) or (category is not None and tag is None):
            st.error(
                'Category and tag should be both None or both not None. please delete both fields or fill them both.')
            return False

        if category not in self.categories_and_tags.keys():
            st.error(f'Category "{category}" does not exist. Please select a valid category.'
                     f'In case you want to add a new category, please do so in the "Categories & Tags" tab.')
            return False

        if tag is None:
            st.error(
                f'Tag cannot be empty while setting a category. Please select a valid tag from the following list:\n'
                f'{self.categories_and_tags[category]}.')
            return False

        if tag not in self.categories_and_tags[category]:
            st.error(
                f'Tag "{tag}" does not exist in the category "{category}". Please select a valid tag from the following'
                f' list:\n{self.categories_and_tags[category]}.\n'
                f'In case you want to add a new tag, please do so in the "Categories & Tags" tab.')
            return False

        return True


class PandasFilterWidgets:
    def __init__(self, df: pd.DataFrame, widgets_map: dict[str, str] = None, keys_prefix: str = None):
        """
        This class will create widgets for filtering a Pandas DataFrame and return the filtered DataFrame.

        Parameters
        ----------
        df: pd.DataFrame
            The DataFrame to filter using the widgets.
        widgets_map: dict
            A dictionary whose keys are the column names of the DataFrame and whose values are the type of widget
            to create for that column. Only the columns in this dictionary will be used to create the widgets.
            Optional widgets are: 'text', 'select', 'multiselect', 'number_range', 'date_range'.
        keys_prefix: str
            A prefix to add to the keys of the widgets. This is useful when using multiple instances of this class in
            the same script.
        """
        self.df = df.copy()
        self.widgets_map = widgets_map if widgets_map is not None else {}
        self.keys_prefix = f'pandas_filter_widgets_{keys_prefix if keys_prefix is not None else ""}'
        self.widgets_returns = {}

        self.fetch_widgets_values()

    def fetch_widgets_values(self):
        """
        This function will create the widgets based on the widgets_map and store the values of the widgets in the
        widgets_returns dictionary.
        """
        for column, widget_type in self.widgets_map.items():
            match widget_type:
                case 'text':
                    self.widgets_returns[column] = self.create_text_widget(column)
                case 'select':
                    self.widgets_returns[column] = self.create_select_widget(column, multi=False)
                case 'multiselect':
                    self.widgets_returns[column] = self.create_select_widget(column, multi=True)
                case 'number_range':
                    self.widgets_returns[column] = self.create_slider_widget(column)
                case 'date_range':
                    self.widgets_returns[column] = self.create_date_range_widget(column)
                case _:
                    raise ValueError(f'Invalid widget type: {widget_type}')

    def create_slider_widget(self, column: str) -> tuple[float, float]:
        df = self.df.copy()
        df = df.loc[df[column].notna(), :]
        max_val = float(df[column].max())
        min_val = float(df[column].min())
        name = column.replace('_', ' ').title()
        lower_bound, upper_bound = st.slider(
            name, min_val, max_val, (min_val, max_val), 50.0, key=f'{self.keys_prefix}_{column}_slider'
        )
        return lower_bound, upper_bound

    def create_select_widget(self, column: str, multi: bool) -> str | list[str]:
        df = self.df.copy()
        df = df.loc[df[column].notna(), :]
        options = df[column].unique()
        options.sort()
        name = column.replace('_', ' ').title()
        if multi:
            selected_list = st.multiselect(name, options, key=f'{self.keys_prefix}_{column}_multiselect')
            return selected_list
        else:
            selected_item = st.selectbox(name, options, key=f'{self.keys_prefix}_{column}_select')
            return selected_item

    def create_text_widget(self, column: str) -> str | None:
        name = column.replace('_', ' ').title()
        text_ = st.text_input(name, key=f"{self.keys_prefix}_{column}_text")
        return text_

    def create_date_range_widget(self, column: str) -> tuple[datetime.date, datetime.date]:
        df = self.df.copy()
        df = df.loc[df[column].notna(), :]
        max_val = datetime.today().date()
        min_val = df[column].apply(lambda x: datetime.strptime(x, '%Y-%m-%d')).min().date()
        name = column.replace('_', ' ').title()
        dates = st.date_input(
            name, (min_val, datetime.today()), min_val, max_val, key=f'{self.keys_prefix}_{column}_date_input'
        )
        try:
            start_date, end_date = dates
        except ValueError:
            start_date, end_date = dates[0], dates[0]

        return start_date, end_date

    def filter_df(self):
        """
        This function will take the input dataframe and all the widgets generated from
        Streamlit Pandas. It will then return a filtered DataFrame based on the changes
        to the input widgets.

        df => the original Pandas DataFrame
        all_widgets => the widgets created by the function create_widgets().
        """
        res = self.df.copy()
        for column, widget_return in self.widgets_returns.items():
            match self.widgets_map[column]:
                case 'text':
                    res = self.filter_string(res, column, widget_return)
                case 'select':
                    res = self.filter_select(res, column, widget_return)
                case 'multiselect':
                    res = self.filter_select(res, column, widget_return)
                case 'number_range':
                    res = self.filter_range(res, column, widget_return[0], widget_return[1])
                case 'date_range':
                    res = self.filter_date(res, column, widget_return[0], widget_return[1])
        return res

    @staticmethod
    def filter_string(df: pd.DataFrame, column: str, text: str | None) -> pd.DataFrame:
        if text is not None:
            return df
        df = df.loc[df[column].str.contains(text, case=False, na=False), :]
        return df

    @staticmethod
    def filter_date(df: pd.DataFrame, column: str, start_date: datetime.date, end_date: datetime.date) -> pd.DataFrame:
        df[column] = df[column].apply(lambda x: datetime.strptime(x, '%Y-%m-%d').date())
        df = df.loc[(df[column] >= start_date) & (df[column] <= end_date), :]
        return df

    @staticmethod
    def filter_range(df: pd.DataFrame, column: str, min_val: float, max_val: float) -> pd.DataFrame:
        df = df.loc[(df[column] >= min_val) & (df[column] <= max_val), :]
        return df

    @staticmethod
    def filter_select(df: pd.DataFrame, column: str, selected_values: str | list[str] | None) -> pd.DataFrame:
        if selected_values is None or selected_values == []:
            return df

        if isinstance(selected_values, str):
            selected_values = [selected_values]
        df = df.loc[df[column].isin(selected_values), :]
        return df
