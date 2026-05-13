---
name: search-connector
description: Implements database connectors conforming to SearchConnector protocol. Use when adding OpenAlex, PubMed, arXiv, IEEE Xplore connectors or implementing search strategy.
---

# Search Connector Implementation

Lean reference for implementing or modifying search connectors.

## Connector Contract (Required)

1. Implement `SearchConnector` from `src/search/base.py`.
2. Return typed paper/search models used by orchestration.
3. Set correct `source_category` for PRISMA counting.
4. Respect per-database limits from config plus connector/API constraints.
5. Use async I/O only.
6. Persist query/date/database/count metadata for appendices and audits.

## Reference Implementations
- Core databases: `src/search/openalex.py`, `src/search/pubmed.py`, `src/search/arxiv.py`, `src/search/ieee_xplore.py`, `src/search/scopus.py`, `src/search/web_of_science.py`, `src/search/embase.py`
- Shared connector helpers: `src/search/common.py` (`HttpSearchConnectorBase`, `ElsevierConnectorMixin`)
- Auxiliary / other-source discovery: `src/search/semantic_scholar.py`, `src/search/crossref.py`, `src/search/perplexity_search.py`, `src/search/clinicaltrials.py`
- Import and expansion helpers: `src/search/csv_import.py`, `src/search/citation_chasing.py`
- Workflow wiring: `src/orchestration/workflow.py`

## Testing

- Mock API responses.
- Verify field mapping to candidate/search models.
- Verify retry/rate-limit behavior and failure surfaces.
