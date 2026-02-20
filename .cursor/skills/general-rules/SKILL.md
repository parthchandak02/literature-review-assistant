---
name: general-rules
description: General project rules and conventions for git operations, documentation, scripting, and Python environment management. Apply when working on git commits, documentation, scripts, or Python dependencies.
---

# General Project Rules

This skill consolidates essential project conventions and best practices. Apply these rules consistently across all development tasks.

## Git Security and Commit Practices

Before any git push or commit, check that no secrets, API keys, or env vars are exposed in staged files.

- Use tools like `git diff --staged` to review changes
- Scan for patterns like `API_KEY=`, `SECRET=`, `PASSWORD=`
- Generate conventional commit messages based on all file changes (e.g., `feat:`, `fix:`, `refactor:`). Prefer `feat:` for new features, `fix:` for bug fixes.
- If major deletions or risky changes detected, pause and confirm with user before committing
- If everything looks safe (no secrets, no major deletions), proceed with commit and push
- Always use `.gitignore` to exclude `.env`, `runs/**`, `*.db` (runtime and registry dbs), and sensitive config files

## Documentation Standards

Keep documentation minimal and focused on getting started. Prioritize "How to use" in README.md.

- Only create additional `.md` files when explicitly requested
- Keep documentation short, utilitarian, no fluff
- When you have too many tasks, you can make a `TASKS.md` to keep track of them
- Once done, check them off and maintain a master running list of tasks in `TASKS.md`

## Script Organization and Management

Use the `scripts` folder to automate important tasks. Identify and organize scripts into two types:

1. **Recurring Usage Scripts**: Automate frequent workflows (e.g., starting backend/frontend, deploying to Cloudflare, resets, batch jobs). Use Bash where possible for speed, but Python where needed.

2. **Temporary Testing Scripts**: Automate one-off or debugging steps (e.g., feature checks, API tests, quick data dumps). Clean up after use if no longer needed.

**Script Guidelines:**
- Name scripts clearly by purpose and type, e.g., `run-backend.sh`, `test-gtt-feature.py`, `debug-price-check.sh`
- Agents should intelligently pick the type and place new scripts in the correct location
- Prefer Bash for fast tasks; use Python for complex/testing automation
- Always document what each script does at the top (brief comment)
- Focus on keeping scripts modular, simple, and easy to run

## Python Environment Management

Use `uv` and `.venv` to run Python scripts and install dependencies.

- Always use `uv` for package installation instead of pip (unless specified otherwise)
- Use `.venv` virtual environment for Python projects
- Activate the virtual environment before running Python scripts

## Code Quality and Linting

If the project uses ruff (check `pyproject.toml` for `[tool.ruff]`), use it to maintain code quality:

- **Before making code changes**: Run `ruff check .` to identify existing issues
- **After making code changes**: Always run `ruff check --fix .` to automatically fix fixable issues
- **For comprehensive fixes**: Use `ruff check --fix --unsafe-fixes .` to fix all auto-fixable issues including unsafe ones
- **Focus on critical errors**: Prioritize fixing E (errors) and F (code quality) rule violations first
- **Periodic checks**: Run `ruff check src/` before committing changes to ensure code quality
- **Configuration**: Ruff configuration is in `pyproject.toml` [tool.ruff] - respect existing settings

**Common ruff commands:**
- `ruff check .` - Check all files for issues
- `ruff check --fix .` - Auto-fix safe issues
- `ruff check --fix --unsafe-fixes .` - Auto-fix all fixable issues
- `ruff check src/ --select E,F` - Check only errors and code quality issues in src/
- `ruff check <file>` - Check specific file

**When to run ruff:**
- After fixing syntax errors or indentation issues
- Before committing code changes
- When encountering import or code quality errors
- Periodically during development to catch issues early

If ruff is not configured in the project, skip ruff-related steps.
