from fad.app.components.tagging_components import TransactionsTaggingComponent
from fad.app.components.data_scraping_components import DataScrapingComponent

scraping_ui = DataScrapingComponent()
scraping_ui.render_data_scraping()


TransactionsTaggingComponent(key_suffix="tagging_page").render_tagging_page()
