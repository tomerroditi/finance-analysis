import streamlit as st

from fad.app.utils import DataUtils, CredentialsUtils
from fad import DB_PATH


if 'conn' not in st.session_state:
    st.session_state['conn'] = st.connection('data', 'sql')
conn = st.session_state['conn']

latest_data_date = DataUtils.get_latest_data_date(conn)
start_date = st.date_input("Set the date from which to start fetching your data "
                           "(Defaults to the latest date in your data).", value=latest_data_date)
if st.button("Fetch Data"):
    creds = CredentialsUtils.load_credentials()
    DataUtils.pull_data(start_date, creds, DB_PATH)
    st.rerun()
