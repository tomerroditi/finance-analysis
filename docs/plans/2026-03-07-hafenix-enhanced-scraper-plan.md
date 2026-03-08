# HaPhoenix Enhanced Scraper Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enhance the HaPhoenix scraper to extract rich per-account data (investment tracks, commissions, deposits, insurance costs, liquidity dates) from all pension and keren hishtalmut accounts.

**Architecture:** The scraper navigates account-by-account through the Angular SPA at my.fnx.co.il, reading cached API data from sessionStorage. Deposit history becomes Transaction objects stored in `insurance_transactions`. Account metadata (tracks, commissions, covers) goes into a new `insurance_accounts` table via an extended `AccountResult`.

**Tech Stack:** Python 3.12, Playwright (async), SQLAlchemy ORM, SQLite

**Design doc:** `docs/plans/2026-03-07-hafenix-enhanced-scraper-design.md`

---

### Task 1: Add `metadata` field to `AccountResult`

Extend the scraper's `AccountResult` dataclass to carry optional metadata that provider scrapers can populate.

**Files:**
- Modify: `scraper/models/account.py`

**Step 1: Add the metadata field**

In `scraper/models/account.py`, add an optional `metadata` field to `AccountResult`:

```python
@dataclass
class AccountResult:
    """Scraped data for a single account."""
    account_number: str
    transactions: list[Transaction] = field(default_factory=list)
    balance: Optional[float] = None
    metadata: Optional[dict] = None
```

**Step 2: Verify no tests break**

Run: `poetry run pytest tests/ -x -q`
Expected: All existing tests pass (metadata defaults to None, no impact on existing scrapers).

**Step 3: Commit**

```bash
git add scraper/models/account.py
git commit -m "feat(scraper): add optional metadata field to AccountResult"
```

---

### Task 2: Create `InsuranceAccount` ORM model

Add the new `insurance_accounts` table for storing per-policy metadata.

**Files:**
- Create: `backend/models/insurance_account.py`
- Modify: `backend/models/__init__.py` (add import + export)
- Modify: `backend/constants/tables.py` (add `INSURANCE_ACCOUNTS` enum value)

**Step 1: Add table constant**

In `backend/constants/tables.py`, add to the `Tables` enum (after the `INSURANCE` line):

```python
INSURANCE_ACCOUNTS = "insurance_accounts"
```

**Step 2: Create the ORM model**

Create `backend/models/insurance_account.py`:

```python
"""Insurance account metadata model."""

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, func

from backend.constants.tables import Tables
from backend.models.base import Base, TimestampMixin


class InsuranceAccount(Base, TimestampMixin):
    """ORM model for insurance account metadata (``insurance_accounts`` table).

    Stores per-policy metadata scraped from insurance providers: investment
    tracks, commission rates, insurance covers, and liquidity dates.
    One row per policy, upserted on each scrape.

    Attributes
    ----------
    provider : str
        Insurance provider identifier (e.g. ``hafenix``).
    policy_id : str
        Unique policy ID from the provider.
    policy_type : str
        Account type: ``pension`` or ``hishtalmut``.
    pension_type : str, optional
        Pension sub-type: ``makifa`` or ``mashlima`` (pension only).
    account_name : str
        Human-readable policy/product name.
    balance : float, optional
        Current account balance.
    balance_date : str, optional
        Date of the balance value (YYYY-MM-DD).
    investment_tracks : str, optional
        JSON string: ``[{name, yield_pct, allocation_pct, sum}]``.
    commission_deposits_pct : float, optional
        Commission rate on deposits (percentage).
    commission_savings_pct : float, optional
        Commission rate on savings/profits (percentage).
    insurance_covers : str, optional
        JSON string: ``[{title, desc, sum}]`` (pension only).
    liquidity_date : str, optional
        Earliest withdrawal date (hishtalmut only, YYYY-MM-DD).
    """

    __tablename__ = Tables.INSURANCE_ACCOUNTS.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String, nullable=False)
    policy_id = Column(String, nullable=False, unique=True)
    policy_type = Column(String, nullable=False)
    pension_type = Column(String, nullable=True)
    account_name = Column(String, nullable=False)
    balance = Column(Float, nullable=True)
    balance_date = Column(String, nullable=True)
    investment_tracks = Column(Text, nullable=True)
    commission_deposits_pct = Column(Float, nullable=True)
    commission_savings_pct = Column(Float, nullable=True)
    insurance_covers = Column(Text, nullable=True)
    liquidity_date = Column(String, nullable=True)
```

