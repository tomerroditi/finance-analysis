---
paths:
  - "frontend/src/components/**/*.tsx"
  - "frontend/src/pages/**/*.tsx"
  - "frontend/src/hooks/**/*.ts"
  - "frontend/src/queryInvalidation.ts"
  - "frontend/src/writePlans.ts"
  - "frontend/src/components/budget/budgetOptimistic.ts"
  - "frontend/src/components/common/PendingButton.tsx"
---

# Frontend Writes — Feedback on Every Click

Every write the user makes gets feedback the moment they click, and every
failure is said out loud. A write is one of two kinds, and which one decides
everything else:

| | **Answers on click** | **Waits for the server** |
|---|---|---|
| When | The result is predictable from what the cache already holds: a retag, a split, a refund mark/cancel/close/link, a month move, a delete, a toggle, a rename, a reorder | Only the server knows the answer: a create that needs a server id, a calculation, a backup, a scrape, a write whose effect the client can't place (a new date or amount) |
| On click | The screen changes before the request goes out | The control that fired it spins (`PendingButton`) and stays disabled; a dialog stays open |
| On success | The refetch confirms (or corrects) the patch | The new state lands; the dialog closes in `onSuccess` |
| On failure | The patch is put back **and** a toast says so | The control stops spinning **and** a message says so |

Prefer answering on click whenever the result is predictable. A spinner is
the fallback, not the default.

## Writes that answer on click

The mechanics live in `onMutate`:

1. **Patch the cache** with `setQueryData` / `setQueriesData` — every cached
   copy the user can see (the list, every budget month, the refund list
   behind a badge…). Reuse the shared patchers rather than writing your own:
   `budgetOptimistic.ts` (`applyRowChanges` and its wrappers
   `patchBudgetForRetag` / `ForDelete` / `ForSplit` / `ForMonthMove` /
   `patchBudgetNets`, which re-run the backend's claim order) and
   `writePlans.ts` (transaction lists, refund caches, month moves).
2. **Return `{ restore, refresh }`.** `restore` puts every patched cache back;
   `refresh` is the write's `RefreshPlan` (`queryInvalidation.ts`). The key is
   **`restore`**, always — not `previous`, `snapshot` or a hand-rolled
   rollback in `onError`. The mutation cache reads that key to know the write
   changed the screen ahead of the server.
3. **`onError: (_e, _v, context) => context?.restore()`** — nothing else.
   The toast is the mutation cache's job (below).

You do **not** need to cancel in-flight reads (the mutation cache drops any
read older than the write, `dropReadsOlderThanTheWrite`) or invalidate
anything (the plan does). A dialog for such a write may close in `onMutate`
(`SplitTransactionModal` does): the mutation's options-level callbacks belong
to the mutation, not the component, so `onError` still restores and the
toast still shows after the dialog unmounted.

A button for an answer-on-click write keeps a plain double-submit guard
(`disabled={x.isPending}` or a `usePendingRows` key) and **no spinner** — the
change is already on screen, and a spinner on something done is noise.
Often the button is gone anyway (the refund button gives way to its badge).

## Failures are never silent

The app-wide mutation cache (`createMutationCache` → `onError`) dispatches
`write-failed`, and `useWriteFailedToast` (mounted once in `App.tsx`) turns
it into one toast per 2 s burst:

- a write whose `onMutate` returned `restore` → **"Couldn't save that
  change, so it was undone."** (`common.writeReverted`);
- a write with **no `onError` of its own** → **"Couldn't save that change.
  Please try again."** (`common.writeFailed`).

So most writes need nothing. A write that already tells the user itself —
its own toast, an error inside its dialog, a caller's `try/catch` around
`mutateAsync` — sets **`meta: { reportsOwnError: true }`** so the user is not
told twice (`SplitTransactionModal`, `TransactionEditorModal`, the delete in
`TransactionsTable` / `RecentTransactionsFeed`, `BudgetRuleModal`'s callers,
`useYearlyRuleMutations`, `LinkRefundModal`, …). A waiting write with an
`onError` that shows nothing is a bug: either show something or drop the
`onError` and let the cache speak.

## Writes that wait

The control that fires the write is a **`PendingButton`**
(`components/common/PendingButton.tsx`):

```tsx
<PendingButton
  pending={save.isPending}
  onClick={() => save.mutate(payload)}
  disabled={!canSave}            // the other reasons it is disabled, not the pending flag
  icon={<Save size={16} />}      // the spinner takes the icon's place while pending
  spinnerSize={16}               // match the icon it replaces
  className="…"
>
  {t("common.save")}            {/* the label stays, so the button keeps its size */}
</PendingButton>
```

It is disabled, `aria-busy` and spinning while `pending`; without `icon` the
spinner goes ahead of the label; icon-only buttons pass `icon` and no
children. Rules:

- **One row's write spins one row.** A list shares one mutation, so derive
  the row's flag from the write's variables
  (`del.isPending && del.variables === row.id`) or a `usePendingRows` key —
  never the bare `isPending`, which would spin every row (`frontend_components.md`
  → "A list shares one mutation"). Several writes on one row each spin their
  own control (`GoalsSection`'s `GOAL_WRITES`).
- **A dialog stays open until the write lands**, and its host closes it in
  `onSuccess` — never close it in the submit handler (`ProjectModal` used to,
  and a failure then had nowhere to show). A form likewise clears itself only
  on success (the add-envelope form on the Transactions page).
- **The cancel button may disable while the write is out**; it is not the
  trigger and stays a plain `<button>`.
- **A layout the wrapper would break** (a `justify-between` row whose right
  badge should become the spinner) passes `ownSpinner` and draws
  `<SavingSpinner />` itself.
- **Not a button** (Enter in an inline rename): make the input `readOnly`
  while pending, guard the key handler against a second submit, and show
  `<SavingSpinner />` beside it (`CategoryDetailPanel`).
- **A read the user waits on** (Calculate) gets the same treatment.

## Checklist for a new write

1. Can the client predict the result from the cache? → answer on click:
   patch in `onMutate`, return `{ restore, refresh }`, `onError` restores.
2. Otherwise → `PendingButton` on its trigger; dialog closes in `onSuccess`.
3. Does it already show its own error? → `meta: { reportsOwnError: true }`.
   Otherwise leave error reporting to the mutation cache.
4. Give it a `RefreshPlan` (CLAUDE.md → PWA / Offline Cache) — never
   invalidate from the component.
5. e2e: hold the write with `page.route` and assert what the user sees while
   it is out (the patched screen, or the busy button), then that the server's
   answer agrees.

## Guards

- `src/pendingButtons.test.ts` — source scan: a plain `<button>` whose
  `disabled` reads the pending flag of a write that waits (a mutation in the
  file with no `restore`, a row tracker it begins, or a pending prop) fails
  unless it is a dialog's cancel.
- `src/queryInvalidation.test.ts` → "a failed write" — which failures toast,
  with which wording, and the opt-out.
- `e2e/budget-instant-actions.spec.ts` — refund mark / month move / split
  answer while the write is held; a refused mark undoes itself and toasts; a
  rule delete spins its button until the server answers.
- `budgetOptimistic.test.ts`, `writePlans.test.ts` — the shared patchers.
