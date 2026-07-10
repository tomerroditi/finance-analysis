# Dashboard Bank-Balance Update Chip — Design

**Date:** 2026-07-10
**Status:** Approved (pending spec review)

## Goal

Let a user update a bank account's balance directly from the dashboard. When
the **Total Bank Balance** KPI card is expanded to show its per-account
breakdown, each account row gets a small **"update" chip**. Clicking it opens a
**modal popup** with explanatory copy and a balance input.

The same modal replaces the current **inline** balance editing on the
DataSources page, so both surfaces share one consistent, self-explanatory flow.

## Background / constraints (from codebase exploration)

- The KPI cards live in `FinancialHealthHeader` inside
  `frontend/src/pages/Dashboard.tsx` (not `NetWorthCard`). The whole 4-stat
  grid toggles a single `expanded` state on any click (lines ~113, 167–170).
  The Bank Balance card renders its per-account breakdown via a generic
  `BreakdownList` that only receives `{ name, amount }[]` — it drops
  `provider`/`id` (Dashboard.tsx ~57–68, 183–195).
- Balance updates use the composite key **`(provider, account_name)`** — there
  is no numeric id in the update path.
- Frontend: `bankBalancesApi.setBalance({ provider, account_name, balance })`
  → `POST /bank-balances/` (trailing slash). Response includes server-computed
  `prior_wealth_amount`, `last_manual_update`, `last_scrape_update`
  (`frontend/src/services/api.ts` ~470–488).
- **Backend precondition:** `BankBalanceService.set_balance` calls
  `_validate_scrape_is_today(provider, account_name)` and raises
  `ValidationException` (HTTP 400) unless the account has a successful scrape
  dated **today**. It then computes
  `prior_wealth = balance - sum(all scraped bank txns for account)` and upserts.
- Existing update UI is the **DataSources page** inline editor
  (`frontend/src/pages/DataSources.tsx` ~158–171, 173–174, 185–200, 382–469):
  a `setBalanceMutation`, `editingBalance`/`balanceInput` state, an
  `isScrapedToday()` guard (via `scrapingApi.getLastScrapes()`), and an inline
  number input with an amber `DollarSign` trigger button.
- Shared modal primitive: `frontend/src/components/common/Modal.tsx` (handles
  overlay, close button, scroll lock, a11y). Use it — do not hand-roll.
- `bank-balances` is already a normal cached GET. **No new endpoints → no PWA /
  IndexedDB persister changes** (`.claude/rules/frontend_pwa.md`).

## Decisions (locked with the user)

1. **Not-scraped-today gate:** show the chip on every account, but **disabled
   with a "Scrape first to set balance" tooltip** when the account was not
   scraped today. Mirrors the existing DataSources behavior; backend enforces
   the same rule.
2. **Edit UI:** a **modal popup** (not inline), reused on **both** the
   dashboard and the DataSources page (replacing the inline input there). The
   modal includes copy explaining **why/how** to update the balance.
3. **Modal guards internally too:** the modal takes an `isScrapedToday` prop;
   when `false` it renders the explanation with the input **disabled** and a
   "scrape first" note (defense-in-depth, since the chip should already be
   disabled in that state).
4. **i18n:** new dedicated **`bankBalance.*`** section (the modal is shared
   across two surfaces), added to both `en.json` and `he.json`.

## Components

### New: `UpdateBankBalanceModal.tsx` (`frontend/src/components/modals/`)

A shared, self-contained unit. It owns its own mutation so both call sites only
control open/close and pass identity.

**Props**
```ts
interface UpdateBankBalanceModalProps {
  isOpen: boolean;
  onClose: () => void;
  provider: string;
  accountName: string;
  currentBalance: number | null;
  isScrapedToday: boolean;
}
```

**Body**
- Account context: humanized provider (`humanizeProvider`) + `accountName`
  (with `dir="auto"` on the user-data account name).
- Explanatory copy (`bankBalance.explanation`): what setting the balance does —
  it is combined with scraped transactions to compute starting (prior) wealth
  so net worth stays accurate — and that the account must be scraped today
  first.
- Number `<input>` seeded with `currentBalance` (empty string when `null`).
  When `isScrapedToday === false`: input disabled + a `bankBalance.scrapeNote`
  warning line; Save disabled.
- **Save / Cancel** buttons. Enter in the input triggers Save.

**Mutation**
```ts
useMutation({
  mutationFn: bankBalancesApi.setBalance,   // { provider, account_name, balance }
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ["bank-balances"] });
    queryClient.invalidateQueries({ queryKey: ["net-worth-over-time"] });
    onClose();
  },
  onError: (error) => notify.error(detail ?? t("bankBalance.failed")),
});
```
Narrow invalidation only (per `frontend_components.md` — no argless
`invalidateQueries()`; the global debounced sweep already covers the rest).
`net-worth-over-time` is invalidated because the card's headline number comes
from `netWorthData`, not from `bankBalances`.

