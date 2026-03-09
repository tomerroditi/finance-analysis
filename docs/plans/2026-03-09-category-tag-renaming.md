# Category & Tag Renaming Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable renaming categories and tags with cascade updates across all database tables.

**Architecture:** Add rename methods to existing repository/service/route layers. Frontend adds inline edit (pencil icon) with click-to-edit on category names and tag chips. Backend validates against collisions and protected names, then cascades the rename across all 7 tables that store category/tag strings.

**Tech Stack:** FastAPI, SQLAlchemy ORM, React 19, TanStack Query, Tailwind CSS 4

---

### Task 1: Repository — rename methods

**Files:**
- Modify: `backend/repositories/tagging_repository.py`
- Modify: `backend/repositories/transactions_repository.py`
- Modify: `backend/repositories/split_transactions_repository.py`
- Modify: `backend/repositories/tagging_rules_repository.py`
- Modify: `backend/repositories/budget_repository.py`

**Step 1: Add `rename_category` to TaggingRepository**

In `backend/repositories/tagging_repository.py`, add after `delete_category`:

```python
def rename_category(self, old_name: str, new_name: str) -> None:
    """Rename a category.

    Parameters
    ----------
    old_name : str
        Current category name.
    new_name : str
        New category name.

    Raises
    ------
    EntityNotFoundException
        If no category with old_name exists.
    EntityAlreadyExistsException
        If a category with new_name already exists.
    """
    existing = self.db.execute(
        select(Category).where(Category.name == new_name)
    ).scalar_one_or_none()
    if existing is not None:
        raise EntityAlreadyExistsException(
            f"Category '{new_name}' already exists"
        )
    cat = self._get_category(old_name)
    cat.name = new_name
    self.db.commit()
```

**Step 2: Add `rename_tag` to TaggingRepository**

In `backend/repositories/tagging_repository.py`, add after `rename_category`:

```python
def rename_tag(self, category: str, old_tag: str, new_tag: str) -> None:
    """Rename a tag within a category.

    Parameters
    ----------
    category : str
        Category containing the tag.
    old_tag : str
        Current tag name.
    new_tag : str
        New tag name.

    Raises
    ------
    EntityNotFoundException
        If the category or tag doesn't exist.
    EntityAlreadyExistsException
        If new_tag already exists in the category.
    """
    cat = self._get_category(category)
    if old_tag not in cat.tags:
        raise EntityNotFoundException(
            f"Tag '{old_tag}' not found in category '{category}'"
        )
    if new_tag in cat.tags:
        raise EntityAlreadyExistsException(
            f"Tag '{new_tag}' already exists in category '{category}'"
        )
    cat.tags = [new_tag if t == old_tag else t for t in cat.tags]
    self.db.commit()
```

**Step 3: Add `rename_category` to ServiceRepository (transactions)**

In `backend/repositories/transactions_repository.py`, add to `ServiceRepository` class after `nullify_category_and_tag`:

```python
def rename_category(self, old_name: str, new_name: str) -> None:
    """Rename category across all transactions in this table.

    Parameters
    ----------
    old_name : str
        Current category name.
    new_name : str
        New category name.
    """
    stmt = (
        update(self.model)
        .where(self.model.category == old_name)
        .values(category=new_name)
    )
    self.db.execute(stmt)
    self.db.commit()

def rename_tag(self, category: str, old_tag: str, new_tag: str) -> None:
    """Rename tag for transactions with given category.

    Parameters
    ----------
    category : str
        Category to filter by.
    old_tag : str
        Current tag name.
    new_tag : str
        New tag name.
    """
    stmt = (
        update(self.model)
        .where(self.model.category == category)
        .where(self.model.tag == old_tag)
        .values(tag=new_tag)
    )
    self.db.execute(stmt)
    self.db.commit()
```

**Step 4: Add `rename_category` and `rename_tag` to TransactionsRepository (aggregate)**

In `backend/repositories/transactions_repository.py`, add to `TransactionsRepository` class after `nullify_category`:

```python
def rename_category(self, old_name: str, new_name: str) -> None:
    """Rename category across all transaction tables.

    Parameters
    ----------
    old_name : str
        Current category name.
    new_name : str
        New category name.
    """
    self.cc_repo.rename_category(old_name, new_name)
    self.bank_repo.rename_category(old_name, new_name)
    self.cash_repo.rename_category(old_name, new_name)
    self.manual_investments_repo.rename_category(old_name, new_name)
    self.insurance_repo.rename_category(old_name, new_name)

def rename_tag(self, category: str, old_tag: str, new_tag: str) -> None:
    """Rename tag across all transaction tables.

    Parameters
    ----------
    category : str
        Category to filter by.
    old_tag : str
        Current tag name.
    new_tag : str
        New tag name.
    """
    self.cc_repo.rename_tag(category, old_tag, new_tag)
    self.bank_repo.rename_tag(category, old_tag, new_tag)
    self.cash_repo.rename_tag(category, old_tag, new_tag)
    self.manual_investments_repo.rename_tag(category, old_tag, new_tag)
    self.insurance_repo.rename_tag(category, old_tag, new_tag)
```

**Step 5: Add `rename_category` and `rename_tag` to SplitTransactionsRepository**

In `backend/repositories/split_transactions_repository.py`, add after `nullify_category`:

```python
def rename_category(self, old_name: str, new_name: str) -> None:
    """Rename category across all split transactions.

    Parameters
    ----------
    old_name : str
        Current category name.
    new_name : str
        New category name.
    """
    stmt = (
        update(SplitTransaction)
        .where(SplitTransaction.category == old_name)
        .values(category=new_name)
    )
    self.db.execute(stmt)
    self.db.commit()

def rename_tag(self, category: str, old_tag: str, new_tag: str) -> None:
    """Rename tag for split transactions with given category.

    Parameters
    ----------
    category : str
        Category to filter by.
    old_tag : str
        Current tag name.
    new_tag : str
        New tag name.
    """
    stmt = (
        update(SplitTransaction)
        .where(SplitTransaction.category == category)
        .where(SplitTransaction.tag == old_tag)
        .values(tag=new_tag)
    )
    self.db.execute(stmt)
    self.db.commit()
```

**Step 6: Add `rename_category` and `rename_tag` to TaggingRulesRepository**

In `backend/repositories/tagging_rules_repository.py`, add after `update_category_for_tag`:

```python
def rename_category(self, old_name: str, new_name: str) -> None:
    """Rename category across all tagging rules.

    Parameters
    ----------
    old_name : str
        Current category name.
    new_name : str
        New category name.
    """
    rules = self.db.query(TaggingRule).filter_by(category=old_name).all()
    for rule in rules:
        rule.category = new_name
    self.db.commit()

def rename_tag(self, category: str, old_tag: str, new_tag: str) -> None:
    """Rename tag in tagging rules for given category.

    Parameters
    ----------
    category : str
        Category to filter by.
    old_tag : str
        Current tag name.
    new_tag : str
        New tag name.
    """
    rules = (
        self.db.query(TaggingRule)
        .filter_by(category=category, tag=old_tag)
        .all()
    )
    for rule in rules:
        rule.tag = new_tag
    self.db.commit()
```

**Step 7: Add `rename_category` and `rename_tag` to BudgetRepository**

In `backend/repositories/budget_repository.py`, add after `delete_by_category_and_tags`. Note: budget tags are semicolon-separated strings, so tag rename needs string manipulation.

```python
def rename_category(self, old_name: str, new_name: str) -> None:
    """Rename category across all budget rules.

    Parameters
    ----------
    old_name : str
        Current category name.
    new_name : str
        New category name.
    """
    stmt = (
        update(BudgetRule)
        .where(BudgetRule.category == old_name)
        .values(category=new_name)
    )
    self.db.execute(stmt)
    self.db.commit()

def rename_tag(self, old_tag: str, new_tag: str) -> None:
    """Rename tag across all budget rules.

    Budget tags are semicolon-separated strings. This finds all rules
    containing old_tag and replaces it with new_tag.

    Parameters
    ----------
    old_tag : str
        Current tag name.
    new_tag : str
        New tag name.
    """
    rules = self.db.query(BudgetRule).filter(
        BudgetRule.tags.isnot(None)
    ).all()
    for rule in rules:
        tags = rule.tags.split(";") if rule.tags else []
        if old_tag in tags:
            tags = [new_tag if t == old_tag else t for t in tags]
            rule.tags = ";".join(tags)
    self.db.commit()
```

**Step 8: Commit**

```bash
git add backend/repositories/tagging_repository.py backend/repositories/transactions_repository.py backend/repositories/split_transactions_repository.py backend/repositories/tagging_rules_repository.py backend/repositories/budget_repository.py
git commit -m "feat: add rename methods to all repositories for category/tag renaming"
```

---

### Task 2: Service — rename_category and rename_tag

**Files:**
- Modify: `backend/services/tagging_service.py`

**Step 1: Add `rename_category` to CategoriesTagsService**

