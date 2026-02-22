# Update Cursor Rules

Audit all existing `.cursor/rules/` files against the current codebase and update any that are stale, incomplete, or missing coverage.

## Steps

1. **Read all existing rules** -- Read every file in `.cursor/rules/` (currently 11 files across `core/`, `domain/`, `python/`, `testing/`, `tool/` subdirectories). List them all with a one-line summary of what each covers.

2. **Survey the actual codebase** -- Inspect the current directory structure and key files:
   - `src/` -- all subdirectories and their public-facing modules
   - `frontend/src/` -- components, views, hooks, lib
   - `config/` -- `review.yaml`, `settings.yaml`
   - `pyproject.toml` -- dependencies, tools configured (ruff, pytest, etc.)
   - Root-level config files (`ecosystem.config.js`, `vite.config.ts`, etc.)

3. **Identify gaps and staleness** -- For each existing rule, check:
   - Are the file paths, module names, and class names still accurate?
   - Are there new modules or patterns in `src/` that the rule does not mention?
   - Are there outdated references to files or classes that no longer exist?
   - Is there a new phase, tool, or architectural pattern that has no rule coverage?

4. **Update stale rules** -- Edit each rule file that needs changes. Be precise:
   - Update file paths, class names, and examples to match current code
   - Add new subsections only for patterns that genuinely recur across the codebase
   - Do NOT add rules for one-off decisions or things already obvious from the code

5. **Add missing rules** -- If a significant recurring pattern has no rule coverage, create a new `.mdc` file in the appropriate subdirectory. Follow the naming convention:
   - `core/` -- always-on project-wide constraints (suffix: `-always.mdc`)
   - `python/` -- Python code style patterns (suffix: `-auto.mdc`)
   - `tool/` -- library/framework-specific patterns (suffix: `-agent.mdc`)
   - `testing/` -- test patterns (suffix: `-auto.mdc`)
   - `domain/` -- domain methodology rules (suffix: `-agent.mdc`)

6. **Report changes** -- Produce a summary table:

   | File | Status | What Changed |
   |------|--------|--------------|
   | `core/project-overview-always.mdc` | Updated / No change / Created | Brief description |

## Rules for This Command

- Only update a rule when the codebase genuinely has diverged from it -- do NOT rewrite rules for style preferences
- Keep rule files concise; do not pad them with redundant examples
- Preserve the existing frontmatter format (name, description, globs, alwaysApply fields) for `.mdc` files
- If a rule references a skill (e.g. `.cursor/skills/`), verify the skill file still exists before referencing it
- After all changes, run a quick sanity check: read the three `core/` always-on rules to confirm they still accurately describe the project
