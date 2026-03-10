# Unified Bulk Edit Bar Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the per-row edit button with a unified bulk actions bar that shows editable fields immediately on selection, with field visibility based on selected transaction types.

**Architecture:** Modify the existing bulk actions bar in `TransactionsTable.tsx` to always show editable fields (no mode switching). Add `amount` to the backend bulk-tag endpoint. Remove the edit button and `TransactionEditorModal` usage from the table.

**Tech Stack:** React 19, TanStack Query, FastAPI, Pydantic

---

### Task 1: Add `amount` to backend bulk-tag endpoint

The bulk-tag API already supports `category`, `tag`, `description`, `account_name`, `date` — but not `amount`. The underlying `update_transaction` already handles amount for manual sources.

**Files:**
- Modify: `backend/routes/transactions.py:44-51` (BulkTagUpdate schema)
- Modify: `backend/services/transactions_service.py:683-730` (bulk_tag_transactions method)

**Step 1: Add `amount` field to `BulkTagUpdate` Pydantic model**

In `backend/routes/transactions.py`, add `amount: Optional[float] = None` to the `BulkTagUpdate` class, after the `date` field.

**Step 2: Pass `amount` through the route handler**

In the same file, the `bulk_tag_transactions` route call (~line 195) needs to pass `data.amount`.

**Step 3: Add `amount` parameter to `bulk_tag_transactions` service method**

In `backend/services/transactions_service.py`, add `amount: float | None = None` parameter and include it in the `updates` dict when not None (same pattern as `description`, `account_name`, `date`).

**Step 4: Add `amount` to frontend API type**

In `frontend/src/services/api.ts`, add `amount?: number` to the `bulkTag` method's data parameter type.

**Step 5: Run backend tests**

Run: `poetry run pytest tests/backend/unit/ -v --tb=short`
Expected: All existing tests pass (no behavior change yet).

**Step 6: Commit**

```bash
git commit -m "feat: add amount field to bulk-tag endpoint"
```

---

### Task 2: Remove per-row edit button and TransactionEditorModal from TransactionsTable

**Files:**
- Modify: `frontend/src/components/TransactionsTable.tsx`

**Step 1: Remove the edit button from the actions column**

In the actions `<td>` (around lines 692-698), remove the entire edit button block:
```tsx
<button
  className="p-1.5 rounded-md hover:bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white transition-colors"
  title="Edit"
  onClick={() => setEditingTransaction(tx)}
>
  <Edit2 size={14} />
</button>
```

**Step 2: Remove `editingTransaction` state and modal rendering**

- Remove `const [editingTransaction, setEditingTransaction] = useState<Transaction | null>(null);` (line ~140-141)
- Remove the `editingTransaction` check in `handleModalSuccess` — simplify it to only handle `splittingTransaction`
- Remove the `TransactionEditorModal` rendering block (lines ~1084-1089)

**Step 3: Remove unused imports**

- Remove `Edit2` from lucide-react imports (line 13)
- Remove `TransactionEditorModal` import (line 24)

**Step 4: Verify the app compiles**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no errors.

**Step 5: Commit**

```bash
git commit -m "refactor: remove per-row edit button from transactions table"
```

---

### Task 3: Replace bulk bar modes with unified inline fields

This is the main task. Replace the current mode-switching bulk bar (tag mode / account mode / default) with a single layout showing all applicable fields immediately.

**Files:**
- Modify: `frontend/src/components/TransactionsTable.tsx`

**Step 1: Replace `bulkMode` state with a single `bulkEditData` state**

Remove:
```tsx
const [bulkMode, setBulkMode] = useState<"tag" | "account" | null>(null);
const [bulkTagData, setBulkTagData] = useState({ category: "", tag: "" });
const [bulkCashData, setBulkCashData] = useState({
  description: "",
  account_name: "",
  date: "",
});
```

Replace with:
```tsx
const [bulkEditData, setBulkEditData] = useState({
  date: "",
  description: "",
  amount: "",
  account_name: "",
  category: "",
  tag: "",
});
```