Add after `delete_category` method. Import `PROTECTED_TAGS` at top alongside `PROTECTED_CATEGORIES`.

```python
def rename_category(self, old_name: str, new_name: str) -> bool:
    """Rename a category and cascade across all tables.

    Parameters
    ----------
    old_name : str
        Current category name.
    new_name : str
        New category name (will be title-cased).

    Returns
    -------
    bool
        True if renamed, False if protected or not found.
    """
    if old_name in PROTECTED_CATEGORIES:
        return False
    if old_name not in self.categories_and_tags:
        return False

    new_name = to_title_case(new_name.strip()) if new_name else new_name
    if not new_name:
        return False
    if new_name.lower() in [k.lower() for k in self.categories_and_tags.keys()]:
        if new_name.lower() != old_name.lower():
            return False

    # Cascade rename across all tables
    self.transactions_repo.rename_category(old_name, new_name)
    self.split_transactions_repo.rename_category(old_name, new_name)
    self.tagging_rules_repo.rename_category(old_name, new_name)
    self.budget_repo.rename_category(old_name, new_name)
    self.tagging_repo.rename_category(old_name, new_name)
    self._invalidate_cache()
    return True
```

Note: Need to add `BudgetRepository` import and instantiation. Add to `__init__`:
```python
from backend.repositories.budget_repository import BudgetRepository
# In __init__:
self.budget_repo = BudgetRepository(db)
```

**Step 2: Add `rename_tag` to CategoriesTagsService**

Add after `rename_category`:

```python
def rename_tag(self, category: str, old_tag: str, new_tag: str) -> bool:
    """Rename a tag and cascade across all tables.

    Parameters
    ----------
    category : str
        Category the tag belongs to.
    old_tag : str
        Current tag name.
    new_tag : str
        New tag name (will be title-cased).

    Returns
    -------
    bool
        True if renamed, False if protected, not found, or collision.
    """
    if old_tag in PROTECTED_TAGS:
        return False
    if category not in self.categories_and_tags:
        return False
    if old_tag not in self.categories_and_tags[category]:
        return False

    new_tag = to_title_case(new_tag.strip()) if new_tag else new_tag
    if not new_tag:
        return False
    if new_tag in self.categories_and_tags[category]:
        if new_tag != old_tag:
            return False

    # Cascade rename
    self.transactions_repo.rename_tag(category, old_tag, new_tag)
    self.split_transactions_repo.rename_tag(category, old_tag, new_tag)
    self.tagging_rules_repo.rename_tag(category, old_tag, new_tag)
    self.budget_repo.rename_tag(old_tag, new_tag)
    self.tagging_repo.rename_tag(category, old_tag, new_tag)
    self._invalidate_cache()
    return True
```

**Step 3: Commit**

```bash
git add backend/services/tagging_service.py
git commit -m "feat: add rename_category and rename_tag to CategoriesTagsService"
```

---

### Task 3: Routes — rename endpoints

**Files:**
- Modify: `backend/routes/tagging.py`

**Step 1: Add Pydantic models and endpoints**

Add after the `TagRelocate` model:

```python
class CategoryRename(BaseModel):
    new_name: str

class TagRename(BaseModel):
    new_name: str
```

Add endpoints after `delete_tag`:

```python
@router.put("/categories/{name}")
async def rename_category(name: str, data: CategoryRename, db: Session = Depends(get_database)):
    """Rename a category and cascade the change across all tables."""
    success = CategoriesTagsService(db).rename_category(name, data.new_name)
    if not success:
        from backend.errors import ValidationException
        raise ValidationException(
            f"Cannot rename category '{name}'. It may be protected, not found, or '{data.new_name}' already exists."
        )
    return {"status": "success"}


@router.put("/tags/{category}/{name}")
async def rename_tag(category: str, name: str, data: TagRename, db: Session = Depends(get_database)):
    """Rename a tag and cascade the change across all tables."""
    success = CategoriesTagsService(db).rename_tag(category, name, data.new_name)
    if not success:
        from backend.errors import ValidationException
        raise ValidationException(
            f"Cannot rename tag '{name}'. It may be protected, not found, or '{data.new_name}' already exists in '{category}'."
        )
    return {"status": "success"}
```

**Step 2: Commit**

```bash
git add backend/routes/tagging.py
git commit -m "feat: add PUT endpoints for category and tag renaming"
```

---

### Task 4: Frontend — API client + mutations

**Files:**
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/pages/Categories.tsx`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/he.json`

