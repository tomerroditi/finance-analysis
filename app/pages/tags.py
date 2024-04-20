import streamlit as st
import pandas as pd
import numpy as np
import yaml
import os

from sqlalchemy.sql import text
from streamlit_tags import st_tags
from src import src_path
from copy import deepcopy

#TODO: when deleting specific tags make sure to delete them from the tags and credit card tables
#TODO: when deleting categories make sure to delete them from the credit card table (tags table update is already implemented)

def edit_categories_and_tags(categories_and_tags, yaml_path, conn) -> None:
    """
    Edit the categories and tags configuration file.
    this function takes care of rendering the categories and tags and allows the user to add/delete tags and categories.

    Parameters
    ----------
    categories_and_tags : dict
        A dictionary containing the categories as keys and their tags as values.
    yaml_path : str
        The path to the yaml file containing the categories and tags.

    Returns
    -------
    None
    """
    change = False

    # render the categories and tags with an option to add/delete tags
    del_cat = None
    for category, tags in categories_and_tags.items():
        st.subheader(category, divider="gray")
        # Render tags input box and use a button to confirm changes
        new_tags = st_tags(label='', value=tags, key=f'{category}_tags')
        if new_tags != tags:
            categories_and_tags[category] = new_tags
            change = True

        # delete category
        if st.button(f'Delete {category}', key=f'{category}_delete'):
            change = True
            del_cat = category

    # delete categories
    if del_cat is not None:
        # remove the deleted categories from the dictionary
        del categories_and_tags[del_cat]
        # update the database (delete the tags with the deleted categories)
        data_to_delete = conn.query('SELECT name FROM tags WHERE category=:category;',
                                    params={'category': del_cat}, ttl=0)
        with conn.session as s:
            for i, row in data_to_delete.iterrows():
                s.execute(text("UPDATE tags SET category='', tag='' WHERE name=:name;"),
                          params={'name': row['name']})
            s.commit()

    # add a new category
    st.subheader('Add a new Category', divider="gray")
    new_category = st.text_input('New Category Name', key='new_category')
    if st.button('Add Category') and new_category != '':
        change = True
        categories_and_tags[new_category] = []

    if change:
        with open(yaml_path, 'w') as file:
            yaml.dump(categories_and_tags, file)
        st.rerun()


def tag_new_data(conn, categories_and_tags):
    df_tags = conn.query("SELECT * FROM tags WHERE category='' OR tag='';", ttl=0)
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


# @st.cache_data
# def fetch_data(connection):
#     # add a pie chart of the amount spent in each category
#     df_transactions = conn.query('SELECT * FROM credit_card_transactions')
#     df_tags = conn.query('SELECT * FROM tags')
#
#     df_transactions['category'] = df_transactions['desc'].apply(lambda x: df_tags[df_tags['name'] == x]['category'].values[0] if x in df_tags['name'].values else 'Other')
#     return df_transactions


def main():
    # if 'conn' not in st.session_state:
    #     st.session_state['conn'] = st.connection('data', 'sql')
    # conn = st.session_state['conn']
    conn = st.connection('data', 'sql')

    # Path to the YAML file
    yaml_path = os.path.join(src_path, 'categories.yaml')

    # Load data only if it's not already in the session state
    if 'categories_and_tags' not in st.session_state:
        with open(yaml_path, 'r') as file:
            st.session_state['categories_and_tags'] = yaml.load(file, Loader=yaml.FullLoader)

    categories_and_tags = st.session_state['categories_and_tags']

    # edit tags table
    st.header('Tag New Data', divider="gray")
    st.write("Tag the new data with the appropriate category and tags. you may see the current categories and their "
             "tags bellow. If you want to create new tags use the input boxes bellow the table.")
    tag_new_data(conn, categories_and_tags)
    edit_tagged_data(conn, categories_and_tags)

    # edit categories and tags configuration file
    # TODO: when deleting tags or categories make sure to update the tagged data as well
    st.header('My Categories and Tags', divider="gray")
    edit_categories_and_tags(categories_and_tags, yaml_path, conn)


if __name__ == '__main__':
    main()
