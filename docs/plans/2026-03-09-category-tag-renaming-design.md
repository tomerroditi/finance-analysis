# Category & Tag Renaming

## Summary

Enable renaming categories and tags, cascading the name change across all database tables that reference them by string.

## Backend

### New Endpoints

- `PUT /tagging/categories/{name}` — rename category (body: `{new_name}`)
- `PUT /tagging/tags/{category}/{name}` — rename tag (body: `{new_name}`)

### Validation

- Block renaming protected categories and protected tags
- Block if new_name already exists (409 EntityAlreadyExistsException)
- Apply toTitleCase normalization

### Cascade Updates (single DB transaction)

**Category rename:**
1. `categories.name`
2. All transaction tables (`bank_transactions`, `credit_card_transactions`, `cash_transactions`, `manual_investment_transactions`, `insurance_transactions`): `category` column
3. `split_transactions.category`
4. `tagging_rules.category`
5. `budget_rules.category`

**Tag rename:**
1. Tag entry in `categories.tags` JSON array
2. All transaction tables: `tag` column where `category` matches
3. `split_transactions.tag`
4. `tagging_rules.tag`
5. `budget_rules.tags` (semicolon-separated string replacement)

## Frontend

- Add inline edit (pencil icon) on category/tag names in management UI
- New API client methods: `renameCategory`, `renameTag`
- Error toast on collision (409)

## Constraints

- Protected categories (Credit Cards, Salary, Other Income, Investments, Ignore, Liabilities) cannot be renamed
- Protected tag (Prior Wealth) cannot be renamed
