---
name: frontend-design-taste
description: Enforces preserve-brand design tokens and anti-slop UI rules for the literature-review React dashboard. Use when editing frontend/src styling, theming, glass components, semantic status colors, or auditing token consistency.
disable-model-invocation: true
---

# Frontend Design Taste (Preserve Brand)

Use this skill for the app dashboard UI, not marketing pages.

Reference philosophy: [taste-skill](https://github.com/Leonxlnx/taste-skill)

## Scope and Non-goals

- Owns: token discipline, semantic styling, theme parity, tasteful dashboard UI.
- Does not own: landing-page hero systems, GSAP-heavy choreography, marketing block generation.
- Preserve existing brand language: violet accent, glass surfaces, Inter.

## Fixed Design Read

Treat this frontend as:

- Research-ops dashboard for technical users.
- Preserve-brand redesign mode (evolve, do not restyle from scratch).
- Dial preset: `DESIGN_VARIANCE=4`, `MOTION_INTENSITY=3`, `VISUAL_DENSITY=8`.

## Token Contract

Single color source of truth:

- `frontend/src/styles/tokens.css` (`@theme` defaults)
- `frontend/src/styles/theme-overrides.css` (`html[data-theme]` overrides)

Rules:

1. Do not introduce raw hex/rgb/hsl color values in `.tsx`/`.ts`.
2. Do not introduce new `text-zinc-*`, `bg-zinc-*`, `border-zinc-*` classes in `.tsx`.
3. Prefer semantic classes and component variants:
   - surfaces: `bg-background`, `bg-card`, `bg-surface-*`, `glass-panel*`
   - text: `text-foreground`, `text-muted`, `text-text-dim`
   - borders: `border-border` or semantic intent borders
   - status/actions: `Badge` variants, `STATUS_*` maps, `Button` variants
4. Keep light and dark mode behavior in parity. No light-only or dark-only additions unless explicitly requested.

## Component Usage Priority

When adding/updating UI, prefer this order:

1. Existing `ui/*` primitives (`button`, `badge`, `section`, `table`, `dialog`)
2. Existing glass utility classes in `frontend/src/styles/components.css`
3. New semantic utility classes/tokens
4. New one-off classes only when there is no reusable alternative

If a one-off style appears in 2+ places, promote it into a primitive or shared utility class.

## Chart and State Colors

- Keep phase/status colors semantic and theme-aware.
- Chart colors should map through theme-backed variables or canonical constants in one place.
- Do not duplicate status color mappings across views; use `frontend/src/lib/constants.ts`.

## Workflow

### 1. Scan

Inventory before editing:

- The touched screen and comparable peer screens.
- Shared primitives already used in the area (`frontend/src/components/ui/`).
- Existing tokens in `tokens.css` / `theme-overrides.css` / `components.css`.
- Whether the need is screen-level, shared-component-level, or theme-level.
- User-visible states: loading, empty, error, disabled, hover, focus, active, success, and responsive layouts.

### 2. Diagnose

Use [references/audit-checklist.md](references/audit-checklist.md). Identify the
highest-risk regressions first, especially action gating, status meaning,
keyboard behavior, dense scanning, and user-facing terminology.

State the visual and behavioral constraints before changing code.

### 3. Make the smallest fix

- Extend an existing primitive or token before adding a one-off style.
- Prefer a small local correction to broad restyling.
- Keep labels, data meaning, control semantics, and request behavior unchanged.
- Use subtle, short motion only when it clarifies state or continuity (respect dial preset and reduced-motion).
- Remove dead styles or duplicated ad-hoc values when safely in the edited area.

Do not replace frameworks, swap fonts, add decorative animation, or expand
whitespace substantially without explicit product direction.

### 4. Pre-flight Checklist

Before considering frontend style work done:

- [ ] No new raw zinc palette classes in changed TSX files.
- [ ] No new raw color literals in changed TS/TSX files.
- [ ] Both light and dark theme render correctly for touched screens.
- [ ] Motion additions respect reduced-motion preferences.
- [ ] No decorative status dots; dots are only for real semantic state.
- [ ] Reusable primitive/utility was used before creating one-off styling.
- [ ] Focus-visible, keyboard, loading, error, empty, and disabled states still work.
- [ ] UI changes did not alter business behavior, data contracts, or action gating.
- [ ] Dense screens remain fast to scan.

## Output

Report what changed, the user-visible benefit, what behavior was deliberately
preserved, and any follow-up debt that should remain separate.

## File Pointers

- `frontend/src/styles/tokens.css`
- `frontend/src/styles/theme-overrides.css`
- `frontend/src/styles/components.css`
- `frontend/src/components/ui/`
- `frontend/src/lib/constants.ts`
