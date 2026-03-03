# Python Scraper Framework — Design Document

**Date:** 2026-03-03
**Status:** Approved

## Overview

Rewrite the israeli-bank-scrapers Node.js package as a native Python scraper framework. The framework lives in `scraper/` at the repo root as a standalone package, using Playwright for browser automation and httpx for API-only scrapers. It mirrors the original repo's class hierarchy for easy upstream sync.

### Goals

1. Eliminate the Node.js subprocess dependency — single-language stack
2. Support all 18 existing bank/credit card providers
3. Extensible architecture for future brokerage, pension, and insurance scrapers
4. Standalone CLI for development/debugging
5. Match current data output exactly (expand later)

### Non-Goals (This Phase)

- New data fields (pakam, currencies, sub-accounts) — follow-up
- Brokerage/insurance/pension scrapers — follow-up
- Frontend changes — none needed
- Changes to transaction storage, auto-tagging, or balance recalculation pipelines

## Package Structure

```
scraper/                          # Top-level Python package
├── __init__.py                   # Public API: create_scraper(), ScraperType enum
├── __main__.py                   # CLI entry point: python -m scraper
├── base/
│   ├── __init__.py
│   ├── base_scraper.py           # BaseScraper — lifecycle, events, error handling
│   ├── browser_scraper.py        # BrowserScraper(BaseScraper) — Playwright management
│   └── api_scraper.py            # ApiScraper(BaseScraper) — pure HTTP (httpx), no browser
├── providers/
│   ├── __init__.py
│   ├── banks/
│   │   ├── __init__.py
│   │   ├── hapoalim.py
│   │   ├── leumi.py
│   │   ├── discount.py
│   │   ├── mercantile.py         # Extends discount
│   │   ├── mizrahi.py
│   │   ├── onezero.py            # Extends ApiScraper (no browser)
│   │   ├── yahav.py
│   │   ├── union.py
│   │   ├── beinleumi_group.py    # Shared base for beinleumi/otsar/massad/pagi
│   │   ├── beinleumi.py
│   │   ├── otsar_hahayal.py
│   │   ├── massad.py
│   │   └── pagi.py
│   ├── credit_cards/
│   │   ├── __init__.py
│   │   ├── isracard_amex_base.py  # Shared base for isracard/amex
│   │   ├── isracard.py
│   │   ├── amex.py
│   │   ├── max.py
│   │   ├── visa_cal.py
│   │   ├── beyahad_bishvilha.py
│   │   └── behatsdaa.py
│   └── test/                     # Demo/test scrapers
│       ├── __init__.py
│       ├── dummy_regular.py
│       ├── dummy_tfa.py
│       └── dummy_tfa_no_otp.py
├── models/
│   ├── __init__.py
│   ├── transaction.py            # Transaction, TransactionType, TransactionStatus
│   ├── account.py                # AccountResult (account number, txns, balance)
│   ├── result.py                 # ScrapingResult, LoginResult
│   └── credentials.py            # ProviderConfig, PROVIDER_CONFIGS registry
├── utils/
│   ├── __init__.py
│   ├── browser.py                # Playwright helpers (fill, click, wait, mask UA)
│   ├── fetch.py                  # In-page fetch (GET/POST via page.evaluate)
│   ├── navigation.py             # Wait for URL, redirect detection
│   ├── dates.py                  # Date range generation, parsing
│   └── transactions.py           # Dedup, sort, installment date fixing
└── exceptions.py                 # ErrorType enum, ScraperError hierarchy
```

## Class Hierarchy

```
BaseScraper (ABC)
├── ApiScraper (httpx, no browser)
│   └── OneZeroScraper
└── BrowserScraper (Playwright)
    ├── HapoalimScraper
    ├── LeumiScraper
    ├── DiscountScraper
    │   └── MercantileScraper
    ├── MizrahiScraper
    ├── MaxScraper
    ├── VisaCalScraper
    ├── YahavScraper
    ├── UnionBankScraper
    ├── BehatsdaaScraper
    ├── BeyahadBishvilhaScraper
    ├── BeinleumiGroupScraper
    │   ├── BeinleumiScraper
    │   ├── OtsarHahayalScraper
    │   ├── MassadScraper
    │   └── PagiScraper
    ├── IsracardAmexBaseScraper
    │   ├── IsracardScraper
    │   └── AmexScraper
    └── Test scrapers (DummyRegular, DummyTFA, DummyTFANoOTP)
```

