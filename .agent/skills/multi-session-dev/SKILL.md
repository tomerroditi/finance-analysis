---
name: multi-session-dev
description: Orchestrates the entire lifecycle of developing a feature in a separate worktree, from setup to PR creation and review. Use this when the user asks YOU to implement a large feature or task that should be isolated.
allowed-tools: Bash, Write, Read, Grep, Glob, notify_user
---

# Multi-Session Development Workflow

This skill defines the protocol for handling large feature requests by isolating them in a separate git worktree. This ensures the main branch remains clean and enables parallel development.

## Phase 1: Initiation (Current Session)

**Trigger:** User asks to "implement feature X" or "start a new task X".

**Agent Actions:**
1.  **Acknowledge & Plan**: State that you will set up an isolated environment for this task.
2.  **Create Worktree**:
    -   Determine a suitable branch name (e.g., `feature/improved-analytics`).
    -   Run the `/create-task-worktree` workflow.
    -   *Note: This creates the folder `../finance-analysis-feature-improved-analytics`.*
3.  **Handover**:
    -   **CRITICAL**: You cannot switch windows yourself. You must instruct the user to do so.
    -   **Final Output**: "I have created the worktree at `../finance-analysis-[feature-name]`. Please open a **NEW WINDOW** for that directory and ask the agent there to: 'Initialize environment and implement [Feature Name]'."

## Phase 2: Execution (New Session)

**Trigger:** User opens the new window and prompts: "Initialize environment and implement [Feature Name]".

**Agent Actions:**
1.  **Initialize**:
    -   Run the `/setup-environment` workflow immediately.
    -   *This installs dependencies and configures unique ports.*
2.  **Plan**:
    -   Enter `task_boundary` (PLANNING mode).
    -   Create `task.md` and `implementation_plan.md`.
    -   Analyze requirements and map out the changes.
3.  **Implement**:
    -   Execute the plan (EXECUTION mode).
    -   Write code, run tests, verify logic.
4.  **Verify**:
    -   Run `pytest` or frontend verification steps.
    -   Ensure the feature works as requested.
5.  **Finalize** (AUTOMATIC - do not wait for user):
    -   Run the `/finalize-feature` workflow to commit, create PR, and self-review.

## Phase 3: Finalization (Automatic after Verification)

**Trigger:** Verification is complete with passing tests.

**Agent Actions:**

### Step 1: Commit Changes
```bash
git add -A
git status
git commit -m "<type>(<scope>): <summary>"
```
- Use conventional commit format
- Type: feat, fix, refactor, docs, test, chore, perf
- Scope: affected area (e.g., budget, auth, api)
- Summary: imperative present tense ("Add X" not "Added X")

### Step 2: Push and Create PR
```bash
git push -u origin HEAD
gh pr create --draft --title "<type>(<scope>): <summary>" --body "<PR body>"
```

### Step 3: Self-Review Loop
**You are now the Reviewer.** Review your own changes critically:

1. **Get the diff**: `gh pr diff`

2. **Review Checklist**:
   - [ ] Logic correctness - edge cases handled?
   - [ ] Security - input validation, no secrets exposed?
   - [ ] Performance - no N+1 queries, unnecessary loops?
   - [ ] Error handling - failures graceful?
   - [ ] Readability - clear names, no magic numbers?
   - [ ] Tests - key scenarios covered?

3. **If issues found**:
   ```bash
   # Fix the issue
   git add -A
   git commit -m "fix(<scope>): address review feedback - <issue>"
   git push
   ```
   Then repeat the review. Continue until all checks pass.

4. **When satisfied**:
   ```bash
   gh pr ready
   ```

### Step 4: Notify User
Use `notify_user` tool with:
- PR number and URL
- Summary of what was implemented
- Any notable design decisions
- Link to walkthrough.md

Example:
> "✅ PR #42 is ready for your review: https://github.com/user/repo/pull/42
> 
> **Implemented:** Sortable/filterable transactions table in budget page
> 
> See [walkthrough.md](file://path/to/walkthrough.md) for details."

## Example Full Flow

> **User (main window):** "Implement a dashboard analytics feature"

**Agent (main window):**
1. Creates worktree `../finance-analysis-feature-dashboard-analytics`
2. "Please open a new window for that folder..."

> **User (new window):** "Initialize environment and implement dashboard analytics"

**Agent (new window):**
1. Runs `/setup-environment`
2. Creates `task.md`, `implementation_plan.md`
3. Implements the feature
4. Verifies with tests
5. **Automatically:**
   - Commits: `feat(analytics): add dashboard analytics`
   - Creates PR #42 (draft)
   - Self-reviews, finds edge case bug
   - Fixes and commits: `fix(analytics): handle empty data`
   - Marks PR ready
6. Notifies user: "PR #42 ready for review"

## Key Principles

1. **Automatic Finalization**: After verification passes, immediately run finalize-feature workflow
2. **Self-Critical Review**: Review as if you're a senior engineer reviewing someone else's code
3. **Iterate Until Clean**: Don't mark PR ready until self-review passes
4. **Always Notify**: User should be informed of the ready PR, not asked for permission to create it
