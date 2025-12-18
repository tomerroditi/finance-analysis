# Components Layer - UI Implementation

## Purpose
Components contain **ALL UI implementation logic** for the application. They render Streamlit widgets, handle user interactions, manage session state, call services for data/actions, and perform simple validations before delegating to services.

## Core Principle: UI Encapsulation

### What Components DO:
✅ **Render Streamlit widgets** - forms, buttons, charts, tables, dialogs  
✅ **Handle user interactions** - button clicks, form submissions, selections  
✅ **Manage session state** - initialize and update `st.session_state`  
✅ **Simple validation** - positive numbers, non-empty strings, valid dates  
✅ **Call services** - delegate business logic and data operations  
✅ **Display data** - charts, metrics, tables from service layer  
✅ **Error messaging** - show user-friendly error messages from services  

### What Components DO NOT DO:
❌ **Business logic** - calculations, filtering, transformations (use services)  
❌ **Direct database access** - always use services/repositories  
❌ **Complex validation** - business rule validation (use services)  
❌ **Data transformation** - services return processed data ready for display  

**Golden Rule:** Components focus on "how it looks and feels" - services handle "what it means and does".

## Architecture Patterns

### Component Structure

**Preferred Pattern:** Class-based components for better structure and maintainability.

```python
import streamlit as st
from fad.app.services.example_service import ExampleService

class ExampleComponent:
    def __init__(self, key_suffix: str = ""):
        """
        Initialize component.
        
        Parameters
        ----------
        key_suffix : str
            Suffix for widget keys when component used multiple times
        """
        self.key_suffix = key_suffix
        self.service = ExampleService()
    
    def render(self) -> None:
        """
        Main entry point for rendering component UI.
        """
        self._display_header()
        self._display_form()
        self._display_results()
    
    def _display_header(self) -> None:
        """Display component header."""
        st.markdown("## Example Component")
    
    def _display_form(self) -> None:
        """Display input form."""
        with st.form(key=f"example_form_{self.key_suffix}"):
            value = st.number_input("Enter value", key=f"value_input_{self.key_suffix}")
            submitted = st.form_submit_button("Submit")
            
            if submitted:
                # Simple validation
                if value <= 0:
                    st.error("Value must be positive")
                    return
                
                # Call service
                try:
                    result = self.service.process_value(value)
                    st.success(f"Result: {result}")
                except ValueError as e:
                    st.error(str(e))
    
    def _display_results(self) -> None:
        """Display results from service."""
        data = self.service.get_data()
        st.dataframe(data)
```

**When to Use Functions:** Simple, one-off utilities (rare). Most components should be classes.

### Standard Entry Point: `render()`

**Pattern:** Every component class should have a `render()` method as the main entry point.

```python
class MyComponent:
    def render(self) -> None:
        """Main entry point - orchestrates all UI rendering."""
        self._display_section1()
        self._display_section2()
        self._handle_interactions()
```

**Benefits:**
- Consistent interface across all components
- Clear entry point for pages
- Easy to test/mock

### Key Suffix for Widget Uniqueness

**Critical:** Every Streamlit widget MUST have a unique `key` parameter.

**Pattern:** Components that may be used multiple times accept `key_suffix`:

```python
class ReusableComponent:
    def __init__(self, key_suffix: str = ""):
        self.key_suffix = key_suffix
    
    def render(self):
        # Use key_suffix to ensure unique keys
        name = st.text_input("Name", key=f"name_input_{self.key_suffix}")
        amount = st.number_input("Amount", key=f"amount_input_{self.key_suffix}")
        st.button("Submit", key=f"submit_btn_{self.key_suffix}")
```

**Usage in Pages:**
```python
# Page uses component multiple times
component1 = ReusableComponent(key_suffix="section1")
component1.render()

component2 = ReusableComponent(key_suffix="section2")
component2.render()
```

**Key Naming Pattern (Flexible):**
- `f"{widget_type}_{key_suffix}"` - Simple
- `f"{component_name}_{field_name}_{key_suffix}"` - Descriptive
- `f"{action}_{identifier}_{key_suffix}"` - Action-based

**Choose pattern that makes keys unique and meaningful.**

### Session State Management

**Preferred:** Components handle most session state interactions (not pages).

#### Pattern 1: Component Initializes State

```python
class DataFilterComponent:
    def __init__(self):
        # Initialize session state if not exists
        if 'selected_category' not in st.session_state:
            st.session_state.selected_category = None
        if 'date_range' not in st.session_state:
            st.session_state.date_range = (None, None)
    
    def render(self):
        # Use and update session state
        category = st.selectbox(
            "Category",
            options=self.get_categories(),
            key='selected_category'  # Directly binds to session state
        )
```

