# Validate Docs

Check that `README.md` and `spec.md` are accurate and aligned with the current state of the codebase. Produce a specific list of updates needed.

## Steps

1. **Read the docs** -- Read `README.md` and `spec.md` in full from the project root.

2. **Survey the codebase state** -- Check the following to understand what is actually implemented:
   - `src/` directory structure (which modules and submodules exist)
   - `frontend/src/` structure (views, components, hooks)
   - `pyproject.toml` -- installed dependencies, entry points, scripts
   - `config/review.yaml` and `config/settings.yaml` -- active configuration
   - Recent git log (`git log --oneline -20`) to understand what has been built lately

3. **Validate README.md** -- For each section in the README, verify:
   - **Setup instructions**: Do the commands still work? Are dependencies accurate?
   - **Directory structure**: Does it match `src/` and `frontend/` as they exist now?
   - **Usage examples**: Do the CLI commands, entry points, and flags still exist?
   - **Configuration references**: Are the config file paths and keys still correct?
   - **Missing sections**: Is there functionality that exists but is not documented?

4. **Validate spec.md** -- For each phase or feature in the spec:
   - Mark phases as "Implemented", "Partial", or "Not started" based on what exists in `src/`
   - Flag any spec section that references a module, class, or file that does not exist
   - Identify any implementation that exists but is not covered by the spec

5. **Produce a diff plan** -- Output a structured list of required changes:

   **README.md changes needed:**
   - Section: [section name] -- Issue: [what is wrong] -- Fix: [what to write]

   **spec.md changes needed:**
   - Phase/Section: [name] -- Issue: [what is wrong] -- Fix: [what to write]

6. **Apply updates** -- Make the changes directly to `README.md` and `spec.md`. Keep the documentation minimal and focused:
   - "How to use" takes priority over architecture explanations
   - No fluff, no redundant sections
   - Keep the spec phase table accurate so it reflects current build progress

## Rules for This Command

- Do NOT create new `.md` files -- only update `README.md` and `spec.md`
- Do NOT add marketing copy or verbose explanations -- keep docs utilitarian
- Do NOT remove spec content unless it has been explicitly cancelled or superseded
- If a phase is partially implemented, say "Partial -- [what is done]" rather than marking it complete
- After edits, re-read both files to confirm the changes look correct in context
