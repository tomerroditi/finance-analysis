from unittest.mock import patch, MagicMock
import pytest
import streamlit as st
from fad.app.services.tagging_service import CategoriesTagsService

@pytest.fixture
def service():
    with patch("fad.app.services.tagging_service.load_categories_and_tags", return_value={}), \
        patch("fad.app.services.tagging_service.save_categories_and_tags", return_value=None):
        yield CategoriesTagsService()

def test_add_category(service):
    assert service.add_category("New Category") is True
    assert "New Category" in service.categories_and_tags

def test_delete_category(service):
    service.add_category("Temporary Category")
    assert service.delete_category("Temporary Category", []) is True
    assert "Temporary Category" not in service.categories_and_tags

def test_reallocate_tags(service):
    service.add_category("Category A")
    service.add_category("Category B")
    service.add_tag("Category A", "Tag1")
    assert service.reallocate_tags("Category A", "Category B", ["Tag1"]) is True
    assert "Tag1" in service.categories_and_tags["Category B"]
    assert "Tag1" not in service.categories_and_tags["Category A"]
