# Python Scraper Framework Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the Node.js israeli-bank-scrapers subprocess integration with a native Python scraper framework using Playwright, supporting all 18 bank/credit card providers.

**Architecture:** Mirrored class hierarchy from the upstream TypeScript repo — `BaseScraper` → `BrowserScraper`/`ApiScraper` → provider-specific scrapers. The framework lives in `scraper/` at the repo root as a standalone async Python package. A thin adapter in `backend/scraper/` bridges it to the existing FastAPI services.

**Tech Stack:** Playwright (async), httpx, Python 3.12+ dataclasses, argparse CLI

**Design doc:** `docs/plans/2026-03-03-python-scraper-framework-design.md`

**Upstream source:** `https://github.com/eshaham/israeli-bank-scrapers` (TypeScript, Puppeteer-based)

---

## Phase 1: Framework + Base Classes

### Task 1: Package Scaffolding

Create all directories and `__init__.py` files for the `scraper/` package.

**Files:**
- Create: `scraper/__init__.py`
- Create: `scraper/__main__.py` (placeholder)
- Create: `scraper/base/__init__.py`
- Create: `scraper/models/__init__.py`
- Create: `scraper/utils/__init__.py`
- Create: `scraper/providers/__init__.py`
- Create: `scraper/providers/banks/__init__.py`
- Create: `scraper/providers/credit_cards/__init__.py`
- Create: `scraper/providers/test/__init__.py`

**Step 1: Create directory structure**

```bash
mkdir -p scraper/base scraper/models scraper/utils \
  scraper/providers/banks scraper/providers/credit_cards scraper/providers/test
```

**Step 2: Create empty `__init__.py` files**

Create empty `__init__.py` in each directory. The root `scraper/__init__.py` will be populated later (Task 13).

**Step 3: Add dependencies to pyproject.toml**

Add `playwright` and `httpx` to the project dependencies:

```toml
playwright = "^1.49"
httpx = "^0.28"
```

**Step 4: Install dependencies and Playwright browsers**

```bash
poetry install --no-root
playwright install chromium
```

**Step 5: Commit**

```bash
git add scraper/ pyproject.toml poetry.lock
git commit -m "chore: scaffold scraper package structure and add dependencies"
```

---

### Task 2: Data Models

Port the TypeScript `Transaction`, `TransactionsAccount`, and related types as Python dataclasses.

**Files:**
- Create: `scraper/models/transaction.py`
- Create: `scraper/models/account.py`
- Create: `scraper/models/result.py`

**Step 1: Create transaction models**

```python
# scraper/models/transaction.py
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TransactionType(str, Enum):
    NORMAL = "normal"
    INSTALLMENTS = "installments"


class TransactionStatus(str, Enum):
    COMPLETED = "completed"
    PENDING = "pending"


@dataclass
class InstallmentInfo:
    """Installment payment details."""

    number: int
    total: int


@dataclass
class Transaction:
    """A single financial transaction scraped from a provider.

    Mirrors the upstream israeli-bank-scrapers Transaction interface.
    """

    type: TransactionType
    status: TransactionStatus
    date: str  # ISO date (YYYY-MM-DD)
    processed_date: str  # ISO date
    original_amount: float
    original_currency: str
    charged_amount: float
    description: str
    identifier: Optional[str] = None
    charged_currency: Optional[str] = None
    memo: Optional[str] = None
    category: Optional[str] = None
    installments: Optional[InstallmentInfo] = None
```

**Step 2: Create account result model**

```python
# scraper/models/account.py
from dataclasses import dataclass, field
from typing import Optional

from scraper.models.transaction import Transaction


@dataclass
class AccountResult:
    """Scraped data for a single account."""

    account_number: str
    transactions: list[Transaction] = field(default_factory=list)
    balance: Optional[float] = None
```

**Step 3: Create scraping result model**

```python
# scraper/models/result.py
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from scraper.models.account import AccountResult


class LoginResult(str, Enum):
    SUCCESS = "success"
    INVALID_PASSWORD = "invalid_password"
    CHANGE_PASSWORD = "change_password"
    ACCOUNT_BLOCKED = "account_blocked"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class ScrapingResult:
    """Result of a complete scraping operation."""

    success: bool
    accounts: list[AccountResult] = field(default_factory=list)
    error_type: Optional[str] = None
    error_message: Optional[str] = None
```

**Step 4: Update models `__init__.py`**

```python
# scraper/models/__init__.py
from scraper.models.account import AccountResult
from scraper.models.result import LoginResult, ScrapingResult
from scraper.models.transaction import (
    InstallmentInfo,
    Transaction,
    TransactionStatus,
    TransactionType,
)

__all__ = [
    "AccountResult",
    "InstallmentInfo",
    "LoginResult",
    "ScrapingResult",
    "Transaction",
    "TransactionStatus",
    "TransactionType",
]
```

**Step 5: Commit**

```bash
git add scraper/models/
git commit -m "feat(scraper): add data models (Transaction, AccountResult, ScrapingResult)"
```

---

### Task 3: Exceptions

Port the error type enum and exception hierarchy from both the upstream TypeScript and the current Python backend.

**Files:**
- Create: `scraper/exceptions.py`

**Step 1: Create exception hierarchy**

