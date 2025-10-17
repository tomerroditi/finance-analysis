import streamlit as st

from fad.app.components.tagging_components import TransactionsTaggingAndEditingComponent
from fad.app.components.data_scraping_components import DataScrapingComponent

st.subheader("Tag, Edit and Scrape Data")


tag_tab, edit_tab, scrap_tab = st.tabs([
    "Tag",
    "Edit",
    "scrape",
])

tag_edit_comp = TransactionsTaggingAndEditingComponent(key_suffix="my_data_page")
scraping_comp = DataScrapingComponent()

with tag_tab:
    tag_edit_comp.render_transactions_tagging()

with edit_tab:
    tag_edit_comp.render_transaction_editing()

with scrap_tab:
    scraping_comp.render_data_scraping()


