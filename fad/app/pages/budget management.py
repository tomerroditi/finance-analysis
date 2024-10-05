"""
tab1:
monthly budget management, should include:
- the total amount of money available for the month and tracking on how much is left to spend
- limitation on how much can be spent per category and tags
- the ability to add/edit/delete a new category or tag limit
- subscriptions automatic tracking
- should view historical data of the monthly budget management
- track liabilities returns

tab 2:
isolated budget management for a project/event (wedding, big trip, home renovation, etc.), should include:
- the total amount of money available for the project and tracking on how much is left to spend
- limitation on how much can be spent per tag of the project
- the ability to add/edit/delete a new tag limit
- the ability to add a new project/event
- the isolated project/event should not be included in the monthly budget management expenses
"""

import pandas as pd
import streamlit as st

from fad.app.utils.budget_management import select_custom_month, select_current_month, add_new_rule, budget_overview, \
    copy_last_month_rules

monthly_tab, project_tab = st.tabs(["Monthly Budget Management", "Project Budget Management"])

with monthly_tab:
    st.session_state.setdefault("year", pd.Timestamp.now().year)
    st.session_state.setdefault("month", pd.Timestamp.now().month)

    history_col, curr_month_col, _ = st.columns([3, 1, 4])
    with history_col:
        select_custom_month()
    with curr_month_col:
        select_current_month()

    year, month = st.session_state.year, st.session_state.month

    add_rule_col, copy_rules_col = st.columns([4, 1])
    with add_rule_col:
        add_new_rule(year, month)

    copy_rules_col.button(
        "Copy last month's rules",
        on_click=copy_last_month_rules,
        args=(year, month),
        kwargs={"overwrite": True},
        key="copy_last_month_rules",
        use_container_width=True
    )

    budget_overview(year, month)