```python
# scraper/exceptions.py
from enum import Enum


class ErrorType(str, Enum):
    """Error categories matching upstream israeli-bank-scrapers."""

    INVALID_PASSWORD = "INVALID_PASSWORD"
    CHANGE_PASSWORD = "CHANGE_PASSWORD"
    ACCOUNT_BLOCKED = "ACCOUNT_BLOCKED"
    TWO_FACTOR_RETRIEVER_MISSING = "TWO_FACTOR_RETRIEVER_MISSING"
    TIMEOUT = "TIMEOUT"
    GENERIC = "GENERIC"
    GENERAL = "GENERAL_ERROR"


class ScraperError(Exception):
    """Base exception for all scraper errors."""

    error_type: ErrorType = ErrorType.GENERAL

    def __init__(self, message: str = "", error_type: ErrorType | None = None):
        super().__init__(message)
        if error_type:
            self.error_type = error_type


class CredentialsError(ScraperError):
    error_type = ErrorType.INVALID_PASSWORD


class PasswordChangeError(ScraperError):
    error_type = ErrorType.CHANGE_PASSWORD


class AccountBlockedError(ScraperError):
    error_type = ErrorType.ACCOUNT_BLOCKED


class TwoFactorError(ScraperError):
    error_type = ErrorType.TWO_FACTOR_RETRIEVER_MISSING


class TimeoutError(ScraperError):
    error_type = ErrorType.TIMEOUT


class ConnectionError(ScraperError):
    error_type = ErrorType.GENERIC
```

**Step 2: Commit**

```bash
git add scraper/exceptions.py
git commit -m "feat(scraper): add exception hierarchy and ErrorType enum"
```

---

### Task 4: Utility — Waiting & Dates

Port the `waiting.ts` and `dates.ts` helpers. These are simple async utilities.

**Files:**
- Create: `scraper/utils/waiting.py`
- Create: `scraper/utils/dates.py`

**Step 1: Create waiting utilities**

```python
# scraper/utils/waiting.py
import asyncio
from typing import Awaitable, Callable, TypeVar

from scraper.exceptions import TimeoutError

T = TypeVar("T")


async def wait_until(
    async_test: Callable[[], Awaitable[T]],
    description: str = "",
    timeout: float = 10.0,
    interval: float = 0.1,
) -> T:
    """Poll an async function until it returns a truthy value or timeout.

    Parameters
    ----------
    async_test : callable
        Async function that returns a value. Polling stops when truthy.
    description : str
        Human-readable description for timeout error message.
    timeout : float
        Maximum seconds to wait.
    interval : float
        Seconds between polls.

    Returns
    -------
    T
        The first truthy value returned by ``async_test``.

    Raises
    ------
    TimeoutError
        If ``timeout`` seconds elapse without a truthy result.
    """
    elapsed = 0.0
    while elapsed < timeout:
        result = await async_test()
        if result:
            return result
        await asyncio.sleep(interval)
        elapsed += interval
    raise TimeoutError(f"Timeout: {description}" if description else "Timeout")


async def sleep(seconds: float) -> None:
    """Async sleep wrapper."""
    await asyncio.sleep(seconds)
```

**Step 2: Create date utilities**

```python
# scraper/utils/dates.py
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta


def get_all_months(start_date: date, future_months: int = 0) -> list[date]:
    """Generate list of first-of-month dates from start_date to now.

    Parameters
    ----------
    start_date : date
        Start date (will be rounded to first of month).
    future_months : int
        Extra months beyond current month to include.

    Returns
    -------
    list[date]
        First-of-month dates from start through current month + future_months.
    """
    current = start_date.replace(day=1)
    end = date.today().replace(day=1) + relativedelta(months=future_months)
    months = []
    while current <= end:
        months.append(current)
        current += relativedelta(months=1)
    return months
```

**Step 3: Commit**

```bash
git add scraper/utils/waiting.py scraper/utils/dates.py
git commit -m "feat(scraper): add waiting and date utility helpers"
```

---

### Task 5: Utility — Browser Helpers

Port `elements-interactions.ts` to Playwright Python equivalents. Playwright's API is higher-level than Puppeteer's, so many helpers become thinner wrappers.

**Files:**
- Create: `scraper/utils/browser.py`

**Step 1: Create browser helpers**

Port each helper function from the upstream `elements-interactions.ts`. Key functions:
- `wait_until_element_found` — wraps `page.wait_for_selector()`
- `wait_until_element_disappear` — wraps `page.wait_for_selector(state="hidden")`
- `wait_until_iframe_found` — polls `page.frames` with `wait_until()`
- `fill_input` — clears via JS then types character-by-character (upstream behavior)
- `set_value` — sets value directly via JS
- `click_button` — clicks via JS `el.click()`
- `page_eval_all` — wraps `page.eval_on_selector_all()`
- `page_eval` — wraps `page.eval_on_selector()`
- `element_present_on_page` — checks if element exists
- `dropdown_select` — wraps `page.select_option()`
- `dropdown_elements` — gets all option elements from a select

Note: The `fill_input` function clears the input field value via JavaScript evaluation, then types the new value. The `click_button` function clicks via JavaScript evaluation. These patterns mirror the upstream Puppeteer behavior where `$eval` is used.

**Step 2: Commit**

```bash
git add scraper/utils/browser.py
git commit -m "feat(scraper): add Playwright browser helper utilities"
```

---

### Task 6: Utility — In-Page Fetch

Port `fetch.ts` — the `fetchGetWithinPage` and `fetchPostWithinPage` functions that execute `fetch()` inside the browser's page context to inherit session cookies. Also include standalone HTTP fetch helpers using httpx.

