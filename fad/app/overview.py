import streamlit as st
import datetime as dt

from fad.app.utils.data import get_db_connection, get_latest_data_date, pull_data
from fad.app.utils.credentials import load_credentials
from fad.app.utils.tagging import CategoriesAndTags
from fad import DB_PATH

conn = get_db_connection()

latest_data_date = get_latest_data_date(conn) - dt.timedelta(days=14)
start_date = st.date_input("Set the date from which to start fetching your data "
                           "(Defaults to 2 weeks previously to the latest date in your data).", value=latest_data_date)
if st.button("Fetch Data") or st.session_state.get("pulling_data", False):
    st.session_state.pulling_data = True
    creds = load_credentials()
    pull_data(start_date, creds, DB_PATH)
    ct = CategoriesAndTags(conn)
    ct.update_raw_data_by_rules()
