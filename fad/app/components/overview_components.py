import streamlit as st
import plotly.express as px
import pandas as pd

from fad.app.services.transactions_service import TransactionsService
from fad.app.naming_conventions import SavingsAndInvestmentsCategories


class OverviewComponents:
    def __init__(self, key_suffix: str = ""):
        self.key_suffix = key_suffix
        self.transactions_service = TransactionsService()

    def net_worth_over_time(self, frequency: str = "M") -> None:
        """
        Net Worth Over Time Component, which is calculated based on bank account transactions. we are excluding
        savings and investments categories from the calculation since they are not an expense that reduces net worth.

        Parameters
        ----------
        frequency : str
            The frequency for resampling the net worth data. Default is "W" for weekly.

        Returns
        -------
        None
        """
        st.markdown("Net Worth Over Time")
        transactions = self.transactions_service.get_all_transactions("bank")
        if transactions.empty:
            st.info("No bank account transactions found.")
            return
        transactions['date'] = pd.to_datetime(transactions['date'])

        # calculate liquidity over time
        transactions = transactions.sort_values(by='date')
        balance = pd.DataFrame({"balance": transactions["amount"].cumsum(), "date": transactions["date"]})
        balance = balance.resample(frequency, on="date").last().fillna(method='ffill').reset_index(names="date")
        fig = px.line(balance, x="date", y='balance', title='Liquidity Over Time', markers=True)
        st.plotly_chart(fig, use_container_width=True, key=f"liquidity_over_time_{self.key_suffix}")

        # plot investments over time
        investments_transactions = transactions[
            transactions["category"] == SavingsAndInvestmentsCategories.INVESTMENTS.value
        ]
        investments_transactions['amount'] = investments_transactions['amount'] * -1  # invert amounts for investments
        if not investments_transactions.empty:
            cum_amount_per_tag = investments_transactions.groupby("tag")["amount"].cumsum()
            investments_transactions = investments_transactions.assign(balance=cum_amount_per_tag)

            # total investments line
            total_investments = investments_transactions.copy()
            total_investments["balance"] = total_investments['amount'].cumsum()
            total_investments["tag"] = "Total"
            total_investments = total_investments.drop_duplicates(subset=['date'], keep='last')
            investments_transactions = pd.concat([investments_transactions, total_investments], ignore_index=True).sort_values(by='date')

            # add a zero balance entry before the earliest date for each tag to ensure the line starts from zero
            earliest_date = transactions['date'].min()
            for tag in investments_transactions['tag'].unique():
                entry_row = pd.DataFrame([{
                    'date': earliest_date,
                    'amount': 0,
                    'category': SavingsAndInvestmentsCategories.INVESTMENTS.value,
                    'tag': tag,
                    'balance': 0
                }])
                investments_transactions = pd.concat([investments_transactions, entry_row], ignore_index=True)

            # add missing dates per tag with forward fill
            investments_transactions = investments_transactions.sort_values(by='date')
            date_range = pd.date_range(start=earliest_date, end=pd.Timestamp.today(), freq=frequency)
            investments_transactions = (
                investments_transactions.set_index('date')
                .groupby('tag')
                .apply(lambda group: group.reindex(date_range, method='ffill'))
                .reset_index(level=0, drop=True)
                .reset_index()
                .rename(columns={'index': 'date'})
            )

            fig_investments = px.line(investments_transactions, x="date", y='balance', color='tag', title='Investments Over Time', symbol='tag')
            fig_investments.update_layout(legend=dict(orientation="h"))
            st.plotly_chart(fig_investments, use_container_width=True, key=f"investments_over_time_{self.key_suffix}")

    def retirement_savings_progress(self):
        st.markdown("Retirement Savings Progress")
        # define retirement payment goals
        # a plot with progress towards retirement savings goals (based on net worth)
        # stats about pansion savings, keren hishtalmut, brokerage accounts, investments

    def investment_portfolio_summary(self):
        st.markdown("Investment Portfolio Summary - pension, keren hishtalmut, brokerage accounts, investments")
        # daily changes in investment portfolio value
        # stats about investment portfolio performance and individual papers performance
        # breakdown by account type

    def debt_reduction_progress(self):
        st.markdown("Debt Reduction Progress")
        # a plot with progress towards debt reduction goals
        # stats about individual debts and overall debt situation

    def monthly_cash_flow_summary(self):
        st.markdown("Monthly Cash Flow Summary")
        # a plot with monthly income vs expenses
        # sankey diagram of cash flow sources and uses
