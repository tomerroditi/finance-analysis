import streamlit as st

from fad.app.components.tagging_components import CategoriesTagsEditor
from fad.app.components.rule_based_tagging_components import RuleBasedTaggingComponent

tab_tags, tab_tagging = st.tabs(["Categories & Tags", "Tagging"])

with tab_tags:
    CategoriesTagsEditor().render()

with tab_tagging:
    RuleBasedTaggingComponent().render()
