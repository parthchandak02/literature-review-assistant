# Deepening Modules

Use this reference to deepen a cluster of shallow Modules safely. Read
`LANGUAGE.md` first for Module, Interface, Seam, and Adapter.

## Classify dependencies

The dependency category determines how the Module can be tested across its Seam.

### In-process

Pure computation or in-memory state with no I/O. Merge related shallow Modules
and test behavior directly through the new Interface. No Adapter is needed.

### Local-substitutable

A dependency with a credible local stand-in, such as an in-memory datastore or
test filesystem. Keep the Seam internal and test the deep Module against the
stand-in. Do not expose test-only mechanics in the external Interface.

### Remote but owned

A service or process controlled by the organization across a network or process
boundary. Define a narrow port at the Seam. The deep Module owns the behavior;
production and in-memory implementations are Adapters.

### True external

A third-party dependency outside the project's control. Inject a small port for
the capability actually needed. Tests use a mock or fake Adapter that describes
the external behavior relevant to the Module.

## Seam discipline

- One Adapter is a hypothetical Seam. Two Adapters make it real, commonly
  production plus test.
- Keep internal Seams private. Tests may use them without making them facts that
  every caller must learn.
- Do not introduce a port solely because a framework makes interfaces easy to
  declare. Variation or isolated testing must justify it.

## Testing strategy

- Replace shallow-module tests with behavior tests at the deep Module's
  Interface when that Interface subsumes them.
- Assert observable outcomes, invariants, errors, and ordering rules, not
  internal state or call choreography.
- A test should survive an internal refactor. If it changes whenever the
  Implementation changes, it is testing past the Interface.
- Use the deletion test: if deleting a wrapper makes complexity disappear, delete
  it. If deleting it spreads complexity to callers, it is earning its keep.