**Step 3: Register in `backend/models/__init__.py`**

Add import:
```python
from backend.models.insurance_account import InsuranceAccount
```

Add to `__all__`:
```python
"InsuranceAccount",
```

**Step 4: Verify no tests break**

Run: `poetry run pytest tests/ -x -q`
Expected: All tests pass.

**Step 5: Commit**

```bash
git add backend/constants/tables.py backend/models/insurance_account.py backend/models/__init__.py
git commit -m "feat(models): add InsuranceAccount ORM model for insurance metadata"
```

---

### Task 3: Add insurance account upsert to backend adapter

Extend `ScraperAdapter` to persist `AccountResult.metadata` into the `insurance_accounts` table when present.

**Files:**
- Modify: `backend/scraper/adapter.py`

**Step 1: Add the upsert method**

In `backend/scraper/adapter.py`, add these imports at the top:

```python
import json
```

Add a new method to `ScraperAdapter` (after `_recalculate_bank_balances`):

```python
def _save_insurance_metadata(self, result) -> None:
    """Persist insurance account metadata from AccountResult.metadata fields."""
    from backend.models.insurance_account import InsuranceAccount

    accounts_to_upsert = []
    for account in result.accounts:
        if account.metadata:
            accounts_to_upsert.append(account.metadata)

    if not accounts_to_upsert:
        return

    with get_db_context() as db:
        for meta in accounts_to_upsert:
            existing = db.query(InsuranceAccount).filter_by(
                policy_id=meta["policy_id"]
            ).first()

            if existing:
                for key, value in meta.items():
                    if key != "policy_id":
                        setattr(existing, key, value)
            else:
                db.add(InsuranceAccount(**meta))

        db.commit()
        logger.info(
            "%s: %s: Saved metadata for %d insurance accounts",
            self.provider_name, self.account_name, len(accounts_to_upsert),
        )
```

**Step 2: Call the upsert in the `run()` method**

In the `run()` method, after the `self._recalculate_bank_balances()` call (line ~138), add:

```python
if self.service_name == "insurances":
    self._save_insurance_metadata(result)
```

**Step 3: Revert `show_browser=True` back to `False`**

In `_create_scraper()` (line ~192), change:
```python
show_browser=True,
```
to:
```python
show_browser=False,
```

**Step 4: Verify no tests break**

Run: `poetry run pytest tests/ -x -q`
Expected: All tests pass.

**Step 5: Commit**

```bash
git add backend/scraper/adapter.py
git commit -m "feat(adapter): save insurance account metadata and revert show_browser"
```

---

### Task 4: Rewrite HaPhoenix `fetch_data()` — account discovery

Replace the current basic `fetch_data()` with the account discovery phase that navigates to the savings page and extracts the account list.

**Files:**
- Modify: `scraper/providers/insurances/hafenix.py`

**Step 1: Update constants and JS snippets**

Replace the existing `SAVINGS_URL`, `_EXTRACT_SAVINGS_JS`, `_EXTRACT_DEPOSITS_JS` constants and add new ones. Keep `LOGIN_URL` and all login selectors unchanged. Replace from line 18 onwards (after `LOGIN_URL`):

