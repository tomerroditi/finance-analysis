"""
this page should display the incomes and outcomes of a user, and an interactive analysis of the data.

the user should be able to view the following data:
- annual income/outcome recap (bar plot)
- the total amount of money spent in the last month (or any other time period the user chooses)
- the total amount of money spent in each category and tag in the last month (or any other time period the user chooses)
- paychecks analysis - total income, net income, pension, taxes, etc.

"""
import streamlit as st
import pandas as pd
from fad.naming_conventions import Tables, TransactionsTableFields, NonExpensesCategories
from fad.app.utils import DataUtils, PandasFilterWidgets, PlottingUtils


amount_col = TransactionsTableFields.AMOUNT.value
date_col = TransactionsTableFields.DATE.value
category_col = TransactionsTableFields.CATEGORY.value
tag_col = TransactionsTableFields.TAG.value
non_expenses_categories = [category.value for category in NonExpensesCategories]

conn = DataUtils.get_db_connection()

# get the data from the database
credit_card_data = DataUtils.get_table(conn, Tables.CREDIT_CARD.value)
bank_data = DataUtils.get_table(conn, Tables.BANK.value)
all_data = pd.concat([credit_card_data, bank_data])
expenses_data = all_data[~all_data[category_col].isin(non_expenses_categories)]
expenses_data.loc[
        ((expenses_data[category_col] == "Other") & (expenses_data[tag_col] == "No tag")), [category_col, tag_col]
    ] = [None, None]

categories_tab, tags_tab, monthly_recap_tab, yearly_recap_tab, paychecks_analysis_tab = \
    st.tabs(["Categories", "Tags", "Monthly Recap", "Yearly Recap", "Paychecks Analysis"])

with categories_tab:
    # color black if light mode and white if dark mode
    st.caption("<p style='font-size:20px;'>"
               "Analysis of your expenses by categories.<br>"
               "</p>",
               unsafe_allow_html=True)
    # filter data by user input
    widgets_map = {
        date_col: 'date_range',
        TransactionsTableFields.PROVIDER.value: 'multiselect',
        TransactionsTableFields.ACCOUNT_NAME.value: 'multiselect',
        TransactionsTableFields.ACCOUNT_NUMBER.value: 'multiselect',
    }
    df_filter = PandasFilterWidgets(expenses_data.copy(), widgets_map, "expenses_analysis_categories")
    filtered_data = df_filter.filter_df()

    ignore_uncategorized = st.checkbox("Ignore Uncategorized", key="expenses_analysis_ignore_uncategorized_categories")
    if ignore_uncategorized:
        filtered_data = filtered_data[~filtered_data[category_col].isnull()]
    else:
        filtered_data.loc[filtered_data[category_col].isnull(), category_col] = "Uncategorized"

    st.plotly_chart(
        PlottingUtils.plot_expenses_by_categories(filtered_data, amount_col, category_col)
    )
    st.plotly_chart(
        PlottingUtils.plot_expenses_by_categories_over_time(
            filtered_data, amount_col, category_col, date_col, "1Y"
        )
    )
    st.plotly_chart(
        PlottingUtils.plot_expenses_by_categories_over_time(
            filtered_data, amount_col, category_col, date_col, "1M"
        )
    )

with tags_tab:
    st.caption("<p style='font-size:20px;'>"
               "Analysis of your expenses by tags.<br>"
               "</p>",
               unsafe_allow_html=True)
    # filter data by user input
    widgets_map = {
        date_col: 'date_range',
        TransactionsTableFields.PROVIDER.value: 'multiselect',
        TransactionsTableFields.ACCOUNT_NAME.value: 'multiselect',
        TransactionsTableFields.ACCOUNT_NUMBER.value: 'multiselect',
        TransactionsTableFields.CATEGORY.value: 'select',
    }
    df_filter = PandasFilterWidgets(expenses_data.copy(), widgets_map, "expenses_analysis_tags")
    filtered_data = df_filter.filter_df()

    ignore_uncategorized = st.checkbox("Ignore Uncategorized", key="expenses_analysis_ignore_uncategorized_tags")
    if ignore_uncategorized:
        filtered_data = filtered_data[~filtered_data[tag_col].isnull()]
    else:
        filtered_data.loc[filtered_data[tag_col].isnull(), tag_col] = "No tag"

    st.plotly_chart(
        PlottingUtils.plot_expenses_by_categories(filtered_data, amount_col, tag_col)
    )
    st.plotly_chart(
        PlottingUtils.plot_expenses_by_categories_over_time(
            filtered_data, amount_col, tag_col, date_col, "1Y"
        )
    )
    st.plotly_chart(
        PlottingUtils.plot_expenses_by_categories_over_time(
            filtered_data, amount_col, tag_col, date_col, "1M"
        )
    )
