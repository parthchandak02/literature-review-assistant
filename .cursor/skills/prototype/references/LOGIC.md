# Logic Prototype

A tiny interactive shell that lets you drive a state model or data shape by
hand. Use this when the question is about business logic, state transitions,
or data shape - the kind of thing that looks reasonable on paper but only
feels wrong once pushed through real cases.

Wrong branch if the question is "what should this look like" - use
[UI.md](UI.md) instead.

## When this is the right shape

- "Does this state machine handle the edge case where X then Y?"
- "Does this data model actually let me represent case Z?"
- "I want to feel out what this API/interface should look like before
  writing it for real."
- Anything where the useful move is to trigger actions and watch state
  change.

Logic under test usually lives in `src/` with typed boundaries in
`src/models/`.

## Process

### 1. State the question

Before writing code, write one paragraph: what state model, what question. A
logic prototype answering the wrong question is pure waste.

### 2. Pick the language and runtime

Use whatever the host project already uses. Match its existing tooling and
conventions (`uv` for Python, `pnpm` for frontend TypeScript); do not add a
new package manager or runtime just for this.

### 3. Isolate the logic in a portable module

Put the actual logic behind a small, pure interface that could be lifted into
the real codebase later. The driving shell around it is throwaway; the logic
module is not. Name throwaway files so they are obviously disposable
(`prototype`, `PROTOTYPE`).

If the prototype crosses phase boundaries, keep typed models at boundaries
(`src/models/` contracts remain authoritative). Do not patch `runs/`
artifacts.

Pick whichever shape fits the question, not whichever is easiest to wire up:

- **A pure reducer** - `(state, action) -> state`. Good for discrete events
  and single-value state.
- **A state machine** - explicit states and transitions. Good when "which
  actions are legal right now" is part of the question.
- **A small set of pure functions** over a plain data type. Good when there
  is no implicit current state, just transformations.
- **A class/module with a clear method surface** when the logic genuinely
  owns ongoing internal state.

Keep it pure: no I/O, no console/print calls for control flow, nothing that
only works inside a terminal. The shell imports it and calls into it; nothing
flows the other direction.

### 4. Build the smallest interactive shell that exposes the state

On every action, clear and re-render the whole view so there is one stable
frame, not growing scrollback (for a terminal shell) or a stable panel (for
anything else the project already supports, for example a debug screen).

Each frame shows, in order:

1. **Current state**, printed plainly (one field per line, or formatted as
   structured data).
2. **Available actions**, listed clearly (for example
   `[a] add item  [d] delete item  [t] tick clock  [q] quit`).

Loop: read one action, dispatch to a handler that updates state via the pure
module, re-render the full frame, repeat until quit.

### 5. Make it runnable in one command

Add it to the project's existing task runner if it has one (scripts,
Makefile, `uv run`, `pnpm`). Otherwise state the run command directly in your
response. Prefer one command such as:

```bash
uv run python path/to/PROTOTYPE_shell.py
```

### 6. Hand it over

Give the run command. The interesting moments are when driving it surfaces
"wait, that should not be possible" or "I assumed X would be different" -
those are bugs in the idea, which is the point. Add actions if requested;
prototypes evolve.

### 7. Capture the answer and clean up

When the prototype has answered the question, state the answer in your
response (or the commit message that lands the real change) before deleting
the prototype. Verdict: keep, discard, or iterate. Do not leave the answer
undocumented. Fold winning logic into production code; delete the throwaway
shell.

## Anti-patterns

- Do not add a full test suite - a prototype that needs production-grade tests
  is no longer a prototype (one deterministic check for the verdict is fine).
- Do not wire it to a real database or external system - use an in-memory
  store unless persistence is the exact question.
- Do not generalize beyond the question asked.
- Do not blur the logic and the shell together - if the reducer/state machine
  references I/O or terminal codes, it is no longer portable.
- Do not ship the driving shell into production; only the logic module behind
  it is worth keeping.
- Do not patch `runs/` or invent untyped dicts across phase boundaries.
