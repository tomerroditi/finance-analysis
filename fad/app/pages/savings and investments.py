import streamlit as st
from fad.app.components.investments_components import InvestmentsComponent

st.title("💰 Savings & Investments")

component = InvestmentsComponent(key_suffix="savings_investments_page")
component.render()
