"""
this page should display the incomes and outcomes of a user, and an interactive analysis of the data.

- annual income/outcome recap (bar plot)
- the total amount of money spent in the last month (or any other time period the user chooses)
- the total amount of money spent in each category and tag in the last month (or any other time period the user chooses)
- paychecks analysis - total income, net income, pension, taxes, etc.
"""
import streamlit as st
import pandas as pd
from fad.app.components.income_outcome_analysis_components import IncomeOutcomeAnalysisComponent
from fad.app.naming_conventions import TransactionsTableFields
from fad.app.utils.widgets import PandasFilterWidgets

amount_col = TransactionsTableFields.AMOUNT.value
date_col = TransactionsTableFields.DATE.value
category_col = TransactionsTableFields.CATEGORY.value
tag_col = TransactionsTableFields.TAG.value

# --- INIT COMPONENT ---
analysis_component = IncomeOutcomeAnalysisComponent()
all_data = analysis_component.all_data

# --- FILTERS (Unified for all sections) ---
if st.session_state.get("analysis_filters_widgets", None) is None:
    widgets_map = {
        date_col: 'date_range',
        TransactionsTableFields.PROVIDER.value: 'multiselect',
        TransactionsTableFields.ACCOUNT_NAME.value: 'multiselect',
        TransactionsTableFields.ACCOUNT_NUMBER.value: 'multiselect',
    }
    df_filter = PandasFilterWidgets(all_data.copy(), widgets_map, "income_outcome_analysis_filters")
    st.session_state.analysis_filters_widgets = df_filter
else:
    df_filter = st.session_state.analysis_filters_widgets

df_filter.display_widgets()
filtered_data = df_filter.filter_df()

# --- RENDER UI ---
analysis_component.render_kpis(filtered_data)

tabs = st.tabs([
    "Expenses", "Savings & Investments", "Income", "Liabilities", "Breakdowns"
])

with tabs[0]:
    analysis_component.render_expenses_tab(filtered_data)
with tabs[1]:
    analysis_component.render_savings_tab(filtered_data)
with tabs[2]:
    analysis_component.render_income_tab(filtered_data)
with tabs[3]:
    analysis_component.render_liabilities_tab(filtered_data)
with tabs[4]:
    analysis_component.render_breakdowns_tab(filtered_data)
