import sqlite3
import tkinter as tk
from enum import Enum

from tkinter import simpledialog
from pathlib import Path
from src import __file__ as src_file
from src import Tables, Columns


class Tags_Manager:
    def __init__(self):
        self.db_path = Path(src_file).parent / 'data.db'
        self.conn = sqlite3.connect(self.db_path)
        self.cur = self.conn.cursor()
        self.root = tk.Tk()
        self.root.withdraw()  # Hide the main window

    def tag_new_data(self):
        """
        Tag new data that has not been tagged yet using a GUI
        """
        # make sure the 'tags' table exists
        self.cur.execute(f"CREATE TABLE IF NOT EXISTS {Tables.TAGS.value} ({Columns.NAME.value} TEXT PRIMARY KEY, "
                            f"{Columns.CATEGORY.value} TEXT, {Columns.TAGS.value} TEXT)")
        self.conn.commit()

        # tag untagged data
        untagged = self.get_untagged_descriptions()
        for desc in untagged:
            category = simpledialog.askstring("Category", f"Enter category for: {desc}")
            tags = simpledialog.askstring("Tags", f"Enter tags for: {desc}")
            if category and tags:  # Only insert if both category and tags are provided
                self.insert_tag(desc, category, tags)
                self.conn.commit()
        self.conn.close()

    def get_untagged_descriptions(self):
        """
        Get all the descriptions that have not been tagged yet. we assume that each description is unique to the same
        company/business, so we only need to tag it once
        """
        self.cur.execute(f"SELECT desc FROM {Tables.CREDIT_CARDS.value} EXCEPT SELECT name FROM {Tables.TAGS.value}")
        return [item[0] for item in self.cur.fetchall()]

    def insert_tag(self, name, category, tags):
        """
        Insert a new tag to the database 'tags' table
        """
        self.cur.execute(f"INSERT INTO {Tables.TAGS.value} (name, category, tags) VALUES (?, ?, ?)", (name, category, tags))
        self.conn.commit()