**Files:**
- Create: `scraper/utils/fetch.py`

**Step 1: Create fetch utilities**

Port two categories of fetch helpers:

**Standalone HTTP helpers (for ApiScraper):**
- `fetch_get(url, extra_headers, client)` — HTTP GET via httpx
- `fetch_post(url, data, extra_headers, client)` — HTTP POST via httpx
- `fetch_graphql(url, query, variables, extra_headers, client)` — GraphQL via POST

**In-page fetch helpers (for BrowserScraper API-via-browser pattern):**
- `fetch_get_within_page(page, url, ignore_errors)` — executes `fetch()` inside the browser page context via `page.evaluate()`, inheriting session cookies. Returns parsed JSON.
- `fetch_post_within_page(page, url, data, extra_headers, ignore_errors)` — same but POST.

The in-page fetch functions pass a JavaScript function string to `page.evaluate()` that calls `fetch()` with `credentials: 'include'`. The response text is returned to Python and parsed as JSON. Error handling follows the upstream pattern: if `ignore_errors` is True, return None on failure; otherwise raise.

**Step 2: Commit**

```bash
git add scraper/utils/fetch.py
git commit -m "feat(scraper): add fetch utilities (standalone httpx + in-page browser fetch)"
```

---

### Task 7: Utility — Navigation

Port `navigation.ts` — URL waiting, redirect detection.

**Files:**
- Create: `scraper/utils/navigation.py`

**Step 1: Create navigation helpers**

- `wait_for_navigation(page_or_frame, wait_until_event)` — wraps `page.wait_for_load_state()`
- `get_current_url(page_or_frame, client_side)` — returns URL, optionally via JS `window.location.href`
- `wait_for_redirect(page_or_frame, timeout, client_side, ignore_list)` — polls until URL changes
- `wait_for_url(page_or_frame, url_pattern, timeout, client_side)` — polls until URL matches string or regex

**Step 2: Commit**

```bash
git add scraper/utils/navigation.py
git commit -m "feat(scraper): add navigation utility helpers"
```

---

### Task 8: Utility — Transactions

Port `transactions.ts` — installment date fixing, sorting, filtering.

**Files:**
- Create: `scraper/utils/transactions.py`

**Step 1: Create transaction helpers**

- `fix_installments(transactions)` — for installment transactions where `number > 1`, shift date forward by `(number - 1)` months
- `sort_transactions_by_date(transactions)` — sort by date ascending
- `filter_old_transactions(transactions, start_date, combine_installments)` — filter out transactions before start_date

**Step 2: Commit**

```bash
git add scraper/utils/transactions.py
git commit -m "feat(scraper): add transaction utility helpers (installments, sort, filter)"
```

---

### Task 9: Utility — Update `__init__.py`

Export key utilities from the utils package.

**Files:**
- Modify: `scraper/utils/__init__.py`

**Step 1: Update utils init**

Export all utility functions from their respective modules.

**Step 2: Commit**

```bash
git add scraper/utils/__init__.py
git commit -m "feat(scraper): export utilities from utils package"
```

---

### Task 10: BaseScraper

The abstract base class that defines the scraper lifecycle: `initialize → login → fetch_data → terminate`. Handles error wrapping and progress callbacks.

**Files:**
- Create: `scraper/base/base_scraper.py`

**Step 1: Create BaseScraper**

Key design:
- `ScraperOptions` dataclass with: `show_browser`, `default_timeout`, `start_date`, `future_months_to_scrape`, `combine_installments`, `store_failure_screenshot_path`, `verbose`
- `BaseScraper(ABC)` with:
  - Constructor: `(provider, credentials, options)`
  - `scrape() -> ScrapingResult` — the main entry point. Orchestrates: `initialize() → login() → fetch_data() → terminate()`. Catches `TimeoutError` and general exceptions at each stage, returns `ScrapingResult` with error info on failure.
  - Abstract methods: `initialize()`, `login() -> LoginResult`, `fetch_data() -> list[AccountResult]`
  - `terminate(success: bool)` — override for cleanup
  - `on_progress: Callable[[str], None]` — optional callback for progress updates
  - `on_otp_request: Callable[[], Awaitable[str]]` — optional async callback for 2FA

**Step 2: Commit**

```bash
git add scraper/base/base_scraper.py
git commit -m "feat(scraper): add BaseScraper with lifecycle orchestration"
```

---

### Task 11: BrowserScraper

The browser-based scraper that manages Playwright lifecycle and provides a generic declarative login flow. This is the core class that most provider scrapers will extend.

**Files:**
- Create: `scraper/base/browser_scraper.py`

**Step 1: Create BrowserScraper**

Key design:

**LoginOptions dataclass:**
- `login_url: str`
- `fields: list[dict[str, str]]` — `[{"selector": "#user", "value": "myuser"}, ...]`
- `submit_button_selector: str | Callable` — CSS selector or async callable
- `possible_results: dict[LoginResult, list[LoginResultCheck]]` — maps `LoginResult` to conditions
- Optional: `check_readiness`, `pre_action`, `post_action`, `user_agent`, `wait_until`

**LoginResultCheck type:** `str | re.Pattern | Callable[..., Awaitable[bool]]`
- String: exact URL match (case-insensitive)
- Regex: URL pattern match
- Callable: async function receiving `(page=, value=)` for custom DOM checks