```python
SAVINGS_URL = "https://my.fnx.co.il/savings"
POLICIES_URL = "https://my.fnx.co.il/policies"

# JS: Extract savings account list from sessionStorage
_EXTRACT_ACCOUNT_LIST_JS = """
() => {
    const appState = JSON.parse(sessionStorage.getItem('appState') || '{}');
    const savingList = appState.share?.resSavings?.savingList;
    if (!savingList) return null;
    return savingList.map(s => ({
        policyId: s.policyId || '',
        policyType: s.policyType || '',
        pensionType: s.pensionType || '',
        balance: s.sum?.value || 0,
        productDescription: s.productDescription || '',
        balanceDate: s.tarNehunut || '',
    }));
}
"""

# JS: Extract pension detail from sessionStorage
_EXTRACT_PENSION_DETAIL_JS = """
() => {
    const appState = JSON.parse(sessionStorage.getItem('appState') || '{}');
    const policy = appState.pensionPolicies?.pensionPolicy;
    if (!policy) return null;
    return {
        general: policy.general || {},
        investmentRoutes: policy.investmentRoutes?.routes || [],
        managementFee: policy.managementFee?.updatedMngFee || {},
        depositsYear: policy.depositsYear || {},
        covers: policy.covers?.list || [],
        accountTransactions: policy.accountTransactions?.list || [],
    };
}
"""

# JS: Extract hishtalmut detail from sessionStorage
_EXTRACT_HISHTALMUT_DETAIL_JS = """
() => {
    const appState = JSON.parse(sessionStorage.getItem('appState') || '{}');
    const policy = appState.gemelPolicies?.hishtalmut;
    if (!policy) return null;
    return {
        general: policy.general || {},
        investmentRoutes: policy.investmentRoutesTransferConcentration?.investmentRoutes?.list || [],
        managementFee: policy.managementFee?.updatedMngFee || {},
        deposits: policy.deposits?.yearlyDeposits || {},
        expectedPayments: policy.expectedPaymentsExcellence?.list || [],
    };
}
"""
```

**Step 2: Rewrite `fetch_data()` — discovery only**

