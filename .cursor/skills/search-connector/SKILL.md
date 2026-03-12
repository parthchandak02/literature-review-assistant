---
name: search-connector
description: Implements database connectors conforming to SearchConnector protocol. Use when adding OpenAlex, PubMed, arXiv, IEEE Xplore connectors or implementing search strategy.
---

# Search Connector Implementation

Guide for implementing database connectors that conform to the SearchConnector protocol.

## Instructions

Every connector must:
1. Implement the connector interface from `src/search/base.py`
2. Return results containing `List[CandidatePaper]` (or equivalent paper model)
3. Set `source_category` (DATABASE or OTHER_SOURCE) for PRISMA diagram
4. Respect config-driven per-database limits from search settings, while enforcing connector/API-specific constraints internally when needed
5. Use async HTTP (aiohttp), never synchronous requests
6. Log search query, date, database name, and result count for PRISMA-S appendix

## Protocol Interface
```python
class SearchConnector(Protocol):
    name: str
    source_category: SourceCategory
    async def search(self, query: str, max_results: int = 100,
                     date_start: int = None, date_end: int = None) -> SearchResult:
        ...
```

## Reference Implementations
- `src/search/openalex.py`, `pubmed.py`, `arxiv.py`, `ieee_xplore.py`, `scopus.py`, `web_of_science.py`
- `src/search/semantic_scholar.py`, `crossref.py`, `perplexity_search.py` (auxiliary)
- `src/orchestration/workflow.py` -- connector construction/factory-style wiring in single-path run

## Testing
- Mock API responses for unit tests
- Verify CandidatePaper field mapping
- Test rate limiter behavior
