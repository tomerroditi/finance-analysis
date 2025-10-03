import pandas as pd
import plotly.express as px
import plotly.graph_objs as go
import streamlit as st
from plotly.subplots import make_subplots

from fad.app.naming_conventions import TransactionsTableFields
from fad.app.services.transactions_service import TransactionsService
from fad.app.utils.plotting import bar_plot_by_categories, pie_plot_by_categories, bar_plot_by_categories_over_time

provider_col = TransactionsTableFields.PROVIDER.value
account_name_col = TransactionsTableFields.ACCOUNT_NAME.value
amount_col = TransactionsTableFields.AMOUNT.value
date_col = TransactionsTableFields.DATE.value
category_col = TransactionsTableFields.CATEGORY.value
tag_col = TransactionsTableFields.TAG.value

display_fields = [provider_col, account_name_col, date_col, amount_col, category_col, tag_col]


# TODO: reload the data when tables has changed
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
            st.metric("Income", f"₪{kpis['income']:,.0f}")
        with col2:
            st.metric("Expenses", f"₪{abs(kpis['expenses']):,.0f}")
        with col3:
            st.metric("Liabilities Paid", f"₪{kpis['liabilities_paid']:,.0f}")
        with col4:
            st.metric("Savings and Investments", f"₪{kpis['savings_and_investments']:,.0f}")
        with col5:
            st.metric("Bank Balance Increase", f"₪{kpis['bank_balance_increase']:,.0f}")
        with col6:
            st.metric("Savings Rate", f"{kpis['savings_rate']:.1f}%")

        st.caption(f"Largest Expense Category: {kpis['largest_expense_cat_name']} (₪{kpis['largest_expense_cat_val']:,.0f})")

    def render_expenses_tab(self, filtered_df: pd.DataFrame):
        data = self.transactions_service.split_data_by_category_types(filtered_df)
        expenses_data = data['expenses']
        st.plotly_chart(pie_plot_by_categories(expenses_data, amount_col, category_col), use_container_width=True)
        st.plotly_chart(bar_plot_by_categories_over_time(expenses_data, amount_col, category_col, date_col, "1YE"), use_container_width=True)
        st.plotly_chart(bar_plot_by_categories_over_time(expenses_data, amount_col, category_col, date_col, "1ME"), use_container_width=True)
        st.dataframe(expenses_data[display_fields].sort_values(date_col, ascending=False), use_container_width=True)

    def render_savings_tab(self, filtered_df: pd.DataFrame):
        data = self.transactions_service.split_data_by_category_types(filtered_df)
        savings_data = data['savings']
        savings_data[amount_col] = savings_data[amount_col] * -1  # Ensure savings are shown as positive values
        st.subheader("Savings & Investments Analysis")
        st.metric("Total Saved/Invested", f"₪{savings_data[amount_col].sum():,.0f}")
        if not savings_data.empty:
            savings_data[date_col] = pd.to_datetime(savings_data[date_col])
            savings_data[date_col] = savings_data[date_col].dt.to_period('M').dt.to_timestamp()
            monthly_savings = savings_data.groupby([date_col, category_col, tag_col])[amount_col].sum().reset_index()

            unique_pairs = monthly_savings[[category_col, tag_col]].drop_duplicates().values.tolist()
            n_rows = len(unique_pairs)
            subplot_titles = [f"{cat} - {tag}" for cat, tag in unique_pairs]
            fig = make_subplots(
                rows=n_rows, cols=1,
                subplot_titles=subplot_titles
            )

            for i, (cat, tag) in enumerate(unique_pairs):
                group = monthly_savings[(monthly_savings[category_col] == cat) & (monthly_savings[tag_col] == tag)]
                group = group.groupby(date_col)[amount_col].sum().reset_index()
                fig.add_trace(
                    go.Waterfall(
                        x=group[date_col],
                        y=group[amount_col],
                        name=f"{cat} - {tag}",
                        increasing={"marker": {"color": 'rgb(144, 238, 144)'}},
                        decreasing={"marker": {"color": 'rgb(255, 192, 203)'}},
                    ),
                    row=i + 1, col=1
                )
                fig.update_yaxes(title_text='Amount (₪)', row=i + 1, col=1)
                fig.update_xaxes(tickformat="%Y-%m", dtick="M1", row=i + 1, col=1, tickangle=30)

            fig.update_layout(title='Savings & Investments Over Time', xaxis_title='Month', yaxis_title='Amount (₪)', height=300 * n_rows)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(savings_data[display_fields].sort_values(date_col, ascending=False), use_container_width=True)
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
            income_trend[date_col] = income_trend[date_col].dt.to_period('M').dt.to_timestamp()
            monthly_income = income_trend.groupby([date_col, category_col, tag_col])[amount_col].sum().reset_index()
            monthly_income['cat_and_tag'] = monthly_income[[category_col, tag_col]].fillna('Uncategorized').agg(' - '.join, axis=1)

            # Sort the legend entries
            sorted_legend = sorted(monthly_income['cat_and_tag'].unique())
            monthly_income['cat_and_tag'] = pd.Categorical(monthly_income['cat_and_tag'], categories=sorted_legend, ordered=True)

            use_color = st.checkbox("Show income breakdown", value=False, key="income_analysis_use_color_by_category_and_tag")
            if not use_color:
                monthly_income = monthly_income.groupby(date_col)[amount_col].sum().reset_index()

            fig = px.bar(
                monthly_income,
                x=date_col,
                y=amount_col,
                color='cat_and_tag' if use_color else None,
                category_orders={'cat_and_tag': sorted_legend},
                color_discrete_sequence=px.colors.qualitative.Plotly,
                title='Income Over Time',
                labels={'month': 'Month', amount_col: 'Amount (₪)', category_col: 'Category'},
                text_auto=True,
            )

            fig.update_layout(
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=-0.4,
                    xanchor="left",
                    x=0,
                    title_text=None,
                    valign='bottom',
                ),
            )

            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(income_data[display_fields].sort_values(date_col, ascending=False), use_container_width=True)
        else:
            st.info("No income data for the selected period.")

    def render_liabilities_tab(self, filtered_df: pd.DataFrame):
        st.subheader("Liabilities Analysis")
        summary = self.transactions_service.get_liabilities_summary(filtered_df)
        col_total_received, col_total_paid, col_outstanding_balance = st.columns(3)
        col_total_paid.metric("Total Paid", f"₪{summary['total_paid']:,.0f}")
        col_total_received.metric("Total Received", f"₪{summary['total_received']:,.0f}")
        col_outstanding_balance.metric("Outstanding Balance", f"₪{summary['outstanding_balance']:,.0f}")
        if not summary['filtered_liabilities'].empty:
            st.dataframe(summary['tag_summary'], use_container_width=True, hide_index=True)
            liabilities_trend = summary['filtered_liabilities'].copy()
            liabilities_trend[date_col] = pd.to_datetime(liabilities_trend[date_col])
            liabilities_trend[date_col] = liabilities_trend[date_col].dt.to_period('M').dt.to_timestamp()

            unique_pairs = liabilities_trend[[category_col, tag_col]].drop_duplicates().values.tolist()
            n_rows = len(unique_pairs)
            subplot_titles = [f"{cat} - {tag}" for cat, tag in unique_pairs]
            fig = make_subplots(
                rows=n_rows, cols=1,
                subplot_titles=subplot_titles,
                row_heights=[300] * n_rows,
            )
            for i, ((cat, tag), group) in enumerate(liabilities_trend.groupby([category_col, tag_col])):
                group = group.groupby(date_col)[amount_col].sum().reset_index()
                fig.add_trace(
                    go.Waterfall(
                        x=group[date_col],
                        y=group[amount_col],
                        name=f"{cat} - {tag}",
                        increasing={'marker': {'color': 'rgb(144, 238, 144)'}},
                        decreasing={'marker': {'color': 'rgb(255, 192, 203)'}}
                    ),
                    row=i + 1, col=1
                )
            fig.update_layout(xaxis_title='Month', yaxis_title='Amount (₪)', title='Liabilities Net Change Over Time')
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(summary['filtered_liabilities'][display_fields].sort_values(date_col, ascending=False), use_container_width=True)
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
