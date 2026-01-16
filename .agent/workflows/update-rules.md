---
description: update agent rules based on recent code changes since a specific commit
---

# Update Rules Workflow

This workflow analyzes code changes since a specific commit (including uncommitted changes) and updates the corresponding `.agent/rules/` files to keep them in sync with the codebase.

## Prerequisites
- Git repository with a valid commit history
- Understanding of which rule files map to which parts of the codebase

## Rule File Mapping

| Rule File | Covers |
|-----------|--------|
| `general.md` | Project-wide architecture, tech stack, conventions |
| `backend_repositories.md` | `backend/repositories/` |
| `backend_services.md` | `backend/services/` |
| `backend_resources.md` | `backend/resources/` |
| `backend_utils.md` | `backend/utils/` |
| `backend_scraper.md` | `backend/scraper/` |
| `frontend_components.md` | `frontend/src/components/` |
| `frontend_pages.md` | `frontend/src/pages/` |
| `frontend_utils.md` | `frontend/src/utils/`, `frontend/src/hooks/` |
| `testing.md` | `tests/` |

---

## Step 1: Identify the Base Commit

Determine the commit from which to analyze changes. Options:

```bash
# View recent commits to pick a starting point
git log --oneline -20
```

The user should provide the commit hash or reference (e.g., `HEAD~5`, `abc1234`, or a branch name like `main`).

---

## Step 2: List All Changed Files

// turbo
```bash
# List all files changed since a specific commit (including uncommitted changes)
git diff --name-only <COMMIT_HASH>
```

**Including staged + unstaged changes:**
```bash
# Staged changes
git diff --cached --name-only

# Unstaged changes  
git diff --name-only

# All changes since commit (committed + uncommitted)
git diff --name-only <COMMIT_HASH> HEAD && git diff --name-only && git diff --cached --name-only
```

**Combined command for full picture:**
```bash
# All changes since commit including working directory
git diff --name-only <COMMIT_HASH>..HEAD; git diff --name-only; git diff --cached --name-only
```

---

## Step 3: View the Actual Changes

For each significant changed file, view the diff to understand what changed:

```bash
# View diff for a specific file since commit
git diff <COMMIT_HASH> -- <FILE_PATH>

# View current uncommitted changes
git diff -- <FILE_PATH>
```

Focus on:
- **New files**: Review the entire file to document new patterns/components
- **Modified files**: Look for API changes, new methods, refactored logic
- **Deleted files**: Note deprecations to remove from rules

---

## Step 4: Categorize Changes by Rule File

Group the changed files by which rule file they affect:

1. **Backend changes** (`backend/repositories/`, `backend/services/`, etc.)
   → Update corresponding `backend_*.md` rule file

2. **Frontend changes** (`frontend/src/components/`, `frontend/src/pages/`, etc.)
   → Update corresponding `frontend_*.md` rule file

3. **Test changes** (`tests/`)
   → Update `testing.md`

4. **Architecture/cross-cutting changes** (new dependencies, config changes, major refactors)
   → Update `general.md`

---

## Step 5: Review Current Rule Files

Before updating, read the relevant rule files to understand their current state:

```bash
# Example: View the backend services rule file
cat .agent/rules/backend_services.md
```

---

## Step 6: Update Rule Files

For each affected rule file, make appropriate updates:

### Types of Updates

1. **Add new entries**: Document new classes, functions, patterns, or conventions
2. **Modify existing entries**: Update signatures, descriptions, or behaviors that changed
3. **Remove deprecated entries**: Remove documentation for deleted code
4. **Update examples**: Ensure code examples reflect current implementation

### Update Checklist

- [ ] Document new public APIs/methods with their signatures
- [ ] Update any changed method signatures or return types
- [ ] Note new dependencies or imports
- [ ] Update architecture diagrams if applicable
- [ ] Remove references to deleted code
- [ ] Ensure examples compile/work with current code
- [ ] Document breaking changes prominently

---

## Step 7: Validate Rule Consistency

After updating, verify:

1. **No stale references**: Grep for class/function names that were deleted
   ```bash
   # Check if a deleted class is still referenced in rules
   grep -r "OldClassName" .agent/rules/
   ```

2. **Cross-reference accuracy**: Ensure rule files reference each other correctly

3. **Example validity**: Code snippets should work with current implementation

---

## Step 8: Commit the Rule Updates

When satisfied with the updates:

```bash
git add .agent/rules/
git commit -m "docs(rules): update rules to reflect changes since <COMMIT_HASH>"
```

---

## Quick Reference Commands

```bash
# Full workflow for updating rules since a commit
COMMIT_HASH="<your-commit>"

# 1. See what files changed
git diff --name-only $COMMIT_HASH

# 2. See summary of changes per file
git diff --stat $COMMIT_HASH

# 3. See detailed changes (limit to specific directories)
git diff $COMMIT_HASH -- backend/services/
git diff $COMMIT_HASH -- frontend/src/components/

# 4. Check for uncommitted changes too
git status

# 5. After updating rules, verify no broken references
grep -r "DELETED_CLASS_NAME" .agent/rules/
```

---

## Notes

- Keep rule files concise but comprehensive
- Focus on documenting **patterns and conventions**, not every implementation detail
- When in doubt, document architectural decisions and the "why" behind choices
- Consider running this workflow after each significant feature/refactor PR
