import subprocess
import pandas as pd
import datetime
import sqlite3
import yaml

from pathlib import Path
from src import __file__ as src_file


def get_onezero_data(credentials: dict, start_date: datetime.datetime) -> str:
    """
    Get the data from the Isracard website

    Parameters
    ----------
    credentials : dict
        The credentials to log in to the website, should contain the following keys: 'id', 'card6Digits', 'password'
    start_date : datetime.datetime
        The date from which to start pulling the data
    """
    assert isinstance(start_date, datetime.datetime), 'start_date should be a datetime.datetime object'

    start_date = start_date.strftime('%Y-%m-%d')
    # Path to your Node.js script
    script_path = Path(__file__).parent / 'node/onezero.js'
    # Run the Node.js script
    result = subprocess.run(['node', script_path, credentials['email'], credentials['password'],
                             'None', credentials['phoneNumber'], start_date],
                            capture_output=True, text=True, encoding='utf-8')
    print(result.stdout.split('\n')[0])
    return result.stdout