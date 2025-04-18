import streamlit as st
import datetime as dt

from fad.app.utils.data import get_db_connection, get_latest_data_date, pull_data_from_all_scrapers_to_db
from fad.app.utils.credentials import load_credentials
from fad.app.utils.tagging import CategoriesAndTags
from fad import DB_PATH

conn = get_db_connection()

latest_data_date = get_latest_data_date(conn) - dt.timedelta(days=14)
start_date = st.date_input("Set the date from which to start fetching your data "
                           "(Defaults to 2 weeks previously to the latest date in your data).", value=latest_data_date)

if 'data_pulling_status' not in st.session_state:
    st.session_state.data_pulling_status = {"success": {}, "failed": {}}

creds = load_credentials()
available_scrapers = []
for service, providers in creds.items():
    for provider, accounts in providers.items():
        for account in accounts:
            available_scrapers.append(f"{service} - {provider} - {account}")
# select desired scrapers
scrapers_to_pull_from = st.pills(
    "Select the scrapers to pull data from",
    available_scrapers,
    selection_mode="multi",
    default=available_scrapers,
    key="selected_scrapers_to_pull_from")
creds_to_use = {}
for service, providers in creds.items():
    for provider, accounts in providers.items():
        for account, cred in accounts.items():
            if f"{service} - {provider} - {account}" in scrapers_to_pull_from:
                creds_to_use.update({service: {provider: {account: cred}}})

if st.button("Fetch Data") or st.session_state.get("current_pulled_resources") is not None:  # continue after 2fa scraping
    pull_data_from_all_scrapers_to_db(start_date, creds_to_use, DB_PATH)
    ct = CategoriesAndTags(conn)
    ct.update_raw_data_by_rules()

for type_, names in st.session_state.data_pulling_status.items():
    if type_ == 'failed':
        for msg in names.values():
            st.warning(msg, icon="⚠️")
    else:
        for msg in names.values():
            st.success(msg, icon="✅")
