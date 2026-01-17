---
description: Finalize a feature by committing, creating PR, self-reviewing, and iterating until ready
---

Run this workflow after completing and verifying a feature implementation to finalize it for review.

## Prerequisites
- All changes are implemented and tested
- No failing tests or build errors

## Steps

1. **Stage and Review Changes**
   ```bash
   git status
   git diff --stat
   ```

2. **Commit Changes**
   Use conventional commit format: `<type>(<scope>): <summary>`
   ```bash
   git add -A
   git commit -m "<type>(<scope>): <summary>"
   ```
   - Types: feat, fix, refactor, docs, test, chore, perf
   - Summary: imperative present tense, capitalize first letter, no period

3. **Push Branch**
   ```bash
   git push -u origin HEAD
   ```

4. **Create Draft PR**
   // turbo
   ```bash
   gh pr create --draft --title "<type>(<scope>): <summary>" --body "## Summary
   <Brief description of changes>

   ## Changes
   - <Change 1>
   - <Change 2>

   ## Testing
   <How changes were verified>

   ## Checklist
   - [x] Implementation complete
   - [x] Tests passing
   - [ ] Ready for review"
   ```

5. **Self-Review (Code Review Phase)**
   Review your own changes as if you were a reviewer:
   
   a. **Get the diff**:
      ```bash
      gh pr diff
      ```
   
   b. **Review Checklist**:
      - [ ] Logic correctness and edge cases handled
      - [ ] No security vulnerabilities (input validation, no hardcoded secrets)
      - [ ] Performance considerations (N+1 queries, unnecessary loops)
      - [ ] Error handling present
      - [ ] Code is readable and maintainable
      - [ ] Tests cover key scenarios
   
   c. **If issues found**: Fix them, commit, and push:
      ```bash
      git add -A
      git commit -m "fix(<scope>): address review feedback"
      git push
      ```
      Then re-review. Repeat until satisfied.

6. **Mark PR Ready**
   // turbo
   ```bash
   gh pr ready
   ```

7. **Notify User**
   Report the PR URL and summary:
   ```bash
   gh pr view --web
   ```
   Use `notify_user` tool to inform: "PR #<number> is ready for your review: <URL>"
