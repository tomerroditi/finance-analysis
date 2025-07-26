import streamlit as st

from fad.app.components.tagging_components import (
    CategoriesTagsEditor, TransactionsTaggingComponent, RuleBasedTaggingComponent
)


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
