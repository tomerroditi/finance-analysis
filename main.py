from datetime import datetime
from src.scraper.scrapers import pull_data
from src.categorization.categorize_expenses import Tags_Manager


if __name__ == "__main__":
    print('Fetching data from the web...')
    pull_data(datetime(2024, 1, 1))
    print('Tagging new data...')
    tags_manager = Tags_Manager()
    tags_manager.tag_new_data()
    print('Done!')