**BrowserScraper(BaseScraper):**
- `initialize()` — launch Playwright Chromium, create page, set viewport 1024x768
- `login()` — generic flow using `get_login_options()`:
  1. Navigate to login URL
  2. Wait for readiness (submit button visible or custom check)
  3. Execute pre_action (e.g., switch to iframe)
  4. Fill input fields
  5. Click submit (selector or custom callable)
  6. Execute post_action or wait for navigation
  7. Detect login result by matching current URL against `possible_results`
- `terminate(success)` — screenshot on failure, close browser and Playwright
- `get_login_options(credentials) -> LoginOptions` — must be overridden by subclasses
- `fetch_get(url) / fetch_post(url, data)` — in-page fetch helpers delegating to utils
- `navigate_to(url, wait_until)` — navigate with error checking

**Step 2: Commit**

```bash
git add scraper/base/browser_scraper.py
git commit -m "feat(scraper): add BrowserScraper with Playwright lifecycle and generic login"
```

---

### Task 12: ApiScraper

The non-browser scraper base class for pure HTTP/API-based providers.

**Files:**
- Create: `scraper/base/api_scraper.py`

**Step 1: Create ApiScraper**

```python
# scraper/base/api_scraper.py
class ApiScraper(BaseScraper):
    """Scraper using HTTP requests only (no browser). Provides httpx.AsyncClient."""

    client: httpx.AsyncClient

    async def initialize(self):
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(30.0), follow_redirects=True)

    async def terminate(self, success):
        if hasattr(self, "client"):
            await self.client.aclose()
```

**Step 2: Update base `__init__.py`**

Export `ApiScraper`, `BaseScraper`, `ScraperOptions`, `BrowserScraper`, `LoginOptions`.

**Step 3: Commit**

```bash
git add scraper/base/
git commit -m "feat(scraper): add ApiScraper (httpx-based, no browser) and update base exports"
```

---

### Task 13: Provider Config Registry & Factory

Create the provider configuration registry and the `create_scraper()` factory function.

**Files:**
- Create: `scraper/models/credentials.py`
- Modify: `scraper/__init__.py`

**Step 1: Create provider config registry**

`ProviderConfig` dataclass with: `provider`, `service`, `name`, `required_fields`, `requires_2fa`.

`PROVIDER_CONFIGS` dict mapping provider string to `ProviderConfig` for all 18 providers. Provider keys must match the values used in `backend/constants/providers.py` (e.g., `"hapoalim"`, `"max"`, `"visa cal"`, `"otsar hahayal"`).

**Step 2: Create factory and package init**

`create_scraper(provider, credentials, options) -> BaseScraper` — maps provider string to scraper class via dict lookup. Uses lazy imports to avoid circular dependencies.

`is_2fa_required(provider) -> bool` — checks `PROVIDER_CONFIGS`.

**Step 3: Commit**

```bash
git add scraper/__init__.py scraper/models/credentials.py
git commit -m "feat(scraper): add provider config registry and create_scraper factory"
```

---

### Task 14: Dummy/Test Scrapers

Port the test scrapers for demo mode. These generate fake data without needing real credentials or a browser.

**Files:**
- Create: `scraper/providers/test/dummy_regular.py`
- Create: `scraper/providers/test/dummy_tfa.py`
- Create: `scraper/providers/test/dummy_tfa_no_otp.py`

**Step 1: Create DummyRegularScraper**

- Extends `BaseScraper`
- `initialize()` — no-op
- `login()` — sleep 1 second, return SUCCESS
- `fetch_data()` — generate 3-13 random transactions with dates between start_date and today, amounts between -1000 and -10, descriptions from a merchant list

Also create `DummyCreditCardScraper` as a trivial subclass (identical behavior).

**Step 2: Create DummyTFAScraper**

- Extends `DummyRegularScraper`
- `login()` — waits for OTP via `self.on_otp_request()`, accepts any code, returns SUCCESS. Returns UNKNOWN_ERROR if no OTP callback or if code is "cancel".

**Step 3: Create DummyTFANoOTPScraper**

Trivial subclass of `DummyTFAScraper`.

**Step 4: Update test providers init**

**Step 5: Commit**

```bash
git add scraper/providers/test/
git commit -m "feat(scraper): add dummy/test scrapers for demo mode"
```

---

### Task 15: CLI Entry Point

Create the `__main__.py` for standalone scraper testing.

**Files:**
- Create: `scraper/__main__.py`

**Step 1: Create CLI**

Usage:
```
python -m scraper --list                              # List all providers
python -m scraper hapoalim --start-date 2024-01-01    # Scrape with date
python -m scraper max --days 30 --output json          # Last 30 days, JSON output
python -m scraper onezero --headless false              # Visible browser
```

Features:
- `--list` lists all providers from `PROVIDER_CONFIGS` with required fields and 2FA status
- Credentials from env vars (`SCRAPER_USERNAME`, `SCRAPER_PASSWORD`, etc.) or interactive prompt (getpass for password)
- 2FA via interactive `input("Enter OTP code: ")`
- Output formats: `text` (default, human-readable table) or `json` (full dataclass serialization)
- Progress messages printed to stderr

**Step 2: Commit**

```bash
git add scraper/__main__.py
git commit -m "feat(scraper): add CLI entry point for standalone scraper testing"
```

---

## Phase 2: Port All 18 Providers