Replace the existing `fetch_data()` method (keep `_build_transactions` and `_parse_date` for now, they'll be replaced in Task 5):

```python
async def fetch_data(self) -> list[AccountResult]:
    """Fetch pension/keren hishtalmut data from HaPhoenix.

    Discovers all accounts from the savings page, then navigates to each
    account's detail page to extract rich data (investment tracks,
    commissions, deposits, covers).

    Returns
    -------
    list[AccountResult]
        One AccountResult per policy with transactions and metadata.
    """
    # Step 1: Navigate to savings page to discover accounts
    self._emit_progress("discovering accounts")
    await self.navigate_to(SAVINGS_URL, wait_until="domcontentloaded")
    await self.page.wait_for_function(
        """
        () => {
            const state = JSON.parse(sessionStorage.getItem('appState') || '{}');
            return state.share?.resSavings?.savingList?.length > 0;
        }
        """,
        timeout=30000,
    )

    account_list = await self.page.evaluate(_EXTRACT_ACCOUNT_LIST_JS)
    if not account_list:
        logger.warning("No accounts found in savingList")
        return []

    logger.info("Discovered %d accounts", len(account_list))

    # Step 2: Scrape each account's detail page
    results: list[AccountResult] = []
    for account_info in account_list:
        try:
            result = await self._scrape_account_detail(account_info)
            if result:
                results.append(result)
        except Exception as e:
            logger.error(
                "Failed to scrape account %s: %s",
                account_info.get("policyId", "unknown"), e,
            )

    return results
```

**Step 3: Add the `_scrape_account_detail` dispatcher**

Add this method to the class (after `fetch_data`):

```python
async def _scrape_account_detail(
    self, account_info: dict
) -> AccountResult | None:
    """Navigate to an account's detail page and extract data.

    Parameters
    ----------
    account_info : dict
        Account summary from savingList with policyId, policyType, etc.

    Returns
    -------
    AccountResult or None
        Account data with transactions and metadata, or None on failure.
    """
    policy_id = account_info["policyId"]
    policy_type = account_info["policyType"].lower()
    pension_type = account_info.get("pensionType", "").lower()

    if "pension" in policy_type or "פנסי" in policy_type:
        return await self._scrape_pension(account_info)
    elif "hishtalmut" in policy_type or "השתלמות" in policy_type:
        return await self._scrape_hishtalmut(account_info)
    else:
        logger.warning(
            "Unknown policy type '%s' for %s, skipping",
            policy_type, policy_id,
        )
        return None
```

**Step 4: Verify the file parses correctly**

Run: `python -c "from scraper.providers.insurances.hafenix import HaPhoenixScraper; print('OK')"`
Expected: OK (the scrape methods don't exist yet, but the import should work since they're defined as methods in Task 5).

Note: This step may fail until Task 5 adds the `_scrape_pension` and `_scrape_hishtalmut` methods. That's fine — proceed to Task 5.

**Step 5: Commit (after Task 5 is complete)**

Do NOT commit yet — the file won't be importable until Task 5 adds the missing methods. Commit both tasks together.

---

### Task 5: Implement pension detail scraping

Add the `_scrape_pension` method that navigates to a pension account's detail page and extracts all data.

**Files:**
- Modify: `scraper/providers/insurances/hafenix.py`

**Step 1: Add imports**

At the top of the file, add `json` import (after `logging`):

```python
import json
```

**Step 2: Implement `_scrape_pension`**

Add this method to `HaPhoenixScraper` (after `_scrape_account_detail`):

```python
async def _scrape_pension(self, account_info: dict) -> AccountResult:
    """Scrape a pension account's detail page.

    Parameters
    ----------
    account_info : dict
        Account summary from savingList.

    Returns
    -------
    AccountResult
        Pension account data with deposit transactions and metadata.
    """
    policy_id = account_info["policyId"]
    pension_type = account_info.get("pensionType", "makifa").lower()
    balance = float(account_info.get("balance", 0))
    balance_date = _parse_date(account_info.get("balanceDate", ""))

    self._emit_progress(f"scraping pension {policy_id}")

    # Navigate to pension detail page
    url = f"https://my.fnx.co.il/policies/pension/{policy_id}/{pension_type}/info"
    await self.navigate_to(url, wait_until="domcontentloaded")
    await self._human_delay(1.0, 2.0)

    # Wait for pension data to populate in sessionStorage
    await self.page.wait_for_function(
        """
        () => {
            const state = JSON.parse(sessionStorage.getItem('appState') || '{}');
            return !!state.pensionPolicies?.pensionPolicy?.general;
        }
        """,
        timeout=30000,
    )
    await self._human_delay(1.0, 2.0)

    detail = await self.page.evaluate(_EXTRACT_PENSION_DETAIL_JS)
    if not detail:
        logger.warning("No pension detail for %s", policy_id)
        return AccountResult(account_number=policy_id, balance=balance)

    # Extract investment tracks
    tracks = []
    routes = detail.get("investmentRoutes", [])
    for route in routes:
        tracks.append({
            "name": route.get("investmentRouteTitle", ""),
            "yield_pct": route.get("yieldPercentage", 0),
            # Single track = 100%. Multi-track: TODO improve when we have a reference
            "allocation_pct": 100.0 if len(routes) == 1 else None,
            "sum": None,
        })

    # Extract commissions
    fee = detail.get("managementFee", {})
    commission_deposits = fee.get("fromDeposit", {}).get("percentageData", {}).get("value")
    commission_savings = fee.get("fromSaving", {}).get("percentageData", {}).get("value")

    # Extract insurance covers
    covers = []
    for cover in detail.get("covers", []):
        covers.append({
            "title": cover.get("coverTitle", ""),
            "desc": cover.get("coverDesc", ""),
            "sum": cover.get("coverSum", 0),
        })

    # Build deposit transactions
    transactions = self._build_pension_deposits(policy_id, detail)

    # Build insurance cost transactions
    transactions.extend(self._build_insurance_costs(policy_id, detail))

    account_name = detail.get("general", {}).get("policyName", f"Pension {policy_id}")

    logger.info(
        "Pension %s: %s (balance: ₪%s, %d tracks, %d deposits, %d covers)",
        policy_id, account_name, balance, len(tracks),
        len(transactions), len(covers),
    )

    return AccountResult(
        account_number=policy_id,
        transactions=transactions,
        balance=balance,
        metadata={
            "provider": "hafenix",
            "policy_id": policy_id,
            "policy_type": "pension",
            "pension_type": pension_type,
            "account_name": account_name,
            "balance": balance,
            "balance_date": balance_date,
            "investment_tracks": json.dumps(tracks, ensure_ascii=False),
            "commission_deposits_pct": commission_deposits,
            "commission_savings_pct": commission_savings,
            "insurance_covers": json.dumps(covers, ensure_ascii=False),
            "liquidity_date": None,
        },
    )
```

**Step 3: Implement `_build_pension_deposits`**

Add after `_scrape_pension`:

```python
def _build_pension_deposits(
    self, policy_id: str, detail: dict
) -> list[Transaction]:
    """Build Transaction objects from pension deposit records.

    Parameters
    ----------
    policy_id : str
        The policy ID.
    detail : dict
        Pension detail data from sessionStorage.

    Returns
    -------
    list[Transaction]
        Deposit transactions across all available years.
    """
    transactions: list[Transaction] = []
    deposits_year = detail.get("depositsYear", {})

    for year_data in deposits_year.get("list", []):
        for deposit in year_data.get("list", []):
            date_raw = deposit.get("depositDate", "")
            date_str = _parse_date(date_raw)
            total = float(deposit.get("totalDeposit", 0))
            employer_name = deposit.get("employerName", "")
            employee = float(deposit.get("employeeDeposit", 0))
            employer = float(deposit.get("employerDeposit", 0))
            compensation = float(deposit.get("compensationDeposit", 0))

            description = f"הפקדה - {employer_name}" if employer_name else "הפקדה"
            memo_parts = []
            if employee:
                memo_parts.append(f"עובד: {employee:.0f}")
            if employer:
                memo_parts.append(f"מעסיק: {employer:.0f}")
            if compensation:
                memo_parts.append(f"פיצויים: {compensation:.0f}")
            memo = " / ".join(memo_parts) if memo_parts else None

            transactions.append(
                Transaction(
                    type=TransactionType.NORMAL,
                    status=TransactionStatus.COMPLETED,
                    date=date_str,
                    processed_date=date_str,
                    original_amount=total,
                    original_currency="ILS",
                    charged_amount=total,
                    charged_currency="ILS",
                    description=description,
                    identifier=f"{policy_id}_{date_str}_{total}",
                    memo=memo,
                )
            )

    return transactions
```

**Step 4: Implement `_build_insurance_costs`**

Add after `_build_pension_deposits`:

```python
def _build_insurance_costs(
    self, policy_id: str, detail: dict
) -> list[Transaction]:
    """Build Transaction objects from pension insurance cost records.

    Parameters
    ----------
    policy_id : str
        The policy ID.
    detail : dict
        Pension detail data from sessionStorage.

    Returns
    -------
    list[Transaction]
        Insurance cost transactions (negative amounts).
    """
    transactions: list[Transaction] = []
    cost_keywords = ["עלות הביטוח לסיכוני נכות", "עלות הביטוח למקרה מוות"]

    for item in detail.get("accountTransactions", []):
        item_type = item.get("type", "")
        if not any(kw in item_type for kw in cost_keywords):
            continue

        amount_data = item.get("amount", {})
        amount_value = float(amount_data.get("value", 0))
        # Insurance costs are expenses — ensure negative
        if amount_value > 0:
            amount_value = -amount_value

        date_raw = item.get("date", "")
        date_str = _parse_date(date_raw)

        short_type = "נכות" if "נכות" in item_type else "מוות"
        description = f"עלות ביטוח - {short_type}"

        transactions.append(
            Transaction(
                type=TransactionType.NORMAL,
                status=TransactionStatus.COMPLETED,
                date=date_str,
                processed_date=date_str,
                original_amount=amount_value,
                original_currency="ILS",
                charged_amount=amount_value,
                charged_currency="ILS",
                description=description,
                identifier=f"{policy_id}_{date_str}_insurance_{short_type}",
                memo=None,
            )
        )

    return transactions
```

**Step 5: Remove old `_build_transactions` method**

Delete the old `_build_transactions` method (lines ~261-319 in the original file). It's replaced by `_build_pension_deposits` and `_build_insurance_costs`.

**Step 6: Verify the module imports**

Run: `python -c "from scraper.providers.insurances.hafenix import HaPhoenixScraper; print('OK')"`
Expected: `OK`

**Step 7: Commit Tasks 4+5 together**

```bash
git add scraper/providers/insurances/hafenix.py
git commit -m "feat(hafenix): rewrite fetch_data with account discovery and pension scraping"
```

---

### Task 6: Implement hishtalmut detail scraping

Add the `_scrape_hishtalmut` method.

**Files:**
- Modify: `scraper/providers/insurances/hafenix.py`

**Step 1: Implement `_scrape_hishtalmut`**

Add this method after `_scrape_pension`:

```python
async def _scrape_hishtalmut(self, account_info: dict) -> AccountResult:
    """Scrape a keren hishtalmut account's detail page.

    Parameters
    ----------
    account_info : dict
        Account summary from savingList.

    Returns
    -------
    AccountResult
        Hishtalmut account data with deposit transactions and metadata.
    """
    policy_id = account_info["policyId"]
    balance = float(account_info.get("balance", 0))
    balance_date = _parse_date(account_info.get("balanceDate", ""))

    self._emit_progress(f"scraping hishtalmut {policy_id}")

    # Navigate to hishtalmut detail page
    encoded_id = policy_id.replace(" ", "%20")
    url = f"https://my.fnx.co.il/policies/hishtalmut/{encoded_id}/info"
    await self.navigate_to(url, wait_until="domcontentloaded")
    await self._human_delay(1.0, 2.0)

    # Wait for hishtalmut data to populate in sessionStorage
    await self.page.wait_for_function(
        """
        () => {
            const state = JSON.parse(sessionStorage.getItem('appState') || '{}');
            return !!state.gemelPolicies?.hishtalmut?.general;
        }
        """,
        timeout=30000,
    )
    await self._human_delay(1.0, 2.0)

    detail = await self.page.evaluate(_EXTRACT_HISHTALMUT_DETAIL_JS)
    if not detail:
        logger.warning("No hishtalmut detail for %s", policy_id)
        return AccountResult(account_number=policy_id, balance=balance)

    # Extract investment tracks (hishtalmut has allocation %)
    tracks = []
    for route in detail.get("investmentRoutes", []):
        tracks.append({
            "name": route.get("investmentRouteTitle", ""),
            "yield_pct": route.get("yieldPercentage", 0),
            "allocation_pct": route.get("investmentPercent", {}).get("value"),
            "sum": route.get("investmentSum", {}).get("value"),
        })

    # Extract commissions
    fee = detail.get("managementFee", {})
    commission_deposits = fee.get("fromDeposit", {}).get("percentageData", {}).get("value")
    commission_savings = fee.get("fromSaving", {}).get("percentageData", {}).get("value")

    # Extract liquidity date
    liquidity_date = None
    for payment in detail.get("expectedPayments", []):
        title = payment.get("title", "")
        if "משיכה חד פעמית" in title or "סכום למשיכה" in title:
            sub_title = payment.get("subTitle", "")
            liquidity_date = self._parse_liquidity_date(sub_title)
            break

    # Build deposit transactions
    transactions = self._build_hishtalmut_deposits(policy_id, detail)

    account_name = detail.get("general", {}).get("policyName", f"Hishtalmut {policy_id}")

    logger.info(
        "Hishtalmut %s: %s (balance: ₪%s, %d tracks, %d deposits, liquidity: %s)",
        policy_id, account_name, balance, len(tracks),
        len(transactions), liquidity_date,
    )

    return AccountResult(
        account_number=policy_id,
        transactions=transactions,
        balance=balance,
        metadata={
            "provider": "hafenix",
            "policy_id": policy_id,
            "policy_type": "hishtalmut",
            "pension_type": None,
            "account_name": account_name,
            "balance": balance,
            "balance_date": balance_date,
            "investment_tracks": json.dumps(tracks, ensure_ascii=False),
            "commission_deposits_pct": commission_deposits,
            "commission_savings_pct": commission_savings,
            "insurance_covers": None,
            "liquidity_date": liquidity_date,
        },
    )
```

**Step 2: Implement `_build_hishtalmut_deposits`**

```python
def _build_hishtalmut_deposits(
    self, policy_id: str, detail: dict
) -> list[Transaction]:
    """Build Transaction objects from hishtalmut deposit records.

    Parameters
    ----------
    policy_id : str
        The policy ID.
    detail : dict
        Hishtalmut detail data from sessionStorage.

    Returns
    -------
    list[Transaction]
        Deposit transactions across all available years.
    """
    transactions: list[Transaction] = []
    yearly_deposits = detail.get("deposits", {})

    for year_data in yearly_deposits.get("list", []):
        for deposit in year_data.get("list", []):
            date_raw = deposit.get("depositDate", "")
            date_str = _parse_date(date_raw)
            total = float(deposit.get("totalDeposit", 0))

            transactions.append(
                Transaction(
                    type=TransactionType.NORMAL,
                    status=TransactionStatus.COMPLETED,
                    date=date_str,
                    processed_date=date_str,
                    original_amount=total,
                    original_currency="ILS",
                    charged_amount=total,
                    charged_currency="ILS",
                    description="הפקדה",
                    identifier=f"{policy_id}_{date_str}_{total}",
                    memo=None,
                )
            )

    return transactions
```

**Step 3: Implement `_parse_liquidity_date`**

```python
@staticmethod
def _parse_liquidity_date(text: str) -> str | None:
    """Parse liquidity date from Hebrew text like 'החל מ31.05.2029'.

    Parameters
    ----------
    text : str
        Hebrew text containing a date.

    Returns
    -------
    str or None
        Date in YYYY-MM-DD format, or None if parsing fails.
    """
    import re
    match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", text)
    if match:
        day, month, year = match.groups()
        return f"{year}-{month}-{day}"
    return None
```

**Step 4: Verify the module imports**

Run: `python -c "from scraper.providers.insurances.hafenix import HaPhoenixScraper; print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
git add scraper/providers/insurances/hafenix.py
git commit -m "feat(hafenix): add hishtalmut detail scraping with deposits and liquidity date"
```

---

### Task 7: Deposit year iteration

Add logic to iterate over all available deposit years (not just the initially loaded ones). The site may only load the current year by default.

**Files:**
- Modify: `scraper/providers/insurances/hafenix.py`

**Step 1: Add year iteration JS and method**

Add a helper that checks what years are available and triggers loading for each year. Add this JS constant (after the existing JS constants):

```python
# JS: Get list of available deposit years from sessionStorage
_GET_PENSION_DEPOSIT_YEARS_JS = """
() => {
    const appState = JSON.parse(sessionStorage.getItem('appState') || '{}');
    const depositsYear = appState.pensionPolicies?.pensionPolicy?.depositsYear;
    if (!depositsYear?.list) return [];
    return depositsYear.list.map(y => y.year);
}
"""

_GET_HISHTALMUT_DEPOSIT_YEARS_JS = """
() => {
    const appState = JSON.parse(sessionStorage.getItem('appState') || '{}');
    const deposits = appState.gemelPolicies?.hishtalmut?.deposits?.yearlyDeposits;
    if (!deposits?.list) return [];
    return deposits.list.map(y => y.year);
}
"""
```

**Step 2: Add year iteration method**

Add a method to the class that clicks through year selectors to load all years:

```python
async def _load_all_deposit_years(self, year_dropdown_selector: str = ".year-select") -> None:
    """Attempt to load all available deposit years by clicking year options.

    This is a best-effort method — if the year selector is not found or
    clicking fails, we proceed with whatever years are already loaded.
    The exact selector may need adjustment based on live testing.

    Parameters
    ----------
    year_dropdown_selector : str
        CSS selector for the year dropdown/select element.
    """
    # TODO: The year selector mechanism needs live testing.
    # The site may use a dropdown, tabs, or API calls for year switching.
    # For now, we rely on whatever years are loaded by default.
    # This method is a placeholder for future improvement.
    try:
        year_elements = await self.page.query_selector_all(
            f"{year_dropdown_selector} option, .year-tab, [data-year]"
        )
        if not year_elements:
            return

        for el in year_elements:
            try:
                await el.click()
                await self._human_delay(0.5, 1.0)
            except Exception:
                continue
    except Exception as e:
        logger.debug("Year iteration not available: %s", e)
```

**Step 3: Call year iteration in both scrape methods**

In `_scrape_pension`, after the `await self._human_delay(1.0, 2.0)` that follows the wait_for_function, add:

```python
# Try to load all deposit years
await self._load_all_deposit_years()
```

Similarly in `_scrape_hishtalmut`, at the same position.

Then re-extract the detail data (it may have been updated with new years):

The `page.evaluate` call that already exists will pick up whatever years have been loaded into sessionStorage.

**Step 4: Verify the module imports**

Run: `python -c "from scraper.providers.insurances.hafenix import HaPhoenixScraper; print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
git add scraper/providers/insurances/hafenix.py
git commit -m "feat(hafenix): add deposit year iteration (best-effort, needs live testing)"
```

---

### Task 8: Clean up and final verification

Remove unused code, clean up imports, and verify everything works.

**Files:**
- Modify: `scraper/providers/insurances/hafenix.py` (cleanup)

**Step 1: Clean up unused imports and code**

In `hafenix.py`:
- Remove `from scraper.utils import sleep` if no longer used directly (the `_human_delay` in base class handles it)
- Remove `wait_until_element_found` import if only used in login (check — it IS used in login, so keep it)
- Ensure `json` and `re` imports are present
- Remove the old `_EXTRACT_SAVINGS_JS` and `_EXTRACT_DEPOSITS_JS` constants if they still exist

**Step 2: Verify module imports cleanly**

Run: `python -c "from scraper.providers.insurances.hafenix import HaPhoenixScraper; print('OK')"`
Expected: `OK`

**Step 3: Run full test suite**

Run: `poetry run pytest tests/ -x -q`
Expected: All tests pass.

**Step 4: Final commit**

```bash
git add scraper/providers/insurances/hafenix.py
git commit -m "chore(hafenix): clean up imports and remove unused code"
```

---

### Task 9: End-to-end manual test

Test the scraper with a visible browser to verify login + data extraction works.

**Step 1: Run with visible browser**

Run: `python -m scraper hafenix --show-browser`

**Step 2: Verify login flow**

- Should navigate to my.fnx.co.il
- Fill ID + phone with human-like typing
- Submit, wait for OTP page
- Enter OTP code when prompted
- Login should succeed

**Step 3: Verify data extraction**

- Should discover accounts from savingList
- Navigate to each account's detail page
- Extract investment tracks, commissions, deposits, covers
- Log counts for each account

**Step 4: Verify DB storage**

After a successful run, check:
- `insurance_transactions` table has deposit + insurance cost rows
- `insurance_accounts` table has metadata rows with JSON investment_tracks

**Step 5: Fix any selector issues discovered during testing**

Update selectors, wait conditions, or JS extraction snippets as needed based on actual page behavior.

**Step 6: Commit any fixes**

```bash
git add -A
git commit -m "fix(hafenix): adjust selectors/extraction based on live testing"
```
