# Postmortem — Why Finance Analysis Churned Out

**Date:** 2026-05-03
**Status:** App taken down, business closed
**Lifespan:** ~6 months (launch → shutdown)
**Trajectory:** strong launch (many sign-ups) → slow, sustained drop-off → handful of holdouts → shutdown

This is an honest, evidence-based look at why the dashboard failed despite a
strong start. Conclusions are grounded in what is actually in the repo —
the file/feature decisions we shipped, the things `docs/next-features.md`
admits we never shipped, and the shape of the recent commit log.

---

## 1. TL;DR

We built a technically excellent **personal-finance scraper and dashboard
for one engineer running it on their own laptop**, and we tried to sell it
as a product to households. The two are not the same product. Every
churn cause below traces back to that mismatch.

The strong launch came from novelty + the Israeli-bank-scraper niche being
genuinely under-served. The decay came from:

1. **Catastrophic install friction** (a desktop app that needs Python 3.12,
   Poetry, Node, and `uvicorn + vite` running locally).
2. **No real multi-device or multi-user story** — single user, single
   machine, no auth.
3. **The headline value props from the README were not actually shipped**
   (forecasting, CSV import, push notifications, mobile-first PWA all sat
   unimplemented in `docs/next-features.md`).
4. **No re-engagement loop** — a finance app the user has to remember to
   open is a finance app the user forgets.
5. **Quality issues that only existed because we never tested with empty
   or non-engineer state** — the kind of bugs the post-launch commit
   stream is dominated by fixing.
6. **No usage analytics**, so by the time we noticed churn we had no idea
   *which* drop-off step was killing us, and we patched cosmetic issues
   instead of structural ones.

We built a beautiful artifact. We did not build a product.

---

## 2. Timeline (qualitative)

- **Month 0 (launch).** Scrapers cover 11 banks + 7 credit-card issuers,
  bilingual EN/HE with full RTL, dashboard + budgets + investments +
  liabilities + retirement page. Strong "wow" demo. Many sign-ups, mostly
  technically-inclined Israelis curious about the bank-scraping angle.
- **Months 1–2.** Engaged users hit empty-state and mobile bugs that
  weren't visible in our demo data (the "Cohen family" fixture used by
  Demo Mode masks them — see `.claude/skills/demo-data-generation/`).
  Most never came back after the first session.
- **Months 2–4.** The remaining users use it once a month, then less. We
  ship polish, mobile fixes, and inline-tag-editor improvements — but no
  new pull (no notifications, no forecast, no CSV import, no sharing).
- **Months 4–6.** DAU collapses. Scrapers break as Israeli banks change
  their sites; we patch them, but the rate-limit ceiling (one scrape per
  account per day, see `CLAUDE.md` "Gotchas") + 5-minute scrape timeout
  means even loyal users feel the app is slow and finicky. Closed.

---

## 3. The product we built vs. the product we promised

The README listed the goals as shipped:

> - [x] Automated scraping for Israeli banks, credit cards, insurance/pension
> - [x] Rule-based auto-tagging
> - [x] Monthly + project budgets
> - [x] Investments with manual/calculated/scraped balance snapshots
> - [x] Liabilities with auto-generated payment schedules
> - [x] Retirement / FIRE calculator
> - [x] Bilingual UI (Hebrew + English) with full RTL support

But `docs/next-features.md` Tier 1 — the four highest-value features — was
**not** shipped at launch:

> 1. Forecasting / cash-flow projection
> 2. CSV / OFX import for non-Israeli accounts
> 3. PWA / offline-first mobile shell
> 4. Push / in-app notifications for budget alerts

The README itself notes that the original goals included a forecast
feature and that it was unimplemented. We checked off "track the past"
seven times and shipped zero of "tell me what's next" — which is the
half users actually pay for.

**Lesson:** the product page should have driven the roadmap, not the
other way around. We let "what's already built" become the launch scope.

---

## 4. Root causes of churn

### 4.1 The install funnel was a wall, not a funnel

To use the real app (not the Vercel demo) a user had to:

