---
description: Finalize a feature by committing, creating PR, self-reviewing, and iterating until ready
---

Run this workflow after completing and verifying a feature implementation to finalize it for review.

## Prerequisites
- All changes are implemented and tested
- No failing tests or build errors

## Steps

1. **Format Code**
   ```bash
   # Python
   black .
   isort .

   # TypeScript
   npx prettier --write .
   ```

2. **commit changes in small commits**
   divide the changes into small commits and commit them one by one (you may select partial changes from several files to commit together instead of committing each file separately - it helps gathering the changes into logical steps - don't abuse it with too many commits).
   for each commit, use conventional commit format: `<type>(<scope>): <summary>`
   - Types: feat, fix, refactor, docs, test, chore, perf
   - Summary: imperative present tense, capitalize first letter, no period
   - Scope: affected area (e.g., budget, auth, api)
   - Example: `feat(auth): add login page`

   ```bash
   git add <file1> <file2> 
   ```

   or for selective changes:
   
   ```bash
   git add -p <filename1>
   git add -p <filename2>
   ```

   then 

   ```bash
   git commit -m "<type>(<scope>): <summary>"
   ```
   repeat until all changes are committed.

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
   
   c. **If issues found**: repeat steps 1-5 untill all issues are fixed.

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