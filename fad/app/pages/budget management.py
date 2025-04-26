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
import streamlit as st

from fad.app.components.budget_overview import (
    MonthlyBudgetUI,
    ProjectBudgetUI,
)

monthly_tab, project_tab = st.tabs(["Monthly Budget Management", "Project Budget Management"])

with monthly_tab:
    # TODO: make the raw data editable from here as well
    monthly_ui = MonthlyBudgetUI()
    monthly_ui.select_month()
    monthly_ui.add_or_copy_rules_ui()
    monthly_ui.monthly_budget_overview()
with project_tab:
    project_ui = ProjectBudgetUI()
    project_ui.project_budget_buttons_bar()
    project_ui.project_budget_overview()
