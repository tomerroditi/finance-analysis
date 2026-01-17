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

## Phase 3: Completion & Review (New Session)

**Trigger:** Feature implementation is complete and verified.

**Agent Actions:**
1.  **Create PR**:
    -   Run `git status` to ensure workspace is clean/staged.
    -   Draft a PR title/body adhering to `create-pr` standards (`type(scope): summary`).
    -   Run `gh pr create`.
2.  **Self-Correction / Agentic Review**:
    -   *Conceptually*: You are now the "Reviewer".
    -   Review your own changes or check CI status if available.
    -   If verified: "PR #[ID] created and verified. It is ready for human review."
    -   If issues found: Fix them in the current session, commit, and push.

## Example Handover Response

> User: "Please add a new Investment Portfolio page."

**Agent**:
"I'll set up a dedicated worktree for the Investment Portfolio feature to keep your current workspace clean.
[Agent runs /create-task-worktree...]
Worktree created at `../finance-analysis-feature-investment-portfolio`.
**Action Required**:
Please open a new window for that folder and ask the agent there to **'Initialize environment and build the Investment Portfolio page'**."
