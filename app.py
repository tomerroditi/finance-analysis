import streamlit as st
import pandas as pd
import numpy as np
import yaml
import os

from src import src_path


conn = st.connection('data', 'sql')


############################################################
# edit categories and their tags configuration file
############################################################
# This page should display all the current categories and their tags, and allow the user to edit them.
# the user should be able to only add categories and tags.
def edit_categories_and_tags():
    # load the categories and tags configuration file
    with open(os.path.join(src_path, 'categories.yaml'), 'r') as file:
        categories_and_tags = yaml.load(file, Loader=yaml.FullLoader)

    # display the current categories and tags
    for category, tags in categories_and_tags.items():
        st.write(f'Category: {category}')
        st.write(f'Tags: {tags}')

    # add a new category
    new_category = st.text_input('New category')
    if new_category:
        categories_and_tags[new_category] = []

    # add a new tag
    new_tag = st.text_input('New tag')
    if new_tag:
        category = st.selectbox('Category', list(categories_and_tags.keys()))
        categories_and_tags[category].append(new_tag)

    # save the new categories and tags
    with open(os.path.join(src_path, 'categories_and_tags.yaml'), 'w') as file:
        yaml.dump(categories_and_tags, file)

    st.write('Categories and tags updated')


############################################################
# edit tags table
############################################################
# def edit_tags_table(conn):
#     df_tags = conn.query('SELECT * FROM tags')
#     df_tags['category'] = df_tags['category'].apply(lambda x: st.selectbox('Category', ['Food', 'Entertainment', 'Transportation', 'Other'], index=['Food', 'Entertainment', 'Transportation', 'Other'].index(x)))
#     df_tags['name'] = df_tags['name'].apply(lambda x: st.text_input('Name', x))
#     st.dataframe(df_tags)
#     conn.write(df_tags, 'tags')
#     st.write('Tags table updated')


# @st.cache_data
# def fetch_data(connection):
#     # add a pie chart of the amount spent in each category
#     df_transactions = conn.query('SELECT * FROM credit_card_transactions')
#     df_tags = conn.query('SELECT * FROM tags')
#
#     df_transactions['category'] = df_transactions['desc'].apply(lambda x: df_tags[df_tags['name'] == x]['category'].values[0] if x in df_tags['name'].values else 'Other')
#     return df_transactions


def main():
    edit_categories_and_tags()


if __name__ == '__main__':
    main()
