import streamlit as st

from fad.app.components.tagging_components import CategoriesTagsEditor
from fad.app.components.rule_based_tagging_components import RuleBasedTaggingComponent
from fad.app.components.transactions_tagging_components import TransactionsTaggingComponent

# Main tabs for the tagging page
tab_tags, tab_transactions, tab_rules = st.tabs([
    "Categories & Tags", 
    "Transaction Tagging", 
    "Rule Management"
])

with tab_tags:
    CategoriesTagsEditor().render()

with tab_transactions:
    TransactionsTaggingComponent().render()

with tab_rules:
    RuleBasedTaggingComponent().render()
