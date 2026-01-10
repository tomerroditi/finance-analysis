---
trigger: glob
globs: backend/services/**/*.py"
---

# Services Layer - Business Logic

## Purpose
The services layer contains **ALL business logic** for the application. Services orchestrate operations between repositories (data access) and components (UI), handling calculations, transformations, validations, and decision-making.

## Core Principle: Business Logic Encapsulation

### What Services DO:
✅ **All business calculations** - totals, averages, percentages, aggregations  
✅ **Data transformations** - filtering, grouping, merging, formatting  
✅ **Complex validations** - rules with business context  
✅ **Decision-making logic** - when to scrape, which rules to apply, etc.  
✅ **Orchestration** - coordinate multiple repositories/services  
✅ **Error handling with business context** - catch repo errors, add meaning  
✅ **Data enrichment** - merge transactions with splits, apply tagging rules  
✅ **Password management** - retrieve from Windows Keyring, pass to scrapers  

### What Services DO NOT DO:
❌ **Direct database access** - always use repositories  
❌ **UI rendering** - no Streamlit widgets  
❌ **Session state management** - avoid `st.session_state` (component responsibility)  
❌ **Direct file I/O** - use repositories for YAML/file operations  

**Golden Rule:** If it's about "what the data means" or "what to do with it" - it's business logic and belongs in services.

## Architecture Patterns

### Service Composition

Services can be **basic** (only use repositories) or **complex** (use other services):

```python
# Basic Service - Only repositories
class TransactionsService:
    def __init__(self, conn):
        self.transactions_repo = TransactionsRepository(conn)
        self.split_repo = SplitTransactionsRepository(conn)
    
    def get_transactions(self):
        return self.transactions_repo.get_all_transactions()

# Complex Service - Uses other services
class BudgetService:
    def __init__(self, conn):
        self.budget_repo = BudgetRepository(conn)
        self.categories_service = CategoriesTagsService()  # Service dependency
        self.transactions_service = TransactionsService(conn)  # Service dependency
```

**Critical Design Rule:** **Avoid circular dependencies!**
- Services should have **linear interaction patterns**
- Service A can depend on Service B
- Service B should **NOT** depend on Service A
- Two services should not be mutually dependent

**Dependency Direction:**
```
Complex Services → Basic Services → Repositories → Database/Files
```

### Connection Parameter (`conn`)

**Purpose:** Dependency injection for easier testing.

**Pattern:**
```python
class ExampleService:
    def __init__(self, conn: SQLConnection = get_db_connection()):
        self.conn = conn
        self.repo = ExampleRepository(conn)
```

**Benefits:**
- Tests can inject mock connections
- Same connection reused across repositories
- Potential for singleton pattern (not currently implemented)

**Note:** Services are currently **not singletons** - new instances created per operation. Consider singleton pattern carefully before implementing (thread safety, state management).

### Session State Interaction

**Current State:** Some services interact with `st.session_state` (legacy pattern).

**Goal:** Components should manage session state, not services.

**Example (Current - Avoid):**
```python
# ❌ Service managing session state (legacy pattern)
class CategoriesTagsService:
    def get_categories_and_tags(self):
        if 'categories_and_tags' not in st.session_state:
            st.session_state['categories_and_tags'] = self.load_from_file()
        return st.session_state['categories_and_tags']
```

**Better Pattern (Target):**
```python
# ✅ Component manages session state
class CategoriesComponent:
    def __init__(self):
        self.service = CategoriesTagsService()
        if 'categories_and_tags' not in st.session_state:
            st.session_state['categories_and_tags'] = self.service.load_categories()
```

**Guideline:** New services should avoid session state. Existing services with session state are being refactored gradually.

## Return Types

Services can return:
- **pandas DataFrames** - For tabular data
- **Primitives** - `int`, `float`, `str`, `bool` for calculations/flags
- **Dictionaries/Lists** - For structured data
- **Custom objects** - Dataclasses, named tuples

