# Pages Layer - App UI Structure

## Purpose
Pages are **thin wrappers** that organize and layout components. They define the structure of each page in the Streamlit app, instantiate components, and orchestrate component rendering. Pages should contain minimal logic - most UI logic lives in components.

## Core Principle: Minimal Logic

### What Pages DO:
✅ **Instantiate components** - Create component instances  
✅ **Layout structure** - Tabs, columns, containers  
✅ **Component orchestration** - Call component `render()` methods  
✅ **Page-level configuration** - Titles, headers, page layout  
✅ **Initialize page-level session state** - If components don't handle it  

### What Pages DO NOT DO:
❌ **UI rendering** - Components handle this  
❌ **Business logic** - Services handle this  
❌ **Data access** - Repositories handle this  
❌ **Complex state management** - Components handle this (preferred)  

**Golden Rule:** If it's more than 2-3 lines of code, it probably belongs in a component.

## Standard Page Structure

### Basic Page Pattern

```python
import streamlit as st
from fad.app.components.my_component import MyComponent

# Page title/header (optional)
st.title("Page Title")

# Instantiate component(s)
component = MyComponent(key_suffix="page_name")

# Render component
component.render()
```

### Page with Tabs

```python
import streamlit as st
from fad.app.components.comp1 import Component1
from fad.app.components.comp2 import Component2

st.title("My Page")

tab1, tab2, tab3 = st.tabs(["Tab 1", "Tab 2", "Tab 3"])

# Instantiate components
comp1 = Component1(key_suffix="tab1")
comp2 = Component2(key_suffix="tab2")

with tab1:
    comp1.render()

with tab2:
    comp2.render()

with tab3:
    st.info("Coming soon")
```

### Page with Multiple Components

```python
import streamlit as st
from fad.app.components.header_component import HeaderComponent
from fad.app.components.data_component import DataComponent
from fad.app.components.chart_component import ChartComponent

# Header
header = HeaderComponent()
header.render()

# Main content in columns
col1, col2 = st.columns([2, 1])

with col1:
    data_comp = DataComponent(key_suffix="main")
    data_comp.render()

with col2:
    chart_comp = ChartComponent(key_suffix="sidebar")
    chart_comp.render()
```

## Page Registration

Pages must be registered in `main.py` to appear in the app navigation:

```python
# main.py
import streamlit as st

st.set_page_config(layout='wide')

pg = st.navigation([
    st.Page("fad/app/overview.py", title="Overview"),
    st.Page("fad/app/pages/my_page.py", title="My Page"),
    st.Page("fad/app/pages/settings.py", title="Settings"),
])

pg.run()
```

## Existing Pages

### 1. `overview.py` (Main Dashboard)
**Purpose:** Landing page with high-level financial overview.

**Structure:**
```python
overview_comp = OverviewComponents()
overview_comp.net_worth_over_time()
overview_comp.retirement_savings_progress()
overview_comp.investment_portfolio_summary()
overview_comp.debt_reduction_progress()
overview_comp.monthly_cash_flow_summary()
```

**Pattern:** Single component with multiple render methods.

### 2. `budget management.py`
**Purpose:** Manage monthly and project budgets.

**Structure:**
- **Tab 1 (Monthly Budget):** `MonthlyBudgetUI` component
- **Tab 2 (Project Budget):** `ProjectBudgetUI` component

**Key Features:**
- Month selector
- Add/edit/delete budget rules
- Budget vs. actual comparison
- Project-specific budget tracking

### 3. `my_data.py`
**Purpose:** Tag, edit, and scrape financial data.

**Structure:**
- **Tab 1 (Tag):** Transaction tagging
- **Tab 2 (Edit):** Transaction editing
- **Tab 3 (Scrape):** Data scraping with 2FA

**Components Used:**
- `TransactionsTaggingAndEditingComponent`
- `DataScrapingComponent`

**Pattern:** Same component instance used in multiple tabs with different render methods.

### 4. `cat_and_tags.py`
**Purpose:** Manage categories and tags configuration.

**Structure:**
```python
categories_comp = CategoriesTagsEditor()
categories_comp.render()
```

**Pattern:** Single component, single render method.

### 5. `income_outcome_analysis.py`
**Purpose:** Analyze income and expenses.

**Structure:**
- Component renders charts and tables
- Filtering and time period selection

### 6. `my_accounts.py`
**Purpose:** Manage financial account credentials.

**Structure:**
- Add/edit/delete account credentials
- Provider-specific forms

### 7. `paycheks.py`
**Purpose:** Track salary and income (planned feature).

### 8. `savings and investments.py`
**Purpose:** Track investment portfolio and savings.

**Structure:**
- Investment portfolio overview
- Add/edit investments
- Track balances over time

### 9. `settings.py`
**Purpose:** Application settings and preferences.

## Page Layout Best Practices

### Use Tabs for Multiple Sections

```python
# ✅ Good - Organized with tabs
tab1, tab2 = st.tabs(["View", "Edit"])

with tab1:
    view_component.render()

with tab2:
    edit_component.render()

# ❌ Avoid - Everything on one long page
view_component.render()
edit_component.render()  # User must scroll
```

### Use Columns for Side-by-Side Layout

```python
# ✅ Good - Side by side
col1, col2 = st.columns([3, 1])

with col1:
    main_component.render()

with col2:
    sidebar_component.render()
```

### Use Containers for Visual Grouping

