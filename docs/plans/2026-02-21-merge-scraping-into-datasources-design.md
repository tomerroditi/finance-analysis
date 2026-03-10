# Merge Scraping Into Data Sources Page

**Date:** 2026-02-21
**Status:** Approved

## Problem

Scraping controls live in a separate `ScrapingWidget` on the dashboard, disconnected from the Data Sources page where accounts are managed. Users must navigate between pages to manage accounts and trigger scrapes.

## Design

### Overview

Move all scraping functionality into the Data Sources page. Extract scraping state management into a `useScraping` hook. Remove the ScrapingWidget from the dashboard entirely.

### Page Header

Current: `[Data Sources title]` ... `[Connect Account button]`

New: `[Data Sources title]` ... `[Timeframe dropdown] [Scrape All button] [Connect Account button]`

- **Timeframe dropdown:** Same options as current widget (Auto, 2 weeks, 1 month, 3 months, 6 months, 1 year). "Auto" is default (calculates from last scrape date).
- **Scrape All button:** Iterates all accounts and starts scraping each sequentially. Shows spinner + disabled state while any scraper is running.

### Per-Card Scraping UI

Each data source card gains:

**Right side — action buttons area:**
- **Scrape button** (play icon): Starts single-account scrape. Replaces with **abort button** (X icon) when scraping is active.
- Sits alongside existing view/edit/delete buttons.

**Status display (inline, between balance area and action buttons):**
- **Idle:** Last sync info — "Synced today" (green), "3d ago", "1w ago", "never synced" (muted)
- **In progress:** Spinner + "Scraping..." text
- **Waiting for 2FA:** Card expands with inline row: OTP text input + Verify button + Resend button (amber accent)
- **Success:** Brief green "Synced" badge (transitions to idle after a few seconds)
- **Failed:** Red "Failed" text with error message in tooltip

### Hook: `useScraping`

Extracted from ScrapingWidget logic. Manages:
- `runningScrapers`: Map of process_id → scraper state (status, service, provider, account, last_updated)
- Polling: checks status every 2s for active scrapers
- `startScrape(service, provider, account, periodDays?)`: starts single scrape
- `scrapeAll(accounts, periodDays?)`: iterates all accounts, starts each
- `submitTfa(service, provider, account, code)`: submits 2FA code
- `abortScrape(processId)`: aborts running scraper
- `getScraperForAccount(service, provider, account)`: returns active scraper state if any
- Query invalidation on completion (last-scrapes, bank-balances, transactions, etc.)

### Files Changed

| File | Action |
|------|--------|
| `frontend/src/hooks/useScraping.ts` | **Create** — extracted hook |
| `frontend/src/pages/DataSources.tsx` | **Modify** — integrate scraping UI |
| `frontend/src/components/dashboard/ScrapingWidget.tsx` | **Delete** |
| Dashboard page (consumer of ScrapingWidget) | **Modify** — remove widget |

### What's Removed (vs. current ScrapingWidget)

- Multi-select checkboxes for picking specific accounts (per user request: all or single only)
- Provider color bars (data source cards already have provider badges)
- Duplicate account list (the data source cards ARE the account list)
