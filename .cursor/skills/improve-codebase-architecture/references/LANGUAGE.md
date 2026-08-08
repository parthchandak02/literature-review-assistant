# Architecture Language

Use these terms consistently in architecture findings.

## Terms

**Module**

Anything with an Interface and an Implementation, from a function or class to a
package or feature slice.

**Interface**

Everything a caller must know to use a Module correctly: type signatures,
invariants, ordering, error modes, required configuration, and relevant
performance characteristics. It is wider than a language-level interface type.

**Implementation**

The code inside a Module. Use Adapter when discussing the role a concrete
implementation plays at a Seam.

**Seam**

The location where behavior can be altered without editing callers. Deciding
where a Seam lives is distinct from deciding what behavior the Module hides.

**Adapter**

A concrete implementation that satisfies an Interface at a Seam.

**Depth**

Leverage at the Interface. A deep Module places substantial behavior behind a
small Interface. A shallow Module exposes nearly as much complexity as it
hides.

**Leverage**

The caller benefit of Depth: one implementation serves many callers and tests.

**Locality**

The maintainer benefit of Depth: changes, bugs, knowledge, and verification
concentrate in one place rather than spreading among callers.

## Principles

- Depth is a property of the Interface, not line count.
- The deletion test distinguishes a useful Module from a pass-through. If
  deletion removes complexity, delete it. If it distributes complexity to
  callers, it earns its keep.
- The Interface is the test surface. Tests and callers should cross the same
  Seam.
- One Adapter is a hypothetical Seam. Two Adapters make it real.
- Internal Seams may help the Implementation without expanding the public
  Interface.