1. Install Python 3.12.
2. Install Poetry.
3. Install Node + npm.
4. Run `poetry install --no-root`.
5. `cd frontend && npm install`.
6. Open two terminals and run `uvicorn` + `npm run dev`.
7. Hand-edit `~/.finance-analysis/credentials.yaml` for each bank.
8. Trust an exe/DMG with their bank password (we ship NSIS + DMG
   installers via `release.yml`, but trust is still the issue).

Even for the Windows installer path, the app runs **locally**, binds
`localhost:8000`, and CORS in `backend/main.py` defaults to
`localhost:5173,127.0.0.1:5173`. There is no hosted product. There is no
account. There is no "open it on your phone."

For a non-engineer Israeli household — our target user — steps 1–6
filtered out >95% of sign-ups before they saw a single transaction. We
optimised the dashboard; we never optimised the path *to* the dashboard.

**What we should have done:** ship a hosted SaaS from day one, with the
local install as a power-user opt-in. Yes, that means the auth + data
isolation work in `docs/next-features.md` "Engineering debt" should have
been *done before launch*, not after.

### 4.2 No multi-device, no multi-user, no auth

`docs/next-features.md` admits the architecture in plain text:

> Currently relies on "single user on localhost". Multi-user needs at
> minimum sessions + password hashing.

Practical consequences for a real user:

- Can't open the app on a phone while at the supermarket — phone is on a
  different machine, and PWA-on-laptop only loads when the laptop is on.
- A couple sharing finances has to either share a login (there is no
  login), run two instances and merge by hand, or pick one of them to
  "own" the data.
- Credentials live in the OS keychain on **one** machine. Reinstalling
  the OS or switching laptops = re-onboard from scratch.

A personal-finance app where the second person in the household can't
also see the budget is a personal-finance app one person uses for two
weeks and then forgets. Couples are the highest-LTV segment in this
category and we made them un-servable.

### 4.3 The Israel-only ceiling

18 scrapers, all Israeli (`scraper/providers/banks/` + `credit_cards/`).
Anyone with a USD brokerage, a foreign salary, an EU bank, or even an
Israeli account at a provider we don't support hit a wall. Our only
escape hatch was `manual_investments` — i.e., "type each transaction
yourself," which is exactly what the product was supposed to remove.

`docs/next-features.md` Tier 1 #2 (CSV / OFX import) was the obvious
fix and we shipped zero of it.

**What we should have done:** ship a generic CSV importer **before**
the eleventh bank scraper. CSV is unsexy but it lifts the TAM ceiling
from "Israeli households with supported banks" to "anyone with a bank
that exports a statement."

### 4.4 No re-engagement loop

For most of the app's life there were:

- No push notifications.
- No email summaries.
- No SMS alerts.
- No "your restaurants budget is at 90%" interruption.

In-app budget alerts only landed at **v1.11.0** (per `CHANGELOG.md`,
"feat(budget): in-app budget alerts with sidebar bell"), and even then
they only fire when the user is *already in the app*. PWA push never
shipped. A finance app users have to remember to open is a finance
app users forget within three weeks of installing.

`docs/next-features.md` Tier 1 #4 covers the engineering reality:

> Backend cron-equivalent (we don't have a job runner — start with
> on-app-load checks first), frontend Notifications API with permission
> prompt, opt-in per budget rule.

We didn't have a job runner. So we couldn't send a single proactive
message to a user. So users had to remember us. So they didn't.

### 4.5 Mobile was an afterthought

