from typing import Dict, List
import streamlit as st
from fad.app.data_access.tagging_data import load_categories_and_tags, save_categories_and_tags

def _sorted_unique(lst):
    return sorted(list(set(lst)))

class CategoriesTagsService:
    def __init__(self):
        if 'categories_and_tags' not in st.session_state:
            st.session_state['categories_and_tags'] = load_categories_and_tags()
        self.categories_and_tags = st.session_state['categories_and_tags']

    def add_category(self, category: str) -> bool:
        if not category or not isinstance(category, str) or not category.strip():
            return False
        if category.lower() in [k.lower() for k in self.categories_and_tags.keys()]:
            return False
        self.categories_and_tags[category] = []
        self._save()
        return True

    def delete_category(self, category: str, protected_categories: List[str]) -> bool:
        if category in protected_categories:
            return False
        if category in self.categories_and_tags:
            del self.categories_and_tags[category]
            self._save()
            return True
        return False

    def reallocate_tags(self, old_category: str, new_category: str, tags: List[str]) -> bool:
        if old_category not in self.categories_and_tags or new_category not in self.categories_and_tags:
            return False
        # Remove tags from old category
        self.categories_and_tags[old_category] = [t for t in self.categories_and_tags[old_category] if t not in tags]
        # Add tags to new category (avoid duplicates)
        self.categories_and_tags[new_category] = _sorted_unique(self.categories_and_tags[new_category] + tags)
        self._save()
        return True

    def add_tag(self, category: str, tag: str) -> bool:
        if category not in self.categories_and_tags:
            return False
        if tag in self.categories_and_tags[category]:
            return False
        self.categories_and_tags[category].append(tag)
        self._save()
        return True

    def delete_tag(self, category: str, tag: str) -> bool:
        if category not in self.categories_and_tags:
            return False
        if tag not in self.categories_and_tags[category]:
            return False
        self.categories_and_tags[category].remove(tag)
        self._save()
        return True

    def _save(self):
        st.session_state['categories_and_tags'] = self.categories_and_tags
        save_categories_and_tags(self.categories_and_tags)
