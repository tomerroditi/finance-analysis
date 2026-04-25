---
paths:
  - "backend/services/transactions_service.py"
  - "backend/repositories/transactions_repository.py"
  - "backend/repositories/split_transactions_repository.py"
  - "backend/routes/transactions.py"
  - "frontend/src/components/modals/SplitTransactionModal.tsx"
---

# Split Transactions — Architecture & Lifecycle

A single bank/credit-card/cash transaction can be split across multiple
categories or tags (e.g. one supermarket charge that's part Food, part
Household). This file documents the data shape and the layering rules so
the split lifecycle stays consistent across services, repos, and routes.

## Data model

| Table                | Role                                                       |
|----------------------|------------------------------------------------------------|
| Source table         | Original row stays put; `type` column flips to `split_parent` |
|                      | (sources: `bank_transactions`, `credit_card_transactions`, |
|                      | `cash_transactions`, `manual_investment_transactions`)     |
| `split_transactions` | One row per slice, FK `transaction_id` + `source` table    |

The original transaction is **never** deleted when split. It stays in its
source table flagged `type = "split_parent"` so the audit trail is
preserved. Reverting a split flips `type` back to `"normal"` and drops all
`split_transactions` rows for that parent.

## Layering — who calls what

```
route -> TransactionsService.split_transaction()  -> TransactionsRepository.split_transaction()
                                                         -> source repo: update_transaction_by_unique_id()
                                                         -> SplitTransactionsRepository.add_split() per slice

route -> TransactionsService.revert_split()       -> TransactionsRepository.revert_split()
                                                         -> source repo: update_transaction_by_unique_id()
                                                         -> SplitTransactionsRepository.delete_all_splits_for_transaction()
```

**Rules:**

- Routes call **service** methods only (`TransactionsService.split_transaction`,
  `TransactionsService.revert_split`). They never instantiate
  `TransactionsRepository` for split operations.
- Service methods raise `ValueError` on failure; routes translate that to
  `HTTP 400`. They never raise generic `Exception`.
- The repository is the only layer that touches the DB and is responsible for
  committing or rolling back the multi-step split write.

## Read-side: merging splits with originals

Use `TransactionsService.get_table_for_analysis(service, include_split_parents=False)`
to read transactions for analysis. It:

1. Fetches the source table.
2. Drops any row marked `split_parent`.
3. Concatenates the matching rows from `split_transactions` (which carry the
   per-slice `amount`, `category`, `tag`).

`include_split_parents=True` keeps the parents (with `type = "split_parent"`)
so the caller can choose to exclude them — this is occasionally useful for
audit views but is **not** the default. KPIs always use the merged view.

## Refunds

A pending refund can attach to a slice, not just to the original transaction.
That's why `pending_refunds` records `source_type` (`"transaction"` or
`"split"`) and `source_id` separately. Always honor `source_type` — a refund
linked to a split must not reduce the parent's balance again.

## Frontend invariants

- The `SplitTransactionModal` UI must constrain the sum of slice amounts to
  equal the parent amount before allowing save.
- After a split or revert, the cache keys to invalidate are
  `["transactions"]`, `["analytics"]`, and `["budget"]` (because budgets
  read split rows directly).

## Anti-patterns (do NOT)

- Don't delete the source row when splitting; you'll lose the audit trail
  and break refund linking.
- Don't write splits without flipping the parent's `type` to `split_parent`;
  the read-side dedup logic relies on that flag.
- Don't call `TransactionsRepository.split_transaction` directly from a
  route — go through the service.
- Don't catch `Exception` in the route layer for split errors. The service
  raises `ValueError` for failure; let everything else propagate to the
  global handler.
