# Interface Design

Use this reference after a candidate is chosen and the user wants to compare
alternative Interfaces. Design more than one shape before committing to a large
refactor.

## 1. Frame the problem

State:

- Constraints the Interface must satisfy.
- The dependency categories from `DEEPENING.md`.
- What behavior belongs behind the Seam.
- A small illustrative sketch that makes constraints concrete, not a chosen
  solution.

Confirm the framing before investing in designs.

## 2. Produce distinct designs

Create at least three materially different Interface designs. Use separate
readonly consultations or clearly separated design passes when useful. Give each
pass a distinct goal:

1. Minimize Interface surface and maximize Leverage.
2. Optimize the common caller path.
3. Maximize extension flexibility.
4. If needed, isolate a remote or external dependency through Adapters.

For every design, specify:

1. Interface: entry points, inputs, invariants, ordering, errors, and relevant
   performance expectations.
2. A caller usage example.
3. Implementation complexity hidden behind the Seam.
4. Dependency and Adapter strategy.
5. Trade-offs in Depth, Locality, and Leverage.

## 3. Compare and recommend

Present each design clearly, then compare:

- Depth: how much useful behavior sits behind the Interface?
- Locality: where will future changes, bugs, and verification concentrate?
- Seam placement: can behavior change without editing callers?
- Test surface: can tests exercise the important behavior through the Interface?

Recommend the strongest design. A hybrid is valid only when it improves the
Interface rather than combining every feature of every option.
