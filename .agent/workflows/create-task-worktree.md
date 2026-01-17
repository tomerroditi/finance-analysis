---
description: Create a new git worktree for a specific task to enable parallel development
---

Use this workflow when you want to work on a new task or branch without disturbing your current workspace state (e.g. while a long process is running or to keep contexts separate).

1. **Check Status**
   Ensure your current workspace is clean (interactive rebase or uncommitted changes might cause issues, though worktrees are generally safe).
   // turbo
   git status

2. **Define Variables**
   Set the branch name and folder name for the new worktree.
   ```zsh
   # Replace with your desired branch name (e.g., feature/advanced-analytics)
   export NEW_BRANCH="feature/replace-me"
   
   # We recommend appending the branch name to the repo name for the folder
   # This creates a folder name like "finance-analysis-feature-replace-me"
   export WORKTREE_DIR="../finance-analysis-${NEW_BRANCH//\//-}"
   ```

3. **Create Worktree**
   This command creates the folder and checks out the new branch.
   ```zsh
   git worktree add -b "$NEW_BRANCH" "$WORKTREE_DIR"
   ```

4. **Copy Configuration**
   Copy your local environment secrets to the new workspace.
   ```zsh
   cp .env "$WORKTREE_DIR/.env" 2>/dev/null || echo "No root .env found"
   cp backend/.env "$WORKTREE_DIR/backend/.env" 2>/dev/null || echo "No backend/.env found"
   ```

5. **Initialize New Environment**
   Open the new directory.
   ```zsh
   echo "Worktree created at: $WORKTREE_DIR"
   cd "$WORKTREE_DIR"
   ```

6. **Open in IDE**
   Open a **NEW WINDOW** in Antigravity IDE for this directory.
   *Do not open it in the same window as the current agent, as they should be treated as separate projects.*

7. **Install Dependencies**
   (Optional) You may need to install dependencies in the new environment.
   ```zsh
   # Run these in the NEW window/terminal
   poetry install
   cd frontend && npm install
   ```