**Examples:**
```python
def get_transactions(self) -> pd.DataFrame:
    return self.transactions_repo.get_all_transactions()

def calculate_total_expenses(self, month: int) -> float:
    transactions = self.get_transactions_for_month(month)
    return transactions['amount'].sum()

def get_spending_by_category(self) -> dict[str, float]:
    transactions = self.get_transactions()
    return transactions.groupby('category')['amount'].sum().to_dict()

def can_scrape_today(self, account: str) -> bool:
    last_scrape = self.history_repo.get_last_scraping_date(account)
    return last_scrape != datetime.today().date()
```

## Validation Logic

### Simple Validation → Components
**Examples:** Positive numbers, non-empty strings, valid dates, field presence

```python
# ✅ Component validates before calling service
if amount <= 0:
    st.error("Amount must be positive")
    return
service.add_budget(amount=amount)
```

### Complex Validation → Services
**Examples:** Business rule violations, duplicate checks, consistency checks

```python
# ✅ Service validates business rules
class BudgetService:
    def validate_rule_inputs(self, name, category, tags, amount, year, month, id_) -> tuple[bool, str]:
        # Check for duplicates
        if self.rule_exists(name, year, month, id_):
            return False, "Budget rule with this name already exists for the period"
        
        # Validate category/tag relationship
        if tags and category not in self.categories_service.get_categories():
            return False, f"Category '{category}' does not exist"
        
        # Business rule: project budgets must have no month/year
        if name.startswith("Project_") and (month or year):
            return False, "Project budgets cannot have month/year specified"
        
        return True, ""
```

## Error Handling

Services catch repository errors and **re-raise with business context**:

```python
def update_budget(self, id: int, amount: float):
    try:
        self.budget_repo.update(id, amount=amount)
    except ValueError as e:
        # Add business context
        raise ValueError(f"Failed to update budget: {e}. Please check the budget ID.")
    except Exception as e:
        # Unexpected errors
        raise RuntimeError(f"Unexpected error updating budget: {e}")
```

**Pattern:**
1. Try repository operation
2. Catch specific exceptions
3. Re-raise with **user-friendly business context**
4. Components display error messages to users

## Existing Services

### 1. `TransactionsService` (at fad.app.services.transactions_service)
**Purpose:** Manage transaction data across multiple sources (credit cards, banks, cash, manual investments).

**Key Responsibilities:**
- Add manual transactions (cash, manual investments)
- Merge transactions from multiple tables
- Filter transactions by date, category, amount
- Calculate totals, averages, spending trends
- Update transaction tagging
- Handle transaction deletion

**Key Methods:**
- `add_transaction()` - Add cash or manual investment transaction
- `get_data_for_analysis()` - Merge all transaction sources
- `get_table_for_analysis()` - Get single source with business filtering
- `update_tagging_by_id()` - Change category/tag for transaction
- `calculate_monthly_totals()` - Aggregate spending by month

**Business Logic Examples:**
- **Negative amounts = expenses, Positive amounts = income**
- Filter out "Ignore" category transactions from analysis
- Merge split transactions into original transaction data

### 2. `CategoriesTagsService` (at fad.app.services.tagging_service)
**Purpose:** Manage category and tag configuration.

**Key Responsibilities:**
- Load/save categories and tags (YAML)
- Add/delete/rename categories
- Reallocate tags between categories
- Manage category icons
- Handle session state (legacy - avoid in new code)

**Key Methods:**
- `get_categories_and_tags()` - Load categories with defaults
- `save_categories_and_tags()` - Persist to YAML
- `add_category()` - Create new category
- `delete_category()` - Remove category (reassign transactions first)
- `reallocate_tag()` - Move tag from one category to another

**Business Rules:**
- Cannot delete category with existing transactions
- Reallocating tags requires updating all affected transactions/rules

### 3. `TaggingRulesService` (at fad.app.services.tagging_rules_service)
**Purpose:** Manage automatic tagging rules with priority-based pattern matching.

**Key Responsibilities:**
- Create/update/delete tagging rules
- Apply rules to transactions
- Evaluate rule conditions (JSON parsing)
- Handle rule priorities (higher number = evaluated first)
- Validate rule logic

**Key Methods:**
- `get_all_rules()` - Retrieve rules ordered by priority
- `create_rule()` - Add new tagging rule with validation
- `update_rule()` - Modify existing rule
- `apply_rules_to_transaction()` - Match transaction against rules
- `validate_rule_conditions()` - Check JSON conditions format

