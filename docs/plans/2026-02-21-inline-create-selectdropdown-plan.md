# Inline Create in SelectDropdown — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow users to create new categories/tags directly from any SelectDropdown, avoiding navigation to the Categories page.

**Architecture:** Add an optional `onCreateNew` callback prop to `SelectDropdown`. When provided, a "+ Create new" button appears at the bottom. Clicking it shows an inline text input. On submit, the callback fires, cache is invalidated, and the new value is auto-selected. A `toTitleCase` utility is added to the frontend for consistent formatting.

**Tech Stack:** React 19, TypeScript, TanStack Query, Tailwind CSS 4, lucide-react icons

---

### Task 1: Add `toTitleCase` utility to frontend

**Files:**
- Create: `frontend/src/utils/textFormatting.ts`

**Step 1: Create the utility file**

```typescript
const INITIALISMS = new Set([
  "ATM", "BTB", "DJ", "GPT", "USA", "P2P", "TV", "PC", "ID",
]);

function processWord(word: string): string {
  if (!word) return word;
  if (INITIALISMS.has(word.toUpperCase())) return word.toUpperCase();
  if (word.includes("-")) {
    return word
      .split("-")
      .map((p) => (INITIALISMS.has(p.toUpperCase()) ? p.toUpperCase() : p.charAt(0).toUpperCase() + p.slice(1).toLowerCase()))
      .join("-");
  }
  return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
}

export function toTitleCase(text: string): string {
  if (!text || !text.trim()) return text;
  return text
    .split(/(\s+)/)
    .map((part) => (/^\s+$/.test(part) ? part : processWord(part)))
    .join("");
}
```

This mirrors the backend's `to_title_case` in `backend/utils/text_utils.py` (same INITIALISMS set, same hyphen handling).

**Step 2: Verify it builds**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/utils/textFormatting.ts
git commit -m "feat: add toTitleCase utility for frontend text formatting"
```

---

### Task 2: Add `onCreateNew` prop to SelectDropdown

**Files:**
- Modify: `frontend/src/components/common/SelectDropdown.tsx`

**Step 1: Add the prop and creation mode state**

Add to the `SelectDropdownProps` interface (after `size`):

```typescript
onCreateNew?: (value: string) => Promise<void> | void;
```

Add state inside the component (after `pos` state):

```typescript
const [isCreating, setIsCreating] = useState(false);
const [createValue, setCreateValue] = useState("");
const createInputRef = useRef<HTMLInputElement>(null);
```

**Step 2: Add creation mode handlers**

Add these functions after `handleKeyDown`:

```typescript
const handleStartCreate = () => {
  setCreateValue(search);
  setIsCreating(true);
  requestAnimationFrame(() => createInputRef.current?.focus());
};

const handleConfirmCreate = async () => {
  const trimmed = createValue.trim();
  if (!trimmed) return;
  try {
    await onCreateNew?.(trimmed);
    onChange(trimmed);
    setIsCreating(false);
    setCreateValue("");
    setIsOpen(false);
  } catch {
    // Stay in creation mode so user can retry
  }
};