**Hook ordering:** all hooks before any early return (Modal handles the
`isOpen` early return internally, so this component can render its body
unconditionally and pass `isOpen` down).

### Dashboard: `FinancialHealthHeader` (`Dashboard.tsx`)

- Add a `lastScrapes` query (`scrapingApi.getLastScrapes()`, key
  `["last-scrapes", isDemoMode]`) and a small `isScrapedToday(provider, name)`
  helper (copy the DataSources logic).
- **Do not** thread `provider` through the generic `BreakdownList` (cash and
  investments reuse it). Instead give the bank card its **own** breakdown
  renderer — a local `BankBreakdownList` (or inline block) that renders, per
  account: name (`dir="auto"`), amount (`formatCurrency`), and the update chip.
- **Chip:** amber `DollarSign` icon button, reusing the established style
  `p-1.5 rounded-lg bg-amber-500/10 text-amber-400 hover:bg-amber-500/20`
  (small enough for the `text-xs` rows). `title` tooltip = `setBalance` or
  `scrapeFirstToSetBalance`. Disabled when not scraped today. Touch target ≥
  32px per responsive rules.
- **`e.stopPropagation()`** on the chip's `onClick` (and keydown) so it never
  toggles the card's `expanded` state.
- Local state `const [balanceModalAccount, setBalanceModalAccount] =
  useState<{ provider: string; account_name: string; balance: number } | null>()`.
- Render one `<UpdateBankBalanceModal>` driven by that state.

### DataSources page (`DataSources.tsx`)

- Remove the inline editor: `editingBalance` / `balanceInput` state, the inline
  `<input>` block (~382–469), and the local `setBalanceMutation` (now inside
  the modal).
- The amber `DollarSign` button now opens the shared modal (seeded with the
  account's current balance + `isScrapedToday`). Keep the disabled/tooltip gate.
- Net simplification: mutation + edit UI move into one shared component.

## i18n (`bankBalance.*`, both en.json + he.json)

| Key | English (approx) |
|---|---|
| `bankBalance.title` | "Update Balance" |
| `bankBalance.explanation` | Why/how: current balance is combined with scraped transactions to compute starting (prior) wealth, keeping net worth accurate. |
| `bankBalance.scrapeNote` | "Scrape this account today first, then set its balance." |
| `bankBalance.balanceLabel` | "Current balance" |
| `bankBalance.placeholder` | "Enter balance…" |
| `bankBalance.save` | "Save" (or reuse `common.save` if present) |
| `bankBalance.failed` | "Failed to set balance." |

Reuse existing `dataSources.setBalance` / `dataSources.scrapeFirstToSetBalance`
for the chip tooltips. Hebrew values hand-translated. Currency via
`formatCurrency`; account name gets `dir="auto"`.

## Error handling

- Client-side: chip disabled + tooltip when not scraped today; modal input
  disabled + note when `isScrapedToday === false`.
- Server-side fallback: a 400 from `set_balance` surfaces via `notify.error`
  using the response `detail`.

## Testing

Per `CLAUDE.md` + `.claude/rules/testing.md`, every UI patch requires a
Playwright MCP walkthrough **and** an e2e spec.

- **Demo Mode first** (Settings toggle) so real data is untouched.
- **Scrape-today caveat:** demo accounts are a frozen snapshot and likely are
  **not** scraped today, so the chip starts **disabled**. The e2e must first
  run a **demo scrape** of a bank account (demo scrapers generate fake data
  instantly, subject to the one-scrape-per-account-per-day limit) so both the
  client gate and the backend precondition pass, then update the balance.
- **e2e spec** (`frontend/e2e/bank-balance-update-chip.spec.ts`): enable demo
  mode → (scrape a bank account) → open dashboard → expand the Bank Balance KPI
  card → assert the update chip is present and enabled for the scraped account
  → click it → modal opens with explanation → type a new balance → Save →
  assert the modal closes and the breakdown/headline reflect the new value.
  Also assert a non-scraped account's chip is disabled. Disable demo mode at
  the end (note: toggling demo re-copies the frozen snapshot).
- Run e2e via `python .claude/scripts/with_server.py -- <playwright cmd>`.

## Out of scope (YAGNI)

- No currency selection (single-currency ILS).
- No change to the backend route/service or the scrape-today rule.
- No new API endpoints; no PWA/persister changes.
- No redesign of the generic `BreakdownList` or the cash/investment breakdowns.
