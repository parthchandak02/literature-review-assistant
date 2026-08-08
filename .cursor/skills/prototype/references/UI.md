# UI Prototype

Generate several radically different UI variations on a single surface,
switchable from a lightweight control. Compare them in place, then throw away
all but the winner.

Wrong branch if the question is about logic or state rather than appearance -
use [LOGIC.md](LOGIC.md) instead.

## When this is the right shape

- "What should this page/screen look like?"
- "I want to see a few layout options before committing."
- "Try a different structure for this view."

Host surfaces live under `frontend/src/`. Prefer existing routes/components
over new throwaway pages.

## Two sub-shapes - prefer adjusting an existing surface

A UI prototype is easiest to judge sitting next to the rest of the app: real
navigation, real data, real density. A prototype in a vacuum looks fine in
isolation regardless of variant. Default to adjusting an existing page or
screen; only build a new throwaway surface if nothing existing can host it.

### Sub-shape A - adjustment to an existing surface (preferred)

The page/screen already exists. Variants render on the same surface, gated by
a query parameter, feature flag, or local toggle. Existing data fetching,
params, and auth stay untouched; only the rendered output swaps.

If the thing being prototyped does not yet have a home but naturally belongs
inside an existing surface (a new section, a new card, a new step in an
existing flow), this is still sub-shape A: mount the variants inside the host
surface.

### Sub-shape B - a new surface (last resort)

Only when there is genuinely no existing surface to embed into. Create a
throwaway route or screen following the project's existing routing or
navigation convention. Name it so it is obviously a prototype
(`prototype`, `PROTOTYPE`). Use the same variant-switching pattern.

Before choosing sub-shape B, double-check: is there really no host? An empty
surface hides design problems a populated one would expose.

## Process

### 1. State the question and pick N

Default to 3 variants. More than 5 stops being radically different and
becomes noise.

Write one line stating the plan, for example: "Three variants of the settings
screen, switchable via a variant toggle, on the existing settings page."

### 2. Generate radically different variants

Each variant should respect:

- The surface's purpose and the data available to it.
- The project's existing component library and styling system (React 19,
  Vite, Tailwind under `frontend/`).
- A clear, distinct name (`VariantA`, `VariantB`, `VariantC`).

Variants must differ structurally: layout, information hierarchy, primary
affordance - not just colour or copy. If two drafts look too similar, redo one
with an explicit constraint (for example "do not use a card grid").

### 3. Wire them together

Add a single switch at the point variants are rendered, keyed off a query
param, flag, or local toggle:

```
variant = read_variant() or "A"
if variant == "A": render VariantA(data)
if variant == "B": render VariantB(data)
if variant == "C": render VariantC(data)
render VariantSwitcher(current=variant)
```

Keep all existing data fetching above the switch; only the rendered subtree
changes per variant.

### 4. Build the switcher control

A small, visually distinct control (for example a fixed-position bar) with:

- Previous / next controls that cycle through variants, wrapping around.
- A label showing the current variant.

Behavior:

- Selecting a variant updates the toggle mechanism (URL param, local storage,
  in-memory state) so it is shareable or at least stable across reloads where
  the project supports that.
- Visually distinct from the surface under evaluation (high-contrast, obvious
  chrome) so it does not read as part of the design being judged.
- Gated out of production builds (environment check, debug flag, or
  equivalent) so a stray merge cannot ship it to users.

### 5. Hand it over

Point at the surface and the variant toggle. One-command run should use the
project's existing tooling (`pnpm --dir frontend dev` or equivalent). The most
useful feedback is usually "I want the header from B with the sidebar from C"
- that is the real design taking shape.

### 6. Capture the answer and clean up

Once a variant wins:

- **Sub-shape A** - delete the losing variants and the switcher; fold the
  winner into the existing surface, rewritten to production standard.
- **Sub-shape B** - promote the winning variant to a real route/screen;
  delete the throwaway surface and the switcher.

State which variant won and why in your response or the commit that lands it.
Verdict: keep, discard, or iterate.

## Anti-patterns

- Variants that differ only in colour or copy - that is a tweak, not a
  prototype.
- Sharing too much code between variants - a shared atom (for example a
  button) is fine; a shared layout scaffold defeats the point.
- Wiring variants to real mutations - keep prototypes read-only; point any
  mutation at a stub.
- Promoting prototype code directly to production without rewriting it to the
  project's real standards.
- Patching `runs/` artifacts or bypassing typed contracts in `src/models/`.
