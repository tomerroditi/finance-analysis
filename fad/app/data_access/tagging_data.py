import yaml
from fad import CATEGORIES_PATH
from typing import Dict, List
from streamlit.connections import SQLConnection
from sqlalchemy.sql import text

def load_categories_and_tags() -> Dict[str, List[str]]:
    """Load categories and tags from the YAML file."""
    try:
        with open(CATEGORIES_PATH, 'r') as file:
            return yaml.safe_load(file) or {}
    except FileNotFoundError:
        return {}

def save_categories_and_tags(categories_and_tags: Dict[str, List[str]]) -> None:
    """Save categories and tags to the YAML file."""
    with open(CATEGORIES_PATH, 'w') as file:
        yaml.dump(categories_and_tags, file)

def assure_tags_table(conn: SQLConnection):
    """Ensure the tags table exists in the database."""
    # This is a placeholder; implement as needed for your DB schema
    # Example: create table if not exists
    with conn.session as s:
        s.execute(text('''
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                category TEXT,
                tag TEXT,
                service TEXT,
                account_number TEXT
            )
        '''))
        s.commit() 