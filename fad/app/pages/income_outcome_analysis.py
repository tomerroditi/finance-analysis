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
from fad.naming_conventions import Tables, TransactionsTableFields
from fad.app.utils import DataUtils, PandasFilterWidgets, PlottingUtils

amount_col = TransactionsTableFields.AMOUNT.value
date_col = TransactionsTableFields.DATE.value
category_col = TransactionsTableFields.CATEGORY.value


conn = DataUtils.get_db_connection()

# get the data from the database
credit_card_table = Tables.CREDIT_CARD.value
bank_table = Tables.BANK.value

credit_card_data = DataUtils.get_table(conn, credit_card_table)
bank_data = DataUtils.get_table(conn, bank_table)

all_data = pd.concat([credit_card_data, bank_data])
all_data.loc[all_data[category_col].isnull(), category_col] = "Uncategorized"

categories_tab, tags_tab, monthly_recap_tab, yearly_recap_tab, paychecks_analysis_tab = \
    st.tabs(["Categories", "Tags", "Monthly Recap", "Yearly Recap", "Paychecks Analysis"])

# TODO: separate between income and outcome when plotting expenses and plot only outcomes
with categories_tab:
    st.caption("<p style='font-size:20px; color: black;'>"
               "This tab displays an analysis of your expenses by categories.<br>"
               "you may filter the data using the widgets below."
               "</p>",
               unsafe_allow_html=True)
    # filter data by user input
    widgets_map = {
        date_col: 'date_range',
        TransactionsTableFields.PROVIDER.value: 'multiselect',
        TransactionsTableFields.ACCOUNT_NAME.value: 'multiselect',
        TransactionsTableFields.ACCOUNT_NUMBER.value: 'multiselect',
    }
    df_filter = PandasFilterWidgets(all_data, widgets_map)
    filtered_data = df_filter.filter_df()
    filtered_data = filtered_data[~filtered_data[category_col].isin(["Salary", "Savings", "Investments"])]

    ignore_uncategorized = st.checkbox("Ignore Uncategorized", key="expenses_analysis_ignore_uncategorized")
    st.plotly_chart(
        PlottingUtils.plot_expenses_by_categories(filtered_data, amount_col, category_col, ignore_uncategorized)
    )
    st.plotly_chart(
        PlottingUtils.plot_expenses_by_categories_over_time(
            filtered_data, amount_col, category_col, date_col, "1Y", ignore_uncategorized
        )
    )
    st.plotly_chart(
        PlottingUtils.plot_expenses_by_categories_over_time(
            filtered_data, amount_col, category_col, date_col, "1M", ignore_uncategorized
        )
    )









