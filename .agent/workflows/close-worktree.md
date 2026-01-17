---
description: Close a git worktree after merging a feature branch (cleanup local folder and git references)
---

Use this workflow after you've finished working on a feature branch in a worktree, created a PR, and merged it. This cleans up the local folder and git worktree references.

1. **Verify Merge Status**
   Ensure the branch has been merged before removing the worktree. Check from the main repository.
   ```zsh
   # Navigate to your main repository first
   cd /Users/tomer/Desktop/finance-analysis
   
   # List merged branches to confirm your branch was merged
   git fetch origin
   git branch --merged main
   ```

2. **List Current Worktrees**
   Check which worktrees exist and identify the one to remove.
   // turbo
   ```zsh
   git worktree list
   ```

3. **Remove the Worktree**
   This removes the worktree folder and cleans up git's internal references.
   ```zsh
   # Replace with the actual worktree path from step 2
   export WORKTREE_PATH="../finance-analysis-feature-your-branch"
   
   git worktree remove "$WORKTREE_PATH"
   ```
   
   > **Note:** If the worktree has uncommitted changes, you'll need to add `--force`:
   > ```zsh
   > git worktree remove --force "$WORKTREE_PATH"
   > ```

4. **Delete the Remote Branch (Optional)**
   If GitHub didn't auto-delete the branch after merge:
   ```zsh
   export BRANCH_NAME="feature/your-branch"
   git push origin --delete "$BRANCH_NAME"
   ```

5. **Delete the Local Branch**
   Clean up the local branch reference from the main repo.
   ```zsh
   export BRANCH_NAME="feature/your-branch"
   git branch -d "$BRANCH_NAME"
   ```
   
   > **Note:** Use `-D` (capital) if git complains the branch isn't fully merged (e.g., squash merge):
   > ```zsh
   > git branch -D "$BRANCH_NAME"
   > ```

6. **Prune Stale Worktree References**
   Clean up any stale worktree metadata (useful if folder was manually deleted).
   // turbo
   ```zsh
   git worktree prune
   ```

7. **Verify Cleanup**
   Confirm the worktree is removed.
   // turbo
   ```zsh
   git worktree list
   git branch -a | grep -v "HEAD" | head -20
   ```
