import streamlit as st

from fad.app.components.tagging_components import (
    CategoriesTagsEditor,
    AutomaticTaggerComponent,
    ManuallyTaggingComponent
)


# TODO: add a feature that enables one to split a transaction into multiple transactions of different amounts and tags
# TODO: make it impossible to delete the Other: No tag tag
tab_tags, tab_auto_tagger, tab_manually_tag = st.tabs(["Categories & Tags", "Automatic Tagger", "Manually Tagging"])

with tab_tags:
    CategoriesTagsEditor().render()

with tab_auto_tagger:
    AutomaticTaggerComponent().render()


with (tab_manually_tag):
    ManuallyTaggingComponent().render()