**Step 2: Add `allSelectedAreManual` computed value**

Add alongside the existing `allSelectedAreCash`:
```tsx
const allSelectedAreManual = useMemo(() => {
  if (selectedIds.size === 0) return false;
  return transactions
    .filter((tx) => selectedIds.has(getTransactionId(tx)))
    .every((tx) => tx.source?.includes("cash") || tx.source?.includes("manual_investment"));
}, [transactions, selectedIds]);
```

**Step 3: Rewrite `handleBulkTag` to use `bulkEditData`**

The handler groups selected transactions by source and sends updates. Only include fields that have values. For non-manual sources, only send category/tag.

```tsx
const handleBulkApply = () => {
  const selectedTxs = transactions.filter((tx) =>
    selectedIds.has(getTransactionId(tx)),
  );
  const bySource = selectedTxs.reduce(
    (acc: Record<string, number[]>, tx) => {
      const source = tx.source || "unknown";
      if (!acc[source]) acc[source] = [];
      acc[source].push(tx.unique_id || tx.id);
      return acc;
    },
    {},
  );

  Object.entries(bySource).forEach(([source, ids]) => {
    const isManualSource =
      source.includes("cash") || source.includes("manual_investment");
    const payload: any = {
      transaction_ids: ids,
      source,
    };
    // Always include category/tag if filled
    if (bulkEditData.category) payload.category = bulkEditData.category;
    if (bulkEditData.tag) payload.tag = bulkEditData.tag;
    // Manual-only fields
    if (isManualSource) {
      if (bulkEditData.date) payload.date = bulkEditData.date;
      if (bulkEditData.description) payload.description = bulkEditData.description;
      if (bulkEditData.amount) payload.amount = parseFloat(bulkEditData.amount);
      if (bulkEditData.account_name) payload.account_name = bulkEditData.account_name;
    }
    bulkTagMutation.mutate(payload);
  });
};
```

**Step 4: Update `bulkTagMutation.onSuccess` to reset `bulkEditData`**

In the mutation's `onSuccess`, replace references to `setBulkMode`, `setBulkTagData`, `setBulkCashData` with:
```tsx
setBulkEditData({ date: "", description: "", amount: "", account_name: "", category: "", tag: "" });
```

**Step 5: Rewrite the bulk action bar UI**

Replace the entire content of the bulk actions bar (the `div` with `flex items-center gap-3` that contains the mode-switching logic) with the unified layout:

