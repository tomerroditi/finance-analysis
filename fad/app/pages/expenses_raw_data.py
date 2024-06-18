"""
this page should display the database of the raw data of the expenses as an editable table.
the user should be able to:
- add new transactions
- edit existing transactions
- delete transactions
"""

import streamlit as st
from streamlit_phone_number import st_phone_number

event = st_phone_number("Phone", placeholder="xxxxxx ", default_country="IL")
st.write(event)