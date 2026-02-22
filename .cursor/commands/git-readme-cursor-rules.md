# git-readme-cursor-rules

Review all uncommitted changes, check for secrets, update cursor rules and README to reflect codebase state, fix any bugs found, and create a clean git commit with all safe files staged.

Steps this command performs:
1. Run git status + git diff to enumerate all changed and untracked files
2. Check for secrets (API keys, tokens, .env content) in modified files
3. Update .cursor/rules/core/ to reflect the current codebase
4. Patch README.md for any stale facts (database counts, directory layout, etc.)
5. Fix any obvious bugs surfaced during review
6. Stage all safe files and commit with a descriptive message
