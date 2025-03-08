from streamlit.testing.v1 import AppTest

from fad.app.utils.tagging import CategoriesAndTags


def test_tagging_page():
    at = AppTest.from_function(CategoriesAndTags._set_auto_tagger_rules_container)
    at.run()