The PWA shell (`frontend/src/sw.ts` and friends, `.claude/rules/frontend_pwa.md`)
landed at **v1.13.0**, in the very last release window before shutdown.
Before that, mobile users were running a desktop SPA in mobile Chrome,
re-fetching everything on every navigation, dying offline, and shipping
a >2 MiB main JS chunk from Plotly (the PWA rules document the 10 MiB
precache budget bump explicitly: *"Plotly inflates the main bundle past
[2 MiB]"*).

The recent commit log is dominated by mobile-fix entries — `fix(frontend):
improve mobile drawer, sankey labels, and minor UX`, `fix(frontend):
wire up transaction edit modal and fix mobile cell bleed`, `fix:
budget-alerts portal popup so overlay covers viewport on mobile`,
`fix: budget-alerts stronger mobile backdrop blur + scroll lock`,
`fix(SelectDropdown): skip search auto-focus on touch devices`,
`feat(frontend): redesign auto-tagging rule editor for mobile`. Each one
of those is "we shipped this broken on mobile."

For an Israeli consumer audience that is overwhelmingly mobile-first,
this was death by a thousand small frustrations.

### 4.6 Quality issues that only happened to users, not us

A pattern in the post-launch commits:

- `fix(backend): guard analytics and budget services against empty database`
  — every brand-new user hit a crashing analytics page on day one.
- `fix(frontend): align API path trailing slashes with backend routes`
  — `.claude/rules/api_paths.md` documents this as silently CSP-blocking
  the entire Investments page in production. Users saw a blank screen
  and bounced; we saw a green dashboard at home with seeded data.
- `fix(frontend): wire up transaction edit modal` — a basic CRUD action
  was non-functional in prod.
- `fix(dashboard): keep budget section visible for months with no rules`
  — UI hid the budget section when there were zero rules, i.e., for
  *every* new user.

These are all "works on the engineer's machine with the Cohen-family demo
data" bugs. We had a thorough demo fixture
(`.claude/skills/demo-data-generation/`), and that fixture quietly hid
every empty-state and onboarding bug from us. Users hit them on day one
and never returned to see the fix two weeks later.

**Lesson:** test against an empty database, on a phone, with a fresh
account, every release. The Cohen family was an asset for development
and a liability for QA.

### 4.7 We had no idea why users were churning

There is no analytics SDK in the repo. No Mixpanel, no Amplitude, no
PostHog, no Sentry session-replay, no funnel telemetry, no opt-in
diagnostic ping. The decision of "what to fix next" was driven by
whatever bug the maintainer noticed in their own session — not by
which step was actually losing the most users.

That is why the recent commit log is dominated by inline-tag-editor
polish (`stage inline tag edits in local state, commit only on Done`,
`patch tx cache directly so inline tag edits reflect immediately`,
`keep inline tag panel open after category/tag selection`) instead of
fixing the install funnel or shipping notifications. We optimised the
visible parts of the app *we* were using.

We were flying blind for six months and only steered using the
instrument panel of our own gut feel.

### 4.8 Scraping is a treadmill, and the treadmill ate us

Israeli bank sites change. We have 18 providers in
`scraper/providers/`. The scrape pipeline has, per `CLAUDE.md`:

- A 5-minute timeout per scrape.
- A daily rate limit (one scrape per account per day).

Both limits are user-visible (a bad scrape feels broken; a same-day
retry is refused). And each provider is a fragile artefact that needs
re-fixing every time a bank changes a CSS selector. With one
maintainer and 18 providers, breakage is the steady state.

**Lesson:** the scraper layer needed either (a) a dedicated team, (b)
to be replaced with Open Banking PSD2-style APIs where available, or
(c) to be radically de-emphasised in favour of the CSV importer. We
did none of those.

### 4.9 Trust signals were absent

Users were asked to put live bank credentials into a self-hosted app
authored by `Author Name <tomerroditi1@gmail.com>` (literally what's in
`pyproject.toml`). No privacy policy. No SOC 2. No incorporated
business name visible in the UI. No "your data never leaves your
machine" callout (which, ironically, was *true*, but we didn't lean on
it). No public security audit. No bug-bounty.

For a "type your bank password here" product, that is the exact
opposite of the trust posture we needed.

### 4.10 We solved problems users didn't have, beautifully

Look at what consumed engineering attention in the final weeks:

- The Data-Flow visualisation page (`frontend/src/components/dataflow/`,
  `revert(dataflow): restore auto-fit-on-mount initial zoom`,
  `feat(dataflow): rewrite platform feature cards and callouts as
  feature highlights`).
- Inline create-on-the-fly across every form (next-features #10, marked
  done).
- The auto-tagging rule editor mobile redesign.

