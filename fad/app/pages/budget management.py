"""
rule - a certain amount of money that can be spent on tag/s of a category

tab1:
monthly budget management, should include:
- the total amount of money available for the month and tracking on how much is left to spend [v]
- add/delete/edit/view rules [v]
- view historical data [v]
- view the raw data of the defined rules
- subscriptions automatic tracking
- track liabilities returns (?)

tab 2:
isolated budget management for a project/event (wedding, big trip, home renovation, etc.), should include:
- add new project/event [v]
- the total amount of money available for the project and tracking on how much is left to spend [v]
- auto create a rule per tag with default spending limit of 1 [v]
- edit/view rules (forbid adding and deleting) [v]
- exclude project/event expenses from the monthly budget management expenses [v]
"""

import pandas as pd
import streamlit as st

from fad.app.naming_conventions import Tables
from fad.app.utils.data import get_db_connection, get_table
from fad.app.utils.budget_management import select_custom_month, select_current_month, add_new_rule, budget_overview, \
    copy_last_month_rules, add_new_project, select_project, view_project_budget, delete_project

budget_rules = get_table(get_db_connection(), Tables.BUDGET_RULES.value)
monthly_tab, project_tab = st.tabs(["Monthly Budget Management", "Project Budget Management"])

with monthly_tab:
    # TODO: view raw data of the defined rules expenses
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
        add_new_rule(year, month, budget_rules)

    copy_rules_col.button(
        "Copy last month's rules",
        on_click=copy_last_month_rules,
        args=(year, month, budget_rules),
        key="copy_last_month_rules",
        use_container_width=True
    )

    budget_overview(year, month, budget_rules)

with project_tab:
    col_select, col_add, col_delete = st.columns([8, 1, 1])
    with col_select:
        project_name = select_project(budget_rules)
    with col_add:
        st.markdown("<br>", unsafe_allow_html=True)
        st.button(
            "New project",
            on_click=add_new_project,
            args=(budget_rules,),
            key="add_new_budget_project",
            use_container_width=True
        )
    with col_delete:
        st.markdown("<br>", unsafe_allow_html=True)
        st.button(
            "Delete project",
            on_click=delete_project,
            key="delete_budget_project",
            use_container_width=True,
            args=(project_name,),
            disabled=project_name is None
        )

    if project_name is not None:
        view_project_budget(project_name, budget_rules)