Each provider scraper is ported from the upstream TypeScript source. They fall into three patterns:

1. **API-via-browser** (most common): Log in via Playwright, then call JSON APIs using in-page fetch. Examples: Hapoalim, Discount, Max, Isracard/Amex.
2. **DOM scraping**: Navigate pages and extract data from HTML elements. Examples: Leumi, Beinleumi group, Mizrahi, Yahav, Union Bank.
3. **Pure API**: No browser. Examples: OneZero.

For each provider task below, the implementation should be ported directly from the upstream TypeScript source at `https://github.com/eshaham/israeli-bank-scrapers/blob/master/src/scrapers/<provider>.ts`. Use `gh api repos/eshaham/israeli-bank-scrapers/contents/src/scrapers/<file>.ts --jq '.content' | base64 -d` to read the source.

### Task 16: Hapoalim Scraper (API-via-browser, live testable)

Port `src/scrapers/hapoalim.ts`. This is an API-via-browser scraper that logs in, then calls Hapoalim's internal REST APIs via `fetchGetWithinPage` and `fetchPostWithinPage`.

**Files:**
- Create: `scraper/providers/banks/hapoalim.py`

**Step 1: Read upstream source**

```bash
gh api repos/eshaham/israeli-bank-scrapers/contents/src/scrapers/hapoalim.ts --jq '.content' | base64 -d
```

**Step 2: Port the scraper**

Port the TypeScript class `HapoalimScraper` to Python:
- Extends `BrowserScraper`
- `get_login_options()` returns credentials mapping for userCode/password
- `fetch_data()` calls Hapoalim's JSON APIs via `self.fetch_get()` and `self.fetch_post()`
- Translate all URL constants, date formatting, and transaction parsing logic
- Map Hapoalim's response format to `Transaction` dataclass

Key upstream patterns to preserve:
- Login URL: `https://login.bankhapoalim.co.il/ng-portals-bt/auth/he/login`
- API calls for fetching accounts list, then transactions per account
- Date format: `YYYYMMDD`
- Transaction identifier from `referenceNumber` or `serialNumber`
- Balance comes from the account data API response

**Step 3: Commit**

```bash
git add scraper/providers/banks/hapoalim.py
git commit -m "feat(scraper): port Hapoalim bank scraper"
```

---

### Task 17: OneZero Scraper (Pure API, live testable)

Port `src/scrapers/one-zero.ts`. This is the only pure API scraper — no browser needed. Uses REST + GraphQL endpoints with OTP-based 2FA.

**Files:**
- Create: `scraper/providers/banks/onezero.py`

**Step 1: Read upstream source**

```bash
gh api repos/eshaham/israeli-bank-scrapers/contents/src/scrapers/one-zero.ts --jq '.content' | base64 -d
```

**Step 2: Port the scraper**

Port `OneZeroScraper` to Python:
- Extends `ApiScraper` (uses `self.client` httpx)
- `login()` handles the OTP flow:
  1. POST to auth endpoint with email/password
  2. If long-term token exists, use it; otherwise trigger OTP via `self.on_otp_request()`
  3. Verify OTP code
- `fetch_data()` uses GraphQL queries to fetch accounts and transactions
- Port the GraphQL query strings and response parsing
- Handle the Hebrew text sanitization (`sanitize_hebrew()` function)

**Step 3: Commit**

```bash
git add scraper/providers/banks/onezero.py
git commit -m "feat(scraper): port OneZero bank scraper (API-only with 2FA)"
```

---

### Task 18: Max Scraper (API-via-browser, live testable)

Port `src/scrapers/max.ts`. API-via-browser pattern similar to Hapoalim.

**Files:**
- Create: `scraper/providers/credit_cards/max.py`

**Step 1: Read upstream source**

```bash
gh api repos/eshaham/israeli-bank-scrapers/contents/src/scrapers/max.ts --jq '.content' | base64 -d
```

**Step 2: Port the scraper**

Port `MaxScraper` to Python:
- Extends `BrowserScraper`
- Login at Max's website, then call their internal APIs via in-page fetch
- Parse Max's transaction format (credit card transactions with installment support)
- Handle the month-by-month fetching logic (iterate through months from start_date to now)
- Map Max-specific fields to `Transaction` dataclass

**Step 3: Commit**

```bash
git add scraper/providers/credit_cards/max.py
git commit -m "feat(scraper): port Max credit card scraper"
```

---

### Task 19: Isracard/Amex Shared Base + Scrapers (API-via-browser, live testable)

Port `src/scrapers/base-isracard-amex.ts`, `isracard.ts`, and `amex.ts`. These share a base class that handles request interception and API calls.

**Files:**
- Create: `scraper/providers/credit_cards/isracard_amex_base.py`
- Create: `scraper/providers/credit_cards/isracard.py`
- Create: `scraper/providers/credit_cards/amex.py`

**Step 1: Read upstream sources**

```bash
gh api repos/eshaham/israeli-bank-scrapers/contents/src/scrapers/base-isracard-amex.ts --jq '.content' | base64 -d
gh api repos/eshaham/israeli-bank-scrapers/contents/src/scrapers/isracard.ts --jq '.content' | base64 -d
gh api repos/eshaham/israeli-bank-scrapers/contents/src/scrapers/amex.ts --jq '.content' | base64 -d
```

**Step 2: Port the shared base**

