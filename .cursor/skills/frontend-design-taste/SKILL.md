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

## Pre-flight Checklist

Before considering frontend style work done:

- [ ] No new raw zinc palette classes in changed TSX files.
- [ ] No new raw color literals in changed TS/TSX files.
- [ ] Both light and dark theme render correctly for touched screens.
- [ ] Motion additions respect reduced-motion preferences.
- [ ] No decorative status dots; dots are only for real semantic state.
- [ ] Reusable primitive/utility was used before creating one-off styling.

## File Pointers

- `frontend/src/styles/tokens.css`
- `frontend/src/styles/theme-overrides.css`
- `frontend/src/styles/components.css`
- `frontend/src/components/ui/`
- `frontend/src/lib/constants.ts`
