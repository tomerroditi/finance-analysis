import streamlit as st
import yaml
import os

from streamlit.connections import SQLConnection
from sqlalchemy.sql import text
from streamlit_tags import st_tags
from fad import CATEGORIES_PATH


# TODO: a major refactor to move all the database operations to a module in the fad folder, and only wrap the functions
#  in the streamlit app
# TODO: when deleting specific tags make sure to delete them from the tags and credit card tables
# TODO: when deleting categories make sure to delete them from the credit card table (tags table update is already
#  implemented)
# TODO: when editing tags, if we add a new tag/category make sure to update the credit card table and the category and
#  tags UI
def edit_categories_and_tags(categories_and_tags, yaml_path, conn):
    # Initialize session state for each category before the loop
    for category in categories_and_tags.keys():
        if f'confirm_delete_{category}' not in st.session_state:
            st.session_state[f'confirm_delete_{category}'] = False

    # Iterate over a copy of the dictionary's items and display the categories and tags and allow editing
    for category, tags in list(categories_and_tags.items()):
        st.subheader(category, divider="gray")
        new_tags = st_tags(label='', value=tags, key=f'{category}_tags')
        if new_tags != tags:
            categories_and_tags[category] = new_tags
            # save changes and rerun to update the UI
            update_yaml_and_rerun(categories_and_tags, yaml_path)

        # delete category
        delete_button = st.button(f'Delete {category}', key=f'my_{category}_delete')
        if delete_button:
            st.session_state[f'confirm_delete_{category}'] = True

        # confirm deletion
        if st.session_state[f'confirm_delete_{category}']:
            confirm_button = st.button('Confirm Delete', key=f'confirm_{category}_delete')
            cancel_button = st.button('Cancel', key=f'cancel_{category}_delete')

            # delete and update database
            if confirm_button:
                del categories_and_tags[category]
                data_to_delete = conn.query('SELECT name FROM tags WHERE category=:category;',
                                            params={'category': category}, ttl=0)
                with conn.session as s:
                    for i, row in data_to_delete.iterrows():
                        s.execute(text("UPDATE tags SET category='', tag='' WHERE name=:name;"),
                                  params={'name': row['name']})
                    s.commit()
                del st.session_state[f'confirm_delete_{category}']
                update_yaml_and_rerun(categories_and_tags, yaml_path)

            # cancel deletion
            if cancel_button:
                st.session_state[f'confirm_delete_{category}'] = False
                st.rerun()

    # add new categories
    st.subheader('Add a new Category', divider="gray")
    new_category = st.text_input('New Category Name', key='new_category')
    if st.button('Add Category') and new_category != '':
        categories_and_tags[new_category] = []
        update_yaml_and_rerun(categories_and_tags, yaml_path)


def update_yaml_and_rerun(categories_and_tags, yaml_path):
    with open(yaml_path, 'w') as file:
        yaml.dump(categories_and_tags, file)
    st.rerun()


def assure_tags_table(conn: SQLConnection):
    with conn.session as s:
        s.execute(text('CREATE TABLE IF NOT EXISTS tags (name TEXT PRIMARY KEY, category TEXT, tag TEXT);'))
        s.commit()


def pull_new_names(conn):
    current_names = conn.query("SELECT name FROM tags;", ttl=0)
    all_names = conn.query("SELECT desc FROM credit_card_transactions;", ttl=0)
    new_names = all_names.loc[~all_names['desc'].isin(current_names), 'desc'].unique()
    with conn.session as s:
        for name in new_names:
            s.execute(text('INSERT INTO tags (name) VALUES (:name);'), params={'name': name})
        s.commit()


def tag_new_data(conn, categories_and_tags):
    df_tags = conn.query("SELECT * FROM tags WHERE category IS NULL OR tag IS NULL;", ttl=0)
    if df_tags.empty:
        st.write("No data to tag")
        return

    # editable table to tag the data
    categories = list(categories_and_tags.keys())
    tags = [f'{category}: {tag}' for category in categories for tag in categories_and_tags[category]]
    df_tags['new tag'] = ''
    tags_col = st.column_config.SelectboxColumn('new tag', options=tags)
    edited_df_tags = st.data_editor(df_tags[['name', 'new tag']], hide_index=True, width=800, column_config={'new tag': tags_col})

    # save the edited data
    if st.button('Save', key='save_tagged_data'):
        edited_df_tags = edited_df_tags.loc[edited_df_tags['new tag'] != '']
        if not edited_df_tags.empty:
            edited_df_tags['category'] = edited_df_tags['new tag'].apply(lambda x: x.split(': ', 1)[0])
            edited_df_tags['tag'] = edited_df_tags['new tag'].apply(lambda x: x.split(': ', 1)[1])
            edited_df_tags = edited_df_tags.drop('new tag', axis=1)
            with conn.session as s:
                for i, row in edited_df_tags.iterrows():
                    s.execute(text('UPDATE tags SET category=:category, tag=:tag WHERE name=:name;'),
                              params={'category': row['category'], 'tag': row['tag'], 'name': row['name']})
                s.commit()
        st.rerun()


def edit_tagged_data(conn, categories_and_tags):
    tagged_data = conn.query("SELECT * FROM tags WHERE category!='' AND tag!='';", ttl=0)
    if tagged_data.empty:
        st.write("No data to edit")
        return

    # editable table to edit the tagged data
    edited_tagged_data = st.data_editor(tagged_data, hide_index=True, width=800, key='edit_tagged_data')
    if st.button('Save', key='save_edited_tagged_data'):
        # keep only the modified rows
        edited_tagged_data = edited_tagged_data[(edited_tagged_data['category'] != tagged_data['category']) |
                                                (edited_tagged_data['tag'] != tagged_data['tag'])]
        # save the edited data to the database
        with conn.session as s:
            for i, row in edited_tagged_data.iterrows():
                s.execute(text('UPDATE tags SET category=:category, tag=:tag WHERE name=:name;'),
                          params={'category': row['category'], 'tag': row['tag'], 'name': row['name']})
            s.commit()
        st.rerun()


def main():
    if 'conn' not in st.session_state:
        st.session_state['conn'] = st.connection('data', 'sql')
    conn = st.session_state['conn']

    # Load data only if it's not already in the session state
    if 'categories_and_tags' not in st.session_state:
        with open(CATEGORIES_PATH, 'r') as file:
            st.session_state['categories_and_tags'] = yaml.load(file, Loader=yaml.FullLoader)

    categories_and_tags = st.session_state['categories_and_tags']

    # edit tags table
    st.header('Tag New Data', divider="gray")
    st.write("Tag the new data with the appropriate category and tags. you may see the current categories and their "
             "tags bellow. If you want to create new tags use the input boxes bellow the table.")
    assure_tags_table(conn)
    pull_new_names(conn)
    tag_new_data(conn, categories_and_tags)
    edit_tagged_data(conn, categories_and_tags)

    # edit categories and tags configuration file
    # TODO: when deleting tags or categories make sure to update the tagged data as well
    st.header('My Categories and Tags', divider="gray")
    edit_categories_and_tags(categories_and_tags, CATEGORIES_PATH, conn)


if __name__ == '__main__':
    main()
