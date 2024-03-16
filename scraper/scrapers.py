import subprocess
import pandas as pd
import datetime

from pathlib import Path
from .credentials import isracard_credentials, max_credentials, onezero_credentials, hafenix_credentials


def get_isracard_data():
    # Path to your Node.js script
    script_path = Path(__file__).parent / 'node/isracard.js'
    # Run the Node.js script
    result = subprocess.run(['node', script_path, isracard_credentials['id'], isracard_credentials['card6Digits'],
                             isracard_credentials['password']], capture_output=True, text=True, encoding='utf-8')
    return result.stdout


def get_max_data():
    # Path to your Node.js script
    script_path = Path(__file__).parent / 'node/max.js'
    # Run the Node.js script
    result = subprocess.run(['node', script_path, max_credentials['username'], max_credentials['password']],
                            capture_output=True, text=True)
    return result.stdout


def get_onezero_data():
    # Path to your Node.js script
    script_path = Path(__file__).parent / 'node/isracard.js'
    # Run the Node.js script
    result = subprocess.run(['node', script_path, isracard_credentials['id'], isracard_credentials['card6Digits'],
                             isracard_credentials['password']], capture_output=True, text=True)
    return result.stdout


def get_hafenixa_data():
    pass


def scraped_data_to_df(data):
    data = data.split('\n')
    if data[0].startswith('found '):
        data = data[1:]
    if data[-1] == '':
        data = data[:-1]
    data = [line.split('| ') for line in data]
    data = [[item.split(': ')[1] for item in line] for line in data]
    df = pd.DataFrame(data, columns=['type', 'id', 'date', 'amount', 'desc', 'status'])
    df['amount'] = df['amount'].astype(float)
    df['date'] = df['date'].apply(lambda x: datetime.datetime.strptime(x, '%Y-%m-%dT%H:%M:%S.%fZ'))
    return df


