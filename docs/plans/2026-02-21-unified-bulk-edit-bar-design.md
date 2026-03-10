# Unified Bulk Edit Bar

## Summary

Remove the per-row edit button from TransactionsTable. All editing happens through the bulk actions bar, which shows editable fields immediately when transactions are selected.

## Current State

- Per-row Edit2 icon button opens `TransactionEditorModal` with full form
- Bulk actions bar supports: bulk tagging (category/tag), bulk account edit (cash only), bulk delete
- Two separate edit paths create redundancy

## Design

### Bulk bar layout on selection

```
[N selected] | Details: [Date] [Description] [Amount] [Account ▼] | Tags: [Category ▼] [Tag ▼] | [✓ Apply] [Delete*] [✗ Cancel]
```

- **Details group**: Only visible when ALL selected transactions are manual (cash or manual_investment)
- **Tags group**: Always visible (all transaction types support category/tag)
- **Delete button**: Only shown when `showDelete` prop is true and selection includes manual transactions
- Fields start empty — only filled fields are sent in the update (partial update)

### Editable fields by transaction type

| Field | Cash | Manual Investment | Bank | Credit Card |
|-------|------|-------------------|------|-------------|
| Date | yes | yes | no | no |
| Description | yes | yes | no | no |
| Amount | yes | yes | no | no |
| Account | yes | yes | no | no |
| Category | yes | yes | yes | yes |
| Tag | yes | yes | yes | yes |

When selecting mixed types (manual + scraped), only the **intersection** of editable fields appears — i.e., category and tag only.

### What gets removed

- Per-row edit button (Edit2 icon)
- `TransactionEditorModal` usage from TransactionsTable (component file stays)
- Separate "tagging mode" and "account edit mode" in the bulk bar — replaced by unified field layout

### Interaction flow

1. User clicks row(s) to select
2. Bulk bar appears with fields immediately visible based on selected transaction types
3. User fills in fields they want to change
4. User clicks Apply → bulk update API call
5. Bar resets, selection clears
