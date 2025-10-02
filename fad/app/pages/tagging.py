import streamlit as st

from fad.app.components.tagging_components import (
    CategoriesTagsEditor, TransactionsTaggingComponent
)


# Main tabs for the tagging page
tab_tags, tab_transactions = st.tabs([
    "Categories & Tags", 
    "Transaction Tagging", 
])

with tab_tags:
    CategoriesTagsEditor().render()

with tab_transactions:
    TransactionsTaggingComponent(key_suffix="tagging_page").render_tagging_page()
