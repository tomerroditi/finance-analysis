from fad.app.components.data_scraping_components import DataScrapingComponent

scraping_ui = DataScrapingComponent()
scraping_ui.set_scraping_start_date()
scraping_ui.select_services_to_scrape()
scraping_ui.fetch_and_process_data()
