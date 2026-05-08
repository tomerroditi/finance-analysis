# Categories Card Layout Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the categories page card layout so action buttons are always visible (no hover-reveal), pinned to the center column across all cards, with the tag count at the far right.

**Architecture:** Replace the linear flex row inside each category card header with a 3-zone layout (left: name area, center: action buttons, right: tag count). Collapse the two duplicate button blocks (desktop hover + mobile always-visible) into one always-visible block. Replace Lucide icon buttons with plain emoji.

**Tech Stack:** React 19, TypeScript, Tailwind CSS 4, Playwright (e2e tests)

---

## Files

| File | Change |
|---|---|
| `frontend/src/pages/Categories.tsx` | Replace category header row markup; remove `Pencil` import |
| `frontend/e2e/categories.spec.ts` | Add test asserting buttons are visible without hover |

---

### Task 1: Add a failing e2e test for always-visible action buttons

**Files:**
- Modify: `frontend/e2e/categories.spec.ts`

- [ ] **Step 1: Add the test case to the existing describe block**

Open `frontend/e2e/categories.spec.ts` and add this test inside the `test.describe("Categories", ...)` block, after the last existing test:

```typescript
test("category action buttons are visible without hover", async ({ page }) => {
  await navigateTo(page, "/categories");
  await page.waitForLoadState("networkidle");

  // Buttons must be visible immediately — no hover required.
  // Title values come from en.json: renameCategory="Rename", addTag="Add Tag", deleteCategory="Delete Category"
  const renameBtn = page.locator('button[title="Rename"]').first();
  const addTagBtn = page.locator('button[title="Add Tag"]').first();
  const deleteBtn = page.locator('button[title="Delete Category"]').first();

  await expect(renameBtn).toBeVisible({ timeout: 10_000 });
  await expect(addTagBtn).toBeVisible({ timeout: 5_000 });
  await expect(deleteBtn).toBeVisible({ timeout: 5_000 });
});
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd /Users/tomer/Desktop/finance-analysis/.claude/worktrees/great-napier-2bff5f
source .venv/bin/activate
python .claude/scripts/with_server.py -- npx playwright test frontend/e2e/categories.spec.ts --reporter=line 2>&1 | tail -30
```

Expected: The new test fails because the buttons currently have `opacity-0` on desktop and are only visible on mobile.

---

### Task 2: Implement the 3-zone card layout and make the test pass

**Files:**
- Modify: `frontend/src/pages/Categories.tsx:5-7` (imports)
- Modify: `frontend/src/pages/Categories.tsx:234-356` (category header row)

- [ ] **Step 1: Remove `Pencil` from the lucide-react import**

In `frontend/src/pages/Categories.tsx`, replace line 4–8:

```typescript
import {
  Plus, Trash2, MoveRight, Wallet, Search,
  ChevronDown, ChevronRight, ChevronsUpDown,
} from "lucide-react";
```

(`Pencil` is removed because both category rename buttons are replaced with the ✏️ emoji.)

- [ ] **Step 2: Replace the category header row with the 3-zone layout**

Find the comment `{/* Category Header Row */}` at line ~234. Replace the entire `<div>` block that follows it (through the closing `</div>` of the header row, ending around line 356) with:

```tsx
{/* Category Header Row */}
<div
  className="flex items-center px-3 md:px-5 py-3 md:py-4 cursor-pointer"
  onClick={() => toggleCategory(category)}
>
  {/* Left zone: chevron + icon + name */}
  <div className="flex flex-1 items-center gap-2 md:gap-3 min-w-0">
    <span className="text-[var(--text-muted)] shrink-0 transition-transform">
      {isExpanded
        ? <ChevronDown size={16} />
        : isRtl ? <ChevronRight size={16} className="rotate-180" /> : <ChevronRight size={16} />
      }
    </span>
    <button
      onClick={(e) => {
        e.stopPropagation();
        setEditingIcon({ category, currentIcon: icon || "💰" });
      }}
      className="p-2 rounded-xl bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-all text-lg w-9 h-9 md:w-10 md:h-10 flex items-center justify-center border border-blue-500/20 shrink-0"
      title={t("categories.changeIcon")}
    >
      {icon || <Wallet size={18} />}
    </button>
    <div className="flex-1 min-w-0">
      {editingCategory === category ? (
        <input
          autoFocus
          type="text"
          value={editName}
          onChange={(e) => setEditName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && editName.trim()) {
              renameCategoryMutation.mutate({ oldName: category, newName: editName });
            }
            if (e.key === "Escape") setEditingCategory(null);
          }}
          onBlur={() => setEditingCategory(null)}
          onClick={(e) => e.stopPropagation()}
          className="font-bold text-base md:text-lg bg-transparent border-b border-[var(--primary)] outline-none w-full"
        />
      ) : (
        <h3 className="font-bold text-sm md:text-base truncate text-white" dir="auto">
          {category}
        </h3>
      )}
    </div>
  </div>

  {/* Center zone: action buttons — always visible on all breakpoints */}
  <div className="flex-1 flex items-center justify-center" onClick={(e) => e.stopPropagation()}>
    <div className="flex items-center gap-1">
      <button
        onClick={() => { if (!isProtected) { setEditingCategory(category); setEditName(category); } }}
        disabled={isProtected}
        className={`p-1.5 rounded-lg transition-colors text-base leading-none ${isProtected ? "opacity-30 cursor-not-allowed" : "hover:bg-[var(--surface-light)]"}`}
        title={isProtected ? t("categories.protectedCannotRename") : t("categories.renameCategory")}
      >
        ✏️
      </button>
      <button
        onClick={() => setIsAddTagOpen({ category })}
        className="p-1.5 rounded-lg hover:bg-[var(--surface-light)] transition-colors text-base leading-none"
        title={t("categories.addTag")}
      >
        ➕
      </button>
      <div className="w-px h-4 bg-[var(--surface-light)] mx-1 shrink-0" />
      <button
        onClick={async () => {
          if (isProtected) return;
          const ok = await confirm({
            title: t("categories.deleteCategory"),
            message: t("categories.confirmDeleteCategory", { name: category }),
            confirmLabel: t("common.delete"),
            isDestructive: true,
          });
          if (ok) deleteCategoryMutation.mutate(category);
        }}
        disabled={isProtected}
        className={`p-1.5 rounded-lg transition-colors text-base leading-none ${isProtected ? "opacity-30 cursor-not-allowed" : "hover:bg-[var(--surface-light)]"}`}
        title={isProtected ? t("categories.protectedCannotRename") : t("categories.deleteCategory")}
      >
        🗑️
      </button>
    </div>
  </div>

  {/* Right zone: tag count */}
  <div className="flex-1 flex items-center justify-end">
    <span className="px-2 py-0.5 rounded-full bg-[var(--surface-light)] text-xs font-bold text-[var(--text-muted)] shrink-0" dir="ltr">
      {tagCount}
    </span>
  </div>
</div>
```

> **What was removed:** The `group` class on the outer div, the `gap-2 md:gap-3` directly on the outer div (now on the left zone), the standalone `<div className="flex-1 min-w-0">` name block, the standalone tag count `<span>`, the desktop-only `hidden md:flex opacity-0 group-hover:opacity-100` button block, and the mobile-only `md:hidden flex` button block.

- [ ] **Step 3: Run TypeScript type-check**

```bash
cd /Users/tomer/Desktop/finance-analysis/.claude/worktrees/great-napier-2bff5f/frontend
npm run build 2>&1 | tail -20
```

Expected: Build succeeds with no type errors.

- [ ] **Step 4: Run lint**

```bash
cd /Users/tomer/Desktop/finance-analysis/.claude/worktrees/great-napier-2bff5f/frontend
npm run lint 2>&1 | tail -20
```

Expected: No errors. If `Pencil` was missed in the import cleanup, lint will report "defined but never used" — fix by removing it from the import.

- [ ] **Step 5: Run the full e2e test suite for categories**

```bash
cd /Users/tomer/Desktop/finance-analysis/.claude/worktrees/great-napier-2bff5f
source .venv/bin/activate
python .claude/scripts/with_server.py -- npx playwright test frontend/e2e/categories.spec.ts --reporter=line 2>&1 | tail -30
```

Expected: All 4 tests pass, including the new "category action buttons are visible without hover" test.

- [ ] **Step 6: Visual verification with Playwright**

```bash
cd /Users/tomer/Desktop/finance-analysis/.claude/worktrees/great-napier-2bff5f
source .venv/bin/activate
python .claude/scripts/with_server.py -- npx playwright test frontend/e2e/categories.spec.ts --headed --reporter=line 2>&1 | tail -10
```

Observe the browser: confirm that on the categories page, all three emoji buttons (✏️ ➕ 🗑️) are visible immediately in each card row without hovering, that they are horizontally aligned across all cards, and that the tag count appears at the far right.

- [ ] **Step 7: Commit**

```bash
cd /Users/tomer/Desktop/finance-analysis/.claude/worktrees/great-napier-2bff5f
git add frontend/src/pages/Categories.tsx frontend/e2e/categories.spec.ts
git commit -m "feat(categories): 3-zone card layout with always-visible action buttons"
```
