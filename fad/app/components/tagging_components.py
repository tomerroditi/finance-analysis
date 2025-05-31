import streamlit as st
from typing import List
from fad.app.services.tagging_service import CategoriesTagsService
from fad.app.naming_conventions import NonExpensesCategories

def format_category_or_tag_strings(s: str) -> str:
    if not s:
        return s
    if s.isupper():
        return s.upper()
    return s.title()

class CategoriesTagsEditor:
    def __init__(self):
        self.service = CategoriesTagsService()
        self.protected_categories = [e.value for e in NonExpensesCategories]
    #     # Call the static method to inject CSS
    #     self.inject_css_for_pills()

    # @staticmethod
    # def inject_css_for_pills():
    #     # Generate CSS for all pills widgets using their keys
    #     for category in st.session_state['categories_and_tags'].keys():
    #         widget_key = f"{category}_tags"
    #         st.markdown(
    #             f"""
    #             <style>
    #             .st-key-{widget_key} p {{
    #                 color: #007BFF; /* Blue color */
    #                 font-size: 18px; /* Adjust the font size */
    #             }}
    #             /* Exclude label text from color changes */
    #             .st-key-{widget_key} label div {{
    #                 color: inherit; /* Inherit the default color */
    #             }}
    #             </style>
    #             """,
    #             unsafe_allow_html=True
    #         )

    def render(self):
        # Always reload from session state to reflect latest changes
        self.service.categories_and_tags = st.session_state['categories_and_tags']
        st.markdown(
            'Pay attention to the special Categories: "Ignore", "Salary", "Other Income", and "Investments".<br>'
            'These categories are used for special purposes in the app and you cannot delete them.',
            unsafe_allow_html=True
        )
        add_col, realloc_col, _ = st.columns([0.15, 0.15, 0.7])
        with add_col:
            st.button('New Category', key='add_new_category_button', on_click=self._add_new_category_dialog)
        with realloc_col:
            st.button('Reallocate Tags', key='reallocate_tags_button', on_click=self._reallocate_tags_dialog)
        # Sort categories alphabetically
        for category in sorted(self.service.categories_and_tags.keys()):
            tags = sorted(self.service.categories_and_tags[category])
            self._view_and_edit_tags(category, tags)
            disable = category in self.protected_categories
            st.button(f'Delete {category}', key=f'delete_{category}', disabled=disable,
                      on_click=self._delete_category_dialog, args=(category,))

    @st.fragment
    def _view_and_edit_tags(self, category: str, tags: List[str]):
        # Always reload from session state to reflect latest changes
        self.service.categories_and_tags = st.session_state['categories_and_tags']
        st.subheader(category, divider="gray")
        # Use segmented control with multi-selection to display and select multiple tags
        selected_tags = st.pills(
            'Tags',
            options=tags,
            selection_mode='multi',
            format_func=lambda tag: f"🔖 {tag.title()}",  # Add an icon and format tags to title case
            key=f'{category}_tags'
        )
        # Align buttons in the same row
        edit_col, realloc_col, add_col, delete_col, _ = st.columns([1, 1.5, 1, 1.5, 9])
        with edit_col:
            if st.button('Edit Tag', key=f'edit_{category}_tag'):
                if selected_tags:
                    self._edit_tag_dialog(category, selected_tags)
                else:
                    st.session_state['warning_message'] = 'No tags selected for editing.'
        with realloc_col:
            if st.button('Reallocate Tags', key=f'reallocate_{category}_tags'):
                if selected_tags:
                    self._reallocate_tags_dialog(category, selected_tags)
                else:
                    st.session_state['warning_message'] = 'No tags selected for reallocation.'
        with add_col:
            if st.button('Add Tag', key=f'add_{category}_tag'):
                self._add_tag_dialog(category)
        with delete_col:
            if st.button('Delete Tag', key=f'delete_{category}_tag'):
                if selected_tags:
                    self._delete_tag_dialog(category, selected_tags)
                else:
                    st.session_state['warning_message'] = 'No tags selected for deletion.'

        # Display warning message in a separate container
        if 'warning_message' in st.session_state:
            st.warning(st.session_state['warning_message'])
            del st.session_state['warning_message']

    @st.dialog('Edit Tag')
    def _edit_tag_dialog(self, category: str, tags: List[str]):
        edited_tags = {}
        for tag in tags:
            new_tag = st.text_input(f'Edit Tag: {tag}', value=tag, key=f'edit_{category}_{tag}_input')
            edited_tags[tag] = new_tag
        if st.button('Save All', key=f'save_all_edit_{category}_tags'):
            success = True
            for old_tag, new_tag in edited_tags.items():
                if old_tag != new_tag:
                    if not (self.service.delete_tag(category, old_tag) and self.service.add_tag(category, new_tag)):
                        success = False
            if success:
                st.success("All tags updated successfully.")
                st.rerun()
            else:
                st.error("Failed to update some tags.")
        if st.button('Cancel', key=f'cancel_edit_{category}_tags'):
            st.rerun()

    @st.dialog('Add Tag')
    def _add_tag_dialog(self, category: str):
        new_tag = st.text_input('New Tag', key=f'new_{category}_tag_input')
        if st.button('Add', key=f'add_new_{category}_tag'):
            if self.service.add_tag(category, new_tag):
                st.success(f"Tag '{new_tag}' added.")
                st.rerun()
            else:
                st.error("Failed to add tag.")
        if st.button('Cancel', key=f'cancel_add_{category}_tag'):
            st.rerun()

    @st.dialog('Add New Category')
    def _add_new_category_dialog(self):
        self.service.categories_and_tags = st.session_state['categories_and_tags']
        new_category = st.text_input('New Category Name', key='new_category')
        if st.button('Add', key='add_category_btn'):
            formatted_category = format_category_or_tag_strings(new_category)
            if self.service.add_category(formatted_category):
                st.success(f"Category '{formatted_category}' added successfully.")
                st.rerun()
            else:
                st.error("Invalid category name or category already exists.")
        if st.button('Cancel', key='cancel_add_category_btn'):
            st.rerun()

    @st.dialog('Reallocate Tags')
    def _reallocate_tags_dialog(self, category: str, selected_tags: List[str]):
        self.service.categories_and_tags = st.session_state['categories_and_tags']
        all_categories = sorted(self.service.categories_and_tags.keys())
        # Remove the current category from the list of new categories
        new_category_options = [cat for cat in all_categories if cat != category]
        old_category = category
        if old_category:
            tags_to_select = sorted(self.service.categories_and_tags[old_category])
            tags_to_reallocate = selected_tags
            new_category = st.selectbox('Select new category', new_category_options, key='new_category', index=None)
            if old_category and new_category and tags_to_reallocate:
                if st.button('Continue', key='continue_reallocate_tags'):
                    formatted_tags = sorted([format_category_or_tag_strings(tag) for tag in tags_to_reallocate])
                    if self.service.reallocate_tags(old_category, new_category, formatted_tags):
                        st.success("Tags reallocated successfully.")
                        st.rerun()
                    else:
                        st.error("Failed to reallocate tags.")
        if st.button('Cancel', key='cancel_reallocate_tags_btn'):
            st.rerun()

    @st.dialog('Confirm Deletion')
    def _delete_category_dialog(self, category: str):
        self.service.categories_and_tags = st.session_state['categories_and_tags']
        st.write(f'Are you sure you want to delete the "{category}" category?')
        if st.button('Yes', key=f'confirm_delete_{category}'):
            if self.service.delete_category(category, self.protected_categories):
                st.success(f"Category '{category}' deleted successfully.")
                st.rerun()
            else:
                st.error("Cannot delete this category.")
        if st.button('No', key=f'cancel_delete_{category}'):
            st.rerun()

    @st.dialog('Delete Tag')
    def _delete_tag_dialog(self, category: str, tags: List[str]):
        st.write(f'Are you sure you want to delete the selected tags?')
        if st.button('Yes', key=f'confirm_delete_{category}_tags'):
            success = True
            for tag in tags:
                if not self.service.delete_tag(category, tag):
                    success = False
            if success:
                st.success("Tags deleted successfully.")
                st.rerun()
            else:
                st.error("Failed to delete some tags.")
        if st.button('No', key=f'cancel_delete_{category}_tags'):
            st.rerun() 