Every one of these is a power-user nicety. None of them moves the
needle on "the user opens this app monthly six months from now."
Meanwhile forecasting, CSV import, and push notifications — the things
that *do* move that needle — sat in the backlog the whole time.

This is the classic founder trap: you build what you can build well,
not what is most missing.

---

## 5. What we should have done differently

In rough priority order, with explicit reference to where in the repo
the gap exists:

1. **Ship as a hosted SaaS from day one.**
   Not a local app. The auth/sessions work that
   `docs/next-features.md` lists as engineering debt is launch-blocking,
   not future work. The whole "local install" path becomes an opt-in
   for power users, not the default.

2. **Stand up usage analytics on day one.**
   Pick PostHog or Mixpanel. Instrument the funnel: install → first
   login → first scrape success → first budget set → 7-day retention →
   30-day retention. Fix the worst-performing step first, every week.

3. **Build the empty state and the first-week story before any other
   feature.** Onboarding wizard, sample data toggle on signup,
   "connect your first account in <3 min" speedrun. Test it on a
   non-engineer roommate before each release.

4. **Forecasting + CSV import + push notifications are launch features,
   not Tier-1 backlog.** These are the three retention drivers in any
   personal-finance category leader (Mint, YNAB, Lunchmoney). Not
   shipping them at launch is shipping a museum, not a tool.

5. **Pick one mobile experience and ship it well from week one.**
   PWA is fine; native is fine; even mobile web is fine *if it actually
   works on a phone*. Shipping a desktop SPA and patching mobile bugs
   for six months is not. The PWA shell at v1.13.0 was the right
   choice arriving five months too late.

6. **Don't run 18 scrapers as one person.** If we want broad coverage,
   either hire scraper-maintainers, contribute to/use a maintained
   shared library, or — better — push users to CSV import for
   everything except the four most common Israeli banks.

7. **Establish trust posture explicitly.** Privacy policy in the UI.
   "Your bank credentials never leave your device" callout where the
   user types them. A real company name. Open-source the scraper code
   so users can audit it. A security@ email.

8. **Have a job runner before any feature that needs reminders.** The
   absence of a backend scheduler is what blocked notifications,
   benchmark refreshes, scheduled scrapes, and snapshot jobs.
   APScheduler or a tiny in-process loop (per the next-features doc)
   would have unblocked half the retention features.

9. **Run an empty-DB + fresh-account smoke test in CI.** The class of
   bug fixed by `guard analytics and budget services against empty
   database` should not have made it to v1.14 — it should have failed
   in CI at v0.1.

10. **Treat the demo fixture as QA poison.** The Cohen family is a
    great development asset. It is also why every "rich data masks the
    bug" issue lasted to production. CI should run all e2e tests
    against an empty DB and against the demo, and lint for "this UI
    only renders when N > 0" patterns.

---

## 6. What we got right (so this isn't a roast)

Worth acknowledging, because the postmortem isn't "everything was bad":

- **Architectural discipline.** Routes → Services → Repositories with
  no leaks (`.claude/rules/general.md`). Most teams don't have this
  level of clarity at year three.
- **Bilingual UI with real RTL support** done properly via
  `i18next` + Tailwind logical properties (`.claude/rules/frontend_i18n.md`).
- **The KPI calculation rules** (`.claude/rules/kpi_calculations.md`)
  are the kind of domain-knowledge document most finance products
  never write down. It's why our numbers are actually right.
- **The CC-deduplication design** is genuinely good and avoids the
  double-counting bug that is the single most common error in Mint
  clones.
- **The repo's `CLAUDE.md` + `.claude/rules/` knowledge base** is a
  serious force-multiplier for a small team.

These are the assets we walk away with. They are exactly the things to
keep if a v2 is ever attempted on a different distribution model.

---

## 7. The one-sentence summary

We built a high-quality desktop dashboard for ourselves and assumed
households would tolerate the friction; they didn't, and we had no
analytics, no notifications, and no shared roadmap pointed at the user
to notice or fix it in time.

Next time: distribution before features, instrumentation before
optimisation, retention before polish.