#### Pattern 2: Page Initializes, Component Uses

```python
# Page code
if 'user_data' not in st.session_state:
    st.session_state.user_data = load_initial_data()

# Component code
class DataDisplayComponent:
    def render(self):
        # Expect session state to be initialized
        data = st.session_state.user_data
        st.dataframe(data)
```

**Both patterns acceptable** - choose based on component scope (reusable vs. page-specific).

### Service Initialization

Components create service instances in `__init__`:

```python
class BudgetComponent:
    def __init__(self):
        self.budget_service = BudgetService()
        self.transactions_service = TransactionsService()
```

**Benefits:**
- Services ready when component renders
- Encapsulation - component owns its dependencies
- Clear service dependencies in `__init__`

## Validation Patterns

### Simple Validation in Components

Before calling services, validate simple inputs:

```python
def _handle_form_submission(self):
    amount = st.session_state.get('amount_input')
    name = st.session_state.get('name_input')
    
    # ✅ Simple validation in component
    if not name or name.strip() == "":
        st.error("Name cannot be empty")
        return
    
    if amount is None or amount <= 0:
        st.error("Amount must be a positive number")
        return
    
    # Call service for complex validation and processing
    try:
        is_valid, error_msg = self.service.validate_and_add(name, amount)
        if not is_valid:
            st.error(error_msg)
        else:
            st.success("Added successfully!")
    except Exception as e:
        st.error(f"Error: {str(e)}")
```

**Simple Validation Examples:**
- ✅ Positive numbers: `amount > 0`
- ✅ Non-empty strings: `name.strip() != ""`
- ✅ Valid dates: `start_date <= end_date`
- ✅ Field presence: `value is not None`
- ✅ String length: `len(text) < 100`

**Complex Validation (Service Layer):**
- ❌ Duplicate checking
- ❌ Business rule violations
- ❌ Cross-field dependencies
- ❌ Database constraints

## Dialog/Modal Pattern

Use `@st.dialog` decorator for popup forms:

```python
@st.dialog("Add New Category")
def add_category_dialog():
    """Modal dialog for adding a new category."""
    category_name = st.text_input("Category Name", key="new_category_name")
    icon = st.text_input("Icon (emoji)", key="new_category_icon")
    
    if st.button("Add", key="add_category_submit"):
        if not category_name:
            st.error("Category name required")
            return
        
        service = CategoriesTagsService()
        service.add_category(category_name, icon)
        st.rerun()  # Refresh to show new category

# In component
class CategoriesComponent:
    def render(self):
        if st.button("New Category", key="open_add_category_dialog"):
            add_category_dialog()
```

**Dialog Best Practices:**
- Use for focused tasks (add, edit, confirm)
- Keep dialogs simple and single-purpose
- Call `st.rerun()` after state changes to refresh main UI
- Validate before closing dialog

## Component Reusability

### Page-Specific Components
Most components are page-specific and contain all UI for a topic/page:

```python
class BudgetManagementComponent:
    """All budget-related UI in one component."""
    def render(self):
        self._display_budget_overview()
        self._display_budget_form()
        self._display_budget_vs_actual()
        self._display_budget_trends()
```

### Reusable Components
When a UI element is used **multiple times** (same/different pages), make it standalone:

```python
# Standalone month selector - used across multiple pages
class MonthSelector:
    def __init__(self, key_suffix: str = ""):
        self.key_suffix = key_suffix
    
    def render(self) -> tuple[int, int]:
        """
        Render month/year selector.
        
        Returns
        -------
        tuple[int, int]
            Selected (year, month)
        """
        col1, col2 = st.columns(2)
        year = col1.selectbox("Year", range(2020, 2030), key=f"year_{self.key_suffix}")
        month = col2.selectbox("Month", range(1, 13), key=f"month_{self.key_suffix}")
        return year, month

# Used in multiple pages
# budget_page.py
selector = MonthSelector(key_suffix="budget_page")
year, month = selector.render()

# analysis_page.py
selector = MonthSelector(key_suffix="analysis_page")
year, month = selector.render()
```

**Guideline:** Extract to standalone component when:
- Used in 2+ places
- Self-contained functionality
- Clear input/output interface

## Existing Components

### 1. `CategoriesTagsEditor` (tagging_components.py)
**Purpose:** Manage categories and tags configuration.

