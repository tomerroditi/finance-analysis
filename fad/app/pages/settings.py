import streamlit as st

from fad.app.utils.credentials import load_credentials, edit_delete_credentials, add_new_data_source


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
    credentials = load_credentials()

    # open a tab for each service
    cards_tab, banks_tab, insurance_tab = st.tabs(['Credit Cards', 'Banks', 'Insurance'])

    with cards_tab:
        edit_delete_credentials(credentials, 'credit_cards')
        add_new_data_source(credentials, 'credit_cards')

    with banks_tab:
        edit_delete_credentials(credentials, 'banks')
        add_new_data_source(credentials, 'banks')

    with insurance_tab:
        edit_delete_credentials(credentials, 'insurances')
        add_new_data_source(credentials, 'insurances')

