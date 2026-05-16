# File Import for Transactions — Design

**Status:** Approved, ready for implementation planning
**Author:** brainstormed with Tomer, 2026-05-16
**Worktree:** `priceless-lamport-a6ce68`

## Problem

The current Data Sources page only supports auto-scraping accounts whose
provider has a Playwright scraper in `scraper/providers/`. Users with
accounts at unsupported institutions — or with one-off historical
statements — have no way to get those transactions into the dashboard.

The fix is a file-import path: upload a CSV/XLSX, map its columns to our
schema once, and have subsequent uploads to the same account use the saved
mapping automatically.

## Goals

- Add a file-import data source alongside scraped data sources, with the
  same lifecycle UX (account card, edit, delete, "do an action" button).
- Persist the column mapping per account so the user maps once, then
  forgets about it.
- Handle the realistic shape of Israeli bank exports: Windows-1255 encoding,
  banner rows above the header, debit/credit split columns, Hebrew column
  names, various date formats.
- De-dup transparently when the user re-uploads a statement that overlaps
  with a prior one.
- Keep auto-tagging working: imported rows without explicit category/tag
  get tagged by the existing rules engine on insert.

## Non-goals (v1)

- Preview-and-confirm import diff UI. Silent content-hash dedup is enough.
- "Type C" amount layout (unsigned amount + separate `DEBIT`/`CREDIT` text
  column). Rare; users can pre-process in Excel.
- OFX / QFX / QIF format support.
- Setting bank balance directly on a file-imported bank account. Existing
  manual prior-wealth flow already covers this.
- Editing an imported account's `service` after creation. Delete + recreate.

## Data model

One new table:

```
imported_accounts
  id              INTEGER PRIMARY KEY AUTOINCREMENT
  service         TEXT    NOT NULL   -- 'banks' | 'credit_cards' | 'cash'
  provider        TEXT    NOT NULL   -- free-text label
  account_name    TEXT    NOT NULL
  mapping_json    TEXT    NOT NULL   -- saved column mapping (see below)
  created_at, updated_at             -- TimestampMixin
  -- UNIQUE(service, provider, account_name)
```

Imported transactions land in the existing tables (`bank_transactions`,
`credit_card_transactions`, `cash_transactions`) with no schema changes.
The `provider` column carries the user's chosen label.

The `(service, provider, account_name)` triple is enforced unique across
`imported_accounts` ∪ `credentials` at create time — this is the key the
frontend uses to tell a card's `origin` apart.

### `mapping_json` shape

```json
{
  "skip_rows": 0,
  "date": { "column": "Transaction Date", "format": "auto" },
  "description": { "column": "Description" },
  "amount": {
    "mode": "single",
    "column": "Amount",
    "sign_convention": "positive_is_income"
  },
  "category": { "column": null },
  "tag": { "column": null },
  "account_number": { "column": null }
}
```

Or with split mode:

```json
{
  "amount": {
    "mode": "split",
    "debit_column": "Debit",
    "credit_column": "Credit"
  }
}
```

- `date.format`: one of `auto`, `iso`, `dd/mm/yyyy`, `mm/dd/yyyy`,
  `dd-mm-yyyy`, `dd.mm.yyyy`, `excel_serial`.
- `amount.sign_convention`: `positive_is_income` (default) or
  `positive_is_expense`. Single mode only; in split mode we always
  compute `amount = credit - debit`.

## UX flow

### Creating an imported account

A new top-level "Import from File" button on `DataSources.tsx`, next to
"Connect Account". Opens a 3-step modal (`ImportAccountWizard`):

1. **Service type** — Bank / Credit card / Cash. Same UI pattern as the
   existing connect-account step 1.
2. **Account metadata** — `Provider` (free-text input with dropdown of
   common labels: Hapoalim, Leumi, Mizrahi, Discover, "Generic"; default
   "Imported"). `Account name` (display label; validated unique across
   `imported_accounts` ∪ `credentials` for the chosen service).
3. **Upload first file** — drag-and-drop zone + browse button. Accepts
   `.csv` / `.xlsx`, 10 MB max. Inline "Expected format" callout with a
   "Download template" link. On drop, transitions to the mapping wizard.