**Business Logic - Rule Evaluation:**
1. Rules sorted by **priority DESC** (highest priority first)
2. Conditions parsed from JSON (field, operator, value)
3. First matching rule wins (no further evaluation)
4. Operators: `contains`, `equals`, `starts_with`, `ends_with`, `gt`, `lt`, `gte`, `lte`, `between`
5. Fields: `description`, `amount`, `provider`, `account_name`, `account_number`, `service`

**Example Rule:**
```python
{
    "name": "Grocery Tagging",
    "priority": 10,
    "conditions": [
        {"field": "description", "operator": "contains", "value": "supermarket"},
        {"field": "amount", "operator": "lt", "value": 0}  # Negative = expense
    ],
    "category": "Food",
    "tag": "Groceries",
    "is_active": True
}
```

### 4. `BudgetService` (at fad.app.services.budget_service)
**Purpose:** Manage monthly and project budgets.

**Key Responsibilities:**
- Create/update/delete budget rules
- Validate budget constraints
- Calculate budget utilization
- Compare actual vs. budgeted spending
- Handle project budgets (no month/year)

**Key Methods:**
- `add_rule()` - Create budget (tags converted to semicolon-separated string)
- `update_rule()` - Modify budget amount/category/tags
- `delete_rule()` - Remove budget
- `validate_rule_inputs()` - Business rule validation
- `get_budget_vs_actual()` - Compare spending to budget

**Business Rules:**
- **Regular budgets:** Have `month` and `year`
- **Project budgets:** `month` and `year` are `NULL` (unlimited timeframe)
- **"Total Budget"** is special category for overall monthly spending limit
- Tags stored as semicolon-separated string in DB (`"tag1;tag2;tag3"`)

### 5. `SplitTransactionsService` (at fad.app.services.split_transactions_service)
**Purpose:** Manage transaction splitting across multiple categories.

**Key Responsibilities:**
- Split transactions into multiple categories/tags
- Validate split amounts (must sum to original)
- Merge splits with original transactions for display
- Handle split updates/deletions

**Key Methods:**
- `create_split()` - Add split to transaction
- `get_splits_for_transaction()` - Retrieve all splits
- `merge_splits_with_transactions()` - Combine for analysis
- `validate_split_amounts()` - Ensure splits sum correctly
- `delete_splits()` - Remove all splits for transaction

**Business Logic - Split Transactions:**
- **Original transaction remains unchanged** in main table
- **Splits stored separately** in `split_transactions` table
- Each split has: `transaction_id`, `amount`, `category`, `tag`
- When fetching data, **merge original with splits**
- Split amounts must sum to original transaction amount
- Deleting original transaction deletes all splits (cascade)

**Example:**
```
Original Transaction:
- ID: 123
- Description: "Monthly shopping"
- Amount: -500
- Category: NULL
- Tag: NULL

Splits:
- Split 1: transaction_id=123, amount=-300, category="Food", tag="Groceries"
- Split 2: transaction_id=123, amount=-200, category="Household", tag="Supplies"

Result for Analysis: Two separate entries (food and household) instead of one uncategorized
```

### 6. `ScrapingService` (DataScrapingService) (at fad.app.services.data_scraping_service)
**Purpose:** Orchestrate web scraping operations with 2FA handling.

**Key Responsibilities:**
- **Retrieve passwords from Windows Keyring** (NOT scraper responsibility)
- Build scraper instances with full credentials
- Manage scraping threads (non-blocking UI)
- Handle 2FA coordination (OTP input)
- Enforce daily scraping limits
- Track scraping status (success/failed/waiting for 2FA)

**Key Methods:**
- `pull_data()` - Initiate scraping with thread management
- `get_credentials_with_passwords()` - **Retrieve passwords from keyring and merge with YAML credentials**
- `handle_2fa()` - Coordinate OTP input with scraper
- `build_scraper_start_dates()` - Determine scraping date ranges
- `can_scrape_today()` - Check daily limits

**Business Logic - Password Management:**
```python
def get_credentials_with_passwords(self, credentials: dict) -> dict:
    """
    Merge YAML credentials with passwords from Windows Keyring.
    Scraper receives complete credentials dict.
    """
    for service_name, providers in credentials.items():
        for provider_name, accounts in providers.items():
            for account_name, creds in accounts.items():
                username = creds.get('username')
                # Retrieve password from keyring
                password = keyring.get_password(provider_name, username)
                creds['password'] = password  # Add to credentials dict
    return credentials
```