**Step 1: Add API methods**

In `frontend/src/services/api.ts`, add to `taggingApi` object after `deleteTag`:

```typescript
renameCategory: (name: string, newName: string) =>
  api.put(`/tagging/categories/${encodeURIComponent(name)}`, { new_name: newName }),
renameTag: (category: string, name: string, newName: string) =>
  api.put(`/tagging/tags/${encodeURIComponent(category)}/${encodeURIComponent(name)}`, { new_name: newName }),
```

**Step 2: Add i18n keys**

In `en.json` categories section, add:
```json
"renameCategory": "Rename Category",
"renameTag": "Rename Tag",
"newName": "New Name",
"renameError": "Cannot rename. The name may already exist or is protected.",
"protectedCannotRename": "Protected items cannot be renamed"
```

In `he.json` categories section, add:
```json
"renameCategory": "שנה שם קטגוריה",
"renameTag": "שנה שם תגית",
"newName": "שם חדש",
"renameError": "לא ניתן לשנות שם. השם עשוי להיות קיים כבר או מוגן.",
"protectedCannotRename": "לא ניתן לשנות שם של פריטים מוגנים"
```

**Step 3: Add inline edit to Categories.tsx**

Add `Pencil` to the lucide-react import:
```typescript
import { Plus, Trash2, MoveRight, Wallet, Search, Pencil } from "lucide-react";
```

Add state for editing:
```typescript
const [editingCategory, setEditingCategory] = useState<string | null>(null);
const [editingTag, setEditingTag] = useState<{ category: string; tag: string } | null>(null);
const [editName, setEditName] = useState("");
```

Add protected categories constant (at top of component or outside):
```typescript
const PROTECTED_CATEGORIES = ["Credit Cards", "Salary", "Other Income", "Investments", "Ignore", "Liabilities"];
const PROTECTED_TAGS = ["Prior Wealth"];
```

Add mutations:
```typescript
const renameCategoryMutation = useMutation({
  mutationFn: ({ oldName, newName }: { oldName: string; newName: string }) =>
    taggingApi.renameCategory(oldName, newName),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ["categories"] });
    queryClient.invalidateQueries({ queryKey: ["category-icons"] });
    setEditingCategory(null);
  },
  onError: () => {
    alert(t("categories.renameError"));
  },
});

const renameTagMutation = useMutation({
  mutationFn: ({ category, oldTag, newTag }: { category: string; oldTag: string; newTag: string }) =>
    taggingApi.renameTag(category, oldTag, newTag),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ["categories"] });
    setEditingTag(null);
  },
  onError: () => {
    alert(t("categories.renameError"));
  },
});
```

**Step 4: Replace category name display with editable inline**

Replace the category name `<h3>` (line ~717):
```tsx
<h3 className="font-bold text-lg text-white">{category}</h3>
```

With:
```tsx
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
    className="font-bold text-lg bg-transparent border-b border-[var(--primary)] outline-none w-full"
  />
) : (
  <h3
    className="font-bold text-lg text-white cursor-pointer hover:text-[var(--primary)] transition-colors"
    onClick={() => {
      if (!PROTECTED_CATEGORIES.includes(category)) {
        setEditingCategory(category);
        setEditName(category);
      }
    }}
    title={PROTECTED_CATEGORIES.includes(category) ? t("categories.protectedCannotRename") : t("categories.renameCategory")}
  >
    {category}
  </h3>
)}
```

**Step 5: Replace tag name display with editable inline**

Replace the tag `<span>` (line ~742-744):
```tsx
<span className="text-sm font-medium text-[var(--text-muted)]">
  {tag}
</span>
```

With:
```tsx
{editingTag?.category === category && editingTag?.tag === tag ? (
  <input
    autoFocus
    type="text"
    value={editName}
    onChange={(e) => setEditName(e.target.value)}
    onKeyDown={(e) => {
      if (e.key === "Enter" && editName.trim()) {
        renameTagMutation.mutate({ category, oldTag: tag, newTag: editName });
      }
      if (e.key === "Escape") setEditingTag(null);
    }}
    onBlur={() => setEditingTag(null)}
    className="text-sm font-medium bg-transparent border-b border-[var(--primary)] outline-none w-20"
  />
) : (
  <span
    className="text-sm font-medium text-[var(--text-muted)] cursor-pointer hover:text-[var(--primary)] transition-colors"
    onClick={() => {
      if (!PROTECTED_TAGS.includes(tag)) {
        setEditingTag({ category, tag });
        setEditName(tag);
      }
    }}
    title={PROTECTED_TAGS.includes(tag) ? t("categories.protectedCannotRename") : t("categories.renameTag")}
  >
    {tag}
  </span>
)}
```