Port `IsracardAmexBaseScraper`:
- Extends `BrowserScraper`
- Uses request interception to block scripts and capture auth tokens
- For Playwright, use `page.route()` for request interception
- Calls Isracard/Amex API endpoints after login to fetch transactions
- Handles the complex month-by-month fetching with detailed transaction parsing

**Step 3: Port Isracard and Amex (thin wrappers)**

Each is ~10 lines — just sets `COMPANY_CODE` (Isracard: "11", Amex: "77").

**Step 4: Commit**

```bash
git add scraper/providers/credit_cards/isracard_amex_base.py \
       scraper/providers/credit_cards/isracard.py \
       scraper/providers/credit_cards/amex.py
git commit -m "feat(scraper): port Isracard/Amex shared base and scrapers"
```

---

### Task 20: Beinleumi Group Shared Base + Scrapers

Port `src/scrapers/base-beinleumi-group.ts` and the 4 thin wrappers: `beinleumi.ts`, `otsar-hahayal.ts`, `massad.ts`, `pagi.ts`.

**Files:**
- Create: `scraper/providers/banks/beinleumi_group.py`
- Create: `scraper/providers/banks/beinleumi.py`
- Create: `scraper/providers/banks/otsar_hahayal.py`
- Create: `scraper/providers/banks/massad.py`
- Create: `scraper/providers/banks/pagi.py`

**Step 1: Read upstream sources**

```bash
gh api repos/eshaham/israeli-bank-scrapers/contents/src/scrapers/base-beinleumi-group.ts --jq '.content' | base64 -d
gh api repos/eshaham/israeli-bank-scrapers/contents/src/scrapers/beinleumi.ts --jq '.content' | base64 -d
```

**Step 2: Port the shared base**

Port `BeinleumiGroupBaseScraper`:
- Extends `BrowserScraper`
- Complex DOM scraping with iframe handling
- Handles both old and new UI variants
- Each subclass just sets a different `BASE_URL`

**Step 3: Port the 4 thin wrappers**

Each is ~10 lines — just a class extending `BeinleumiGroupBaseScraper` with a provider-specific URL constant.

**Step 4: Commit**

```bash
git add scraper/providers/banks/beinleumi_group.py \
       scraper/providers/banks/beinleumi.py \
       scraper/providers/banks/otsar_hahayal.py \
       scraper/providers/banks/massad.py \
       scraper/providers/banks/pagi.py
git commit -m "feat(scraper): port Beinleumi group shared base and 4 bank scrapers"
```

---

### Task 21: Discount + Mercantile Scrapers

Port `src/scrapers/discount.ts` and `src/scrapers/mercantile.ts`. Mercantile extends Discount with just a different login URL.

**Files:**
- Create: `scraper/providers/banks/discount.py`
- Create: `scraper/providers/banks/mercantile.py`

**Step 1: Read upstream source and port**

```bash
gh api repos/eshaham/israeli-bank-scrapers/contents/src/scrapers/discount.ts --jq '.content' | base64 -d
gh api repos/eshaham/israeli-bank-scrapers/contents/src/scrapers/mercantile.ts --jq '.content' | base64 -d
```

Port `DiscountScraper` (API-via-browser pattern). `MercantileScraper` is a trivial wrapper that just sets a different `LOGIN_URL`.

**Step 2: Commit**

```bash
git add scraper/providers/banks/discount.py scraper/providers/banks/mercantile.py
git commit -m "feat(scraper): port Discount and Mercantile bank scrapers"
```

---

### Task 22: Leumi Scraper

Port `src/scrapers/leumi.ts`. DOM scraping + intercepted HTTP response pattern.

**Files:**
- Create: `scraper/providers/banks/leumi.py`

**Step 1: Read upstream source and port**

```bash
gh api repos/eshaham/israeli-bank-scrapers/contents/src/scrapers/leumi.ts --jq '.content' | base64 -d
```

Port `LeumiScraper` — extends `BrowserScraper`, uses DOM scraping with some API interception.

**Step 2: Commit**

```bash
git add scraper/providers/banks/leumi.py
git commit -m "feat(scraper): port Leumi bank scraper"
```

---

### Task 23: Mizrahi Scraper

Port `src/scrapers/mizrahi.ts`. DOM scraping with iframe handling — one of the more complex scrapers.

**Files:**
- Create: `scraper/providers/banks/mizrahi.py`

**Step 1: Read upstream source and port**

```bash
gh api repos/eshaham/israeli-bank-scrapers/contents/src/scrapers/mizrahi.ts --jq '.content' | base64 -d
```

**Step 2: Commit**

```bash
git add scraper/providers/banks/mizrahi.py
git commit -m "feat(scraper): port Mizrahi bank scraper"
```

---

### Task 24: Visa Cal Scraper

Port `src/scrapers/visa-cal.ts`. API-via-browser with session storage token extraction.

**Files:**
- Create: `scraper/providers/credit_cards/visa_cal.py`

**Step 1: Read upstream source and port**

```bash
gh api repos/eshaham/israeli-bank-scrapers/contents/src/scrapers/visa-cal.ts --jq '.content' | base64 -d
```

Port `VisaCalScraper` — logs in via browser, extracts auth token from session storage, then calls Visa Cal's REST API.

**Step 2: Commit**

```bash
git add scraper/providers/credit_cards/visa_cal.py
git commit -m "feat(scraper): port Visa Cal credit card scraper"
```

---

### Task 25: Yahav Scraper

