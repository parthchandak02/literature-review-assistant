# Validate Docs

Check that project documentation is accurate and aligned with the current codebase. Produce a specific list of updates needed, then apply them.

## Steps

1. **Discover project docs** -- List markdown files in the project root and any `docs/` directory. Identify which files serve as the primary user-facing README and the technical specification (commonly `README.md` and `spec.md` or similar). Read them in full.

2. **Survey the codebase state** -- Understand what is actually implemented:
   - List all source directories and their subdirectories
   - Read the primary dependency file to understand installed packages and entry points
   - Read any config files that define runtime behavior
   - Run `git log --oneline -20` to understand what has been built or changed recently

3. **Validate the README** -- For each section in the README, verify:
   - **Setup instructions**: Do the install and run commands still work? Are dependencies accurate?
   - **Directory structure**: Does it match what actually exists on disk?
   - **Usage examples**: Do CLI commands, entry points, flags, and scripts still exist?
   - **Configuration references**: Are config file paths and option names still correct?
   - **Missing sections**: Is there implemented functionality that has no documentation at all?

4. **Validate the technical spec** -- For each phase or feature described in the spec:
   - Determine its status: "Implemented", "Partial -- [what is done]", or "Not started"
   - Flag any section referencing a module, class, or file that does not exist in the codebase
   - Flag any implementation that exists in the codebase but is not mentioned in the spec

5. **Produce a diff plan** -- Before making changes, output a structured list:

   **README changes needed:**
   - Section: [name] -- Issue: [what is wrong] -- Fix: [what to write]

   **Spec changes needed:**
   - Phase/Section: [name] -- Issue: [what is wrong] -- Fix: [what to write]

6. **Apply updates** -- Make the changes directly to the doc files. Keep documentation minimal and utilitarian:
   - "How to use" takes priority over architecture explanations
   - No fluff, no redundant sections, no marketing language
   - If a phase is partial, say exactly what is and is not done -- do not round up to "complete"

7. **Verify** -- Re-read both files after editing to confirm the changes are correct in context and nothing was accidentally broken.

## Rules for This Command

- Do NOT create new documentation files -- only update files that already exist
- Do NOT remove spec content unless it has been explicitly cancelled or superseded by the user
- Do NOT add verbose architecture explanations -- keep it focused on what a developer needs to get started and run the project
- If a referenced config key or CLI flag does not exist in the codebase, mark it as stale rather than silently removing it -- ask the user for confirmation before deleting documented features
