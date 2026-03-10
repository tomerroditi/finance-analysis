# Scraper Development Skill — Design Doc

## Purpose

A project-level Claude Code skill that guides interactive browser exploration of financial websites and generates scraper provider code for the finance-analysis framework. Two-phase workflow: explore a live site via Playwright MCP (read-only), then generate a `BrowserScraper` or `ApiScraper` subclass.

## Location

`.claude/skills/scraper-development/SKILL.md` (project skill)

## Workflow

### Phase 1 — Exploration (Read-Only Browser Session)

1. User provides: provider name, site URL, what data they need (transactions, balances, loan details, etc.)
2. Agent opens browser via Playwright MCP, navigates to login page
3. Agent asks user to log in manually — agent never touches credentials
4. Once logged in, agent explores using `browser_snapshot`, `browser_click` (navigation only), `browser_network_requests`, `browser_evaluate`
5. Agent documents: page structure, API endpoints observed in network tab, CSS selectors, data formats, authentication tokens
6. Agent produces an exploration report summarizing findings before moving to Phase 2

### Phase 2 — Code Generation

1. Agent reads 2-3 existing provider implementations as reference (e.g., Hapoalim for BrowserScraper, OneZero for ApiScraper)
2. Decides BrowserScraper vs ApiScraper based on whether site uses discoverable API calls or server-rendered HTML
3. Generates the provider class following existing patterns
4. Registers in `PROVIDER_CONFIGS` and the `create_scraper()` factory
5. Writes test stub

## Safety Framework

### Tier 1 — ABSOLUTE PROHIBITIONS

- Never type/fill credentials — user logs in manually
- Never click submit/confirm/send on forms that create, modify, or delete data
- Never click buttons labeled: delete, remove, cancel, close, transfer, send, pay, approve, confirm, submit, update, save, apply, activate, deactivate, disable, enable, change, modify, edit, reset, unsubscribe, opt-out, upgrade, downgrade
- Never interact with settings/preferences pages — don't even navigate to them
- Never click "agree", "accept", or "consent" on terms/policy dialogs — ask user
- Never download or open executable files (.exe, .msi, .dmg, .pkg)
- Never fill any form fields during exploration (including search boxes — ask user first)

### Tier 2 — SAFE ACTIONS (allowed freely)

- Click navigation links (menu items, tabs, breadcrumbs, pagination)
- Click "view", "show", "details", "expand", "collapse", "filter" elements
- Click date range selectors to change the viewing window
- Use `browser_snapshot` to read page structure
- Use `browser_network_requests` to observe API calls
- Use `browser_evaluate` to inspect DOM or read JS variables
- Navigate back/forward, scroll

### Tier 3 — ASK FIRST

- Any button/link not clearly in Tier 1 or Tier 2
- Pop-up dialogs — describe to user, ask what to do
- Any action that would leave the main site domain
- Downloading files (PDFs, CSVs) — could trigger account events
- Clicking "export" or "download" buttons — could trigger notifications
- Using search/filter inputs — describe intent, get approval first

### Tier 4 — RECOVERY

- Accidentally on settings page → go back immediately, notify user
- Unexpected confirmation dialog → dismiss/cancel, notify user
- "Are you sure" prompt → always decline, notify user
- Session expired → stop, ask user to re-login

### Additional Safety Measures

- **Domain lock:** Track initial domain. Any cross-domain navigation requires user approval.
- **Network monitoring:** After any ambiguous click, check `browser_network_requests` for POST/PUT/DELETE. Alert user immediately if detected.
- **Periodic checkpoint:** Every 5-10 actions, summarize and confirm with user.
- **Screenshot before Tier 3 actions:** User sees exactly what agent is about to click.
- **Hebrew awareness:** Many buttons will be in Hebrew. The prohibitions apply regardless of language — agent must translate/understand Hebrew button labels before clicking.

## Code Generation Output

The skill produces:
- A provider class in `scraper/providers/banks/` or `scraper/providers/credit_cards/`
- Registration entry in `scraper/models/credentials.py` (`PROVIDER_CONFIGS`)
- Factory entry in `scraper/__init__.py`
- Export in the appropriate `__init__.py`

## What the Skill Does NOT Do

- Does not run the generated scraper (user tests it separately)
- Does not modify backend integration code (adapter.py, services)
- Does not store credentials anywhere