## Core Interfaces

### BaseScraper

```python
class BaseScraper(ABC):
    def __init__(self, provider: str, credentials: dict, start_date: date,
                 options: ScraperOptions = None): ...

    async def scrape(self) -> ScrapingResult:
        """Main entry point: initialize → login → fetch → terminate."""

    @abstractmethod
    async def initialize(self) -> None: ...

    @abstractmethod
    async def login(self) -> LoginResult: ...

    @abstractmethod
    async def fetch_data(self) -> list[AccountResult]: ...

    async def terminate(self) -> None: ...

    # Callbacks
    on_progress: Callable[[str], None] | None
    on_otp_request: Callable[[], Awaitable[str]] | None
```

### BrowserScraper

```python
class BrowserScraper(BaseScraper):
    browser: Browser
    page: Page

    async def initialize(self) -> None:
        """Launch Playwright browser, create page, set viewport, mask UA."""

    async def login(self) -> LoginResult:
        """Generic login: navigate → fill fields → submit → detect result.
        Subclasses configure via class attributes."""

    async def terminate(self) -> None:
        """Screenshot on failure, close browser."""

    # Subclass configuration
    login_url: str
    login_fields: dict[str, str]       # CSS selector → credential key
    possible_login_results: dict[LoginResult, str | re.Pattern | Callable]

    # In-page HTTP helpers (API-via-browser pattern)
    async def fetch_get(self, url: str) -> dict: ...
    async def fetch_post(self, url: str, body: dict) -> dict: ...
```

### ApiScraper

```python
class ApiScraper(BaseScraper):
    client: httpx.AsyncClient

    async def initialize(self) -> None:
        """Create httpx client with default headers."""

    async def terminate(self) -> None:
        """Close httpx client."""
```

## Data Models

```python
@dataclass
class Transaction:
    type: TransactionType          # "normal" | "installments"
    status: TransactionStatus      # "completed" | "pending"
    date: str                      # YYYY-MM-DD
    processed_date: str | None
    original_amount: float
    original_currency: str         # "ILS", "USD", etc.
    charged_amount: float
    charged_currency: str | None
    description: str
    identifier: str | None
    memo: str | None
    category: str | None
    installments: InstallmentInfo | None

@dataclass
class InstallmentInfo:
    number: int
    total: int

@dataclass
class AccountResult:
    account_number: str
    transactions: list[Transaction]
    balance: float | None = None

@dataclass
class ScrapingResult:
    success: bool
    accounts: list[AccountResult]
    error_type: ErrorType | None = None
    error_message: str | None = None

class LoginResult(str, Enum):
    SUCCESS = "success"
    INVALID_PASSWORD = "invalid_password"
    CHANGE_PASSWORD = "change_password"
    ACCOUNT_BLOCKED = "account_blocked"
    UNKNOWN_ERROR = "unknown_error"

@dataclass
class ProviderConfig:
    provider: str
    service: str                   # "banks" | "credit_cards"
    required_fields: list[str]
    requires_2fa: bool = False
    login_url: str = ""
```

## Backend Integration

The backend connects to the scraper framework via a thin adapter layer.

### Adapter

```python
# backend/scraper/adapter.py
class ScraperAdapter:
    """Bridges scraper framework ↔ backend services."""

    async def run_scraper(self, service, provider, account,
                          credentials, start_date, process_id) -> None:
        scraper = create_scraper(provider, credentials, start_date)

        if scraper.requires_2fa:
            scraper.on_otp_request = self._create_otp_callback(process_id)

        result: ScrapingResult = await scraper.scrape()

        df = self._result_to_dataframe(result, provider, account)
        self._save_transactions(df, service)
        self._apply_auto_tagging()
        self._recalculate_balances(service, provider, account)

    def _result_to_dataframe(self, result, provider, account) -> pd.DataFrame:
        """Maps ScrapingResult → DataFrame with columns matching current pipeline:
        id, date, amount, description, provider, account_name,
        account_number, type, status, source."""
```

### What Changes in backend/