Port `src/scrapers/yahav.ts`. DOM scraping pattern.

**Files:**
- Create: `scraper/providers/banks/yahav.py`

**Step 1: Read upstream source and port**

```bash
gh api repos/eshaham/israeli-bank-scrapers/contents/src/scrapers/yahav.ts --jq '.content' | base64 -d
```

**Step 2: Commit**

```bash
git add scraper/providers/banks/yahav.py
git commit -m "feat(scraper): port Yahav bank scraper"
```

---

### Task 26: Union Bank Scraper

Port `src/scrapers/union-bank.ts`. DOM scraping with iframe.

**Files:**
- Create: `scraper/providers/banks/union.py`

**Step 1: Read upstream source and port**

```bash
gh api repos/eshaham/israeli-bank-scrapers/contents/src/scrapers/union-bank.ts --jq '.content' | base64 -d
```

**Step 2: Commit**

```bash
git add scraper/providers/banks/union.py
git commit -m "feat(scraper): port Union Bank scraper"
```

---

### Task 27: Beyahad Bishvilha Scraper

Port `src/scrapers/beyahad-bishvilha.ts`. DOM scraping pattern.

**Files:**
- Create: `scraper/providers/credit_cards/beyahad_bishvilha.py`

**Step 1: Read upstream source and port**

```bash
gh api repos/eshaham/israeli-bank-scrapers/contents/src/scrapers/beyahad-bishvilha.ts --jq '.content' | base64 -d
```

**Step 2: Commit**

```bash
git add scraper/providers/credit_cards/beyahad_bishvilha.py
git commit -m "feat(scraper): port Beyahad Bishvilha credit card scraper"
```

---

### Task 28: Behatsdaa Scraper

Port `src/scrapers/behatsdaa.ts`. DOM scraping pattern.

**Files:**
- Create: `scraper/providers/credit_cards/behatsdaa.py`

**Step 1: Read upstream source and port**

```bash
gh api repos/eshaham/israeli-bank-scrapers/contents/src/scrapers/behatsdaa.ts --jq '.content' | base64 -d
```

**Step 2: Commit**

```bash
git add scraper/providers/credit_cards/behatsdaa.py
git commit -m "feat(scraper): port Behatsdaa credit card scraper"
```

---

### Task 29: Update Provider Package Inits

Update all `__init__.py` files to export the provider classes.

**Files:**
- Modify: `scraper/providers/banks/__init__.py`
- Modify: `scraper/providers/credit_cards/__init__.py`
- Modify: `scraper/providers/__init__.py`

**Step 1: Update bank providers init**

Export all bank scraper classes from `scraper/providers/banks/__init__.py`.

**Step 2: Update credit card providers init**

Export all credit card scraper classes from `scraper/providers/credit_cards/__init__.py`.

**Step 3: Commit**

```bash
git add scraper/providers/
git commit -m "feat(scraper): update provider package exports"
```

---

## Phase 3: Backend Integration

### Task 30: Backend Scraper Adapter

Create the adapter layer that bridges the new `scraper/` framework to the existing backend services. This replaces the current 1,492-line `backend/scraper/scrapers.py`.

**Files:**
- Create: `backend/scraper/adapter.py`
- Modify: `backend/scraper/__init__.py`

**Step 1: Create the adapter**

`ScraperAdapter` class:
- Constructor: `(service_name, provider_name, account_name, credentials, start_date, process_id)`
- `run()` — async method: creates scraper via `create_scraper()`, wires 2FA callback, runs `scraper.scrape()`, converts result to DataFrame, feeds through existing pipeline (save transactions, auto-tag, recalculate balances), records scraping history
- `_otp_callback()` — async method that waits on `asyncio.Event` for OTP code
- `set_otp_code(code)` — sets code and signals the event
- `_result_to_dataframe(result)` — converts `ScrapingResult` to DataFrame with columns matching current pipeline: `id, date, amount, description, provider, account_name, account_number, type, status, source`
- `_save_transactions(df)` — calls `TransactionsRepository.add_scraped_transactions()`
- `_apply_auto_tagging()` — calls `CategoriesTagsService.add_new_credit_card_tags()` + `TaggingRulesService.apply_rules()` + `auto_tag_credit_cards_bills()`
- `_recalculate_balances()` — calls `BankBalanceService.recalculate_for_account()` for bank scrapers only
- Demo mode: transparently redirects to `DummyRegularScraper`/`DummyCreditCardScraper`

`CANCEL = "cancel"` — sentinel for aborting 2FA

**Step 2: Update backend/scraper/__init__.py**

Export `ScraperAdapter` and `is_2fa_required` (which reads from `PROVIDER_CONFIGS`).

**Step 3: Commit**

```bash
git add backend/scraper/adapter.py backend/scraper/__init__.py
git commit -m "feat(scraper): add backend adapter bridging scraper framework to services"
```

---

### Task 31: Update ScrapingService for Asyncio

Modify `backend/services/scraping_service.py` to use asyncio instead of threading.

**Files:**
- Modify: `backend/services/scraping_service.py`

**Step 1: Update ScrapingService**

