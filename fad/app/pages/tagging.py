import streamlit as st

from fad.app.utils.tagging import CategoriesAndTags
from fad.app.utils.data import get_db_connection


# TODO: add a feature that enables one to split a transaction into multiple transactions of different amounts and tags
# TODO: make it impossible to delete the Other: No tag tag
categories_and_tags = CategoriesAndTags(get_db_connection())
tab_tags, tab_auto_tagger, tab_manually_tag = st.tabs(["Categories & Tags", "Automatic Tagger", "Manually Tagging"])

with tab_tags:
    categories_and_tags.edit_categories_and_tags()

with tab_auto_tagger:
    st.caption("<p style='font-size:20px;'>"
               "The automatic tagger will tag new data according to the rules you set here"
               "</p>",
               unsafe_allow_html=True)
    categories_and_tags.pull_new_transactions_names()
    cc_tab, bank_tab = st.tabs(["Credit Card", "Bank"])

    with cc_tab:
        categories_and_tags.set_auto_tagger_rules('credit_card')
        st.divider()
        categories_and_tags.edit_auto_tagger_rules('credit_card')

    with bank_tab:
        categories_and_tags.set_auto_tagger_rules('bank')
        st.divider()
        categories_and_tags.edit_auto_tagger_rules('bank')

with (tab_manually_tag):
    categories_and_tags.edit_raw_data_tags()
