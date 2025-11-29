---
applyTo:
  - fad/scraper/**
---

# Scraper Module - Web Scraping for Israeli Financial Providers

## Purpose
Automates data collection from Israeli banks, credit cards, and insurance companies using Playwright-based Node.js scrapers wrapped in Python. Handles authentication, 2FA (Two-Factor Authentication), error handling, and data persistence.

## Architecture Overview

### Hybrid Python/Node.js Design
- **Python Layer (`scrapers.py`)**: Orchestration, database operations, error handling, 2FA coordination
- **Node.js Layer (`node/`)**: Actual web scraping using `israeli-bank-scrapers` npm package
- **Communication**: Python calls Node.js scripts via subprocess, receives structured text output

### Data Flow
```
User initiates scraping
    ↓
Python Scraper class
    ↓
subprocess.run() → Node.js script (Playwright)
    ↓
Israeli bank/card website (login, navigate, scrape)
    ↓
Node.js outputs structured text to stdout
    ↓
Python parses text → pandas DataFrame
    ↓
TransactionsRepository saves to SQLite
    ↓
ScrapingHistoryRepository logs attempt (success/fail/canceled)
```

## Core Components

### 1. `scrapers.py` - Main Scraper Classes

#### Base Class: `Scraper` (Abstract)
**Responsibilities:**
- Define scraper interface (abstract methods)
- Handle subprocess execution of Node.js scripts
- Parse scraped data into DataFrames
- Coordinate 2FA flow (OTP input)
- Record scraping history
- Save transactions to database

**Key Abstract Methods (must implement in subclasses):**
- `service_name` - 'credit_cards', 'banks', or 'insurance'
- `provider_name` - e.g., 'isracard', 'hapoalim', 'max'
- `script_path` - Path to Node.js script for this provider
- `table_name` - Database table name (Tables enum)
- `table_unique_key` - Column name for deduplication
- `sort_by_columns` - Columns to sort results
- `scrape_data(start_date)` - Provider-specific scraping logic

#### Concrete Scraper Classes
Each provider has a dedicated class inheriting from `Scraper`:
- **Credit Cards:** `IsracardScraper`, `MaxScraper`, `VisaCalScraper`, `AmexScraper`, etc.
- **Banks:** `HapoalimScraper`, `LeumiScraper`, `DiscountScraper`, `OneZeroScraper`, etc.
- **Test Scrapers:** `DummyTFAScraper`, `DummyTFAScraperNoOTP` (for testing 2FA flows)

**Factory Function:**
```python
scraper = get_scraper(service_name, provider_name, account_name, credentials)
```

### 2. `exceptions.py` - Error Hierarchy

Custom exception hierarchy for standardized error handling across Python and Node.js:

**Error Types (ErrorType enum):**
- `GENERAL` - Generic scraper error
- `CREDENTIALS` - Invalid username/password
- `CONNECTION` - Network issues
- `TIMEOUT` - Operation took too long
- `DATA` - Parsing/processing errors
- `LOGIN` - Authentication failed
- `PASSWORD_CHANGE` - Password reset required
- `ACCOUNT` - Account blocked/suspended
- `SERVICE` - Provider site unavailable
- `RATE_LIMIT` - Too many requests
- `SECURITY` - CAPTCHA, additional verification

**Exception Classes:**
- `ScraperError` (base)
  - `LoginError`
    - `CredentialsError`
    - `PasswordChangeError`
  - `ConnectionError`
  - `TimeoutError`
  - `DataError`
  - `AccountError`
  - `ServiceError`
  - `RateLimitError`
  - `SecurityError`

**Usage:**
```python
try:
    self.scrape_data(start_date)
except CredentialsError as e:
    # Handle invalid credentials
    print(f'Credentials error: {e.message}')
    print(f'Original error: {e.original_error}')
```

### 3. `node/` - Node.js Scripts

**Structure:**
```
node/
├── base_scraper.js          # Base class for all scrapers
├── credit_cards/            # Credit card provider scripts
│   ├── isracard.js
│   ├── max.js
│   └── ...
├── banks/                   # Bank provider scripts
│   ├── hapoalim.js
│   ├── leumi.js
│   └── ...
├── dummy_tfa.js             # Test scraper with 2FA
├── dummy_tfa_no_otp.js      # Test scraper without OTP
└── package.json             # npm dependencies
```

**Dependencies:**
- `israeli-bank-scrapers` - Playwright-based scrapers for Israeli financial providers (primary and currently only package used)

## Two-Factor Authentication (2FA) Flow

### How It Works
1. User initiates scraping via UI
2. Scraping runs in **separate thread** (non-blocking to main app)
3. Scraper detects provider requires 2FA (`requires_2fa = True`)
4. Node.js script triggers 2FA (sends SMS/email to user)
5. Python scraper waits on `otp_event` (threading.Event)
6. UI prompts user for OTP code
7. User enters code → calls `scraper.set_otp_code(code)`
8. `otp_event.set()` wakes up the waiting scraper thread
9. OTP code sent to Node.js script via **stdin**
10. Scraping continues and completes

### Cancellation
- User enters "cancel" as OTP code (or presses cancel button)
- `scraper.otp_code == scraper.CANCEL`
- Scraping terminates gracefully
- History logged as `CANCELED` status

### 2FA Scrapers
Only some providers require 2FA. Check `requires_2fa` class attribute:
```python
class OneZeroScraper(Scraper):
    requires_2fa = True
```

## Scraping History Tracking

### Purpose
Track scraping attempts to prevent excessive requests and provide audit trail.

### Storage
`scraping_history` table via `ScrapingHistoryRepository`

### Fields Recorded
- `service_name` - 'banks', 'credit_cards', 'insurance'
- `provider_name` - e.g., 'hapoalim', 'max'
- `account_name` - User-defined account name
- `date` - Timestamp of attempt
- `status` - 'SUCCESS', 'FAILED', 'CANCELED'
- `start_date` - Date range requested

### Daily Limits
UI checks scraping history to **enforce** daily limits - prevents scraping same account more than once per day to respect provider rate limits and avoid account blocks.

## Error Handling Best Practices

### In Python Code
1. Always catch specific exceptions before generic ones
2. Log original error details for debugging
3. Set `self.error` message for UI display
4. Record scraping attempt in history (even on failure)
5. Return gracefully - don't crash the app

**Example:**
```python
try:
    self.scrape_data(start_date)
except CredentialsError as e:
    self.error = f"Invalid credentials for {self.provider_name}"
    print(f'DEBUG: {e.original_error}', flush=True)
    return
except TimeoutError as e:
    self.error = f"Scraping timed out after {timeout} seconds"
    return
finally:
    self._record_scraping_history(start_date)
```

### In Node.js Scripts
- Output errors to **stderr** in structured format
- Python reads stderr and **maps Node.js error types to Python exception classes** via error mapping logic
- Include error type identifier in stderr for proper exception mapping
- See `_handle_error()` method in `Scraper` base class for mapping implementation

## Adding a New Provider

### Step 1: Add Provider to Enums
Update `naming_conventions.py`:
```python
class CreditCards(Enum):
    NEW_CARD = 'new_card'

class LoginFields:
    providers_fields = {
        'new_card': ['username', 'password'],
    }
```

### Step 2: Check Node.js Support
Verify `israeli-bank-scrapers` npm package supports this provider. If not, implement custom Node.js script.

### Step 3: Create Python Scraper Class
```python
class NewCardScraper(Scraper):
    requires_2fa = False
    
    @property
    def service_name(self):
        return 'credit_cards'
    
    @property
    def provider_name(self):
        return 'new_card'
    
    @property
    def script_path(self):
        return os.path.join(NODE_JS_SCRIPTS_DIR, 'credit_cards', 'new_card.js')
    
    @property
    def table_name(self):
        return Tables.CREDIT_CARD.value
    
    @property
    def table_unique_key(self):
        return CreditCardTableFields.UNIQUE_ID.value
    
    @property
    def sort_by_columns(self):
        return [CreditCardTableFields.DATE.value]
    
    def scrape_data(self, start_date: str):
        # Note: Password retrieval is handled by the service layer, not scraper
        # Scraper receives credentials dict with all needed fields
        username = self.credentials['username']
        password = self.credentials['password']  # Already retrieved from keyring by service
        return self._scrape_data(start_date, username, password)
```

### Step 4: Add to Factory Function
Update `get_scraper()` in `scrapers.py`:
```python
if service_name == 'credit_cards':
    if provider_name == 'new_card':
        return NewCardScraper(account_name, credentials)
```

### Step 5: Create/Verify Node.js Script
Ensure `node/credit_cards/new_card.js` exists and follows output format.

### Step 6: Add to Service Layer
Update `DataScrapingService` to handle password retrieval from Windows Keyring for the new provider.

### Step 7: Test
1. Add test credentials to `test_credentials.yaml`
2. Create integration test marked with `@pytest.mark.sensitive`
3. Test manually via UI

## Common Patterns

### Scraping with Credentials
```python
def scrape_data(self, start_date: str):
    # Credentials dict already contains password (retrieved by service layer)
    username = self.credentials['username']
    password = self.credentials['password']
    return self._scrape_data(start_date, username, password)
```

### Handling Empty Results
```python
if self.data.empty:
    if self.otp_code == self.CANCEL:
        print('Scraping canceled by user')
    else:
        print('No transactions found')
    return
```

### Data Transformation After Scraping
```python
self.data = self.data.sort_values(by=self.sort_by_columns)
self.data = self._add_account_name_and_provider_columns(self.data)
self.data = self._add_missing_columns(self.data)
```

## Security Considerations

### Password Storage
- **Never** store passwords in YAML files or code
- Passwords stored in Windows Keyring (handled by service layer, not scraper)
- Scraper receives credentials dict with password already retrieved
- Passwords passed to Node.js scripts via subprocess stdin (ephemeral)

### Credentials in Logs
- Never log passwords or full credentials
- Redact sensitive info in error messages
- Use `flush=True` for real-time debugging output

### 2FA Codes
- OTP codes are ephemeral (only in memory)
- Never persist OTP codes to disk
- Clear OTP code after use

## Testing

### Unit Tests
- Mock subprocess calls to avoid hitting real providers
- Test error handling for all exception types
- Test data parsing with various output formats

### Integration Tests (`@pytest.mark.sensitive`)
- Use `test_credentials.yaml` with real (test) accounts
- Verify full scraping flow end-to-end
- Test 2FA flow with dummy scrapers
- Check database persistence

### Dummy Scrapers for Testing
- `DummyTFAScraper` - Simulates 2FA flow with OTP
- `DummyTFAScraperNoOTP` - Simulates provider without 2FA
- Useful for UI development without real accounts

## Performance Considerations

### Timeout Handling
- **Fixed timeout: 300 seconds (5 minutes)** for all providers
- Always catch `subprocess.TimeoutExpired` exception
- Timeout errors recorded in scraping history as FAILED

### Rate Limiting
- **Daily limits enforced** via scraping history checks (one scrape per account per day)
- No automatic retry or exponential backoff currently implemented
- Manual retry via UI if scraping fails

## Troubleshooting

### Common Issues

**"Timeout: scraping took too long"**
- Provider site may be slow or unresponsive
- Increase timeout or retry later
- Check internet connection

**"Invalid credentials"**
- Verify username in YAML matches provider requirements
- Check Windows Keyring has correct password (via service layer debugging)
- Ensure password hasn't expired or been changed
- Note: Scraper receives password from service - credential issues likely in service/keyring layer

**"No transactions found"**
- Verify `start_date` is correct
- Provider may have no transactions in that period
- Check if account is active

**Node.js script errors**
- Ensure `npm install` ran successfully
- Check Node.js version compatibility
- Review stderr output for details

## Notes
- All Israeli providers use Hebrew websites - scraping logic accounts for RTL text
- Date formats vary by provider - always normalize to 'YYYY-MM-DD'
- Transaction amounts: Negative = expense, Positive = income/refund
- **Scraping runs in separate threads** to keep UI responsive during long operations
- **Daily scraping limits are enforced** via history checks - prevents account blocks
- **Password management is service layer responsibility** - scrapers receive credentials dict
- **Insurance scrapers planned** for future (pension, keren hishtalmut data)
- Error mapping from Node.js stderr to Python exceptions happens in `_handle_error()` method
