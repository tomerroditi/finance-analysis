---
applyTo:
  - fad/app/utils/**
---

# Utils Layer - Helper Functions

## Purpose
Utility modules contain **pure helper functions** and reusable classes that don't fit into other layers. Utils are stateless, focused, and provide common functionality used across components and services.

## Core Principle: Pure Functions

### What Utils DO:
✅ **Plotting utilities** - Reusable chart generation (Plotly)  
✅ **Widget utilities** - Reusable UI helper classes  
✅ **Streamlit helpers** - Common Streamlit operations  
✅ **Pure transformations** - Stateless data manipulation  
✅ **Common calculations** - Shared math/formatting logic  

### What Utils DO NOT DO:
❌ **Business logic** - Use services  
❌ **Database access** - Use repositories  
❌ **Session state management** - Use components (mostly)  
❌ **Component rendering** - Use components  

**Golden Rule:** Utils are helpers - stateless, reusable, no side effects (except UI rendering for widget utils).

## Existing Utility Modules

### 1. `plotting.py` - Chart Generation Utilities

**Purpose:** Reusable Plotly chart generation functions.

**Key Functions:**

#### `bar_plot_by_categories(df, values_col, category_col)`
**Purpose:** Create horizontal bar chart grouped by category.

**Parameters:**
- `df` - DataFrame with transaction data
- `values_col` - Column with amounts (negative = expenses)
- `category_col` - Column to group by

**Returns:** `plotly.graph_objects.Figure`

**Example:**
```python
import plotly.graph_objects as go
from fad.app.utils.plotting import bar_plot_by_categories

# Get data from service
transactions = service.get_expenses()

# Create chart
fig = bar_plot_by_categories(
    df=transactions,
    values_col='amount',
    category_col='category'
)

# Display in component
st.plotly_chart(fig, use_container_width=True)
```

**Business Logic Built-In:**
- Multiplies amounts by -1 (makes negative expenses positive for display)
- Adds note about negative values representing income
- Groups and sums by category

#### `bar_plot_by_categories_over_time(df, values_col, category_col, date_col, time_interval)`
**Purpose:** Create stacked bar chart showing category spending over time.

**Parameters:**
- `df` - DataFrame with transaction data
- `values_col` - Column with amounts
- `category_col` - Column to group by
- `date_col` - Date column for time grouping
- `time_interval` - Pandas frequency string ('1D', '1M', '1Y')

**Returns:** `plotly.graph_objects.Figure`

**Example:**
```python
fig = bar_plot_by_categories_over_time(
    df=transactions,
    values_col='amount',
    category_col='category',
    date_col='date',
    time_interval='1M'  # Monthly aggregation
)
st.plotly_chart(fig)
```

**Other Functions (explore `plotting.py`):**
- Pie charts
- Line charts
- Multi-subplot figures
- Custom layout helpers

### 2. `streamlit.py` - Streamlit Helper Functions

**Purpose:** Common Streamlit operations.

#### `clear_session_state(keys, starts_with, ends_with)`
**Purpose:** Clear specific keys from `st.session_state`.

**Parameters:**
- `keys` - List of specific keys to remove
- `starts_with` - List of prefixes (remove all keys starting with these)
- `ends_with` - List of suffixes (remove all keys ending with these)

**Returns:** None (modifies `st.session_state` in place)

**Example:**
```python
from fad.app.utils.streamlit import clear_session_state

# Clear specific keys
clear_session_state(keys=['user_input', 'temp_data'])

# Clear all keys starting with "filter_"
clear_session_state(starts_with=['filter_'])

# Clear all keys ending with "_cache"
clear_session_state(ends_with=['_cache'])

# Combined
clear_session_state(
    keys=['reset_flag'],
    starts_with=['temp_', 'old_'],
    ends_with=['_backup']
)
```

**Use Cases:**
- Reset form state after submission
- Clear cached data when switching pages
- Clean up temporary session state

### 3. `widgets.py` - Reusable Widget Classes

**Purpose:** Advanced reusable UI components.

#### `PandasFilterWidgets` Class

**Purpose:** Automatically generate filter widgets for DataFrame columns and return filtered results.

**Initialization:**
```python
from fad.app.utils.widgets import PandasFilterWidgets

# Create filter widget set
filter_widgets = PandasFilterWidgets(
    df=transactions,
    widgets_map={
        'category': 'select',       # Dropdown
        'tag': 'multiselect',       # Multi-select
        'amount': 'number_range',   # Slider
        'date': 'date_range',       # Date range picker
        'description': 'text'       # Text input
    },
    key_suffix='my_page'  # Unique identifier
)
```

**Widget Types:**
- `'text'` - Exact match text input
- `'text_contains'` - Partial match text input
- `'select'` - Single selection dropdown
- `'multiselect'` - Multiple selection
- `'number_range'` - Numeric slider
- `'date_range'` - Date range picker

**Usage Pattern:**
```python
# Display filter widgets
filter_widgets.display_widgets()

# Get filtered DataFrame
filtered_df = filter_widgets.get_filtered_df()

# Display results
st.dataframe(filtered_df)

# Reset filters (if needed)
filter_widgets.delete_session_state()
```

**Key Features:**
- **Singleton-like pattern** - Reuses instance from session state
- **Automatic state management** - Filters persist across reruns
- **Flexible configuration** - Choose which columns to filter
- **Type-appropriate widgets** - Auto-detects data types

**Example in Component:**
```python
class TransactionFilterComponent:
    def __init__(self, key_suffix: str = ""):
        self.key_suffix = key_suffix
        self.service = TransactionsService()
    
    def render(self):
        # Get data from service
        transactions = self.service.get_transactions()
        
        # Create filter widgets
        filter_widgets = PandasFilterWidgets(
            df=transactions,
            widgets_map={
                'category': 'multiselect',
                'amount': 'number_range',
                'date': 'date_range'
            },
            key_suffix=f"transactions_{self.key_suffix}"
        )
        
        # Display filters and get filtered data
        with st.expander("Filters"):
            filter_widgets.display_widgets()
        
        filtered = filter_widgets.get_filtered_df()
        
        # Display results
        st.dataframe(filtered, use_container_width=True)
```

## Common Patterns

### Creating Reusable Plot Functions

```python
import plotly.graph_objects as go
import pandas as pd

def create_trend_chart(df: pd.DataFrame, x_col: str, y_col: str, title: str) -> go.Figure:
    """
    Create a line chart showing trends over time.
    
    Parameters
    ----------
    df : pd.DataFrame
        Data to plot
    x_col : str
        Column for x-axis (usually date)
    y_col : str
        Column for y-axis (usually amount)
    title : str
        Chart title
    
    Returns
    -------
    go.Figure
        Plotly figure object
    """
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df[x_col],
        y=df[y_col],
        mode='lines+markers',
        name=y_col
    ))
    
    fig.update_layout(
        title=title,
        xaxis_title=x_col.title(),
        yaxis_title=y_col.title(),
        hovermode='x unified'
    )
    
    return fig
```

### Pure Data Transformation Functions

```python
import pandas as pd

def format_currency(amount: float, currency: str = "₪") -> str:
    """
    Format number as currency string.
    
    Parameters
    ----------
    amount : float
        Amount to format
    currency : str
        Currency symbol
    
    Returns
    -------
    str
        Formatted currency string
    """
    return f"{currency}{amount:,.2f}"

def aggregate_by_month(df: pd.DataFrame, date_col: str, value_col: str) -> pd.DataFrame:
    """
    Aggregate values by month.
    
    Parameters
    ----------
    df : pd.DataFrame
        Data to aggregate
    date_col : str
        Date column name
    value_col : str
        Value column to sum
    
    Returns
    -------
    pd.DataFrame
        Aggregated data with columns: [month, total]
    """
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    df['month'] = df[date_col].dt.to_period('M')
    
    result = df.groupby('month')[value_col].sum().reset_index()
    result['month'] = result['month'].astype(str)
    
    return result
```

### Session State Utilities

```python
import streamlit as st
from typing import Any

def get_or_create(key: str, default: Any) -> Any:
    """
    Get value from session state or create with default.
    
    Parameters
    ----------
    key : str
        Session state key
    default : Any
        Default value if key doesn't exist
    
    Returns
    -------
    Any
        Value from session state or default
    """
    if key not in st.session_state:
        st.session_state[key] = default
    return st.session_state[key]

def reset_form_state(form_prefix: str) -> None:
    """
    Clear all session state keys starting with form prefix.
    
    Parameters
    ----------
    form_prefix : str
        Prefix of form keys to clear
    """
    keys_to_remove = [k for k in st.session_state.keys() if k.startswith(form_prefix)]
    for key in keys_to_remove:
        del st.session_state[key]
```

## Adding New Utilities

### Step 1: Choose Appropriate Module

- **Plotting** → `plotting.py` (Plotly charts)
- **Streamlit helpers** → `streamlit.py` (session state, UI utilities)
- **Widget classes** → `widgets.py` (reusable widget sets)
- **New category?** → Create new module (e.g., `date_utils.py`, `formatting.py`)

### Step 2: Write Pure Function

```python
def my_utility_function(input_data: pd.DataFrame, param: str) -> pd.DataFrame:
    """
    Brief description of what this does.
    
    Parameters
    ----------
    input_data : pd.DataFrame
        Description of input
    param : str
        Description of parameter
    
    Returns
    -------
    pd.DataFrame
        Description of output
    
    Examples
    --------
    >>> df = pd.DataFrame({'a': [1, 2, 3]})
    >>> result = my_utility_function(df, 'test')
    >>> result
       a
    0  2
    1  4
    2  6
    """
    # Pure logic - no side effects
    result = input_data.copy()
    result['a'] = result['a'] * 2
    return result
```

### Step 3: Document Well

- Clear docstring (NumPy style)
- Type hints for parameters and return
- Examples in docstring (if complex)
- Explain assumptions/constraints

### Step 4: Keep It Simple

- One function, one purpose
- No side effects (except UI rendering for widget classes)
- No hidden dependencies
- Stateless (no class attributes that change)

## Best Practices

1. **Pure functions** - No side effects, predictable output
2. **Type hints** - Always include parameter and return types
3. **Docstrings** - NumPy style with examples
4. **Single responsibility** - One function, one task
5. **Stateless** - Don't rely on external state
6. **Reusable** - Generic enough for multiple use cases
7. **Tested** - Unit tests for complex logic
8. **Documented examples** - Show how to use
9. **No business logic** - Keep it generic
10. **Minimal dependencies** - Avoid importing services/repositories

## Utility Guidelines

### When to Create a Utility

✅ **Create utility when:**
- Same logic used in 3+ places
- Pure transformation/calculation
- Generic enough for reuse
- No business logic involved

❌ **Don't create utility when:**
- Logic is business-specific
- Needs database access
- Manages state
- Only used once

### Plotting Utilities

**Pattern:** Return `go.Figure`, let components display it.

```python
# ✅ Good - Utility returns figure
def create_chart(df: pd.DataFrame) -> go.Figure:
    return go.Figure(...)

# Component displays
fig = create_chart(data)
st.plotly_chart(fig)

# ❌ Bad - Utility renders directly
def display_chart(df: pd.DataFrame):
    fig = go.Figure(...)
    st.plotly_chart(fig)  # Side effect!
```

### Widget Utilities

**Pattern:** Class-based for stateful widgets, functions for simple helpers.

```python
# ✅ Good - Class for complex widget set
class PandasFilterWidgets:
    def __init__(self, df, widgets_map, key_suffix):
        # Setup
        pass
    
    def display_widgets(self):
        # Render widgets
        pass
    
    def get_filtered_df(self):
        # Return filtered data
        pass

# ✅ Good - Function for simple helper
def render_month_selector(key_suffix: str) -> tuple[int, int]:
    year = st.selectbox("Year", range(2020, 2030), key=f"year_{key_suffix}")
    month = st.selectbox("Month", range(1, 13), key=f"month_{key_suffix}")
    return year, month
```

## Testing Utils

```python
# Unit test example
import pandas as pd
from fad.app.utils.plotting import bar_plot_by_categories

def test_bar_plot_by_categories():
    # Arrange
    df = pd.DataFrame({
        'category': ['Food', 'Transport', 'Food'],
        'amount': [-100, -50, -75]
    })
    
    # Act
    fig = bar_plot_by_categories(df, 'amount', 'category')
    
    # Assert
    assert fig is not None
    assert 'data' in fig
    # Further assertions on chart structure
```

## Common Use Cases

### Format Display Values

```python
def format_amount(amount: float) -> str:
    """Format amount with currency and sign."""
    sign = "+" if amount >= 0 else ""
    return f"{sign}₪{abs(amount):,.2f}"

# In component
st.metric("Balance", format_amount(balance))
```

### Date Range Helpers

```python
from datetime import datetime, timedelta

def get_current_month_range() -> tuple[datetime, datetime]:
    """Get start and end dates of current month."""
    today = datetime.now()
    start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Last day of month
    if today.month == 12:
        end = start.replace(year=today.year + 1, month=1) - timedelta(days=1)
    else:
        end = start.replace(month=today.month + 1) - timedelta(days=1)
    
    return start, end
```

### Data Validation Helpers

```python
def is_valid_category(category: str, valid_categories: list[str]) -> bool:
    """Check if category is in valid list."""
    return category in valid_categories

def is_positive_amount(amount: float) -> bool:
    """Check if amount is positive."""
    return amount > 0
```

## Notes

- Utils are pure helper functions/classes
- No business logic - keep it generic
- Plotting utilities return figures (components display them)
- Widget utilities can render UI (but keep stateless)
- Always use type hints and docstrings
- Test complex utilities
- Extract to utils when used 3+ times
- Prefer functions over classes unless stateful