**Business Logic - Daily Limits:**
- Check `scraping_history` table
- Prevent scraping same account more than once per day
- Enforced in UI and service layer

**Business Logic - 2FA Flow:**
1. Start scraping in separate thread
2. Scraper detects 2FA required
3. Service tracks scraper in `tfa_scrapers_waiting` dict
4. Component prompts user for OTP
5. User enters OTP → service calls `scraper.set_otp_code()`
6. Scraper continues in background thread

### 7. `CredentialsService` (at fad.app.services.credentials_service)
**Purpose:** Manage user credentials for financial providers.

**Key Responsibilities:**
- Read/write credentials YAML
- **Interact with Windows Keyring** for password storage
- Validate credentials structure
- Provide credential templates

**Key Methods:**
- `read_credentials()` - Load from YAML
- `save_credentials()` - Persist to YAML
- `set_password()` - Store in Windows Keyring
- `get_password()` - Retrieve from Windows Keyring
- `delete_password()` - Remove from keyring

**Security Pattern:**
```python
# ✅ Passwords in Windows Keyring
keyring.set_password(service_name=provider, username=username, password=password)

# ✅ Credentials YAML stores only non-sensitive data
credentials = {
    'banks': {
        'hapoalim': {
            'my_account': {
                'username': 'user123',
                'userCode': '12345'
                # NO PASSWORD HERE
            }
        }
    }
}
```

### 8. `OverviewService` (at fad.app.services.overview_service)
**Purpose:** Provide dashboard-level aggregated data and insights.

**Key Responsibilities:**
- Calculate overall financial health metrics
- Aggregate spending across categories
- Track income vs. expenses
- Generate monthly summaries

**Key Methods:**
- `get_monthly_summary()` - Income, expenses, savings
- `get_category_breakdown()` - Spending by category
- `get_trends()` - Month-over-month comparisons

### 9. `InvestmentsService` (at fad.app.services.investments_service)
**Purpose:** Manage investment portfolio tracking.

**Key Responsibilities:**
- Create/update/close investments
- Track balance changes over time
- Calculate portfolio value
- Generate investment reports

**Key Methods:**
- `add_investment()` - Create new investment entry
- `update_balance()` - Record new balance
- `get_portfolio_value()` - Sum all active investments
- `get_investment_history()` - Balance changes over time

## Common Patterns

### Data Merging (Transactions + Splits)

```python
def get_transactions_with_splits(self) -> pd.DataFrame:
    """Merge original transactions with splits for analysis"""
    # Get original transactions
    transactions = self.transactions_repo.get_all_transactions()
    
    # Get all splits
    splits = self.split_repo.get_all_splits()
    
    # Business logic: Replace split transactions with individual splits
    if not splits.empty:
        # Remove original transactions that have splits
        split_ids = splits['transaction_id'].unique()
        transactions = transactions[~transactions['id'].isin(split_ids)]
        
        # Add splits as separate transactions
        transactions = pd.concat([transactions, splits], ignore_index=True)
    
    return transactions
```

### Filtering Non-Expense Categories

```python
def get_expenses_only(self) -> pd.DataFrame:
    """Filter out non-expense categories for analysis"""
    all_transactions = self.get_all_transactions()
    
    # Business rule: Exclude these categories
    non_expense_cats = [
        NonExpensesCategories.IGNORE.value,
        NonExpensesCategories.SALARY.value,
        NonExpensesCategories.OTHER_INCOME.value,
        NonExpensesCategories.SAVINGS.value,
        NonExpensesCategories.INVESTMENTS.value,
        NonExpensesCategories.LIABILITIES.value
    ]
    
    expenses = all_transactions[~all_transactions['category'].isin(non_expense_cats)]
    
    # Business rule: Negative amounts = expenses
    expenses = expenses[expenses['amount'] < 0]
    
    return expenses
```

### Applying Tagging Rules

