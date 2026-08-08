# ADR Format (this repository)

ADRs live in `docs/adr/` and use sequential numbering: `0001-slug.md`,
`0002-slug.md`, etc. Existing examples already use a short Context / Decision /
Consequences shape.

Create the `docs/adr/` directory only if missing, and only when Doc creation in
the skill allows it (user asked, or user accepted an ADR offer).

## Template (matches repo style)

```md
# ADR-000N: {Short title of the decision}

## Status

Accepted

## Context

{1-3 sentences: what forced the decision.}

## Decision

- {Concrete choice and ownership.}

## Consequences

- {Non-obvious downstream effects.}
```

Keep ADRs short. The value is recording *that* a decision was made and *why*.

## Optional extras

Only add these when they help a future reader:

- Status variants: `proposed | accepted | deprecated | superseded by ADR-NNNN`
- Considered options (when rejected alternatives matter)
- Extra consequence detail for parity or resume surfaces

## Numbering

Scan `docs/adr/` for the highest existing number and increment by one.

## When to offer an ADR

All three must be true:

1. **Hard to reverse** - changing later is costly
2. **Surprising without context** - a future reader would wonder why
3. **Real trade-off** - genuine alternatives existed

### What qualifies in this repo

- Runtime plane or persistence ownership changes
- Resume / checkpoint / user-resumable phase boundaries
- API vs frontend contract splits that lock clients
- Synthesis or cohort truth rules that other phases must honor
- Deliberate deviations from the obvious path (for example manual SQL over ORM)
- Rejected alternatives that would otherwise resurface in grilling

If the decision is easy to reverse, obvious, or not a real trade-off, skip the ADR.
Do not invent a `CONTEXT.md` glossary as a substitute.
