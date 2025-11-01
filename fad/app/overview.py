import streamlit as st

from fad.app.components.overview_components import OverviewComponents


overview_comp = OverviewComponents()
overview_comp.net_worth_over_time()
overview_comp.retirement_savings_progress()
overview_comp.investment_portfolio_summary()
overview_comp.debt_reduction_progress()
overview_comp.monthly_cash_flow_summary()