### Mapping wizard

Triggered by the first upload (and accessible later via "Edit mapping"
on the account card). Renders three things stacked:

1. **Raw preview** — header row + first 5 data rows as a read-only table.
2. **Mapping form** — see table below.
3. **Live mapped preview** — first 5 rows rendered through the current
   mapping, showing Date / Description / Amount columns the way they'll
   appear after import. Updates as the user picks columns.

| Field | Required | UI | Notes |
|---|---|---|---|
| Date column | ✓ | dropdown of file headers | auto-suggested if header name contains "date" |
| Date format | ✓ | dropdown (auto / ISO / DD/MM/YYYY / MM/DD/YYYY / DD-MM-YYYY / DD.MM.YYYY / Excel serial) | "auto" uses `dateutil.parser` on a sample |
| Description column | ✓ | dropdown | auto-suggested by name match |
| Amount mode | ✓ | radio: single signed / debit + credit | |
| ↳ Amount column | ✓ if single | dropdown | |
| ↳ Sign convention | ✓ if single | radio: positive = money in / positive = money out | default "money in" |
| ↳ Debit column | ✓ if split | dropdown | |
| ↳ Credit column | ✓ if split | dropdown | computes `amount = credit - debit` |
| Category column | – | dropdown + "(none)" | optional |
| Tag column | – | dropdown + "(none)" | optional |
| Account number column | – | dropdown + "(none)" | useful when one file mixes multiple cards |
| Skip rows | – | number, default 0 | for files with banner rows above the header (e.g. Hapoalim) |

**Save gates:** all required fields mapped; date format parses ≥ 90% of
sample rows; amount produces a finite number for ≥ 90% of sample rows.
Failures surface the offending sample rows inline.

### Re-uploading

Existing imported account card shows an "Upload" button (replaces the
"Scrape" play-button on scraped cards). Click opens a dropzone modal that
runs the saved mapping immediately. No mapping step.

### Editing the saved mapping

Separate "Edit mapping" link in the action row, for when the export
format changes. Opens a dropzone asking for a sample file (needed to
render the preview), then the same mapping wizard pre-filled with the
saved mapping. Saving updates `mapping_json` only — does **not**
re-import historical rows and does **not** trigger import of the sample
file. The next regular "Upload" picks up the new mapping.

### Import flow (backend)

1. **Parse** — pandas `read_csv` / `read_excel`, applying `skip_rows`
   and encoding fallback (UTF-8 → Windows-1255).
2. **Apply mapping** — produce a DataFrame with canonical columns:
   `date`, `description`, `amount`, optional `category`, `tag`,
   `account_number`.
3. **Row-level validation** — drop rows with unparseable date,
   non-numeric amount, or (in split mode) both debit and credit empty.
   Track count for the response.
4. **Dedup** — for each candidate, hash `date|description|amount`. Query
   existing transactions for this account (matching `service`,
   `provider`, `account_name`) over the file's date range, build a set
   of existing hashes, skip candidates whose hash is already present.
5. **Auto-tag** — rows without a mapped category/tag run through
   `TaggingRulesService.apply_rules()`. Rows with a mapped category/tag
   bypass auto-tagging.
6. **Insert** — bulk insert via the existing source repo
   (`BankRepository` / `CreditCardRepository` / `CashRepository`).
   Each row carries `provider`, `account_name`, `source` matching the
   imported account; `type='normal'`, `status='completed'`.
7. **Side effects** — if `service == 'cash'`, call
   `CashBalanceService.recalculate_current_balance(account_name)`.
8. **Response** — `{ inserted: N, skipped_duplicates: M, dropped_invalid: K, errors: [...] }`.

**Failure modes:**
- Whole-file parse failure (corrupt file, encoding fail past CP1255,
  mapping references a missing column): 400, no rows touched.
- Partial row failures don't abort. Counted in `dropped_invalid` and
  surfaced in the toast; the rest of the file imports.

**Frontend display:** spinner during upload; success toast summarises
counts (`Imported 47 new transactions, skipped 12 duplicates, dropped 1
invalid row`); card shows last-upload timestamp.

## Backend layout

New files, following existing layer rules
(routes → services → repositories):

