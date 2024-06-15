from datetime import datetime
from fad.scraper.credit_card import pull_data


if __name__ == "__main__":
    print('Fetching data from the web...')
    pull_data(datetime(2024, 1, 1))
