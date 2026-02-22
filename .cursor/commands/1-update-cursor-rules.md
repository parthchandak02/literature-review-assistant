# Update Cursor Rules

Audit all existing `.cursor/rules/` files against the current codebase and update any that are stale, incomplete, or missing coverage.

## Steps

1. **Discover existing rules** -- List all files in `.cursor/rules/` recursively. Read each one and note a one-line summary of what it covers. Do not assume a fixed set -- discover what is actually there.

2. **Survey the actual codebase** -- Explore the current project structure to understand what is implemented:
   - List all top-level directories and identify key source directories (e.g. `src/`, `frontend/`, `config/`, `tests/`)
   - Within each source directory, list subdirectories and public-facing modules
   - Read the primary dependency file (e.g. `pyproject.toml`, `package.json`) to identify active libraries and tools
   - Read any root-level config files to understand the build and runtime setup

3. **Identify gaps and staleness** -- For each existing rule, check:
   - Are file paths, module names, and class names still accurate for the current codebase?
   - Are there new modules, patterns, or libraries that the rule does not mention?
   - Are there references to files, classes, or tools that no longer exist?
   - Is there a new recurring pattern that has no rule coverage at all?

4. **Update stale rules** -- Edit rule files that need changes:
   - Update paths, class names, and examples to match current code
   - Add new content only for patterns that genuinely recur across the codebase
   - Do NOT add rules for one-off decisions or things obvious from reading the code
   - Preserve the existing frontmatter format of `.mdc` files (name, description, globs, alwaysApply fields)

5. **Add missing rules** -- If a significant recurring pattern has no rule coverage, create a new `.mdc` file. Follow the project's naming conventions by examining existing files in each subdirectory:
   - `core/` -- always-on project-wide constraints
   - `python/`, `tool/`, `testing/`, `domain/` -- language, library, test, and domain-specific rules
   - Match the suffix pattern already used in that subdirectory (e.g. `-always.mdc`, `-auto.mdc`, `-agent.mdc`)

6. **Verify skill references** -- If any rule references a `.cursor/skills/` file, confirm that skill file actually exists. Remove or update broken references.

7. **Report changes** -- Produce a summary table of every rule file that was touched:

   | Rule File | Action | What Changed |
   |-----------|--------|--------------|
   | (path relative to `.cursor/rules/`) | Updated / Created / No change | Brief description |

## Rules for This Command

- Only update a rule when the codebase has genuinely diverged from it -- do NOT rewrite rules for style or preference
- Keep rule files concise; do not pad them with redundant examples
- After all changes, re-read the always-on rules in `core/` to confirm they still accurately describe the project
- If uncertain whether something warrants a new rule, default to NOT creating one -- rules should encode recurring hard-won knowledge, not obvious conventions