```python
with st.container(border=True):
    st.markdown("### Section Title")
    component.render()
```

## Session State in Pages

**Preferred:** Components manage session state.

**Acceptable:** Pages initialize minimal page-level state:

```python
# Page code
if 'current_page' not in st.session_state:
    st.session_state.current_page = 'overview'

if 'selected_year' not in st.session_state:
    st.session_state.selected_year = datetime.now().year

# Component uses the state
component = MyComponent()
component.render()  # Component reads/updates st.session_state.selected_year
```

**Avoid:** Complex state logic in pages - move to components.

## Adding a New Page

### Step 1: Create Page File

Create file in `fad/app/pages/` with descriptive name:

```
fad/app/pages/my_new_page.py
```

### Step 2: Write Page Code

```python
import streamlit as st
from fad.app.components.my_component import MyComponent

st.title("My New Page")

# Optional: Initialize page-level session state
if 'page_state' not in st.session_state:
    st.session_state.page_state = {}

# Instantiate and render component
component = MyComponent(key_suffix="new_page")
component.render()
```

### Step 3: Register in Navigation

Update `main.py`:

```python
pg = st.navigation([
    st.Page("fad/app/overview.py", title="Overview"),
    # ... existing pages ...
    st.Page("fad/app/pages/my_new_page.py", title="My New Page"),
    st.Page("fad/app/pages/settings.py", title="Settings"),
])
```

### Step 4: Test

Run app and verify:
- Page appears in navigation
- Component renders correctly
- No duplicate widget key errors
- Session state works as expected

## Common Patterns

### Single Component Page

```python
import streamlit as st
from fad.app.components.my_component import MyComponent

component = MyComponent()
component.render()
```

### Multi-Tab Page

```python
import streamlit as st
from fad.app.components.comp1 import Comp1
from fad.app.components.comp2 import Comp2

tab1, tab2 = st.tabs(["Section 1", "Section 2"])

comp1 = Comp1(key_suffix="tab1")
comp2 = Comp2(key_suffix="tab2")

with tab1:
    comp1.render()

with tab2:
    comp2.render()
```

### Component with Multiple Render Methods

```python
import streamlit as st
from fad.app.components.multi_comp import MultiComponent

st.header("My Page")

comp = MultiComponent()

# Different sections rendered separately
comp.render_header()
comp.render_main_content()
comp.render_footer()
```

### Page with Subheader

```python
import streamlit as st
from fad.app.components.my_comp import MyComp

st.subheader("Page Subtitle or Description")

component = MyComp(key_suffix="page")
component.render()
```

## Page Design Guidelines

1. **Keep pages thin** - Maximum ~50 lines of code
2. **One component per major section** - Don't split unnecessarily
3. **Use tabs for distinct workflows** - View vs. Edit, Monthly vs. Project
4. **Consistent layout** - Similar pages should have similar structure
5. **Clear navigation** - Logical page order in `main.py`
6. **Descriptive titles** - Make purpose clear
7. **Reuse components** - Same component across pages with different `key_suffix`
8. **Avoid business logic** - If you need calculations, create a service
9. **Avoid complex UI** - If rendering gets complex, create a component
10. **Test in isolation** - Each page should work independently

## Page Organization

### Current Page Structure

```
fad/app/
├── overview.py                    # Main dashboard (special - not in pages/)
└── pages/
    ├── budget management.py       # Budget planning
    ├── cat_and_tags.py           # Category management
    ├── income_outcome_analysis.py # Financial analysis
    ├── my_accounts.py            # Credentials management
    ├── my_data.py                # Data tagging/editing/scraping
    ├── paycheks.py               # Income tracking
    ├── savings and investments.py # Investment tracking
    └── settings.py               # App settings
```

### Naming Conventions

- Use descriptive names (not abbreviations)
- Spaces in filenames are acceptable
- Group related pages (e.g., `budget_` prefix for all budget pages)

## Error Handling

Pages rarely need error handling - components handle this. Exceptions:

```python
# Only if page-level initialization can fail
try:
    component = MyComponent()
    component.render()
except Exception as e:
    st.error(f"Failed to load page: {e}")
    st.info("Please contact support if this persists.")
```

## Testing Pages

### Manual Testing Checklist

- ✅ Page appears in navigation
- ✅ Title/header displays correctly
- ✅ All components render without errors
- ✅ No duplicate widget key warnings
- ✅ Tabs work correctly (if used)
- ✅ Session state initializes properly
- ✅ Page functions independently (reload works)
- ✅ Layout responsive (wide mode)

## Best Practices

1. **Pages are thin wrappers** - Most logic in components
2. **One page, one purpose** - Don't cram multiple features
3. **Register in `main.py`** - Add to navigation immediately
4. **Use unique `key_suffix`** - Even if component used once, good practice
5. **Let components manage state** - Pages should be stateless if possible
6. **Tabs for organization** - Group related functionality
7. **Consistent structure** - Similar pages look similar
8. **Clear titles** - Users know where they are
9. **Test navigation** - Ensure page order makes sense
10. **Document TODOs** - Comment planned features at top of file

## Notes

- Pages define app structure, components define app functionality
- `overview.py` is special - lives in `fad/app/` not `fad/app/pages/`
- All pages must be registered in `main.py` navigation
- Use wide layout mode (configured in `main.py`)
- Pages should be independently testable (reload works)
- Components handle session state management (preferred)
- Keep pages simple - if it gets complex, extract to component