- `backend/models/imported_account.py` — SQLAlchemy ORM.
- `backend/repositories/imported_accounts_repository.py` — CRUD.
- `backend/services/imported_accounts_service.py` — business logic.
  Composes `TransactionsRepository`, `TaggingRulesService`,
  `CashBalanceService`.
- `backend/services/file_import_parser.py` — pure helper: raw bytes +
  mapping → canonical DataFrame. Tested in isolation.
- `backend/routes/imported_accounts.py` — endpoints; registered in
  `backend/main.py`.
- `backend/constants/tables.py` — add `Tables.IMPORTED_ACCOUNTS`.

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET`    | `/api/imported-accounts/` | List imported accounts |
| `POST`   | `/api/imported-accounts/` | Create (service, provider, account_name) |
| `PUT`    | `/api/imported-accounts/{id}` | Update mapping |
| `DELETE` | `/api/imported-accounts/{id}` | Delete account + cascade its transactions |
| `POST`   | `/api/imported-accounts/{id}/upload` | Multipart file → import |
| `POST`   | `/api/imported-accounts/preview` | Multipart file + mapping → preview rows (no persist) |
| `GET`    | `/api/imported-accounts/template` | Static template CSV download |

Per `.claude/rules/api_paths.md`, every path is matched character-for-
character on both sides. Trailing slashes preserved.

### PWA cache layer

Per `.claude/rules/frontend_pwa.md`:

- `/api/imported-accounts/*` GETs — normal, safe to cache. No exclusion
  needed.
- `/api/imported-accounts/preview` and `/upload` — POST, never cached.
- `/template` — static CSV, can be cached.

### Migration

Tables auto-create via `Base.metadata.create_all(engine)` on startup.
No migration script — same pattern every other table uses.

## Frontend layout

### API client (`services/api.ts`)

```ts
export const importedAccountsApi = {
  getAll: () => api.get("/imported-accounts/"),
  create: (data: { service: string; provider: string; account_name: string }) =>
    api.post("/imported-accounts/", data),
  updateMapping: (id: number, mapping: ColumnMapping) =>
    api.put(`/imported-accounts/${id}`, { mapping }),
  delete: (id: number) => api.delete(`/imported-accounts/${id}`),
  upload: (id: number, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return api.post(`/imported-accounts/${id}/upload`, fd);
  },
  preview: (file: File, mapping: ColumnMapping) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("mapping", JSON.stringify(mapping));
    return api.post("/imported-accounts/preview", fd);
  },
};
```

`ColumnMapping` type lives in `frontend/src/types/importedAccount.ts`.

### New components, under `frontend/src/components/dataSources/`

- `ImportFileButton.tsx` — the new top-level button. Opens the wizard.
- `ImportAccountWizard.tsx` — 3-step modal mirroring the existing
  connect-account wizard.
- `ColumnMappingWizard.tsx` — mapping form + live preview. Reused by
  both first-time setup and the "Edit mapping" path.
- `UploadFileDropzone.tsx` — drag-and-drop zone, 10 MB cap, MIME check.
- `MappingPreviewTable.tsx` — pure presentational preview table.
- `FormatDocsCallout.tsx` — "Expected format" help block + template link.

### `DataSources.tsx` changes

- Add a parallel `useQuery(["imported-accounts"])`.
- Build a merged `allAccounts` array; each item carries
  `origin: 'scraped' | 'imported'`.
- `renderAccountCard` branches on `origin`:
  - **Scraped** — current behaviour (Scrape button, last-scrape status,
    2FA inline).
  - **Imported** — Upload button (`Upload` icon from lucide), "Imported"
    badge in place of the sync-status pill, last-import date instead of
    last-scrape date, "Edit mapping" action, destructive delete
    confirms with "this will also delete N imported transactions".
- Header gets a second top-level button "Import from File" next to
  "Connect Account".
- Empty state gets a secondary "or import a file" CTA beneath the
  primary "Connect first account" button.

### Mobile parity

The new top-level button stacks with "Connect Account" via the existing
`flex flex-wrap` toolbar. The wizard modal uses the responsive pattern:
`w-full max-w-[calc(100vw-2rem)] md:max-w-xl`, `max-h-[90vh]`,
scrollable body. Per `frontend_responsive.md`.

### i18n

All user-facing strings via `t(...)` per
`.claude/rules/frontend_i18n_checklist.md`. New section
`dataSources.import.*` with keys for button labels, wizard steps,
mapping form labels, sample row pills, validation messages, toast
summary, format docs body, template download. Keys added to **both**
`en.json` and `he.json`.

## Format docs & template

Inline help in `FormatDocsCallout.tsx`:

- **Required columns** — date, description, and either one signed amount
  column OR a debit + credit pair.
- **Optional columns** — category, tag, account number.
- **Supported file types** — `.csv` (UTF-8 or Windows-1255) and `.xlsx`.
- **Supported date formats** — list of formats the dropdown offers;
  "auto-detect" line at the top.
- **Sign convention note** — "If your file shows expenses as positive
  numbers (most bank exports), pick that option in the mapping — we'll
  flip the sign so expenses are stored as negative."
- **First-row note** — "If your file has banner/header rows above the
  actual column names, set 'Skip rows' to the number of rows to ignore."

**Downloadable template:** `GET /api/imported-accounts/template` returns

```csv
date,description,amount,category,tag
2026-03-01,Coffee shop,-12.50,Food,Coffee
2026-03-03,Salary,8500.00,Salary,Salary
2026-03-05,Refund,45.00,Food,Groceries
2026-03-07,Gym membership,-180.00,,
2026-03-10,Withdrawal,-200.00,,
```

The "Download template" link is a plain `<a download href="/api/imported-accounts/template">`.

## Testing

### Backend (`tests/backend/unit/`)

- `services/test_file_import_parser.py` — parser end-to-end against
  fixtures:
  - Hapoalim-style CSV (debit/credit split, banner rows, Windows-1255).
  - Simple signed-amount CSV (UTF-8).
  - `.xlsx` with single signed amount.
  - Date format edge cases (ISO, DD/MM/YYYY, ambiguous formats).
  - Sign convention variations.
  - Malformed rows (1 bad date in 100 → 99 imported, 1 dropped).
  - Empty file / header-only file.
- `services/test_imported_accounts_service.py` — dedup, auto-tagging
  integration, cash balance recalculation hook, transaction-table
  routing per service.
- `repositories/test_imported_accounts_repository.py` — CRUD,
  uniqueness constraint, cascade delete.
- `routes/test_imported_accounts.py` — endpoint smoke tests via
  `TestClient`. Multipart upload covered.

Fixtures under `tests/backend/fixtures/imports/`.

### Frontend (`frontend/src/**/*.test.tsx`)

- `ColumnMappingWizard.test.tsx` — preview updates as mapping changes;
  validation gates block save until required fields mapped;
  sign-convention toggle flips preview amounts.
- `ImportAccountWizard.test.tsx` — step flow, validation, mapping
  persisted on submit.
- `DataSources.test.tsx` — extend: imported accounts render with
  Upload button + Imported badge; mixed list orders correctly.

### Playwright E2E (`frontend/e2e/`)

Per `.claude/rules/testing.md` "Verifying UI patches with Playwright":
one new spec `import-file.spec.ts` driving the golden path — open the
wizard, create a bank-typed imported account, upload a fixture CSV,
map columns, confirm the imported rows show up on the Transactions
page with correct sign and category.

## Build order

Suggested implementation sequence (writing-plans will refine):

1. Backend: `imported_accounts` ORM + repo + migration auto-create.
2. Backend: `file_import_parser` with full unit tests against fixtures.
3. Backend: `imported_accounts_service` (CRUD + import + dedup +
   auto-tag + side effects).
4. Backend: routes; register in `main.py`; route tests.
5. Frontend: `ColumnMapping` type + `importedAccountsApi`.
6. Frontend: `ColumnMappingWizard` + `MappingPreviewTable` (pure UI,
   testable in isolation).
7. Frontend: `ImportAccountWizard` + `ImportFileButton`.
8. Frontend: `DataSources.tsx` merge logic + Upload action + Imported
   badge.
9. Frontend: i18n keys (en + he).
10. E2E spec; verify Playwright golden path.
11. Manual smoke against a real Hapoalim CSV export (the actual reason
    this feature exists).