**Step 6: Commit**

```bash
git add frontend/src/services/api.ts frontend/src/pages/Categories.tsx frontend/src/locales/en.json frontend/src/locales/he.json
git commit -m "feat: add category and tag renaming UI with inline editing"
```

---

### Task 5: Test and verify

**Step 1: Run backend**

```bash
poetry run uvicorn backend.main:app --reload
```

**Step 2: Run frontend**

```bash
cd frontend && npm run dev
```

**Step 3: Manual test in browser (Demo Mode)**

1. Enable Demo Mode
2. Go to Categories page
3. Click a non-protected category name → should become editable input
4. Type new name, press Enter → should update
5. Try renaming to an existing category name → should show error alert
6. Click a non-protected tag → should become editable
7. Type new name, press Enter → should update
8. Try clicking protected categories (Credit Cards, Salary, etc.) → should NOT become editable
9. Try clicking Prior Wealth tag → should NOT become editable

**Step 4: Run lint**

```bash
cd frontend && npm run lint
```

**Step 5: Run backend tests**

```bash
poetry run pytest tests/backend/unit/ -v
```

**Step 6: Commit any fixes**

---

### Task 6: Write unit tests

**Files:**
- Create: `tests/backend/unit/test_rename_category_tag.py`

**Step 1: Write tests**

```python
"""Tests for category and tag renaming functionality."""

import pytest
from unittest.mock import MagicMock, patch

from backend.services.tagging_service import CategoriesTagsService


class TestRenameCategoryService:
    """Tests for CategoriesTagsService.rename_category."""

    def test_rename_protected_category_returns_false(self):
        """Renaming a protected category should return False."""
        db = MagicMock()
        with patch.object(CategoriesTagsService, "__init__", lambda self, db: None):
            service = CategoriesTagsService(db)
            service.categories_and_tags = {"Credit Cards": []}
            result = service.rename_category("Credit Cards", "CC")
            assert result is False

    def test_rename_nonexistent_category_returns_false(self):
        """Renaming a category that doesn't exist should return False."""
        db = MagicMock()
        with patch.object(CategoriesTagsService, "__init__", lambda self, db: None):
            service = CategoriesTagsService(db)
            service.categories_and_tags = {"Food": ["Groceries"]}
            result = service.rename_category("NonExistent", "New Name")
            assert result is False

    def test_rename_to_existing_name_returns_false(self):
        """Renaming to a name that already exists should return False."""
        db = MagicMock()
        with patch.object(CategoriesTagsService, "__init__", lambda self, db: None):
            service = CategoriesTagsService(db)
            service.categories_and_tags = {"Food": [], "Shopping": []}
            result = service.rename_category("Food", "Shopping")
            assert result is False


class TestRenameTagService:
    """Tests for CategoriesTagsService.rename_tag."""

    def test_rename_protected_tag_returns_false(self):
        """Renaming a protected tag should return False."""
        db = MagicMock()
        with patch.object(CategoriesTagsService, "__init__", lambda self, db: None):
            service = CategoriesTagsService(db)
            service.categories_and_tags = {"Other Income": ["Prior Wealth"]}
            result = service.rename_tag("Other Income", "Prior Wealth", "Old Money")
            assert result is False

    def test_rename_tag_nonexistent_category_returns_false(self):
        """Renaming a tag in a nonexistent category should return False."""
        db = MagicMock()
        with patch.object(CategoriesTagsService, "__init__", lambda self, db: None):
            service = CategoriesTagsService(db)
            service.categories_and_tags = {"Food": ["Groceries"]}
            result = service.rename_tag("NonExistent", "Groceries", "New Tag")
            assert result is False

    def test_rename_to_existing_tag_returns_false(self):
        """Renaming to a tag that already exists in the category should return False."""
        db = MagicMock()
        with patch.object(CategoriesTagsService, "__init__", lambda self, db: None):
            service = CategoriesTagsService(db)
            service.categories_and_tags = {"Food": ["Groceries", "Restaurants"]}
            result = service.rename_tag("Food", "Groceries", "Restaurants")
            assert result is False
```

**Step 2: Run the tests**

```bash
poetry run pytest tests/backend/unit/test_rename_category_tag.py -v
```

**Step 3: Commit**

```bash
git add tests/backend/unit/test_rename_category_tag.py
git commit -m "test: add unit tests for category and tag renaming"
```
