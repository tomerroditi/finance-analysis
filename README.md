# finance-analysis
This project aims to help individuals track their finance status, including savings and expenses, by automating data scraping and analyzing the findings. 


# goals
- automate the process of scraping data from bank accounts, credit cards, and insurance companies
- automate the process of labeling and categorizing expenses
- automate the process of analyzing the data
- provide a forecast feature to predict future savings 
- provide a visualization of the data
- provide a summary of the data


# progress
- [x] automate the process of scraping data from credit cards
- automate the process of scraping data from bank accounts and insurance companies
    - find a workaround for 2FA (two-factor authentication) automation
- [x] convert the scraped data into a dataframe
- maintain a database of the scraped data (consider using SQLite)
- create a labeling/categorization system for the expenses
    - a framework for labeling new data (adding new labels as well)
    - automation of labeling data that is already labeled
- create a dashboard to visualize the data and it's analysis (maybe grafana)
- create a forecasting feature to predict future savings
- create a summary of the data