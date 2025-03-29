# Changelog

All notable changes to this project will be documented in this file.
## v1.0.0 (2025-03-29)

### Feat

- implement app deployment process
- **budget_management**: added an option to see raw data of each rule's associated expenses
- **budget_management, utils.budget_management**: added project budget feature. the user can now set a budget for a project which might spread over long period of time and should not be included in the monthly budget management.
- **budget_management, utils.budget_management**: a new page for budget management which allows the user to add, edit and delete budget rules of different months.
- **data, naming_conventions**: added a new table for budget management feature
- **app.overview**: made the wide page mode the default of the app layout
- **app.utils.widgets**: added an option for last month/year in the PandasFilterWidgets class and made the object itself persist in memory to improve the selections state persistent over different app usages
- **onezero**: onezero scraper now support fetching a new long term token when the current one is not valid. improved the scraping flow.
- **exceptions**: added a new model for custom exceptions
- **naming_conventions**: added a new enum class for service names (credit_card, bank, etc.)
- **app.overview**: added a spinner to visualize progress in data fetching
- **app.income_outcome_analysis, app.utils**: added expenses analysis by categories. the user can now view their expenses analysis by categories in total and over periods of time (months and years) to gain some insights over their expenses.

### Fix

- **app.utils.tagging**: fixed bug in adding new category due to missmatch between widget output and saved values
- **app.utils.plotting**: fixed empty data handling to plot empty figures
- **app.pages.income_outcome_analysis**: added keys to streamlit components that where missing keys
- **app.utils.data**: fixed incorrect col name of budget rules, `tag` to `tags`. changed hardcoded strings to to enum values
- **app.utils.budget_management**: fixed hard coded strings in sql queries
- **data**: added missing columns to the database transactions tables
- **data**: fixed latest date fetching when there is no data at all
- **data**: fixed data.db file creation in case it doesn't exist.
- fixed wrong paths handling
- **app.utils.data**: fixed file not found when credentials file hasn't created yet. now it creates a file if it doesn't exists
- **app.utils.credentials**: fixed file not found when credentials file hasn't created yet. now it creates a file if it doesn't exists
- **app.utils.data, app.overview**: fixed the all data pull feature to work properly with 2fa scrapers classes as well.
- **scrapers**: fixed 2fa handling by making sure that the process is not hanged due to stdin and stdout. enabled the 'cancel' feature to interrupt the data fetching process.
- **scrapers**: fixed error handling of the js scripts
- **overview, main**: fixed the new paging layout
- **app.utils.tagging**: fixed a bug in fetching new bank account data for auto tagger rules
- **scraper**: fixed the 2fa issue where the tread where hanged due to unclosed stdin stream.
- **scrapers, app.utils, scraper.utils**: fixed 2fa scraping
- **scraper**: fixed a bug of removing duplicated rows
- **scraper.utils**: fixed a bug regarding one zero transaction date format.
- **app.tagging**: fixed an sql query bug
- **app.tagging**: fixed a sql text bracket misplace.
- **app.pages.tags**: fix an initialization table bug. perf(app.pages.tags): added a new function to pull new transactions descriptions for tagging.

### Refactor

- **scraper.scrapers**: added a print for failed scraping to ease the debugging process.
- **tests.test_app**: updated function name after refactoring.
- **app.budget_management**: minor changes to improve the UX
- **budget_management**: improvements to the code structure and readability
- **tagging**: changed the reformat of tags and categories. ';' is not a valid character in them from now.
- **budget_management**: added docstrings and made the database calls less repetitive by reading it once per rerun.
- **budget_management**: added more verifications on user input, refactor the module to use naming conventions. project expenses are now not included in the monthly budget management
- **utils.budget_management**: minor changes
- **app.utils.tagging**: changed the buttons view of the new category and reallocate tags
- **app.overview**: reordered the pages in the sidebar for future app UI design
- **app.utils.widgets**: changed the buttons type in the date selection widgets
- **analysis**: deprecated unused files
- **app.utils**: break the utils module into a dir of utils containing modules for each utility type
- **app.utils**: improved error handling and UX
- **scraper.scrapers**: enhanced error handling to be more informative
- fixed the run.sh file
- removed some printing for solved debugging
- **app.utils**: deleted redundant prints
- **scraper**: refactored the 2fa scraping method of one zero
- **scraper**: added functions and classes to __all__ in the init file
- **categories**: added new categories and tags
- **utils, overview**: improved data scraping code to enable retrieving a new OTP when the current one is invalid
- **utils**: improved tagging UI and stability
- **naming_conventions**: moved the naming_conventions.py module into the app dir
- **app.tagging**: removed some redundant code that was used for debugging
- **tagging, utils**: minor changes to improve stability of the app.
- **tagging**: moved the tagging related code to the utils module. improved the UX of the tagging system to be more restricted and more resilient to user errors.
- **tagging**: functions renaming, added type hints, fixed sql bugs and improved the overall UX of the tagging interface.
- **categories**: all categories and tags are now formated to title format.
- **naming_conventions**: added more categories to non expenses categories
- **app.income_outcome_analysis**: visualization utils functions renaming
- **categories**: added some new categories and tags
- **utils**: added a new visualization function and minor improvements to existing code
- **app.tagging**: minor changes to improve code readability and performance
- **income_outcome_analysis, utils**: minor UX improvements.
- **app.naming_conventions**: as part of the tagging UX improvement added new columns names for the tags table
- **app.income_outcome_analysis**: removed a done TODO and changed the order of the figures.
- **tagging**: gathered all tagging related pages into a single page with tabs to handle tags editing, auto tagger and raw tagged data editing. made some improvements in the UX to make it more user-friendly (ordered categories and tags for example), and added TODOs for future work.
- **scraper**: combined all the scrapers classes into a single module to easily maintain the code.
- **app.utils**: minor changes to improve readability
- **tags**: moved the categories.yaml file into the app package
- **scraper**: refactored the scraper package to clean the code and remove code duplications. fix(scraper): fixed bugs in the scraper package.

### Perf

- **utils, income_outcome_analysis, naming_conventions**: seperated the expenses from income when displaying the data analysis.
- **utils**: update_db_table now return immediately if no data is edited, and expenses plots now doesn't consider "Other: No tag" tagging, and rounds the visualized numbers in the figures to 2 decimal points.
- **app.expensses_raw_data, app.utils**: improved the data table filtering mechanism. you can now filter the data by date and amount range, and the filters widgets are presented as a column aside the data table instead in the sidebar.
- **app.tags**: transactions database is now updated with the tag and categories selected for them. perf(app.expenses_raw_data): added a new filter method to help maintain the database edditing.
- **naming_conventions**: moved the module to the fad package from fad.app. added enums classes for the tables names and their columns names. perf(app.utils): added new utils top get the app sql connection and the categories and tags dictionary (from the yaml file)
