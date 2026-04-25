---
paths:
  - "frontend/src/**/*.{ts,tsx}"
  - "frontend/src/locales/*.json"
---

# Frontend i18n Checklist — User-Facing Strings

Detail rules for the `t()` discipline. Pairs with `frontend_i18n.md` (which
covers RTL, formatting, provider labels). Read this whenever you touch
user-facing UI.

## Anything visible to a user MUST go through `t()`

A string is "user-facing" if a real user could ever see it on screen — even
once, even for a moment, in any language.

### Required (MUST translate)

- Button / link / menu labels
- Headings, sub-headings, section titles
- Table column headers, row labels, cell badges
- Form field labels
- **Input `placeholder` attributes** (the most commonly missed)
- **Examples** in placeholders ("e.g., Wallet, Home Safe")
- Empty-state messages ("No insurance data yet", "No matching transactions")
- Loading messages ("Loading rules...")
- `aria-label`, `title`, `alt` on icons/buttons (screen readers read them)
- `window.confirm()` / `window.alert()` text
- Toast / inline error and success messages
- Tooltip body text
- Modal titles + body copy
- Icons followed by labels (translate the label, not the icon)

### Not required (acceptable in English)

- `console.log` / `console.error` / `console.warn` (developer-only)
- Code-level identifiers: type names, variable names, query keys, route paths
- Test files (`*.test.tsx`, `*.spec.ts`)
- Internal data shapes (DB column names, API field names) — the visible
  rendering of those values still needs translation

## Workflow when adding or changing strings

1. Pick a key. Use the existing nested-section convention:
   `<feature>.<key>` for page features, `<feature>.<sub>.<key>` for
   sub-sections, `common.<key>` for genuinely cross-cutting strings.
   Example: `transactions.envelopeNamePlaceholder`.
2. Add the key to **both** `frontend/src/locales/en.json` and
   `frontend/src/locales/he.json`. Missing keys silently render the key
   path as text (e.g. user sees `transactions.envelopeNamePlaceholder`).
3. Use `{{var}}` interpolation for dynamic content
   (`t("budget.daysRemaining", { count: 15 })`), not string concatenation.
4. For numeric/currency content embedded in translated text, keep the value
   in `dir="ltr"` so the shekel sign and minus stay correct under RTL.
5. For `confirm()` and `alert()` — translate the message even though it's a
   browser dialog. Hebrew users see English browser dialogs as a regression.

## Common naming patterns

| Pattern              | Use for                                |
|----------------------|----------------------------------------|
| `xxxLabel`           | Form field label                       |
| `xxxPlaceholder`     | Input placeholder, especially examples |
| `xxxHint` / `xxxHelp`| Help text under an input               |
| `xxxAriaLabel`       | Standalone aria-label not visible      |
| `confirmDeleteXxx`   | "Are you sure" confirm-modal copy      |
| `noXxx` / `emptyXxx` | Empty-state message                    |
| `loadingXxx`         | Loading copy                           |
| `xxxFailed`          | Error toast                            |

## Quick grep checks before opening a PR

```bash
# Hardcoded English in placeholder attributes (common miss):
grep -rn 'placeholder="[A-Za-z][^"]*"' frontend/src/pages/ frontend/src/components/

# Hardcoded English in aria-labels:
grep -rn 'aria-label="[A-Za-z][^"]*"' frontend/src/pages/ frontend/src/components/

# Hardcoded confirm/alert dialogs:
grep -rn 'window\.\(confirm\|alert\)("[A-Za-z]' frontend/src/
```

If anything matches and the string is user-facing, fix it before merging.

## Anti-patterns (do NOT)

- Hardcode English placeholders with the assumption "we'll translate later"
- Concatenate translated chunks (`t("a") + " " + t("b")`) — use a single key
  with `{{var}}` interpolation instead, since word order changes between
  languages
- Translate dynamic data (transaction descriptions, account names from the
  scraper) — only translate the surrounding chrome
- Add a key to only one locale file — both `en.json` and `he.json` must have
  it, even if the values match
- Use array-callback parameter names that shadow `t` (`tags.map((t) => …)`):
  rename the callback parameter