| File | Change |
|------|--------|
| `backend/scraper/scrapers.py` (1,492 lines) | Replaced by `adapter.py` (~100 lines) |
| `backend/scraper/node/` (entire directory) | Deleted |
| `backend/services/scraping_service.py` | `Thread` → `asyncio.create_task`, `threading.Event` → `asyncio.Event` |
| `backend/constants/providers.py` | `LoginFields` imports from `scraper.models.credentials.PROVIDER_CONFIGS` |

### What Stays the Same

- Credentials handling (CredentialsRepository + Keyring)
- Transaction storage (TransactionsRepository.add_scraped_transactions)
- Auto-tagging pipeline (TaggingRulesService)
- Bank balance recalculation (BankBalanceService)
- Scraping history (ScrapingHistoryRepository)
- Frontend (zero changes)

## CLI Interface

```bash
python -m scraper --list                              # List all providers
python -m scraper hapoalim --start-date 2024-01-01    # Scrape with date
python -m scraper max --days 30                       # Last 30 days
python -m scraper hapoalim --output json              # JSON to stdout
python -m scraper hapoalim --output csv               # CSV to stdout
python -m scraper onezero --headless false             # Visible browser
```

Credentials sourced from env vars (`SCRAPER_USERNAME`, `SCRAPER_PASSWORD`) or interactive prompt. No dependency on the backend's Keyring.

2FA via interactive `input("Enter OTP code: ")` prompt.

## Three Scraping Patterns

### Pattern A: API-via-browser (most common)
Log in through browser UI, then call the institution's internal JSON APIs using `fetch_get()`/`fetch_post()` which execute fetch() inside the page context to inherit session cookies. Used by Hapoalim, Discount, Max, Isracard/Amex, Visa Cal.

### Pattern B: DOM scraping
Navigate to transaction pages and extract data via Playwright selectors. Used by Leumi, Beinleumi group, Mizrahi, Yahav, Union Bank, Behatsdaa, Beyahad Bishvilha.

### Pattern C: Pure API (no browser)
REST/GraphQL directly via httpx. Used by OneZero. Future brokerage/insurance scrapers would likely use this pattern.

## Async Model

- Scraper framework is fully async (asyncio + Playwright async API)
- 2FA handled via `on_otp_request` async callback — no threading needed
- Backend integration: `asyncio.create_task()` replaces `Thread(target=...)`
- FastAPI routes are already async — natural fit

## Migration Phases

### Phase 1: Framework + Base Classes
Build `scraper/` package with BaseScraper, BrowserScraper, ApiScraper. Port all utils. Port data models, exceptions, CLI entry point. Test with dummy scrapers.

### Phase 2: Port All 18 Providers
Start with the 4 testable live (Hapoalim, OneZero, Isracard, Max). Port shared base classes (beinleumi_group, isracard_amex_base). Port remaining 14 providers from TypeScript source.

### Phase 3: Backend Integration
Write adapter.py. Update ScrapingService for asyncio. Update providers.py. Delete Node.js scraper code. End-to-end test with live accounts.

### Phase 4: Cleanup
Remove israeli-bank-scrapers npm dependency. Remove Node.js scripts. Update documentation.

## Testable Accounts

| Provider | Service | Account | Can Test Live |
|----------|---------|---------|---------------|
| Hapoalim | banks | Shir | Yes |
| OneZero | banks | Tomer, Shir & Tomer | Yes |
| Isracard | credit_cards | Tomer, Shir & Tomer | Yes |
| Max | credit_cards | Tomer | Yes |
| All others (14) | — | — | No (structural port only) |

## Dependencies

| Purpose | Package |
|---------|---------|
| Browser automation | playwright |
| HTTP client (API scrapers) | httpx |
| Date handling | datetime + python-dateutil (already in project) |
| CLI | argparse (stdlib) |

## Future Extensibility

When adding brokerage/insurance/pension scrapers:
- New result types (e.g., `HoldingResult`, `PolicyResult`) alongside `Transaction`
- New provider directories under `scraper/providers/` (e.g., `brokerages/`, `insurance/`)
- Most would extend `ApiScraper` (financial data APIs, not bank website scraping)
- `ScrapingResult` wrapper stays the same — just contains different account types
- Backend adapter handles new result types with additional mapping methods