```python
def apply_rules_to_transactions(self, transactions: pd.DataFrame) -> pd.DataFrame:
    """Apply tagging rules based on priority"""
    rules = self.tagging_rules_repo.get_all_rules(active_only=True)
    
    # Sort by priority DESC (highest first)
    rules = rules.sort_values('priority', ascending=False)
    
    for _, rule in rules.iterrows():
        conditions = json.loads(rule['conditions'])
        
        # Evaluate conditions
        mask = self._evaluate_conditions(transactions, conditions)
        
        # Apply tags to matching transactions (first match wins)
        untagged = transactions['category'].isna()
        transactions.loc[mask & untagged, 'category'] = rule['category']
        transactions.loc[mask & untagged, 'tag'] = rule['tag']
    
    return transactions
```

### Tag Conversion (List ↔ String)

```python
# Business pattern: Tags stored as "tag1;tag2;tag3" in DB
def tags_to_string(tags: list[str]) -> str:
    return ";".join(tags) if isinstance(tags, list) else tags

def tags_to_list(tags_str: str) -> list[str]:
    return tags_str.split(";") if isinstance(tags_str, str) else []

# Usage
def add_budget(self, tags: list[str]):
    tags_str = tags_to_string(tags)
    self.budget_repo.add(tags=tags_str)

def get_budget(self) -> pd.DataFrame:
    budgets = self.budget_repo.read_all()
    budgets['tags'] = budgets['tags'].apply(tags_to_list)
    return budgets
```

## Adding a New Service

### Step 1: Determine Service Type
- **Basic Service:** Only uses repositories
- **Complex Service:** Uses other services + repositories

### Step 2: Check Dependencies
- Ensure no circular dependencies
- Map dependency direction (should be linear)

### Step 3: Create Service Class

```python
from streamlit.connections import SQLConnection
from fad.app.data_access import get_db_connection

class NewService:
    def __init__(self, conn: SQLConnection = get_db_connection()):
        self.conn = conn
        self.repo = NewRepository(conn)
        # If complex service:
        # self.other_service = OtherService(conn)
    
    def business_method(self, param: str) -> pd.DataFrame:
        """Business logic here"""
        data = self.repo.get_data()
        # Transform, calculate, filter
        return processed_data
```

### Step 4: Add Validation

```python
def validate_input(self, value: float) -> tuple[bool, str]:
    """Complex business validation"""
    if value <= 0:
        return False, "Value must be positive"
    if self.exceeds_limit(value):
        return False, "Value exceeds allowed limit"
    return True, ""
```

### Step 5: Handle Errors

```python
def perform_operation(self, id: int):
    try:
        result = self.repo.get_by_id(id)
        if result.empty:
            raise ValueError(f"No record found with ID {id}")
        return result
    except ValueError as e:
        raise ValueError(f"Operation failed: {e}")
    except Exception as e:
        raise RuntimeError(f"Unexpected error: {e}")
```

### Step 6: Use in Components

```python
# Component creates service and calls methods
service = NewService()
data = service.business_method("param")
```

## Best Practices

1. **Keep business logic in services** - Not in repositories or components
2. **Avoid session state** - Let components manage it
3. **Return appropriate types** - DataFrame, primitives, dicts as needed
4. **Validate with context** - Simple in components, complex in services
5. **Re-raise errors with meaning** - Add business context to exceptions
6. **Linear dependencies** - No circular service dependencies
7. **Use dependency injection** - Accept `conn` parameter for testing
8. **Handle negative amounts** - Negative = expense, Positive = income
9. **Consider singletons carefully** - Not currently implemented
10. **Document business rules** - Explain WHY, not just WHAT

## Testing

### Unit Tests
- Mock repositories
- Test business logic calculations
- Verify validation rules
- Test error handling

### Integration Tests
- Use real database connection
- Test service composition
- Verify data transformations
- Test with realistic data

## Notes
- Services orchestrate business logic between data and UI layers
- Avoid `st.session_state` in new services (component responsibility)
- Services can call other services (avoid circular dependencies)
- Password retrieval from Windows Keyring is service responsibility
- Split transactions remain separate in DB, merged in service layer for analysis
- Tagging rules evaluated by priority (highest first, first match wins)
- Connection parameter enables dependency injection for testing
- Consider singleton pattern impacts before implementing

