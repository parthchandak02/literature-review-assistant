# ADR-0003: Opaque data surfaces vs glass chrome

## Status

Accepted

## Context

The research-ops UI uses glass blur on chrome and data panes. Long scrolling tables and log streams become hard to read when translucency stacks.

## Decision

- Keep glass styling on toolbar, tabs, and sidebar chrome.
- Use `.data-surface` (opaque `surface-1`, no blur) for tables, log streams, and database explorer panes.

## Consequences

- Improved scanability for dense data views without changing the overall dark cockpit aesthetic.
