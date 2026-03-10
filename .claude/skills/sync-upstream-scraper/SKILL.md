---
name: sync-upstream-scraper
description: Check for and port changes from the upstream Israeli bank scrapers TypeScript repo into the local Python scraper package.
disable-model-invocation: true
argument-hint: "[provider-name | --base]"
---

# Sync Upstream Scraper Command

When invoked, immediately execute the workflow below. Do not just display reference -- act.

## Arguments

`$ARGUMENTS` determines the mode:
- Empty -- scan ALL providers for recent upstream changes
- `<provider>` -- sync a specific provider (e.g., `hapoalim`, `max`, `visa-cal`)
- `--base` -- check base classes and framework files only

## Provider Name Mapping

| Upstream TS file | Local Python file |
|---|---|
| `hapoalim.ts` | `scraper/providers/banks/hapoalim.py` |
| `leumi.ts` | `scraper/providers/banks/leumi.py` |
| `discount.ts` | `scraper/providers/banks/discount.py` |
| `mercantile.ts` | `scraper/providers/banks/mercantile.py` |
| `mizrahi.ts` | `scraper/providers/banks/mizrahi.py` |
| `otsar-hahayal.ts` | `scraper/providers/banks/otsar_hahayal.py` |
| `union-bank.ts` | `scraper/providers/banks/union.py` |
| `beinleumi.ts` | `scraper/providers/banks/beinleumi.py` |
| `base-beinleumi-group.ts` | `scraper/providers/banks/beinleumi_group.py` |
| `massad.ts` | `scraper/providers/banks/massad.py` |
| `yahav.ts` | `scraper/providers/banks/yahav.py` |
| `pagi.ts` | `scraper/providers/banks/pagi.py` |
| `one-zero.ts` | `scraper/providers/banks/onezero.py` |
| `max.ts` | `scraper/providers/credit_cards/max.py` |
| `visa-cal.ts` | `scraper/providers/credit_cards/visa_cal.py` |
| `isracard.ts` | `scraper/providers/credit_cards/isracard.py` |
| `amex.ts` | `scraper/providers/credit_cards/amex.py` |
| `base-isracard-amex.ts` | `scraper/providers/credit_cards/isracard_amex_base.py` |
| `beyahad-bishvilha.ts` | `scraper/providers/credit_cards/beyahad_bishvilha.py` |
| `behatsdaa.ts` | `scraper/providers/credit_cards/behatsdaa.py` |
| `base-scraper.ts` | `scraper/base/base_scraper.py` |
| `base-scraper-with-browser.ts` | `scraper/base/browser_scraper.py` |
| `interface.ts` | `scraper/models/transaction.py` + `scraper/models/account.py` |
| `errors.ts` | `scraper/exceptions.py` |
| `factory.ts` | `scraper/__init__.py` |

## Execution: Scan All Providers (no args)

**Step 1:** Run the bulk scan to get last commit date per upstream provider:

```bash
for f in hapoalim leumi discount mercantile mizrahi otsar-hahayal union-bank beinleumi massad yahav pagi one-zero max visa-cal isracard amex beyahad-bishvilha behatsdaa base-scraper base-scraper-with-browser interface; do
  date=$(gh api "repos/eshaham/israeli-bank-scrapers/commits?path=src/scrapers/${f}.ts&per_page=1" --jq '.[0].commit.committer.date[:10]' 2>/dev/null)
  echo "$date  $f"
done | sort -r
```

**Step 2:** Also check for new upstream providers not yet ported:

```bash
gh api "repos/eshaham/israeli-bank-scrapers/git/trees/master?recursive=1" \
  --jq '.tree[] | .path' | grep '^src/scrapers/' | grep -v '.test.ts'
```

Compare against the mapping table. Flag any files that don't have a local counterpart.

**Step 3:** Present a summary table to the user:

| Provider | Last Upstream Change | Status |
|---|---|---|
| hapoalim | 2026-02-15 | May need update |
| max | 2026-01-03 | Likely current |
| ... | ... | ... |

Ask the user which provider(s) to sync. Then proceed to the single-provider flow below.

## Execution: Sync Specific Provider

**Step 1 - Fetch upstream changes:** Get recent commits for the provider:

```bash
gh api "repos/eshaham/israeli-bank-scrapers/commits?path=src/scrapers/<provider>.ts&per_page=15" \
  --jq '.[] | "\(.commit.committer.date[:10]) \(.sha[:7]) \(.commit.message | split("\n")[0])"'
```

**Step 2 - Read upstream source:** Fetch the current TypeScript source:

```bash
gh api "repos/eshaham/israeli-bank-scrapers/contents/src/scrapers/<provider>.ts" \
  --jq '.content' | base64 -d
```

**Step 3 - Read local Python port:** Read the corresponding local file using the mapping table.

**Step 4 - Diff and analyze:** Compare the upstream TS with the local Python port. Identify:
- New logic, URL changes, selector changes, API endpoint changes
- New fields or transaction parsing changes
- Login flow changes
- Error handling changes

Present a clear summary of what changed and what needs porting.

**Step 5 - Ask before porting:** Show the user exactly what changes you plan to make. Get confirmation before editing.

**Step 6 - Port changes** using these translation rules:

TS to Python patterns:
- `fetchGetWithinPage(page, url)` -> `fetch_get_within_page(self.page, url)`
- `fetchPostWithinPage(page, url, data)` -> `fetch_post_within_page(self.page, url, data)`
- `waitUntilElementFound(page, sel)` -> `wait_until_element_found(self.page, sel)`
- `page.evaluate(...)` -> `await self.page.evaluate(...)`
- `page.waitForNavigation()` -> `await self.page.wait_for_navigation()`
- `moment(date).format('YYYYMMDD')` -> `date.strftime('%Y%m%d')`

Puppeteer to Playwright:
- `page.$eval(sel, fn)` -> `page_eval(self.page, sel, fn)` (from `scraper/utils/browser`)
- `page.$$eval(sel, fn)` -> `page_eval_all(self.page, sel, fn)`
- `page.type(sel, text)` -> `await self.page.fill(sel, text)` or `_type_like_human()`
- `{ waitUntil: 'networkidle0' }` -> `wait_until="networkidle"`

Always prefer framework utilities over raw Playwright:
- `scraper/utils/browser.py` -- DOM helpers
- `scraper/utils/fetch.py` -- HTTP helpers
- `scraper/utils/navigation.py` -- URL helpers
- `scraper/utils/waiting.py` -- Polling
- `scraper/utils/transactions.py` -- Transaction processing
- `scraper/utils/dates.py` -- Date utilities

**Step 7 - Verify:** Run `poetry run pytest tests/backend/unit/test_scraper/ -v` to check nothing broke.

**Step 8 - Commit:** `git commit -m "fix(scraper): update <provider> to match upstream changes"`