```tsx
<div className="flex items-center gap-3 flex-wrap">
  {/* Details group - only for manual transactions */}
  {allSelectedAreManual && (
    <>
      <span className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">Details</span>
      <input
        type="date"
        value={bulkEditData.date}
        onChange={(e) => setBulkEditData({ ...bulkEditData, date: e.target.value })}
        className="bg-[var(--surface-light)] border border-[var(--surface-light)] rounded-lg px-3 py-1.5 text-sm w-36 focus:outline-none focus:border-[var(--primary)]/50"
        placeholder="Date"
      />
      <input
        type="text"
        value={bulkEditData.description}
        onChange={(e) => setBulkEditData({ ...bulkEditData, description: e.target.value })}
        className="bg-[var(--surface-light)] border border-[var(--surface-light)] rounded-lg px-3 py-1.5 text-sm w-40 focus:outline-none focus:border-[var(--primary)]/50"
        placeholder="Description"
      />
      <input
        type="number"
        value={bulkEditData.amount}
        onChange={(e) => setBulkEditData({ ...bulkEditData, amount: e.target.value })}
        className="bg-[var(--surface-light)] border border-[var(--surface-light)] rounded-lg px-3 py-1.5 text-sm w-28 focus:outline-none focus:border-[var(--primary)]/50"
        placeholder="Amount"
        step="0.01"
      />
      <div className="w-36">
        <SelectDropdown
          options={
            allSelectedAreCash
              ? cashBalances.map((b: any) => ({ label: b.account_name, value: b.account_name }))
              : []
          }
          value={bulkEditData.account_name}
          onChange={(val) => setBulkEditData({ ...bulkEditData, account_name: val })}
          placeholder="Account"
          size="sm"
        />
      </div>
      <div className="w-px h-6 bg-[var(--surface-light)]" />
    </>
  )}
  {/* Tags group - always visible */}
  <span className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">Tags</span>
  <div className="w-40">
    <SelectDropdown
      options={categories ? Object.keys(categories).map((cat) => ({ label: cat, value: cat })) : []}
      value={bulkEditData.category}
      onChange={(val) => setBulkEditData({ ...bulkEditData, category: val, tag: "" })}
      placeholder="Category"
      size="sm"
      onCreateNew={async (name) => {
        const formatted = await createCategory(name);
        setBulkEditData({ ...bulkEditData, category: formatted, tag: "" });
      }}
    />
  </div>
  <div className="w-40">
    <SelectDropdown
      options={
        bulkEditData.category && categories?.[bulkEditData.category]
          ? categories[bulkEditData.category].map((tag: string) => ({ label: tag, value: tag }))
          : []
      }
      value={bulkEditData.tag}
      onChange={(val) => setBulkEditData({ ...bulkEditData, tag: val })}
      placeholder="Tag"
      size="sm"
      onCreateNew={async (name) => {
        const formatted = await createTag(bulkEditData.category, name);
        setBulkEditData({ ...bulkEditData, tag: formatted });
      }}
    />
  </div>
  <div className="w-px h-6 bg-[var(--surface-light)]" />
  {/* Actions */}
  <button
    className="p-1.5 rounded-lg bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 disabled:opacity-50"
    onClick={handleBulkApply}
    disabled={bulkTagMutation.isPending}
    title="Apply changes"
  >
    <CheckCircle2 size={20} />
  </button>
  {showDelete && (
    <button
      className="p-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 transition-all"
      onClick={handleBulkDelete}
      title="Delete selected"
    >
      <Trash2 size={18} />
    </button>
  )}
  <button
    className="p-1.5 rounded-lg hover:bg-[var(--surface-light)] text-[var(--text-muted)]"
    onClick={() => setSelectedIds(new Set())}
    title="Cancel selection"
  >
    <X size={20} />
  </button>
</div>
```

**Step 6: Reset `bulkEditData` when selection clears**

Add a `useEffect` that resets `bulkEditData` when `selectedIds` becomes empty:
```tsx
useEffect(() => {
  if (selectedIds.size === 0) {
    setBulkEditData({ date: "", description: "", amount: "", account_name: "", category: "", tag: "" });
  }
}, [selectedIds]);
```

**Step 7: Verify the app compiles and renders**

Run: `cd frontend && npm run build`
Expected: Build succeeds.

**Step 8: Commit**

```bash
git commit -m "feat: unified inline bulk edit bar with type-aware field visibility"
```

---

### Task 4: Clean up unused code

**Files:**
- Modify: `frontend/src/components/TransactionsTable.tsx`

**Step 1: Remove any remaining references to `bulkMode`, `bulkTagData`, `bulkCashData`**

Search for any leftover references and remove them.

**Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: Clean build, no warnings about unused variables.

**Step 3: Commit**

```bash
git commit -m "chore: remove unused bulk mode state and imports"
```

---

### Task 5: Manual smoke test

**Step 1: Start both servers**

Run: `python .claude/scripts/with_server.py -- sleep 300`

**Step 2: Verify in browser**

Open `http://localhost:5173`, navigate to Transactions page:
1. Click a row — bulk bar appears with Tags fields (Category, Tag)
2. Click a cash transaction row — bulk bar shows Details group (Date, Description, Amount, Account) + Tags group
3. Select one bank + one cash row — only Tags group appears
4. Fill category/tag, click Apply — transactions update
5. Confirm no edit button exists on any row
6. Confirm split, delete, refund buttons still work in the actions column
