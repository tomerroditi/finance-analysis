"""
Inspect schema of split_transactions
"""
import sqlite3
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from backend.database import DB_PATH

def inspect():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("Tables:")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    print(cursor.fetchall())
    
    print("\nColumns in split_transactions:")
    cursor.execute("PRAGMA table_info(split_transactions)")
    for col in cursor.fetchall():
        print(col)

    print("\nSample data from split_transactions:")
    cursor.execute("SELECT * FROM split_transactions LIMIT 5")
    print(cursor.fetchall())

    conn.close()

if __name__ == "__main__":
    inspect()
