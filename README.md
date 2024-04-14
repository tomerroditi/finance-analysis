# finance-analysis
This project aims to help individuals track their finance status, including savings and expenses, by automating data scraping and analyzing the findings. 


# goals
- automate the process of scraping data from bank accounts, credit cards, and insurance companies
- automate the process of labeling and categorizing expenses
- automate the process of analyzing the data
- provide a forecast feature to predict future savings 
- provide a visualization of the data
- provide a summary of the data


# progress (focusing on credit cards for now)
- [x] automate the process of scraping data from credit cards
- automate the process of scraping data from bank accounts and insurance companies
    - find a workaround for 2FA (two-factor authentication) automation
- [x] convert the scraped data into a dataframe
- [x] maintain a database of the scraped data (consider using SQLite)
- [x] create a labeling/categorization system for the expenses
    - [x] a framework for labeling new data (adding new labels as well)
    - [x] automation of labeling data that is already labeled
- create a dashboard to visualize the data and it's analysis (maybe grafana)
- create a forecasting feature to predict future savings
- create a summary of the data


# Streamlit App
the app should be able to:
- categories setting page to add new categories and tags
- add\edit\delete credentials of different data scraping websites
- edit the tags of the expenses (the tags table of the database)
- visualize the data in various ways with an interactive dashboard
- provide a forecast of the future savings
- provide a summary of the data
- upload a pdf of their monthly salary to be digested by the system
- support the 2 factor authentication process