const handleCancelCreate = () => {
  setIsCreating(false);
  setCreateValue("");
};
```

**Step 3: Reset creation state when dropdown closes**

In the existing `useEffect` that runs when `isOpen` changes (the one that resets `search` and `highlightIndex`), also reset creation state:

```typescript
useEffect(() => {
  if (!isOpen) {
    setSearch("");
    setHighlightIndex(-1);
    setIsCreating(false);
    setCreateValue("");
    return;
  }
  // ... rest unchanged
}, [isOpen, updatePosition, showSearch]);
```

**Step 4: Render the "+ Create new" button / inline input at the bottom of the dropdown**

After the "No matches found" / "No options available" empty state `div` (inside the `listRef` div), and **only when `onCreateNew` is provided**, add:

```tsx
{onCreateNew && (
  <>
    {(filteredOptions.length > 0 || isCreating) && (
      <div className="border-t border-[var(--surface-light)]" />
    )}
    {isCreating ? (
      <div className="p-1.5">
        <div className="flex items-center gap-1">
          <input
            ref={createInputRef}
            type="text"
            value={createValue}
            onChange={(e) => setCreateValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                handleConfirmCreate();
              } else if (e.key === "Escape") {
                e.preventDefault();
                handleCancelCreate();
              }
              e.stopPropagation();
            }}
            placeholder="Enter name..."
            className="flex-1 px-3 py-1.5 text-sm bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-lg outline-none focus:border-[var(--primary)] text-[var(--text-default)] placeholder:text-[var(--text-muted)]"
          />
          <button
            type="button"
            onClick={handleConfirmCreate}
            className="p-1.5 text-emerald-400 hover:bg-emerald-500/10 rounded-lg transition-colors"
          >
            <Check size={14} />
          </button>
          <button
            type="button"
            onClick={handleCancelCreate}
            className="p-1.5 text-[var(--text-muted)] hover:bg-[var(--surface-light)] rounded-lg transition-colors"
          >
            <X size={14} />
          </button>
        </div>
      </div>
    ) : (
      <button
        type="button"
        onClick={handleStartCreate}
        className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-[var(--primary)] hover:bg-[var(--surface-light)] transition-colors"
      >
        <Plus size={14} />
        Create new
      </button>
    )}
  </>
)}
```

Import `Plus` and `X` from lucide-react at the top (add `Plus, X` to the existing import — `Check` and `Search` are already imported).

**Step 5: Verify it builds**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 6: Commit**

```bash
git add frontend/src/components/common/SelectDropdown.tsx
git commit -m "feat: add onCreateNew prop to SelectDropdown for inline creation"
```

---

### Task 3: Add `useCategoryTagCreate` hook

Create a shared hook that encapsulates the create-category and create-tag logic, so all 6 consumers use the same code instead of duplicating it.

**Files:**
- Create: `frontend/src/hooks/useCategoryTagCreate.ts`

**Step 1: Create the hook**

```typescript
import { useQueryClient } from "@tanstack/react-query";
import { taggingApi } from "../services/api";
import { toTitleCase } from "../utils/textFormatting";

export function useCategoryTagCreate() {
  const queryClient = useQueryClient();

  const createCategory = async (name: string) => {
    const formatted = toTitleCase(name);
    await taggingApi.createCategory(formatted);
    await queryClient.invalidateQueries({ queryKey: ["categories"] });
    return formatted;
  };

  const createTag = async (category: string, name: string) => {
    const formatted = toTitleCase(name);
    await taggingApi.createTag(category, formatted);
    await queryClient.invalidateQueries({ queryKey: ["categories"] });
    return formatted;
  };

  return { createCategory, createTag };
}
```

**Step 2: Verify it builds**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/hooks/useCategoryTagCreate.ts
git commit -m "feat: add useCategoryTagCreate hook for shared inline creation logic"
```

---

### Task 4: Wire up TransactionEditorModal

**Files:**
- Modify: `frontend/src/components/modals/TransactionEditorModal.tsx`

**Step 1: Import the hook and wire up both dropdowns**

Add import:
```typescript
import { useCategoryTagCreate } from "../../hooks/useCategoryTagCreate";
```

Inside the component, add:
```typescript
const { createCategory, createTag } = useCategoryTagCreate();
```

Add `onCreateNew` to the category `SelectDropdown` (line ~171):
```typescript
onCreateNew={async (name) => {
  const formatted = await createCategory(name);
  setFormData({ ...formData, category: formatted, tag: "" });
}}
```

Add `onCreateNew` to the tag `SelectDropdown` (line ~189):
```typescript
onCreateNew={async (name) => {
  const formatted = await createTag(formData.category, name);
  setFormData({ ...formData, tag: formatted });
}}
```

**Step 2: Verify it builds**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/modals/TransactionEditorModal.tsx
git commit -m "feat: add inline category/tag creation to TransactionEditorModal"
```

---

### Task 5: Wire up TransactionFormModal

**Files:**
- Modify: `frontend/src/components/modals/TransactionFormModal.tsx`

**Step 1: Import and wire up**

Same pattern as Task 4. Add import for `useCategoryTagCreate`, call the hook, add `onCreateNew` to both category (line ~281) and tag (line ~299) `SelectDropdown`s.

Category `onCreateNew`:
```typescript
onCreateNew={async (name) => {
  const formatted = await createCategory(name);
  setFormData({ ...formData, category: formatted, tag: "" });
}}
```

Tag `onCreateNew`:
```typescript
onCreateNew={async (name) => {
  const formatted = await createTag(formData.category, name);
  setFormData({ ...formData, tag: formatted });
}}
```

**Step 2: Verify it builds**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/modals/TransactionFormModal.tsx
git commit -m "feat: add inline category/tag creation to TransactionFormModal"
```

---

### Task 6: Wire up SplitTransactionModal

**Files:**
- Modify: `frontend/src/components/modals/SplitTransactionModal.tsx`

**Step 1: Import and wire up**

Same hook import. For this modal, each split row has its own category/tag dropdowns indexed by `index`.

