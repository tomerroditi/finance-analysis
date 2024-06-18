import streamlit as st

from fad.app.utils import CredentialsUtils


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
    # fetch credentials
    credentials = CredentialsUtils.load_credentials()

    # open a tab for each service
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

