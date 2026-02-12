---
globs: backend/scraper/**/*.py, backend/services/scraping_service.py
---

# Scraper Module - Web Scraping for Israeli Financial Providers

Automates data collection from Israeli banks/credit cards using Playwright-based Node.js scrapers wrapped in Python.

## Architecture

```
User -> Python Scraper class -> subprocess -> Node.js (Playwright) -> Bank website
                                              |
Python parses stdout -> DataFrame -> TransactionsRepository -> SQLite
```

- **Python Layer (`scrapers.py`)**: Orchestration, DB ops, error handling, 2FA coordination
- **Node.js Layer (`node/`)**: Actual scraping via `israeli-bank-scrapers` npm package

## Core Components

### Scraper Base Class
Abstract class defining the interface. Key abstract properties:
- `service_name` - 'credit_cards', 'banks', or 'insurance'
- `provider_name` - e.g., 'isracard', 'hapoalim'
- `script_path` - Path to Node.js script
- `table_name` - Target database table
- `requires_2fa` - Whether provider needs OTP

### Concrete Scrapers
- **Credit Cards:** `IsracardScraper`, `MaxScraper`, `VisaCalScraper`, `AmexScraper`
- **Banks:** `HapoalimScraper`, `LeumiScraper`, `DiscountScraper`, `OneZeroScraper`
- **Test:** `DummyTFAScraper`, `DummyTFAScraperNoOTP`

### Error Hierarchy (`exceptions.py`)

| Error Type | When |
|------------|------|
| `CredentialsError` | Invalid username/password |
| `ConnectionError` | Network issues |
| `TimeoutError` | Operation took too long |
| `PasswordChangeError` | Password reset required |
| `AccountError` | Account blocked/suspended |
| `RateLimitError` | Too many requests |

## Two-Factor Authentication (2FA) Flow

1. Scraping runs in **separate thread** (non-blocking)
2. Node.js triggers 2FA (SMS/email sent to user)
3. Python scraper waits on `otp_event` (threading.Event)
4. UI prompts user -> user calls `scraper.set_otp_code(code)`
5. OTP sent to Node.js via stdin -> scraping continues

**Cancellation:** User enters "cancel" -> `scraper.otp_code == scraper.CANCEL` -> logged as `CANCELED`

## Scraping History

Tracked in `scraping_history` table for audit and rate limiting:
- **Daily limits enforced** - one scrape per account per day
- **Status values:** `SUCCESS`, `FAILED`, `CANCELED`

## Adding a New Provider

1. **Add to enums** in `backend/constants/providers.py` (CreditCards/Banks enum, LoginFields)
2. **Check Node.js support** - verify `israeli-bank-scrapers` supports provider
3. **Create scraper class:**
```python
class NewCardScraper(Scraper):
    requires_2fa = False

    @property
    def service_name(self): return 'credit_cards'

    @property
    def provider_name(self): return 'new_card'

    @property
    def script_path(self): return os.path.join(NODE_JS_SCRIPTS_DIR, 'credit_cards', 'new_card.js')
```
4. **Add to factory** in `get_scraper()`
5. **Create/verify Node.js script** in `node/credit_cards/`

## Security

| Safe | Never |
|---------|----------|
| Passwords from Keyring (service layer) | Passwords in YAML/code |
| Credentials via subprocess stdin | Log credentials |
| OTP codes ephemeral (memory only) | Persist OTP codes |

**Note:** Scraper receives credentials dict with password already retrieved by service layer.

## Timeouts & Limits

- **Fixed timeout:** 300 seconds (5 minutes) for all providers
- **Daily limit:** One scrape per account per day
- **No automatic retry** - manual retry via UI

## Notes

- All Israeli providers use Hebrew websites (RTL text handled)
- Date format normalized to 'YYYY-MM-DD'
- Transaction amounts: Negative = expense, Positive = income
- Error mapping from Node.js stderr -> Python exceptions in `_handle_error()`
