# Frontend Design Taste Audit Checklist

Use this checklist after scanning peers, tokens, and shared primitives for the
literature-review dashboard (`frontend-design-taste`).

## Structure and primitives

- Does the screen follow established page shell, sections, tables, dialogs, or action patterns?
- Is a shared `ui/*` primitive available before a new local component is added?
- Is the change correctly scoped to a screen, shared primitive, or theme token?
- Does the layout preserve the product's intended information density (`VISUAL_DENSITY=8`)?

## Tokens and visual language

- Use project tokens in `frontend/src/styles/tokens.css` and `theme-overrides.css`.
- Prefer semantic surfaces (`bg-background`, `bg-card`, `glass-panel*`) over raw palette classes.
- Avoid new hardcoded colors, `text-zinc-*` / `bg-zinc-*` / `border-zinc-*`, and duplicated spacing literals.
- Keep typography hierarchy coherent with peer screens (Inter, preserve brand).
- Avoid a new visual style that competes with violet accent + glass language.

## Controls and state

- Preserve action names, request behavior, validation, permissions, and gating.
- Keep status colors, badges, and icons semantically consistent (`Badge`, `STATUS_*`, `constants.ts`).
- Make hover, focus-visible, active, disabled, loading, success, error, and empty states clear.
- Use native or shared accessible controls rather than hand-rolled substitutes.
- No decorative status dots; dots are only for real semantic state.

## Accessibility and responsiveness

- Keyboard navigation reaches and visibly identifies every interactive control.
- Labels, descriptions, and error messages remain available to assistive technology.
- Touch targets, contrast, and text scaling meet project conventions.
- Narrow layouts retain hierarchy and avoid horizontal overflow.
- Light and dark theme both remain correct for touched screens.

## CSS and implementation hygiene

- Prefer scoped styles and avoid broad selectors with cross-screen effects.
- Reuse tokens / `components.css` utilities instead of creating theme-like local constants.
- Remove dead styles only when their ownership is clear.
- Do not introduce no-op wrappers, props, or abstractions.

## Anti-slop guardrails

- No decorative hero treatment, novelty layout, or excessive whitespace unless product direction calls for it.
- No heavy animation, scroll effects, or motion that slows work (`MOTION_INTENSITY=3`).
- No wholesale framework, font, or component-library replacement as a polish patch.
- No visual change that obscures workflows, data density, or familiar labels.
