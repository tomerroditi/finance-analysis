import streamlit as st
import plotly.express as px

from fad.app.services.overview_service import OverviewService


class OverviewComponents:
    def __init__(self, key_suffix: str = ""):
        self.key_suffix = key_suffix
        self.overview_service = OverviewService()

    def net_worth_over_time(self, frequency: str = "M") -> None:
        """Display liquidity and investments over time charts."""
        st.markdown("Net Worth Over Time")

        transactions = self.overview_service.get_transactions_for_net_worth()
        if transactions.empty:
            st.info("No bank account transactions found.")
            return

        self._display_liquidity_chart(transactions, frequency)
        self._display_investments_chart(transactions, frequency)

    def _display_liquidity_chart(self, transactions, frequency: str) -> None:
        """Display cumulative balance over time chart."""
        balance_df = self.overview_service.calculate_cumulative_balance(transactions, frequency)
        fig = px.line(balance_df, x="date", y='balance', title='Liquidity Over Time', markers=True, line_shape='hv')
        st.plotly_chart(fig, use_container_width=True, key=f"liquidity_over_time_{self.key_suffix}")

    def _display_investments_chart(self, transactions, frequency: str) -> None:
        """Display investments balance over time by tag."""
        investments_df = self.overview_service.get_investment_transactions(transactions)
        if investments_df.empty:
            return

        investments_df = self.overview_service.prepare_investments_over_time(
            investments_df, transactions, frequency
        )
        fig = px.line(
            investments_df,
            x="date",
            y='balance',
            color='tag',
            title='Investments Over Time',
            symbol='tag',
            line_shape='hv',
        )
        fig.update_layout(legend=dict(orientation="h"))
        st.plotly_chart(fig, use_container_width=True, key=f"investments_over_time_{self.key_suffix}")

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