Category `onCreateNew` (line ~141):
```typescript
onCreateNew={async (name) => {
  const formatted = await createCategory(name);
  updateSplit(index, "category", formatted);
}}
```

Tag `onCreateNew` (line ~154):
```typescript
onCreateNew={async (name) => {
  const formatted = await createTag(split.category, name);
  updateSplit(index, "tag", formatted);
}}
```

**Step 2: Verify it builds**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/modals/SplitTransactionModal.tsx
git commit -m "feat: add inline category/tag creation to SplitTransactionModal"
```

---

### Task 7: Wire up RuleEditorModal

**Files:**
- Modify: `frontend/src/components/transactions/RuleEditorModal.tsx`

**Step 1: Import and wire up**

The `RuleForm` sub-component receives category/tag state from parent. The hook must be called in the parent `RuleEditorModal` and passed down.

In `RuleEditorModal`, add:
```typescript
import { useCategoryTagCreate } from "../../hooks/useCategoryTagCreate";
// Inside component:
const { createCategory, createTag } = useCategoryTagCreate();
```

Pass new props to `RuleForm`:
```typescript
<RuleForm
  // ... existing props
  onCreateCategory={async (name) => {
    const formatted = await createCategory(name);
    setCategory(formatted);
    setTag("");
  }}
  onCreateTag={async (name) => {
    const formatted = await createTag(category, name);
    setTag(formatted);
  }}
/>
```

In the `RuleForm` function signature, add the new props:
```typescript
onCreateCategory: (name: string) => Promise<void>;
onCreateTag: (name: string) => Promise<void>;
```

In the `RuleForm` JSX, add `onCreateNew` to both `SelectDropdown`s:
- Category: `onCreateNew={onCreateCategory}`
- Tag: `onCreateNew={onCreateTag}`

**Step 2: Verify it builds**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/transactions/RuleEditorModal.tsx
git commit -m "feat: add inline category/tag creation to RuleEditorModal"
```

---

### Task 8: Wire up BudgetRuleModal (category only)

**Files:**
- Modify: `frontend/src/components/modals/BudgetRuleModal.tsx`

**Step 1: Import and wire up category dropdown only**

Tags in BudgetRuleModal use a chip-toggle UI, not SelectDropdown — so only the category dropdown gets `onCreateNew`.

Add import for `useCategoryTagCreate`, call the hook, add `onCreateNew` to the category `SelectDropdown` (line ~154):

```typescript
onCreateNew={async (name) => {
  const formatted = await createCategory(name);
  setCategory(formatted);
  setSelectedTags([]);
}}
```

**Step 2: Verify it builds**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/modals/BudgetRuleModal.tsx
git commit -m "feat: add inline category creation to BudgetRuleModal"
```

---

### Task 9: Wire up TransactionsTable bulk tag bar

**Files:**
- Modify: `frontend/src/components/TransactionsTable.tsx`

**Step 1: Import and wire up**

Add import for `useCategoryTagCreate`, call the hook inside the component. Find the bulk tag `SelectDropdown` pair (around lines 950-972).

Category `onCreateNew`:
```typescript
onCreateNew={async (name) => {
  const formatted = await createCategory(name);
  setBulkTagData({ ...bulkTagData, category: formatted, tag: "" });
}}
```

Tag `onCreateNew`:
```typescript
onCreateNew={async (name) => {
  const formatted = await createTag(bulkTagData.category, name);
  setBulkTagData({ ...bulkTagData, tag: formatted });
}}
```

**Step 2: Verify it builds**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/TransactionsTable.tsx
git commit -m "feat: add inline category/tag creation to bulk tag bar"
```

---

### Task 10: Manual QA and final commit

**Step 1: Run full build**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no errors

**Step 2: Run lint**

Run: `cd frontend && npm run lint`
Expected: No errors

**Step 3: Manual QA checklist (run dev server)**

Run: `cd frontend && npm run dev`

Test each consumer:
1. Open any transaction → Edit → Category dropdown → click "+ Create new" → type "test category" → Enter → verify it appears as "Test Category" and is selected
2. Same for tag dropdown (select a category first)
3. Verify Escape cancels creation mode
4. Verify creating a category that already exists doesn't crash (backend returns error gracefully)
5. Test in SplitTransactionModal (split any transaction)
6. Test in RuleEditorModal (create a new rule)
7. Test in BudgetRuleModal (add budget rule — category only)
8. Test in bulk tag bar (select transactions, use category/tag dropdowns)

**Step 4: Clean up test data**

Delete any test categories created during QA from the Categories page.