**Key Features:**
- Display all categories with tags
- Add/edit/delete categories and tags
- Reallocate tags between categories
- Protected categories (cannot delete)
- Alphabetically sorted display

**Key Methods:**
- `render()` - Main entry point
- `_add_new_category_dialog()` - Modal for new category
- `_reallocate_tags_dialog()` - Move tags between categories
- `_delete_category()` - Remove category with validation

**Session State:** Manages `categories_and_tags`

**Protected Categories:** Cannot delete categories in `NonExpensesCategories` enum

### 2. `DataScrapingComponent` (data_scraping_components.py)
**Purpose:** Orchestrate web scraping with 2FA handling.

**Key Features:**
- Select accounts to scrape
- Display scraping status (success/failed/waiting for 2FA)
- Handle OTP input for 2FA
- Apply tagging rules post-scrape
- Display scraping results

**Key Methods:**
- `render_data_scraping()` - Main entry point
- `select_services_to_scrape()` - Multi-select for accounts
- `fetch_and_process_data()` - Initiate scraping
- `handle_2fa_input()` - Collect and send OTP code

**Session State:** Uses `scraping_service` (singleton-like pattern)

**Services:** `ScrapingService`, `CredentialsService`, `TaggingRulesService`

### 3. `OverviewComponents` (overview_components.py)
**Purpose:** Display dashboard-level financial overview.

**Key Features:**
- Net worth over time
- Liquidity chart
- Investments breakdown
- Accepts `key_suffix` for reusability

**Key Methods:**
- `net_worth_over_time()` - Display cumulative balance
- `_display_liquidity_chart()` - Cash balance over time
- `_display_investments_chart()` - Investments by tag

**Reusable:** Can be used in multiple pages with different `key_suffix`

### 4. `MonthSelector` (month_selector.py)
**Purpose:** Standalone month/year selection UI.

**Key Features:**
- Current month button
- Next/Previous month navigation
- Custom month selection dialog
- Updates `st.session_state.year` and `st.session_state.month`

**Functions:**
- `select_custom_month()` - Dialog for custom selection
- `select_current_month()` - Jump to current month
- `select_next_month()` - Navigate forward
- `select_previous_month()` - Navigate backward

**Reusable:** Used across budget, analysis, and overview pages

### 5. `BudgetOverview` (budget_overview.py)
**Purpose:** Display budget overview and comparison.

**Key Features:**
- Budget vs. actual spending
- Category-level breakdowns
- Monthly/project budget displays

### 6. `CredentialsComponents` (credentials_components.py)
**Purpose:** Manage user credentials for financial providers.

**Key Features:**
- Add/edit/delete account credentials
- Provider-specific field rendering
- Password input (stored in keyring via service)

### 7. `IncomeOutcomeAnalysisComponents` (income_outcome_analysis_components.py)
**Purpose:** Display income and expense analysis.

**Key Features:**
- Income vs. expenses over time
- Category breakdowns
- Trend analysis

## Common Patterns

### Form Submission Pattern

```python
def _display_form(self):
    with st.form(key=f"my_form_{self.key_suffix}"):
        # Input fields
        name = st.text_input("Name", key=f"name_{self.key_suffix}")
        amount = st.number_input("Amount", min_value=0.0, key=f"amount_{self.key_suffix}")
        
        submitted = st.form_submit_button("Submit")
        
        if submitted:
            # Simple validation
            if not name:
                st.error("Name is required")
                return
            if amount <= 0:
                st.error("Amount must be positive")
                return
            
            # Call service
            try:
                self.service.add_entry(name, amount)
                st.success("Added successfully!")
                st.rerun()  # Refresh to show new data
            except ValueError as e:
                st.error(f"Error: {e}")
```

### Data Display Pattern

```python
def _display_data_table(self):
    """Display data from service in a table."""
    # Get data from service
    data = self.service.get_data()
    
    if data.empty:
        st.info("No data available")
        return
    
    # Simple UI filtering (not business logic)
    search = st.text_input("Search", key=f"search_{self.key_suffix}")
    if search:
        data = data[data['name'].str.contains(search, case=False, na=False)]
    
    # Display table
    st.dataframe(
        data,
        use_container_width=True,
        hide_index=True,
        key=f"data_table_{self.key_suffix}"
    )
```

### Chart Display Pattern

