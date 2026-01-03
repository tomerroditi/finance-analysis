# finance-analysis
This project aims to help individuals track their finance status, including savings and expenses, by automating data scraping and analyzing the findings. 


# How to Run

## Backend

The backend is built with FastAPI and uses Poetry for dependency management.

1.  **Install dependencies**:
    ```bash
    # From the project root
    poetry install
    ```

2.  **Start the server**:
    ```bash
    poetry run uvicorn backend.main:app --reload
    ```
    The API will be available at [http://127.0.0.1:8000](http://127.0.0.1:8000). Documentation is available at [/docs](http://127.0.0.1:8000/docs).

## Frontend

The frontend is built with React and Vite.

1.  **Navigate to the frontend directory**:
    ```bash
    cd frontend
    ```

2.  **Install dependencies**:
    ```bash
    npm install
    ```

3.  **Start the development server**:
    ```bash
    npm run dev
    ```
    The application will be available at [http://localhost:5173](http://localhost:5173).

# goals
- automate the process of scraping data from bank accounts, credit cards, and insurance companies
- automate the process of labeling and categorizing expenses
- automate the process of analyzing the data
- provide a forecast feature to predict future savings 
- provide a visualization of the data
- provide a summary of the data


# progress (focusing on credit cards for now)
- [x] automate the process of scraping data from credit cards
- [x] automate the process of scraping data from bank accounts and insurance companies
    - [x]find a workaround for 2FA (two-factor authentication) automation
- [x] convert the scraped data into a dataframe
- [x] maintain a database of the scraped data (consider using SQLite)
- [x] create a labeling/categorization system for the expenses
    - [x] a framework for labeling new data (adding new labels as well)
    - [x] automation of labeling data that is already labeled
- [x] create an app to visualize the data and it's analysis
- create a forecasting feature to predict future savings
- create a summary of the data


# Streamlit App
the app should be able to:
- [x] categories setting page to add new categories and tags
- [x] add\edit\delete credentials of different data scraping websites
- [x] edit the tags of the expenses (the tags table of the database)
- [x] visualize the data in various ways with an interactive dashboard
- provide a forecast of the future savings
- provide a summary of the data
- upload a pdf of their monthly salary to be digested by the system
- [x] support the 2 factor authentication process
