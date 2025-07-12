import pandas as pd
import streamlit as st
import plotly.graph_objs as go
from fad.app.services.transactions_service import TransactionsService
from fad.app.naming_conventions import TransactionsTableFields
from fad.app.utils.plotting import bar_plot_by_categories, pie_plot_by_categories, bar_plot_by_categories_over_time

amount_col = TransactionsTableFields.AMOUNT.value
date_col = TransactionsTableFields.DATE.value
category_col = TransactionsTableFields.CATEGORY.value
tag_col = TransactionsTableFields.TAG.value

class IncomeOutcomeAnalysisComponent:
    def __init__(self, conn=None):
        self.transactions_service = TransactionsService(conn) if conn else TransactionsService()
        self.all_data = self.transactions_service.get_data_for_analysis()

    def get_filtered_data(self, filters: dict) -> pd.DataFrame:
        df = self.all_data.copy()
        for col, val in filters.items():
            if val is not None:
                if isinstance(val, tuple) and len(val) == 2 and pd.api.types.is_datetime64_any_dtype(df[col]):
                    df = df[(df[col] >= val[0]) & (df[col] <= val[1])]
                elif isinstance(val, list):
                    df = df[df[col].isin(val)]
                else:
                    df = df[df[col] == val]
        return df

    def render_kpis(self, filtered_df: pd.DataFrame):
        kpis = self.transactions_service.get_kpis(filtered_df)
        st.subheader("Key Financial Metrics")
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        with col1:
            st.metric("Total Income", f"₪{kpis['total_income']:,.0f}")
        with col2:
            st.metric("Total Expenses", f"₪{abs(kpis['total_expenses']):,.0f}")
        with col3:
            st.metric("Total Savings/Investments", f"₪{kpis['total_savings']:,.0f}")
        with col4:
            st.metric("Net Savings", f"₪{kpis['net_savings']:,.0f}")
        with col5:
            st.metric("Actual Savings Rate", f"{kpis['actual_savings_rate']:.1f}%")
        with col6:
            st.metric("Liabilities Paid/Received", f"₪{kpis['liabilities_paid']:,.0f} / ₪{kpis['liabilities_received']:,.0f}")
        st.caption(f"Largest Expense Category: {kpis['largest_expense_cat_name']} (₪{kpis['largest_expense_cat_val']:,.0f})")

    def render_expenses_tab(self, filtered_df: pd.DataFrame):
        data = self.transactions_service.split_data_by_category_types(filtered_df)
        expenses_data = data['expenses']
        st.subheader("Actual Expenses Analysis")
        st.plotly_chart(bar_plot_by_categories(expenses_data, amount_col, category_col), use_container_width=True)
        st.plotly_chart(pie_plot_by_categories(expenses_data, amount_col, category_col), use_container_width=True)
        st.plotly_chart(bar_plot_by_categories_over_time(expenses_data, amount_col, category_col, date_col, "1YE"), use_container_width=True)
        st.plotly_chart(bar_plot_by_categories_over_time(expenses_data, amount_col, category_col, date_col, "1ME"), use_container_width=True)
        st.dataframe(expenses_data[[date_col, amount_col, category_col, tag_col]].sort_values(date_col, ascending=False), use_container_width=True)

    def render_savings_tab(self, filtered_df: pd.DataFrame):
        data = self.transactions_service.split_data_by_category_types(filtered_df)
        savings_data = data['savings']
        st.subheader("Savings & Investments Analysis")
        st.metric("Total Saved/Invested", f"₪{savings_data[amount_col].sum():,.0f}")
        if not savings_data.empty:
            savings_trend = savings_data.copy()
            savings_trend[date_col] = pd.to_datetime(savings_trend[date_col])
            savings_trend['month'] = savings_trend[date_col].dt.to_period('M').dt.to_timestamp()
            monthly_savings = savings_trend.groupby('month')[amount_col].sum().reset_index()
            fig = go.Figure()
            fig.add_trace(go.Bar(x=monthly_savings['month'], y=monthly_savings[amount_col], name='Savings/Investments', marker_color='purple'))
            fig.update_layout(xaxis_title='Month', yaxis_title='Amount (₪)', title='Savings/Investments Over Time')
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(savings_data[[date_col, amount_col, category_col, tag_col]].sort_values(date_col, ascending=False), use_container_width=True)
        else:
            st.info("No savings/investments data for the selected period.")

    def render_income_tab(self, filtered_df: pd.DataFrame):
        data = self.transactions_service.split_data_by_category_types(filtered_df)
        income_data = data['income']
        st.subheader("Income Analysis")
        st.metric("Total Income", f"₪{income_data[amount_col].sum():,.0f}")
        if not income_data.empty:
            income_trend = income_data.copy()
            income_trend[date_col] = pd.to_datetime(income_trend[date_col])
            income_trend['month'] = income_trend[date_col].dt.to_period('M').dt.to_timestamp()
            monthly_income = income_trend.groupby(['month', category_col])[amount_col].sum().reset_index()
            fig = go.Figure()
            for cat in monthly_income[category_col].unique():
                cat_data = monthly_income[monthly_income[category_col] == cat]
                fig.add_trace(go.Bar(x=cat_data['month'], y=cat_data[amount_col], name=cat))
            fig.update_layout(barmode='stack', xaxis_title='Month', yaxis_title='Amount (₪)', title='Income Over Time')
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(income_data[[date_col, amount_col, category_col, tag_col]].sort_values(date_col, ascending=False), use_container_width=True)
        else:
            st.info("No income data for the selected period.")

    def render_liabilities_tab(self, filtered_df: pd.DataFrame):
        st.subheader("Liabilities Analysis")
        summary = self.transactions_service.get_liabilities_summary(filtered_df)
        st.metric("Total Paid", f"₪{summary['total_paid']:,.0f}")
        st.metric("Total Received", f"₪{summary['total_received']:,.0f}")
        st.metric("Net Change", f"₪{summary['net_change']:,.0f}")
        if not summary['filtered_liabilities'].empty:
            st.dataframe(summary['tag_summary'], use_container_width=True)
            liabilities_trend = summary['filtered_liabilities'].copy()
            liabilities_trend[date_col] = pd.to_datetime(liabilities_trend[date_col])
            liabilities_trend['month'] = liabilities_trend[date_col].dt.to_period('M').dt.to_timestamp()
            monthly_liabilities = liabilities_trend.groupby('month')[amount_col].sum().reset_index()
            # Make all values positive for the figure
            monthly_liabilities[amount_col] = monthly_liabilities[amount_col].abs()
            fig = go.Figure()
            fig.add_trace(go.Bar(x=monthly_liabilities['month'], y=monthly_liabilities[amount_col], name='Net Liabilities', marker_color='orange'))
            fig.update_layout(xaxis_title='Month', yaxis_title='Amount (₪)', title='Liabilities Net Change Over Time')
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(summary['filtered_liabilities'][[date_col, amount_col, category_col, tag_col]].sort_values(date_col, ascending=False), use_container_width=True)
        else:
            st.info("No liabilities data for the selected period.")

    def render_breakdowns_tab(self, filtered_df: pd.DataFrame):
        data = self.transactions_service.split_data_by_category_types(filtered_df)
        expenses_data = data['expenses']
        categories_tab, tags_tab = st.tabs(["Categories", "Tags"])
        with categories_tab:
            st.caption("Analysis of your expenses by categories.")
            ignore_uncategorized = st.checkbox("Ignore Uncategorized", key="expenses_analysis_ignore_uncategorized_categories")
            exp_data = expenses_data.copy()
            if ignore_uncategorized:
                exp_data = exp_data[~exp_data[category_col].isnull()]
            else:
                exp_data.loc[exp_data[category_col].isnull(), category_col] = "Uncategorized"
            st.plotly_chart(bar_plot_by_categories(exp_data, amount_col, category_col), key="bar_plot_by_categories")
            st.plotly_chart(pie_plot_by_categories(exp_data, amount_col, category_col), key="pie_plot_by_categories")
            st.plotly_chart(bar_plot_by_categories_over_time(exp_data, amount_col, category_col, date_col, "1YE"), key="bar_plot_by_categories_over_time_1Y")
            st.plotly_chart(bar_plot_by_categories_over_time(exp_data, amount_col, category_col, date_col, "1ME"), key="bar_plot_by_categories_over_time_1M")
        with tags_tab:
            st.caption("Analysis of your expenses by tags.")
            ignore_uncategorized = st.checkbox("Ignore Uncategorized", key="expenses_analysis_ignore_uncategorized_tags")
            tag_data = expenses_data.copy()
            if ignore_uncategorized:
                tag_data = tag_data[~tag_data[tag_col].isnull()]
            else:
                tag_data.loc[tag_data[tag_col].isnull(), tag_col] = "No tag"
            st.plotly_chart(bar_plot_by_categories(tag_data, amount_col, tag_col), key="bar_plot_by_tags")
            st.plotly_chart(bar_plot_by_categories_over_time(tag_data, amount_col, tag_col, date_col, "1YE"), key="bar_plot_by_tags_over_time_1Y")
            st.plotly_chart(bar_plot_by_categories_over_time(tag_data, amount_col, tag_col, date_col, "1ME"), key="bar_plot_by_tags_over_time_1M")
