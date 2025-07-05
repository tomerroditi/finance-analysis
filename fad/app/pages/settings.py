import streamlit as st

from fad.app.components.credentials_components import CredentialsComponents
from fad.app.services.credentials_service import CredentialsService

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
    credentials = CredentialsService().credentials
    credentials_ui = CredentialsComponents()

    # open a tab for each service
    cards_tab, banks_tab, insurance_tab = st.tabs(['Credit Cards', 'Banks', 'Insurance'])

    with cards_tab:
        credentials_ui.edit_delete_credentials('credit_cards')
        credentials_ui.add_new_data_source('credit_cards')

    with banks_tab:
        credentials_ui.edit_delete_credentials('banks')
        credentials_ui.add_new_data_source('banks')

    with insurance_tab:
        credentials_ui.edit_delete_credentials('insurances')
        credentials_ui.add_new_data_source('insurances')
