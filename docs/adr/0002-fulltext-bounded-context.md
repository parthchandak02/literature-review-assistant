# ADR-0002: Full-text bounded context in src/fulltext/

## Status

Accepted

## Context

Full-text tier racing lived in `src/extraction/table_extraction.py` alongside Gemini vision table extraction, causing cross-imports between extraction, search, and screening.

## Decision

- Move tier resolver code to `src/fulltext/retrieval.py`.
- Expose `FullTextResolver`, `fetch_full_text`, and `resolve_landing_page` from `src/fulltext/__init__.py`.
- Keep `table_extraction.py` for vision table extraction with backward-compatible re-exports.

## Consequences

- Full-text bugs localize to `src/fulltext/`.
- Legacy imports continue to work during migration.
