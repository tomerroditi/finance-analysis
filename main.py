import streamlit as st

# TODO: add a login page to authenticate the user
# TODO: make an option to add a new user
# TODO: add an option to delete a user
# TODO: improve credentials security by using `keyring` library
# TODO: make it so each account has its own database, or one big shared db?
# TODO: make it so accounts can be associated with each other for shared expenses (family account)

st.set_page_config(layout='wide')

pg = st.navigation(
    [
        st.Page("fad/app/overview.py", title="Overview"),
        st.Page("fad/app/pages/budget management.py", title="Budget Management"),
        st.Page("fad/app/pages/income_outcome_analysis.py", title="Income/Outcome Analysis"),
        st.Page("fad/app/pages/paycheks.py", title="Paychecks"),
        st.Page("fad/app/pages/savings and investments.py", title="Savings and Investments"),
        st.Page("fad/app/pages/tagging.py", title="Tagging"),
        st.Page("fad/app/pages/settings.py", title="Settings"),

    ]
)
pg.run()