```python
def _display_chart(self):
    """Display chart from service data."""
    import plotly.express as px
    
    # Get processed data from service
    data = self.service.get_chart_data()
    
    if data.empty:
        st.info("No data to display")
        return
    
    # Create chart (visualization logic only)
    fig = px.bar(
        data,
        x='category',
        y='amount',
        title='Spending by Category'
    )
    
    st.plotly_chart(
        fig,
        use_container_width=True,
        key=f"chart_{self.key_suffix}"
    )
```

### Button Action Pattern

```python
def _handle_delete_action(self, item_id: int):
    """Handle delete button click."""
    # Confirmation
    if st.button(f"Delete Item {item_id}", key=f"delete_{item_id}_{self.key_suffix}"):
        try:
            self.service.delete_item(item_id)
            st.success("Deleted successfully!")
            st.rerun()  # Refresh UI
        except ValueError as e:
            st.error(f"Cannot delete: {e}")
```

### Columns Layout Pattern

```python
def _display_metrics(self):
    """Display metrics in columns."""
    col1, col2, col3 = st.columns(3)
    
    with col1:
        total = self.service.get_total()
        st.metric("Total", f"₪{total:,.2f}")
    
    with col2:
        avg = self.service.get_average()
        st.metric("Average", f"₪{avg:,.2f}")
    
    with col3:
        count = self.service.get_count()
        st.metric("Count", count)
```

### Tabs Pattern

```python
def render(self):
    tab1, tab2, tab3 = st.tabs(["Overview", "Details", "Settings"])
    
    with tab1:
        self._display_overview()
    
    with tab2:
        self._display_details()
    
    with tab3:
        self._display_settings()
```

## Error Handling in Components

```python
def _handle_user_action(self):
    try:
        # Call service
        result = self.service.perform_action()
        st.success(f"Action completed: {result}")
    
    except ValueError as e:
        # Business rule violation
        st.error(f"Invalid input: {e}")
    
    except RuntimeError as e:
        # Unexpected error
        st.error(f"An error occurred: {e}")
        st.warning("Please try again or contact support")
    
    except Exception as e:
        # Catch-all
        st.error(f"Unexpected error: {e}")
        # Optionally log to file/service
```

## Adding a New Component

### Step 1: Determine Scope
- **Page-specific:** Contains all UI for a page/topic
- **Reusable:** Standalone, used in multiple places

### Step 2: Create Class Structure

```python
import streamlit as st
from fad.app.services.my_service import MyService

class MyComponent:
    def __init__(self, key_suffix: str = ""):
        self.key_suffix = key_suffix
        self.service = MyService()
        self._initialize_session_state()
    
    def _initialize_session_state(self):
        """Initialize session state variables."""
        if 'my_data' not in st.session_state:
            st.session_state.my_data = None
    
    def render(self) -> None:
        """Main entry point."""
        st.markdown("## My Component")
        self._display_form()
        self._display_results()
    
    def _display_form(self):
        """Render input form."""
        pass
    
    def _display_results(self):
        """Display results from service."""
        pass
```

### Step 3: Add Validation

```python
def _validate_input(self, value, name) -> bool:
    """Simple validation before service call."""
    if value is None:
        st.error(f"{name} is required")
        return False
    if value <= 0:
        st.error(f"{name} must be positive")
        return False
    return True
```

### Step 4: Use in Page

```python
# page.py
from fad.app.components.my_component import MyComponent

component = MyComponent(key_suffix="my_page")
component.render()
```

## Best Practices

1. **Use classes for structure** - Better maintainability than functions
2. **Standard `render()` entry point** - Consistent interface
3. **Unique widget keys** - Use `key_suffix` when reusable
4. **Components manage session state** - Preferred over pages managing it
5. **Simple validation in components** - Complex validation in services
6. **Create services in `__init__`** - Component owns dependencies
7. **Use dialogs for focused tasks** - Keep them simple and single-purpose
8. **Extract reusable components** - When used 2+ times
9. **Handle errors gracefully** - Show user-friendly messages
10. **Keep business logic in services** - Components only handle UI

## Testing

### Manual Testing
- Test with different `key_suffix` values
- Verify unique widget keys (no warnings)
- Test form validation (empty, negative, etc.)
- Test error handling (service errors displayed correctly)

### Component Testing Tips
- Mock services to test UI logic
- Test session state initialization
- Verify correct service methods called
- Test edge cases (empty data, errors)

## Notes
- Components are the UI layer - focus on user experience
- Services handle all business logic and data operations
- Session state managed primarily by components (not pages)
- Every widget needs a unique `key` parameter
- Use `@st.dialog` for modal dialogs
- Simple validation in components, complex in services
- Extract standalone components when used multiple times
- Class-based components preferred for structure