Key changes:
- Replace `from backend.scraper import Scraper, get_scraper, is_2fa_required` with `from backend.scraper import ScraperAdapter, is_2fa_required`
- Replace `_tfa_scrapers_waiting: Dict[str, Tuple[Scraper, Thread]]` with `_tfa_scrapers_waiting: Dict[str, ScraperAdapter]`
- `start_scraping_single()`:
  - Create `ScraperAdapter` instead of calling `get_scraper()`
  - Replace `Thread(target=scraper.pull_data_to_db); thread.start()` with `asyncio.create_task(adapter.run())`
  - If 2FA: store `adapter` in `_tfa_scrapers_waiting` (not a tuple with thread)
- `submit_2fa_code()`:
  - Get `adapter` from `_tfa_scrapers_waiting`
  - Call `adapter.set_otp_code(code)` directly
- `abort_scraping_process()`:
  - Get `adapter` from `_tfa_scrapers_waiting`
  - Call `adapter.set_otp_code(adapter.CANCEL)`

**Step 2: Commit**

```bash
git add backend/services/scraping_service.py
git commit -m "refactor(scraper): update ScrapingService to use asyncio adapter"
```

---

### Task 32: Update providers.py

Update `backend/constants/providers.py` to source provider metadata from the scraper framework's `PROVIDER_CONFIGS` instead of duplicating it.

**Files:**
- Modify: `backend/constants/providers.py`

**Step 1: Update LoginFields**

Replace the hardcoded `providers_fields` dict in `LoginFields` with a dynamic lookup from `PROVIDER_CONFIGS`:

```python
class LoginFields:
    @staticmethod
    def get_fields(provider: str) -> list[str]:
        from scraper.models.credentials import PROVIDER_CONFIGS
        config = PROVIDER_CONFIGS.get(provider)
        if config:
            return config.required_fields
        raise ValueError(f"Unknown provider: {provider}")
```

Keep the `Services`, `Banks`, `CreditCards`, `Fields` enums as-is (they're used throughout the backend).

**Step 2: Commit**

```bash
git add backend/constants/providers.py
git commit -m "refactor(scraper): source LoginFields from scraper framework PROVIDER_CONFIGS"
```

---

### Task 33: End-to-End Testing with Demo Mode

Verify the full pipeline works by running in demo mode.

**Step 1: Start both servers**

```bash
python .claude/scripts/with_server.py -- echo "Servers running"
```

**Step 2: Enable demo mode and test scraping**

Use the browser to navigate to the Data Sources page, enable demo mode, and trigger a scrape. Verify:
- Scraping starts and completes
- Transactions appear in the database
- Auto-tagging runs
- No errors in server logs

**Step 3: Test CLI**

```bash
python -m scraper --list
```

Verify all 18 providers are listed.

---

## Phase 4: Cleanup

### Task 34: Remove Node.js Scraper Code

Delete the old Node.js-based scraper code and npm dependency.

**Files:**
- Delete: `backend/scraper/node/` (entire directory)
- Delete: `backend/scraper/scrapers.py` (the old 1,492-line file)
- Delete: `backend/scraper/exceptions.py` (replaced by `scraper/exceptions.py`)

**Step 1: Remove old files**

```bash
rm -rf backend/scraper/node/
rm backend/scraper/scrapers.py
rm backend/scraper/exceptions.py
```

**Step 2: Verify no imports reference old code**

Search for any remaining references to the deleted files and update them.

```bash
grep -r "NODE_JS_SCRIPTS_DIR\|from backend.scraper.scrapers\|from backend.scraper.exceptions" backend/
```

**Step 3: Verify tests still pass**

```bash
poetry run pytest
```

**Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove Node.js scraper code (replaced by Python framework)"
```

---

### Task 35: Update Documentation

Update CLAUDE.md and any other docs to reflect the new architecture.

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Update CLAUDE.md**

Add scraper framework section:
- New `scraper/` package location and purpose
- CLI usage examples
- How to add new providers
- How to sync upstream fixes

Remove references to Node.js scraper scripts.

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for Python scraper framework"
```

---

## Execution Notes

### Provider Implementation Pattern

For each provider scraper (Tasks 16-28), follow this pattern:

1. **Read the upstream TypeScript source** using `gh api`
2. **Identify the pattern** (API-via-browser, DOM scraping, or pure API)
3. **Port the class** preserving:
   - Login URL and field selectors
   - API endpoint URLs and query parameters
   - Response parsing logic and field mappings
   - Transaction date formatting
   - Error handling
4. **Map Puppeteer calls to Playwright:**
   - `page.goto()` → `page.goto()`
   - `page.waitForSelector()` → `page.wait_for_selector()`
   - `page.type()` → `page.type()`
   - `page.$eval()` → `page.eval_on_selector()`
   - `page.$$eval()` → `page.eval_on_selector_all()`
   - `page.evaluate()` → `page.evaluate()`
   - `page.setRequestInterception()` → `page.route()`
   - `page.frames()` → `page.frames`
   - `frame.url()` → `frame.url`

### Live Testing Priority

1. **Hapoalim** (bank, API-via-browser) — test first
2. **Max** (credit card, API-via-browser) — test second
3. **Isracard** (credit card, shared base) — test third
4. **OneZero** (bank, API-only with 2FA) — test fourth (requires 2FA setup)

### Syncing Upstream Fixes (Future)

When a provider breaks and the upstream TypeScript repo has a fix:

1. `gh api repos/eshaham/israeli-bank-scrapers/contents/src/scrapers/<provider>.ts --jq '.content' | base64 -d > /tmp/<provider>.ts`
2. Diff the TypeScript changes against the Python port
3. Apply equivalent changes to the Python scraper
4. Test with live account if available
