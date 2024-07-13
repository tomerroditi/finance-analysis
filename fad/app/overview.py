import streamlit as st
import datetime as dt

from fad.app.utils import DataUtils, CredentialsUtils
from fad import DB_PATH


conn = DataUtils.get_db_connection()

latest_data_date = DataUtils.get_latest_data_date(conn) - dt.timedelta(days=14)
start_date = st.date_input("Set the date from which to start fetching your data "
                           "(Defaults to 2 weeks previously to the latest date in your data).", value=latest_data_date)
if st.button("Fetch Data"):
    creds = CredentialsUtils.load_credentials()
    DataUtils.pull_data(start_date, creds, DB_PATH)
    st.rerun()
